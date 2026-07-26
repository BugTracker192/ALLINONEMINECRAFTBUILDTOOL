from __future__ import annotations

from collections.abc import Iterable

from ..errors import FormatError


def decode_unsigned_varints(data: bytes, *, expected_count: int | None = None, max_bits: int = 32) -> list[int]:
    values: list[int] = []
    result = 0
    shift = 0
    for offset, byte in enumerate(data):
        result |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            values.append(result)
            if expected_count is not None and len(values) > expected_count:
                raise FormatError(
                    "SPONGE_BLOCK_DATA_EXCESS",
                    "Sponge block data decoded more palette indexes than the structure volume.",
                    {"expected": expected_count, "actualAtLeast": len(values)},
                )
            result = 0
            shift = 0
        else:
            shift += 7
            if shift >= max_bits:
                raise FormatError(
                    "SPONGE_VARINT_OVERFLOW",
                    "Sponge block data contains a varint wider than the configured integer width.",
                    {"offset": offset, "maxBits": max_bits},
                )
    if shift != 0:
        raise FormatError("SPONGE_VARINT_UNTERMINATED", "Sponge block data ends inside a varint.")
    if expected_count is not None and len(values) != expected_count:
        raise FormatError(
            "SPONGE_BLOCK_DATA_LENGTH",
            "Sponge block data count does not match structure volume.",
            {"expected": expected_count, "actual": len(values)},
        )
    return values


def encode_unsigned_varints(values: Iterable[int]) -> bytes:
    out = bytearray()
    for value in values:
        if value < 0:
            raise ValueError("unsigned varint cannot encode a negative number")
        while True:
            byte = value & 0x7F
            value >>= 7
            if value:
                out.append(byte | 0x80)
            else:
                out.append(byte)
                break
    return bytes(out)
