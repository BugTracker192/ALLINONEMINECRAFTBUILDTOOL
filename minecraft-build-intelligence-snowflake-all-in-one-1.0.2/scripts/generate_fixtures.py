#!/usr/bin/env python3
from __future__ import annotations

import hashlib
from pathlib import Path

from mbi.canonical import BuildDocument, BuildRegion, BuildSource, IntBoundingBox, IntVector3, PaletteEntry
from mbi.export import export_litematic, export_sponge_v3

ROOT = Path(__file__).resolve().parents[1] / "packages" / "test-fixtures" / "generated"


def document(name: str, bounds: IntBoundingBox, blocks: dict[IntVector3, int], palette: list[PaletteEntry]) -> BuildDocument:
    source = BuildSource(name, "generated", "raw_nbt", hashlib.sha256(name.encode()).hexdigest(), 0, 0, 3953, 1)
    return BuildDocument(
        "1.0.0",
        "fixture_" + name.replace(".", "_"),
        source,
        {"Name": name},
        bounds,
        bounds.min,
        palette,
        [BuildRegion("Main", bounds.min, bounds.dimensions, bounds, tuple(p.canonical_state for p in palette))],
        blocks,
    )


def main() -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    palette = [
        PaletteEntry.from_state(0, "minecraft:air"),
        PaletteEntry.from_state(1, "minecraft:stone"),
        PaletteEntry.from_state(2, "minecraft:oak_stairs[facing=east,half=top,shape=inner_left,waterlogged=false]"),
        PaletteEntry.from_state(3, "minecraft:water[level=0]"),
        PaletteEntry.from_state(4, "example_mod:unknown_block[variant=blue]"),
    ]
    fixtures = {
        "one-block": document("one-block", IntBoundingBox(IntVector3(0, 0, 0), IntVector3(0, 0, 0)), {IntVector3(0, 0, 0): 1}, palette),
        "asymmetric-corners": document(
            "asymmetric-corners",
            IntBoundingBox(IntVector3(-2, 3, 5), IntVector3(4, 5, 9)),
            {
                IntVector3(-2, 3, 5): 1,
                IntVector3(4, 3, 5): 2,
                IntVector3(-2, 5, 9): 3,
                IntVector3(4, 5, 9): 4,
            },
            palette,
        ),
    }
    for name, value in fixtures.items():
        (ROOT / f"{name}.schem").write_bytes(export_sponge_v3(value))
        (ROOT / f"{name}.litematic").write_bytes(export_litematic(value))
    print(f"Generated {len(fixtures) * 2} fixtures in {ROOT}")


if __name__ == "__main__":
    main()
