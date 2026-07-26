from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from app.ai.multimodal import run_tool_request_file
from app.project import load_document
from app.render import CameraSpec, SoftwareRenderer, pixel_to_block
from app.storage import atomic_write_json
from app.workflows import apply_build_plan, export_run, patch_action, pipeline, rollback_patch, snapshot_run
from app.assets import ResourcePackSource


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--fixture", type=Path, default=Path("tests/fixtures/reference.schem"))
    parser.add_argument("--resource-pack", type=Path, required=True)
    parser.add_argument("--root", type=Path, default=Path("var/snowflake-dynamic-e2e"))
    parser.add_argument("--report", type=Path, default=Path("var/reports/snowflake-dynamic-e2e.json"))
    args = parser.parse_args()
    if args.root.exists():
        shutil.rmtree(args.root)
    args.root.mkdir(parents=True)
    run = args.root / "imported"
    checks: list[dict[str, object]] = []

    initial = pipeline(args.fixture, run, export_format="schem", size=(256, 256))
    checks.append({"name": "flat_pipeline", "passed": initial["export"]["passed"] is True and initial["snapshot_count"] >= 10})

    textured = snapshot_run(run, resource_pack=args.resource_pack, views=("global", "layers", "slices"), size=(256, 256), pixels_per_block=6)
    diagnostics = json.loads((run / "diagnostics.json").read_text("utf-8"))
    checks.append({"name": "textured_cpu_snapshots", "passed": len(textured) >= 14 and diagnostics["render_mode"] == "software-textured", "snapshot_count": len(textured)})

    document = load_document(run)
    pack = ResourcePackSource(args.resource_pack)
    try:
        arbitrary = SoftwareRenderer(document, resource_pack=pack).render(
            run,
            camera=CameraSpec(37.0, 28.0, 0.0, 1.1, None, True, 1.5),
            crop=document.bounds,
            size=(300, 220),
            mode="textured",
            name="dynamic_arbitrary_crop",
        )
    finally:
        pack.close()
    hit = None
    for py in range(arbitrary.manifest["resolution"][1]):
        for px in range(arbitrary.manifest["resolution"][0]):
            hit = pixel_to_block(arbitrary.manifest_path, px, py)
            if hit:
                break
        if hit:
            break
    checks.append({"name": "arbitrary_crop_pixel_grounding", "passed": hit is not None, "sample_hit": hit})

    point = [-2, 3, 5]
    patch_payload = {
        "reason": "Dynamic exact-coordinate edit",
        "author": "dynamic-test",
        "bounds": {"min": point, "max": point},
        "max_affected_blocks": 1,
        "operations": [{"type": "set_block", "position": point, "state": "minecraft:gold_block"}],
        "evidence_refs": ["view:dynamic_arbitrary_crop"],
    }
    patch_file = args.root / "patch.json"
    patch_file.write_text(json.dumps(patch_payload, sort_keys=True), "utf-8")
    rejected = patch_action(run, patch_file, action="reject", resource_pack=args.resource_pack)
    checks.append({"name": "patch_rejection", "passed": rejected["status"] == "rejected" and load_document(run).state_at(type(document.bounds.min)(*point)).canonical_state == "minecraft:stone"})

    previewed = patch_action(run, patch_file, action="preview", resource_pack=args.resource_pack)
    checks.append({"name": "patch_preview_visual_and_analysis", "passed": previewed["status"] == "previewed" and bool(previewed["before_snapshot"]) and bool(previewed["after_snapshot"]) and "analysis_delta" in previewed})
    committed = patch_action(run, patch_file, action="commit", resource_pack=args.resource_pack)
    committed_state = load_document(run).state_at(type(document.bounds.min)(*point)).canonical_state
    checks.append({"name": "patch_commit", "passed": committed_state == "minecraft:gold_block", "patch_id": committed["patch_id"]})
    rolled = rollback_patch(run, committed["patch_id"])
    restored_state = load_document(run).state_at(type(document.bounds.min)(*point)).canonical_state
    checks.append({"name": "exact_rollback", "passed": rolled["status"] == "rolled_back" and restored_state == "minecraft:stone"})

    request_file = args.root / "tool-request.json"
    request_file.write_text(json.dumps({"requests": [
        {"id": "materials", "tool": "get_material_histogram", "arguments": {}},
        {"id": "chunk", "tool": "get_chunk", "arguments": {"chunk": [-1, 0, 0]}},
        {"id": "slice", "tool": "get_slice", "arguments": {"axis": "x", "index": -2}},
    ]}, sort_keys=True), "utf-8")
    tool_result = run_tool_request_file(run, request_file, resource_pack=args.resource_pack)
    checks.append({"name": "json_exact_tool_bridge", "passed": tool_result["completed_count"] == 3 and all(row["ok"] for row in tool_result["results"])})

    schem = export_run(run, format_name="schem", verify=True)
    lite = export_run(run, format_name="litematic", verify=True)
    checks.append({"name": "both_verified_exports", "passed": schem["passed"] is True and lite["passed"] is True and schem["coordinate_mismatches"] == 0 and lite["state_mismatches"] == 0})

    plan = {
        "brief": {
            "name": "DynamicHall",
            "build_type": "guild_hall",
            "style": "medieval",
            "dimensions": [16, 12, 16],
            "floors": 2,
            "interior_required": True,
            "export_format": "litematic",
        },
        "critique_iterations": 1,
    }
    plan_path = args.root / "build-plan.json"
    plan_path.write_text(json.dumps(plan, sort_keys=True), "utf-8")
    generated_root = args.root / "generated"
    generated = apply_build_plan(plan_path, generated_root)
    generated_verify = json.loads((generated_root / "export" / "verify_report.json").read_text("utf-8"))
    stage_manifest = json.loads((generated_root / "construction_stages" / "manifest.json").read_text("utf-8"))
    checks.append({
        "name": "staged_generation_render_critique_export",
        "passed": generated["quality_gates"]["passed"] is True and generated_verify["passed"] is True and generated["stage_evidence_count"] > 20 and len(stage_manifest["stages"]) >= 5,
        "stage_evidence_count": generated["stage_evidence_count"],
    })

    report = {
        "schema": "mbi.snowflake-dynamic-e2e.v1",
        "passed": all(bool(item["passed"]) for item in checks),
        "python_only": True,
        "gl_context_used": False,
        "browser_used": False,
        "resource_pack_sha256": sha(args.resource_pack),
        "checks": checks,
        "artifacts": {
            "imported_run": str(run),
            "generated_run": str(generated_root),
            "arbitrary_png": str(arbitrary.png_path),
        },
    }
    atomic_write_json(args.report, report)
    print(json.dumps(report, indent=2, default=str))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
