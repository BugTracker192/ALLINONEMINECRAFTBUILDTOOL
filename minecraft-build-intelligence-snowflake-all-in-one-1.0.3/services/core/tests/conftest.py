from __future__ import annotations

import hashlib

import pytest

from mbi.canonical import BuildDocument, BuildRegion, BuildSource, IntBoundingBox, IntVector3, PaletteEntry


@pytest.fixture
def sample_document() -> BuildDocument:
    bounds = IntBoundingBox(IntVector3(-1, 0, -2), IntVector3(2, 2, 1))
    palette = [
        PaletteEntry.from_state(0, "minecraft:air"),
        PaletteEntry.from_state(1, "minecraft:stone_bricks"),
        PaletteEntry.from_state(2, "minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]"),
        PaletteEntry.from_state(3, "minecraft:glass"),
    ]
    blocks = {
        IntVector3(x, 0, z): 1
        for x in range(bounds.min.x, bounds.max.x + 1)
        for z in range(bounds.min.z, bounds.max.z + 1)
    }
    blocks[IntVector3(0, 1, 0)] = 2
    blocks[IntVector3(1, 1, 0)] = 3
    source = BuildSource("fixture", "generated", "raw_nbt", hashlib.sha256(b"fixture").hexdigest(), 0, 0, 3953, 1)
    return BuildDocument(
        "1.0.0",
        "build_fixture",
        source,
        {"Name": "Fixture"},
        bounds,
        bounds.min,
        palette,
        [BuildRegion("Main", bounds.min, bounds.dimensions, bounds, tuple(p.canonical_state for p in palette))],
        blocks,
    )
