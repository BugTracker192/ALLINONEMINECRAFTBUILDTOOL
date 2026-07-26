from __future__ import annotations

import gzip
import zlib

from mbi.compression import Compression, decompress_nbt, detect_compression
from mbi.limits import NBTLimits


def test_compression_detection() -> None:
    raw = b"\x0a\x00\x00\x00"
    assert detect_compression(raw) is Compression.RAW_NBT
    assert detect_compression(gzip.compress(raw)) is Compression.GZIP
    assert detect_compression(zlib.compress(raw)) is Compression.ZLIB
    assert decompress_nbt(gzip.compress(raw), NBTLimits())[1] == raw
