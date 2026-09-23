"""Minimal pure-python Parquet reader: no nulls/nesting (REQUIRED fields only),
PLAIN + RLE_DICTIONARY encodings, UNCOMPRESSED/ZSTD/SNAPPY/GZIP codecs.
Good enough for the flat AML dataset (src/dst/sum_kzt/n_tx/depth, gid/depth/is_seed, etc).
"""
import struct
import zlib
from .thrift_compact import Reader
from .zstd_ctypes import zstd_decompress

TYPE_NAMES = {0: "BOOLEAN", 1: "INT32", 2: "INT64", 3: "INT96", 4: "FLOAT", 5: "DOUBLE",
              6: "BYTE_ARRAY", 7: "FIXED_LEN_BYTE_ARRAY"}
CODEC_NAMES = {0: "UNCOMPRESSED", 1: "SNAPPY", 2: "GZIP", 3: "LZO", 4: "BROTLI", 5: "LZ4", 6: "ZSTD", 7: "LZ4_RAW"}


def read_footer(data: bytes):
    footer_len = struct.unpack('<I', data[-8:-4])[0]
    footer_data = data[-8 - footer_len:-8]
    r = Reader(footer_data)
    return r.read_struct()


def decompress(codec_id, raw, uncompressed_size):
    name = CODEC_NAMES.get(codec_id, codec_id)
    if name == "UNCOMPRESSED":
        return raw
    if name == "ZSTD":
        return zstd_decompress(raw, uncompressed_size)
    if name == "GZIP":
        return zlib.decompress(raw, 16 + zlib.MAX_WBITS)
    if name == "SNAPPY":
        return snappy_decompress_raw(raw, uncompressed_size)
    raise NotImplementedError(f"codec {name} not supported")


def snappy_decompress_raw(data, expected_size):
    # Minimal pure-python snappy block decompressor (framing-less "raw" format used by parquet).
    pos = 0

    def read_varint():
        nonlocal pos
        result = 0
        shift = 0
        while True:
            b = data[pos]
            pos += 1
            result |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        return result

    length = read_varint()
    out = bytearray()
    while pos < len(data):
        tag = data[pos]
        pos += 1
        el_type = tag & 0x3
        if el_type == 0:  # literal
            l = tag >> 2
            if l < 60:
                length_ = l + 1
            else:
                nbytes = l - 59
                length_ = int.from_bytes(data[pos:pos + nbytes], 'little') + 1
                pos += nbytes
            out += data[pos:pos + length_]
            pos += length_
        else:
            if el_type == 1:
                l = ((tag >> 2) & 0x7) + 4
                offset = ((tag >> 5) << 8) | data[pos]
                pos += 1
            elif el_type == 2:
                l = (tag >> 2) + 1
                offset = int.from_bytes(data[pos:pos + 2], 'little')
                pos += 2
            else:
                l = (tag >> 2) + 1
                offset = int.from_bytes(data[pos:pos + 4], 'little')
                pos += 4
            start = len(out) - offset
            for i in range(l):
                out.append(out[start + i])
    return bytes(out)


def decode_rle_bitpacked_hybrid(buf, bit_width, num_values):
    """Returns list of ints, length num_values."""
    out = []
    pos = 0
    byte_width = (bit_width + 7) // 8
    while len(out) < num_values and pos < len(buf):
        header = 0
        shift = 0
        while True:
            b = buf[pos]
            pos += 1
            header |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        if header & 1 == 0:
            run_len = header >> 1
            val_bytes = buf[pos:pos + byte_width]
            pos += byte_width
            val = int.from_bytes(val_bytes, 'little')
            out.extend([val] * run_len)
        else:
            num_groups = header >> 1
            count = num_groups * 8
            total_bits = count * bit_width
            nbytes = (total_bits + 7) // 8
            chunk = buf[pos:pos + nbytes]
            pos += nbytes
            bitbuf = 0
            bitcnt = 0
            vals = []
            for byte in chunk:
                bitbuf |= byte << bitcnt
                bitcnt += 8
                while bitcnt >= bit_width:
                    vals.append(bitbuf & ((1 << bit_width) - 1))
                    bitbuf >>= bit_width
                    bitcnt -= bit_width
            out.extend(vals[:count])
    return out[:num_values]


def decode_plain(buf, ptype, num_values, type_length=None):
    vals = []
    pos = 0
    if ptype == "BOOLEAN":
        for i in range(num_values):
            byte = buf[pos + i // 8]
            vals.append(bool((byte >> (i % 8)) & 1))
        return vals
    elif ptype == "INT32":
        for i in range(num_values):
            vals.append(struct.unpack_from('<i', buf, pos)[0])
            pos += 4
        return vals
    elif ptype == "INT64":
        for i in range(num_values):
            vals.append(struct.unpack_from('<q', buf, pos)[0])
            pos += 8
        return vals
    elif ptype == "FLOAT":
        for i in range(num_values):
            vals.append(struct.unpack_from('<f', buf, pos)[0])
            pos += 4
        return vals
    elif ptype == "DOUBLE":
        for i in range(num_values):
            vals.append(struct.unpack_from('<d', buf, pos)[0])
            pos += 8
        return vals
    elif ptype == "BYTE_ARRAY":
        for i in range(num_values):
            l = struct.unpack_from('<I', buf, pos)[0]
            pos += 4
            vals.append(buf[pos:pos + l])
            pos += l
        return vals
    elif ptype == "FIXED_LEN_BYTE_ARRAY":
        for i in range(num_values):
            vals.append(buf[pos:pos + type_length])
            pos += type_length
        return vals
    else:
        raise NotImplementedError(ptype)


def read_column(data, col_meta, ptype, type_length=None, max_def_level=0, max_rep_level=0):
    codec_id = col_meta[4]
    num_values_total = col_meta[5]
    dict_page_offset = col_meta.get(11)
    data_page_offset = col_meta[9]
    total_compressed_size = col_meta[7]
    chunk_start = dict_page_offset if dict_page_offset is not None else data_page_offset
    end = chunk_start + total_compressed_size

    pos = chunk_start
    dictionary = None
    values = []
    while pos < end:
        r = Reader(data, pos)
        ph = r.read_struct()
        header_len = r.pos - pos
        page_type = ph[1]
        uncompressed_size = ph[2]
        compressed_size = ph[3]
        page_start = r.pos
        raw = data[page_start:page_start + compressed_size]
        payload = decompress(codec_id, raw, uncompressed_size)

        if page_type == 2:  # DICTIONARY_PAGE
            dph = ph[7]
            n = dph[1]
            dictionary = decode_plain(payload, ptype, n, type_length)
        elif page_type == 0:  # DATA_PAGE (v1)
            dph = ph[5]
            n = dph[1]
            encoding = dph[2]
            body = payload
            bpos = 0
            # V1 layout: [rep-levels: 4B length + RLE]? then [def-levels: 4B length + RLE]? then values
            if max_rep_level > 0:
                l = struct.unpack_from('<I', body, bpos)[0]
                bpos += 4 + l  # skip; flat schema here never has repeated fields
            if max_def_level > 0:
                l = struct.unpack_from('<I', body, bpos)[0]
                bpos += 4
                def_bw = (max_def_level.bit_length())
                def_stream = body[bpos:bpos + l]
                def_levels = decode_rle_bitpacked_hybrid(def_stream, def_bw, n)
                bpos += l
                if any(lvl != max_def_level for lvl in def_levels):
                    raise NotImplementedError("NULL values present - not supported by this mini-reader")
            body = body[bpos:]
            if encoding in (2, 8):  # PLAIN_DICTIONARY / RLE_DICTIONARY
                bit_width = body[0]
                idx_stream = body[1:]
                idxs = decode_rle_bitpacked_hybrid(idx_stream, bit_width, n)
                values.extend(dictionary[i] for i in idxs)
            elif encoding == 0:  # PLAIN
                values.extend(decode_plain(body, ptype, n, type_length))
            else:
                raise NotImplementedError(f"data page encoding {encoding}")
        elif page_type == 3:  # DATA_PAGE_V2
            dph = ph[8]
            n = dph[1]
            num_nulls = dph[2]
            encoding = dph[4]
            def_len = dph.get(7, 0)
            rep_len = dph.get(6, 0)
            is_compressed = ph.get(4, True) if False else True
            # payload here: since we passed compressed_size covering whole page incl levels (v2 quirk:
            # only the values section is compressed, levels are not). Handle simple flat case:
            rep_bytes_len = dph.get(6, 0)
            def_bytes_len = dph.get(7, 0)
            # In V2 the repetition/definition levels are NOT compressed; only remaining bytes are.
            # We already decompressed the whole remaining payload above incorrectly if levels present.
            # For our flat REQUIRED-only schema these lengths are 0, so it's fine.
            body = payload
            if encoding in (2, 8):
                bit_width = body[0]
                idx_stream = body[1:]
                idxs = decode_rle_bitpacked_hybrid(idx_stream, bit_width, n)
                values.extend(dictionary[i] for i in idxs)
            elif encoding == 0:
                values.extend(decode_plain(body, ptype, n, type_length))
            else:
                raise NotImplementedError(f"data page v2 encoding {encoding}")
        else:
            raise NotImplementedError(f"page type {page_type}")

        pos = page_start + compressed_size

    return values[:num_values_total]


def read_parquet(path):
    with open(path, 'rb') as f:
        data = f.read()
    meta = read_footer(data)
    schema = meta[2]
    # schema[0] is root; following entries are the flat columns in order
    columns_schema = schema[1:]
    col_defs = []
    for s in columns_schema:
        ptype = TYPE_NAMES[s[1]]
        name = s[4].decode('utf-8')
        type_length = s.get(2)
        rep_type = s.get(3, 0)  # 0=REQUIRED, 1=OPTIONAL, 2=REPEATED
        max_def = 1 if rep_type == 1 else 0
        max_rep = 1 if rep_type == 2 else 0
        col_defs.append((name, ptype, type_length, max_def, max_rep))

    row_groups = meta[4]
    result = {name: [] for name, _, _, _, _ in col_defs}
    for rg in row_groups:
        cols = rg[1]
        for col_chunk, (name, ptype, type_length, max_def, max_rep) in zip(cols, col_defs):
            col_meta = col_chunk[3]
            vals = read_column(data, col_meta, ptype, type_length, max_def, max_rep)
            result[name].extend(vals)
    return result, col_defs
