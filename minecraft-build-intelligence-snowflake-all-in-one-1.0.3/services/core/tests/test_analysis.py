from __future__ import annotations

from mbi.analysis import analyze_document
from mbi.analysis.rooms import classify_manual_room
from mbi.canonical import (
    BuildDocument,
    BuildRegion,
    BuildSource,
    IntBoundingBox,
    IntVector3,
    PaletteEntry,
)


def test_analysis_reports_materials_and_components(sample_document) -> None:
    report = analyze_document(sample_document)
    assert report["materials"]["totalNonAir"] == len(sample_document.blocks)
    assert report["components"]["count"] >= 1
    room_count = len(report["rooms"]["rooms"])
    assert len(report["navigation"]["roomReachability"]) == room_count
    assert len(report["lighting"]["rooms"]) == room_count
    balcony_report = report["interiorExterior"]
    assert balcony_report["possibleInaccessibleBalconyWeightedCount"] == sum(
        item["navigabilityWeight"]
        for item in balcony_report["possibleInaccessibleBalconySample"]
    )


def test_manual_room_seals_clip_boundary_and_reports_leak_path(
    sample_document,
) -> None:
    bounds = IntBoundingBox(
        IntVector3(-1, 1, -2),
        IntVector3(0, 2, -1),
    )
    room = classify_manual_room(
        sample_document,
        bounds,
        seed=IntVector3(-1, 1, -2),
        room_id=42,
    )

    assert room.evidence["manual_seed_and_clip"] is True
    assert room.evidence["sealed_opening_count"] > 0
    assert room.evidence["leak_detected"] is True
    assert room.evidence["leak_path"][0] == (-1, 1, -2)


def test_structure_envelope_seals_open_door_before_room_detection() -> None:
    bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(4, 3, 4))
    palette = [
        PaletteEntry.from_state(0, "minecraft:air"),
        PaletteEntry.from_state(1, "minecraft:stone_bricks"),
    ]
    blocks = {}
    for x in range(5):
        for z in range(5):
            blocks[IntVector3(x, 0, z)] = 1
            blocks[IntVector3(x, 3, z)] = 1
    for y in (1, 2):
        for x in range(5):
            blocks[IntVector3(x, y, 0)] = 1
            blocks[IntVector3(x, y, 4)] = 1
        for z in range(1, 4):
            blocks[IntVector3(0, y, z)] = 1
            blocks[IntVector3(4, y, z)] = 1
    del blocks[IntVector3(2, 1, 0)]
    del blocks[IntVector3(2, 2, 0)]
    source = BuildSource(
        "fixture",
        "generated",
        "raw_nbt",
        "0" * 64,
        0,
        0,
        3953,
        1,
    )
    document = BuildDocument(
        "1.1.0",
        "open_room",
        source,
        {},
        bounds,
        bounds.min,
        palette,
        [
            BuildRegion(
                "Main",
                bounds.min,
                bounds.dimensions,
                bounds,
                tuple(item.canonical_state for item in palette),
            )
        ],
        blocks,
    )

    ordinary = analyze_document(document)
    sealed = analyze_document(document, seal_structure_envelope=True)

    assert ordinary["rooms"]["enclosedSpaceCount"] == 0
    assert sealed["rooms"]["enclosedSpaceCount"] == 1
    room = sealed["rooms"]["rooms"][0]
    assert room["evidence"]["structure_envelope_sealed"] is True
    assert room["evidence"]["sealed_opening_count"] >= 2
    assert room["evidence"]["method"] == "constructed-column-envelope-seal-v1"
