from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.project import load_document, load_patch_engine, persist_patch_engine
from app.workflows import import_file
from mbi.canonical import IntBoundingBox, IntVector3


def run_cli(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-m", "app.cli", *arguments],
        cwd=cwd,
        text=True,
        capture_output=True,
        check=False,
    )


def test_version_graph_survives_reloads(reference_schem: Path, tmp_path: Path) -> None:
    root = tmp_path / "run"
    import_file(reference_schem, root)
    engine = load_patch_engine(root)
    original_id = engine.active_version_id
    engine.create_checkpoint("original")
    patch = engine.create_patch(
        "Persistent graph edit",
        "test",
        IntBoundingBox(IntVector3(-2, 3, 5), IntVector3(-2, 3, 5)),
        1,
        [{"type": "set_block", "position": [-2, 3, 5], "state": "minecraft:gold_block"}],
        expected_parent_hash=engine.active.document.content_hash,
    )
    engine.validate(patch)
    committed = engine.commit(patch)
    persist_patch_engine(root, engine)

    reloaded = load_patch_engine(root)
    assert reloaded.active_version_id == committed.version_id
    assert reloaded.active.parent_version_id == original_id
    assert reloaded.checkpoints["original"] == original_id
    restored = reloaded.restore_checkpoint("original")
    reloaded.branch_version("experiment", committed.version_id)
    persist_patch_engine(root, reloaded)

    again = load_patch_engine(root)
    assert again.current_branch == "experiment"
    assert again.branch_heads["experiment"] == committed.version_id
    assert again.checkpoints["original"] == original_id
    assert restored.document.content_hash == load_document(root, version_id=original_id).content_hash


def test_cli_out_keeps_source_immutable(reference_schem: Path, tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    source = tmp_path / "source"
    derived = tmp_path / "derived"
    import_file(reference_schem, source)

    analyzed = run_cli("analyze", str(source), "--out", str(derived), cwd=repository)
    assert analyzed.returncode == 0, analyzed.stderr
    assert (derived / "canonical.json").is_file()
    assert (derived / "analysis.json").is_file()
    assert not (source / "analysis.json").exists()

    patch_path = tmp_path / "patch.json"
    patch_path.write_text(
        json.dumps(
            {
                "reason": "Output isolation",
                "author": "test",
                "bounds": {"min": [-2, 3, 5], "max": [-2, 3, 5]},
                "max_affected_blocks": 1,
                "operations": [
                    {"type": "set_block", "position": [-2, 3, 5], "state": "minecraft:gold_block"}
                ],
            }
        ),
        "utf-8",
    )
    patch_out = tmp_path / "patched"
    committed = run_cli(
        "patch", "commit", str(source), str(patch_path), "--out", str(patch_out), cwd=repository
    )
    assert committed.returncode == 0, committed.stderr
    point = IntVector3(-2, 3, 5)
    assert load_document(source).state_at(point).canonical_state == "minecraft:stone"
    assert load_document(patch_out).state_at(point).canonical_state == "minecraft:gold_block"
