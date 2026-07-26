from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from app.workflows import import_file


def run_cli(*arguments: str, cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "app.cli", *arguments], cwd=cwd, text=True, capture_output=True, check=False)


def test_pipeline_query_patch_rollback_and_both_exports(reference_schem: Path, tiny_resource_pack: Path, tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    run = tmp_path / "run"
    result = run_cli("pipeline", str(reference_schem), "--out", str(run), "--resource-pack", str(tiny_resource_pack), "--size", "256x256", cwd=repository)
    assert result.returncode == 0, result.stderr
    for expected in (
        "canonical.json", "chunks/manifest.json", "raw_preserved/source.original", "diagnostics.json",
        "analysis.json", "snapshots/manifest.json", "export/out.schem", "export/verify_report.json",
    ):
        assert (run / expected).exists(), expected
    diagnostics = json.loads((run / "diagnostics.json").read_text("utf-8"))
    assert diagnostics["render_mode"] == "software-textured"

    query = run_cli("query", "block", str(run), "--x", "-2", "--y", "3", "--z", "5", "--json", cwd=repository)
    assert query.returncode == 0, query.stderr
    assert json.loads(query.stdout)["state"]["canonical_state"] == "minecraft:stone"

    patch = tmp_path / "patch.json"
    patch.write_text(json.dumps({
        "reason": "Grounded integration replacement",
        "author": "test",
        "bounds": {"min": [-2, 3, 5], "max": [-2, 3, 5]},
        "max_affected_blocks": 1,
        "operations": [{"type": "set_block", "position": [-2, 3, 5], "state": "minecraft:gold_block"}],
    }), "utf-8")
    commit = run_cli("patch", "commit", str(run), str(patch), "--resource-pack", str(tiny_resource_pack), cwd=repository)
    assert commit.returncode == 0, commit.stderr
    committed = json.loads(commit.stdout)
    assert (run / committed["before_snapshot"]).exists()
    assert (run / committed["after_snapshot"]).exists()
    rollback = run_cli("patch", "rollback", str(run), "--patch-id", committed["patch_id"], cwd=repository)
    assert rollback.returncode == 0, rollback.stderr
    restored = run_cli("query", "block", str(run), "--x", "-2", "--y", "3", "--z", "5", "--json", cwd=repository)
    assert json.loads(restored.stdout)["state"]["canonical_state"] == "minecraft:stone"

    lite = run_cli("export", str(run), "--format", "litematic", "--verify", cwd=repository)
    assert lite.returncode == 0, lite.stderr
    assert json.loads(lite.stdout)["passed"] is True


def test_json_tool_bridge_batch_commit_and_query(reference_schem: Path, tmp_path: Path) -> None:
    run = tmp_path / "tool-run"
    import_file(reference_schem, run)
    request = tmp_path / "request.json"
    request.write_text(
        json.dumps(
            {
                "requests": [
                    {
                        "id": "begin",
                        "tool": "begin_patch",
                        "arguments": {
                            "reason": "Tool bridge exact edit",
                            "author": "test",
                            "bounds": {"min": [-2, 3, 5], "max": [-2, 3, 5]},
                            "maxAffectedBlocks": 1,
                            "operations": [
                                {"type": "set_block", "position": [-2, 3, 5], "state": "minecraft:gold_block"}
                            ],
                        },
                    },
                    {"id": "preview", "tool": "preview_patch", "arguments": {"patchId": "$last_patch_id"}},
                    {"id": "commit", "tool": "commit_patch", "arguments": {"patchId": "$last_patch_id"}},
                    {"id": "query", "tool": "get_block", "arguments": {"position": [-2, 3, 5]}},
                ]
            },
            sort_keys=True,
        ),
        "utf-8",
    )
    completed = subprocess.run(
        [sys.executable, "-m", "app.cli", "tool", str(run), str(request), "--allow-commit"],
        cwd=Path(__file__).parents[2],
        check=False,
        text=True,
        capture_output=True,
    )
    assert completed.returncode == 0, completed.stderr
    result = json.loads(completed.stdout)
    assert result["completed_count"] == 4
    assert all(item["ok"] for item in result["results"])
    query = result["results"][-1]["result"]
    assert query["state"]["canonical_state"] == "minecraft:gold_block"
    assert (run / "ai" / "tool_results" / "request.result.json").exists()


def test_pipeline_outputs_are_byte_deterministic(reference_schem: Path, tmp_path: Path) -> None:
    import hashlib

    repository = Path(__file__).resolve().parents[2]
    first, second = tmp_path / "det-a", tmp_path / "det-b"
    for target in (first, second):
        result = run_cli("pipeline", str(reference_schem), "--out", str(target), "--size", "192x192", cwd=repository)
        assert result.returncode == 0, result.stderr

    def digest_tree(root: Path) -> dict[str, str]:
        result = {}
        for path in sorted(root.rglob("*")):
            if path.is_file():
                relative = str(path.relative_to(root))
                result[relative] = hashlib.sha256(path.read_bytes()).hexdigest()
        return result

    assert digest_tree(first) == digest_tree(second)


def test_cli_exact_chunk_and_block_entity_queries(reference_schem: Path, tmp_path: Path) -> None:
    repository = Path(__file__).resolve().parents[2]
    run = tmp_path / "query-run"
    imported = run_cli("import", str(reference_schem), "--out", str(run), cwd=repository)
    assert imported.returncode == 0, imported.stderr

    chunk = run_cli("query", "chunk", str(run), "--cx", "-1", "--cy", "0", "--cz", "0", "--json", cwd=repository)
    assert chunk.returncode == 0, chunk.stderr
    payload = json.loads(chunk.stdout)
    assert payload["coordinate_space"] == "document"
    assert any(item["position"] == [-2, 3, 5] and item["state"] == "minecraft:stone" for item in payload["blocks"])

    entity = run_cli("query", "block-entity", str(run), "--x", "-2", "--y", "3", "--z", "5", "--json", cwd=repository)
    assert entity.returncode == 0, entity.stderr
    assert json.loads(entity.stdout)["block_entity"] is None
