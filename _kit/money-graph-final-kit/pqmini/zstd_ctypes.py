import ctypes
import ctypes.util

_lib = ctypes.CDLL("/usr/lib/x86_64-linux-gnu/libzstd.so.1")
_lib.ZSTD_decompress.restype = ctypes.c_size_t
_lib.ZSTD_decompress.argtypes = [
    ctypes.c_void_p, ctypes.c_size_t,
    ctypes.c_void_p, ctypes.c_size_t,
]
_lib.ZSTD_isError.restype = ctypes.c_uint
_lib.ZSTD_isError.argtypes = [ctypes.c_size_t]
_lib.ZSTD_getFrameContentSize.restype = ctypes.c_ulonglong
_lib.ZSTD_getFrameContentSize.argtypes = [ctypes.c_void_p, ctypes.c_size_t]


def zstd_decompress(src: bytes, dst_size: int) -> bytes:
    src_buf = ctypes.create_string_buffer(src, len(src))
    dst_buf = ctypes.create_string_buffer(dst_size)
    ret = _lib.ZSTD_decompress(dst_buf, dst_size, src_buf, len(src))
    if _lib.ZSTD_isError(ret):
        raise RuntimeError(f"ZSTD decompress error code {ret}")
    if ret != dst_size:
        # still return what we got, truncate/pad expectations upstream
        return dst_buf.raw[:ret]
    return dst_buf.raw[:dst_size]
