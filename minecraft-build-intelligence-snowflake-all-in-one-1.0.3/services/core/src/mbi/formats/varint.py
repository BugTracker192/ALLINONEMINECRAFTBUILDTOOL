from __future__ import annotations

from collections.abc import Iterable, Iterator

from ..errors import FormatError


def iter_unsigned_varints(
    data: bytes,
    *,
    expected_count: int | None = None,
    max_bits: int = 32,
) -> Iterator[int]:
    """Yield unsigned varints while preserving the legacy decoder's errors.

    Consumers must exhaust the iterator so terminal unterminated-stream and
    expected-count validation can run.
    """
    result = 0
    shift = 0
    count = 0
    for offset, byte in enumerate(data):
        result |= (byte & 0x7F) << shift
        if byte & 0x80 == 0:
            count += 1
            if expected_count is not None and count > expected_count:
                raise FormatError(
                    "SPONGE_BLOCK_DATA_EXCESS",
                    "Sponge block data decoded more palette indexes than the structure volume.",
                    {"expected": expected_count, "actualAtLeast": count},
                )
            yield result
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
    if expected_count is not None and count != expected_count:
        raise FormatError(
            "SPONGE_BLOCK_DATA_LENGTH",
            "Sponge block data count does not match structure volume.",
            {"expected": expected_count, "actual": count},
        )


def decode_unsigned_varints(
    data: bytes,
    *,
    expected_count: int | None = None,
    max_bits: int = 32,
) -> list[int]:
    return list(
        iter_unsigned_varints(
            data,
            expected_count=expected_count,
            max_bits=max_bits,
        )
    )


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
