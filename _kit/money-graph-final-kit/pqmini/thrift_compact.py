"""Minimal Thrift Compact Protocol reader — just enough to parse Parquet footers."""

CT_STOP = 0
CT_BOOLEAN_TRUE = 1
CT_BOOLEAN_FALSE = 2
CT_BYTE = 3
CT_I16 = 4
CT_I32 = 5
CT_I64 = 6
CT_DOUBLE = 7
CT_BINARY = 8
CT_LIST = 9
CT_SET = 10
CT_MAP = 11
CT_STRUCT = 12


class Reader:
    def __init__(self, data, pos=0):
        self.data = data
        self.pos = pos

    def read_byte(self):
        b = self.data[self.pos]
        self.pos += 1
        return b

    def read_bytes(self, n):
        b = self.data[self.pos:self.pos + n]
        self.pos += n
        return b

    def read_varint(self):
        result = 0
        shift = 0
        while True:
            b = self.read_byte()
            result |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        return result

    def read_zigzag(self):
        n = self.read_varint()
        return (n >> 1) ^ -(n & 1)

    def read_double(self):
        import struct
        b = self.read_bytes(8)
        return struct.unpack('<d', b)[0]

    def read_binary(self):
        n = self.read_varint()
        return self.read_bytes(n)

    def read_string(self):
        return self.read_binary().decode('utf-8')

    def read_struct(self):
        """Returns dict: field_id -> value"""
        fields = {}
        last_fid = 0
        while True:
            b = self.read_byte()
            if b == CT_STOP:
                break
            delta = (b >> 4) & 0x0F
            ctype = b & 0x0F
            if delta == 0:
                fid = self.read_zigzag_i16()
            else:
                fid = last_fid + delta
            last_fid = fid
            val = self.read_value(ctype)
            fields[fid] = val
        return fields

    def read_zigzag_i16(self):
        return self.read_zigzag()

    def read_value(self, ctype):
        if ctype == CT_BOOLEAN_TRUE:
            return True
        elif ctype == CT_BOOLEAN_FALSE:
            return False
        elif ctype == CT_BYTE:
            b = self.read_byte()
            return b - 256 if b > 127 else b
        elif ctype in (CT_I16, CT_I32, CT_I64):
            return self.read_zigzag()
        elif ctype == CT_DOUBLE:
            return self.read_double()
        elif ctype == CT_BINARY:
            return self.read_binary()
        elif ctype == CT_LIST:
            return self.read_list()
        elif ctype == CT_SET:
            return self.read_list()
        elif ctype == CT_MAP:
            return self.read_map()
        elif ctype == CT_STRUCT:
            return self.read_struct()
        else:
            raise ValueError(f"Unknown compact type {ctype}")

    def read_list(self):
        b = self.read_byte()
        size = (b >> 4) & 0x0F
        etype = b & 0x0F
        if size == 15:
            size = self.read_varint()
        etype_full = self._elem_type(etype)
        if etype == 1:  # boolean list: each element is a plain byte 1/2
            return [self.read_byte() == 1 for _ in range(size)]
        return [self.read_value(etype_full) for _ in range(size)]

    def read_map(self):
        size = self.read_varint()
        if size == 0:
            return []
        b = self.read_byte()
        ktype = self._elem_type((b >> 4) & 0x0F)
        vtype = self._elem_type(b & 0x0F)
        out = []
        for _ in range(size):
            k = self.read_value(ktype)
            v = self.read_value(vtype)
            out.append((k, v))
        return out

    def _elem_type(self, compact_id):
        # compact list/set/map element type ids differ slightly for bool
        mapping = {
            1: CT_BOOLEAN_TRUE,  # bool in list uses id 1, value packed separately - treat as bool
            2: CT_BYTE,
            3: CT_I16,
            4: CT_I32,
            5: CT_I64,
            6: CT_DOUBLE,
            8: CT_BINARY,
            9: CT_LIST,
            10: CT_SET,
            11: CT_MAP,
            12: CT_STRUCT,
        }
        return mapping.get(compact_id, compact_id)
