from __future__ import annotations

from mbi.canonical import IntBoundingBox, IntVector3
from mbi.patch import PatchEngine


def _commit(engine, ops, bounds, reason="extended"):
    patch = engine.create_patch(reason, "tester", bounds, 100000, ops, expected_parent_hash=engine.active.document.content_hash)
    engine.validate(patch)
    engine.preview(patch)
    return engine.commit(patch)


def test_geometry_branch_checkpoint_and_merge(sample_document) -> None:
    engine = PatchEngine(sample_document)
    bounds = sample_document.bounds
    root = engine.active_version_id
    version = _commit(engine, [
        {"type": "draw_sphere", "center": [0, 1, 0], "radius": 1, "state": "minecraft:gold_block"},
        {"type": "draw_line", "start": [-1, 2, -2], "end": [2, 2, 1], "state": "minecraft:redstone_block"},
    ], bounds)
    assert version.version_id != root
    checkpoint = engine.create_checkpoint("after geometry")
    assert checkpoint == version.version_id
    branch = engine.branch_version("variant")
    assert engine.current_branch == "variant"
    assert engine.active_version_id == branch.version_id
    _commit(engine, [{"type": "mirror_region", "min": [-1, 0, -2], "max": [1, 2, 1], "axis": "x", "origin": [0, 0, 0]}], bounds)
    restored = engine.restore_checkpoint("after geometry")
    assert restored.version_id == version.version_id
    undone = engine.undo()
    assert undone.version_id == root


def test_pending_patch_can_be_rejected(sample_document) -> None:
    from mbi.canonical import IntBoundingBox, IntVector3
    from mbi.patch import PatchEngine

    engine = PatchEngine(sample_document)
    point = IntVector3(0, 1, 0)
    patch = engine.create_patch(
        "Reject this proposal",
        "reviewer",
        IntBoundingBox(point, point),
        1,
        [{"type": "set_block", "position": list(point.as_tuple()), "state": "minecraft:gold_block"}],
    )
    engine.validate(patch)
    engine.reject(patch, reason="Visual review failed")
    assert patch.status.value == "rejected"
    assert engine.active.document.content_hash == sample_document.content_hash
    assert patch.validation_report["rejectionReason"] == "Visual review failed"
