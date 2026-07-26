from __future__ import annotations

from mbi.canonical import IntBoundingBox, IntVector3
from mbi.patch import PatchEngine


def test_patch_commit_and_undo(sample_document) -> None:
    engine = PatchEngine(sample_document)
    root_id = engine.active_version_id
    patch = engine.create_patch(
        "Add trim",
        "test",
        IntBoundingBox(IntVector3(-1, 0, -2), IntVector3(2, 2, 1)),
        10,
        [{"type": "set_block", "position": [2, 2, 1], "state": "minecraft:gold_block"}],
    )
    engine.validate(patch)
    version = engine.commit(patch)
    assert version.version_id != root_id
    assert version.document.state_at(IntVector3(2, 2, 1)).canonical_state == "minecraft:gold_block"
    engine.undo()
    assert engine.active_version_id == root_id


def test_advanced_geometry_operations_are_bounded_and_reversible(sample_document) -> None:
    engine = PatchEngine(sample_document)
    bounds = sample_document.bounds
    operations = [
        {"type": "draw_bezier", "controlPoints": [[-1, 0, -2], [0, 2, -1], [2, 1, 1]], "state": "minecraft:gold_block", "samples": 12},
        {"type": "extrude_profile", "profile": [[-1, 0, -2], [-1, 1, -2]], "offset": [1, 0, 0], "steps": 2, "state": "minecraft:diamond_block"},
        {"type": "loft_profiles", "profiles": [[[-1, 0, -2], [-1, 0, -1]], [[1, 2, 0], [1, 2, 1]]], "state": "minecraft:redstone_block"},
    ]
    patch = engine.create_patch("advanced geometry", "test", bounds, bounds.volume, operations)
    engine.validate(patch)
    preview = engine.preview(patch)
    assert preview.content_hash != sample_document.content_hash
    committed = engine.commit(patch)
    assert committed.document.content_hash == preview.content_hash
    restored = engine.undo()
    assert restored.document.content_hash == sample_document.content_hash
