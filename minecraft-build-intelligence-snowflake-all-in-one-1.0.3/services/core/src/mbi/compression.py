from __future__ import annotations

import gzip
import io
import zlib
from enum import StrEnum

from .errors import NBTError
from .limits import NBTLimits


class Compression(StrEnum):
    GZIP = "gzip"
    ZLIB = "zlib"
    RAW_NBT = "raw_nbt"


def detect_compression(data: bytes) -> Compression:
    if data.startswith(b"\x1f\x8b"):
        return Compression.GZIP
    if len(data) >= 2:
        cmf, flg = data[0], data[1]
        if (cmf & 0x0F) == 8 and ((cmf << 8) + flg) % 31 == 0:
            return Compression.ZLIB
    return Compression.RAW_NBT


def _bounded_read(stream: io.BufferedIOBase, limit: int) -> bytes:
    out = bytearray()
    while True:
        chunk = stream.read(min(1024 * 1024, limit - len(out) + 1))
        if not chunk:
            break
        out.extend(chunk)
        if len(out) > limit:
            raise NBTError(
                "NBT_DECOMPRESSED_SIZE_LIMIT",
                "Decompressed NBT exceeds the configured byte limit.",
                {"limit": limit},
            )
    return bytes(out)


def decompress_nbt(data: bytes, limits: NBTLimits) -> tuple[Compression, bytes]:
    if len(data) > limits.max_compressed_bytes:
        raise NBTError(
            "NBT_COMPRESSED_SIZE_LIMIT",
            "Compressed input exceeds the configured byte limit.",
            {"actual": len(data), "limit": limits.max_compressed_bytes},
        )
    compression = detect_compression(data)
    try:
        if compression is Compression.GZIP:
            with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as stream:
                return compression, _bounded_read(stream, limits.max_decompressed_bytes)
        if compression is Compression.ZLIB:
            dec = zlib.decompressobj()
            out = bytearray()
            for start in range(0, len(data), 1024 * 1024):
                out.extend(dec.decompress(data[start : start + 1024 * 1024], limits.max_decompressed_bytes - len(out) + 1))
                if len(out) > limits.max_decompressed_bytes:
                    raise NBTError("NBT_DECOMPRESSED_SIZE_LIMIT", "Decompressed NBT is too large")
            out.extend(dec.flush(limits.max_decompressed_bytes - len(out) + 1))
            if len(out) > limits.max_decompressed_bytes:
                raise NBTError("NBT_DECOMPRESSED_SIZE_LIMIT", "Decompressed NBT is too large")
            return compression, bytes(out)
        return compression, data
    except (OSError, EOFError, zlib.error) as exc:
        raise NBTError("NBT_DECOMPRESSION_FAILED", "Could not decompress NBT input.", {"error": str(exc)}) from exc
