from __future__ import annotations

import random

from mbi.canonical import IntVector3
from mbi.formats.litematic import bits_per_entry, normalize_region, pack_block_states, unpack_block_states


def test_negative_region_sizes() -> None:
    bounds = normalize_region(IntVector3(10, 20, 30), IntVector3(-4, 5, -6))
    assert bounds.min == IntVector3(7, 20, 25)
    assert bounds.max == IntVector3(10, 24, 30)
    assert bounds.dimensions == IntVector3(4, 5, 6)


def test_bit_width_boundaries() -> None:
    assert bits_per_entry(1) == 2
    assert bits_per_entry(4) == 2
    assert bits_per_entry(5) == 3
    assert bits_per_entry(16) == 4
    assert bits_per_entry(17) == 5


def test_pack_unpack_cross_word_property() -> None:
    rng = random.Random(78231)
    for palette_size in (2, 3, 4, 5, 7, 8, 9, 15, 16, 17, 255, 256, 257):
        for length in (1, 2, 31, 32, 33, 63, 64, 65, 129, 500):
            values = [rng.randrange(palette_size) for _ in range(length)]
            bits = bits_per_entry(palette_size)
            words = pack_block_states(values, bits)
            assert unpack_block_states(words, len(values), bits) == values
