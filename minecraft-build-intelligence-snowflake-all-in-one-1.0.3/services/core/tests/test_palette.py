from __future__ import annotations

import pytest

from mbi.errors import FormatError
from mbi.palette import parse_block_state


def test_canonical_property_order() -> None:
    parsed = parse_block_state("minecraft:oak_stairs[shape=straight,facing=north,half=bottom]")
    assert parsed.canonical == "minecraft:oak_stairs[facing=north,half=bottom,shape=straight]"


def test_duplicate_property_rejected() -> None:
    with pytest.raises(FormatError) as error:
        parse_block_state("minecraft:stone[a=1,a=2]")
    assert error.value.code == "DUPLICATE_BLOCK_PROPERTY"
