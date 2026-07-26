from __future__ import annotations

import random

import pytest

from mbi.errors import FormatError
from mbi.formats.varint import decode_unsigned_varints, encode_unsigned_varints


def test_varint_property_round_trip() -> None:
    rng = random.Random(91241)
    for _ in range(250):
        values = [rng.randrange(0, 2**31) for _ in range(rng.randrange(0, 500))]
        assert decode_unsigned_varints(encode_unsigned_varints(values), expected_count=len(values)) == values


def test_varint_rejects_unterminated() -> None:
    with pytest.raises(FormatError) as error:
        decode_unsigned_varints(b"\x80")
    assert error.value.code == "SPONGE_VARINT_UNTERMINATED"
