from __future__ import annotations

import hashlib

from mbi.canonical import BuildDocument, BuildRegion, BuildSource, CanonicalBlockEntity, CanonicalEntity, IntBoundingBox, IntVector3, PaletteEntry
from mbi.export.litematic import export_litematic
from mbi.export.verify import verify_round_trip
from mbi.importer import import_build


def test_multi_region_signed_overlap_round_trip() -> None:
    palette = [
        PaletteEntry.from_state(0, "minecraft:air"),
        PaletteEntry.from_state(1, "minecraft:stone"),
        PaletteEntry.from_state(2, "minecraft:gold_block"),
    ]
    a = BuildRegion("A", IntVector3(3, 0, 0), IntVector3(-3, 2, 2), IntBoundingBox(IntVector3(1, 0, 0), IntVector3(3, 1, 1)), tuple(p.canonical_state for p in palette))
    b = BuildRegion("B", IntVector3(2, 0, 0), IntVector3(3, 2, 2), IntBoundingBox(IntVector3(2, 0, 0), IntVector3(4, 1, 1)), tuple(p.canonical_state for p in palette))
    a_values = {point: 1 for point in a.bounds.iter_points()}
    b_values = {point: 2 for point in b.bounds.iter_points()}
    flattened = dict(a_values)
    flattened.update(b_values)
    source = BuildSource("overlap.litematic", "litematic", "gzip", hashlib.sha256(b"overlap").hexdigest(), 0, 0, 3953, 6)
    doc = BuildDocument(
        "1.1.0", "build_overlap", source, {"Name": "Overlap"},
        IntBoundingBox(IntVector3(1, 0, 0), IntVector3(4, 1, 1)), IntVector3(1, 0, 0), palette, [a, b], flattened,
        region_blocks={"A": a_values, "B": b_values},
        block_entities=[CanonicalBlockEntity(IntVector3(1, 0, 0), "minecraft:chest", {"CustomName": "A"}, "A")],
        entities=[CanonicalEntity("minecraft:armor_stand", (2.5, 1.0, 0.5), {"Invisible": 1}, "B")],
        pending_block_ticks=[{"$regionName": "A", "x": 1, "y": 0, "z": 0, "i": "minecraft:stone"}],
        pending_fluid_ticks=[{"$regionName": "B", "x": 2, "y": 0, "z": 0, "i": "minecraft:water"}],
    )
    exported = export_litematic(doc, preserve_regions=True)
    reparsed = import_build(exported, "overlap.litematic")
    assert [region.name for region in reparsed.regions] == ["A", "B"]
    assert reparsed.regions[0].source_signed_size == IntVector3(-3, 2, 2)
    assert reparsed.region_blocks["A"][IntVector3(2, 0, 0)] != reparsed.region_blocks["B"][IntVector3(2, 0, 0)]
    report = verify_round_trip(doc, exported, "overlap.litematic")
    assert report.valid, report.messages
