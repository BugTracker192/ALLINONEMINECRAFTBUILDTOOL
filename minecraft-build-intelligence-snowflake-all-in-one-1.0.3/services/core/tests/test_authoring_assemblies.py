from __future__ import annotations

import copy

from mbi.canonical import IntBoundingBox, IntVector3
from mbi.patch import PatchEngine
from mbi.patch.assemblies import draw_dormer, fixture_catalog


def test_compound_assemblies_symmetry_and_repetition_are_reviewable(sample_document) -> None:
    document = copy.deepcopy(sample_document)
    document.bounds = IntBoundingBox(IntVector3(-20, -5, -20), IntVector3(20, 20, 20))
    engine = PatchEngine(document)
    operations = [
        {
            "type": "draw_truss",
            "origin": [-6, 2, 0],
            "width": 7,
            "height": 4,
            "state": "minecraft:oak_log",
        },
        {
            "type": "draw_arcade",
            "origin": [-6, 1, 4],
            "bayCount": 2,
            "bayWidth": 5,
            "height": 4,
            "state": "minecraft:stone_bricks",
        },
        {
            "type": "symmetry_edit",
            "axis": "x",
            "origin": [0, 0, 0],
            "operations": [
                {
                    "type": "place_fixture",
                    "fixture": "bench",
                    "origin": [3, 1, 1],
                    "length": 3,
                    "state": "minecraft:oak_planks",
                }
            ],
        },
        {
            "type": "repeat_module",
            "count": 3,
            "spacing": [0, 0, 3],
            "seed": 17,
            "variation": 0,
            "operation": {
                "type": "place_fixture",
                "fixture": "brazier",
                "origin": [0, 1, -6],
                "state": "minecraft:iron_block",
            },
        },
    ]
    patch = engine.create_patch(
        "compound authoring",
        "test",
        document.bounds,
        10_000,
        operations,
    )
    engine.validate(patch)
    assert len(patch.changes) > 30
    points = {change.position for change in patch.changes}
    assert any(point.x > 0 for point in points)
    assert any(point.x < 0 for point in points)
    assert fixture_catalog()["fixtures"]["bench"]


def test_seeded_greeble_surface_is_deterministic(sample_document) -> None:
    first = PatchEngine(copy.deepcopy(sample_document))
    second = PatchEngine(copy.deepcopy(sample_document))
    operation = {
        "type": "greeble_surface",
        "min": [-1, 0, -2],
        "max": [2, 0, 1],
        "detailState": "minecraft:mossy_stone_bricks",
        "probability": 0.5,
        "seed": 42,
    }
    patches = [
        engine.create_patch("detail", "test", sample_document.bounds, 100, [operation])
        for engine in (first, second)
    ]
    first.validate(patches[0])
    second.validate(patches[1])
    assert [
        (change.position, change.new_state) for change in patches[0].changes
    ] == [
        (change.position, change.new_state) for change in patches[1].changes
    ]


def test_dormer_has_a_ridge_and_greeble_changes_surface_depth(
    sample_document,
) -> None:
    dormer = draw_dormer(
        {
            "origin": [0, 0, 0],
            "width": 5,
            "depth": 2,
            "height": 3,
            "roofState": "minecraft:oak_stairs",
        }
    )
    assert IntVector3(2, 5, 0) in dormer
    assert IntVector3(0, 3, 0) in dormer

    document = copy.deepcopy(sample_document)
    document.bounds = IntBoundingBox(
        IntVector3(-3, -2, -4),
        IntVector3(4, 4, 3),
    )
    engine = PatchEngine(document)
    operation = {
        "type": "greeble_surface",
        "min": [-1, 0, -2],
        "max": [2, 0, 1],
        "detailState": "minecraft:mossy_stone_bricks",
        "probability": 1.0,
        "seed": 7,
        "mode": "protrude",
        "depth": 1,
    }
    patch = engine.create_patch(
        "depth detail",
        "test",
        document.bounds,
        100,
        [operation],
    )
    engine.validate(patch)
    assert any(
        change.position.y != 0
        or change.position.x not in range(-1, 3)
        or change.position.z not in range(-2, 2)
        for change in patch.changes
    )
