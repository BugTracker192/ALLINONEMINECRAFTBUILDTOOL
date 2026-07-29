from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mbi.ai.construction import AutonomousConstructionExecutor, ConstructionBrief
from mbi.analysis import analyze_document
from mbi.canonical import BuildDocument, IntBoundingBox, IntVector3
from mbi.export import export_litematic, export_sponge_v3, verify_round_trip
from mbi.importer import import_build
from mbi.patch import PatchEngine
from mbi.scoping import scoped_document

from app.assets import open_resource_pack
from app.errors import AppError
from app.jobs import JobRecord, JobState
from app.project import (initialize_layout, load_document, load_patch_engine, persist_patch_engine, preserve_source, save_document, write_diagnostics)
from app.render import CameraSpec, SoftwareRenderer
from app.storage import atomic_write_bytes, atomic_write_json


def import_file(source: str | Path, output_root: str | Path) -> BuildDocument:
    source_path = Path(source)
    root = Path(output_root)
    initialize_layout(root)
    data = source_path.read_bytes()
    job = JobRecord.create("import", {"source": hashlib.sha256(data).hexdigest()}, {"filename": source_path.name})
    job.state = JobState.RUNNING
    job.persist(root)
    try:
        document = import_build(data, source_path.name)
        preserve_source(root, source_path, data)
        save_document(root, document)
        atomic_write_json(root / "raw_preserved" / "unknown_tags.json", document.extension_data)
        write_diagnostics(root, document)
        job.state = JobState.SUCCEEDED
        job.stage = "complete"
        job.progress = 1.0
        job.result_refs = ["canonical.json", "chunks/manifest.json", "diagnostics.json"]
        job.persist(root)
        return document
    except Exception as exc:
        job.state = JobState.FAILED
        job.error = {"code": getattr(exc, "code", "IMPORT_FAILED"), "message": str(exc), "details": getattr(exc, "details", {})}
        job.persist(root)
        raise


def analyze_run(
    run_root: str | Path,
    *,
    bounds: IntBoundingBox | None = None,
    lighting_max_cells: int | None = 10_000_000,
    dark_threshold: int = 7,
    room_max_cells: int = 20_000_000,
    manual_rooms: tuple[
        tuple[IntBoundingBox, IntVector3 | None], ...
    ] = (),
    seal_structure_envelope: bool = False,
) -> dict[str, Any]:
    root = Path(run_root)
    source_document = load_document(root)
    document = scoped_document(source_document, bounds) if bounds is not None else source_document
    configuration = {
        "profile": "bounded" if bounds else "full",
        "bounds": asdict(document.bounds),
        "lighting_max_cells": lighting_max_cells,
        "dark_threshold": dark_threshold,
        "room_max_cells": room_max_cells,
        "seal_structure_envelope": seal_structure_envelope,
        "manual_rooms": [
            {
                "bounds": asdict(room_bounds),
                "seed": asdict(seed) if seed is not None else None,
            }
            for room_bounds, seed in manual_rooms
        ],
    }
    job = JobRecord.create("analysis", {"build": source_document.content_hash}, configuration)
    job.state = JobState.RUNNING
    job.stage = "analysis"
    job.persist(root)
    try:
        result = analyze_document(
            document,
            lighting_max_cells=lighting_max_cells,
            dark_threshold=dark_threshold,
            room_max_cells=room_max_cells,
            manual_rooms=manual_rooms,
            seal_structure_envelope=seal_structure_envelope,
        )
        payload = {
            "schema_version": "mbi.analysis.v2",
            "build_version_hash": document.content_hash,
            "parent_build_version_hash": (
                source_document.content_hash if bounds is not None else None
            ),
            "scope": {
                "type": "bounds" if bounds is not None else "document",
                "bounds": asdict(document.bounds),
                "block_count": len(document.blocks),
            },
            "configuration": configuration,
            "algorithms": {
                "materials": "exact-histogram-v1",
                "surfaces": "six-neighbor-v1",
                "components": "configurable-adjacency-v1",
                "rooms": (
                    "constructed-column-envelope-seal-v1"
                    if seal_structure_envelope
                    else "outside-flood-fill-v1"
                ),
                "navigation": "standable-headroom-heuristic-v1",
                "lighting": "heuristic-emitter-coverage-v1",
                "facade": "surface-patch-depth-v1",
                "consistency": "grounded-rule-set-v1",
            },
            "results": result,
            "warnings": ["Lighting values are heuristic and are not exact Minecraft light-engine values."],
        }
        atomic_write_json(root / "analysis.json", payload)
        job.state = JobState.SUCCEEDED
        job.stage = "complete"
        job.progress = 1.0
        job.result_refs = ["analysis.json"]
        job.persist(root)
        return payload
    except Exception as exc:
        job.state = JobState.FAILED
        job.error = {"code": getattr(exc, "code", "ANALYSIS_FAILED"), "message": str(exc), "details": getattr(exc, "details", {})}
        job.persist(root)
        raise


def _occupied_layers(document: BuildDocument) -> list[int]:
    return sorted({position.y for position in document.blocks}) or [document.bounds.min.y]


def _issue_coordinates(analysis: dict[str, Any]) -> dict[IntVector3, int]:
    """Convert grounded analysis samples into stable semantic issue categories.

    The issue map is deliberately conservative: only findings that already carry
    exact block coordinates are projected. Air-only navigation findings remain in
    analysis.json instead of being incorrectly attached to a neighboring block.
    """

    result: dict[IntVector3, int] = {}

    def add(raw: Any, code: int) -> None:
        if isinstance(raw, dict):
            raw = raw.get("position")
        if isinstance(raw, (list, tuple)) and len(raw) == 3:
            point = IntVector3(*(int(value) for value in raw))
            result[point] = max(result.get(point, 0), code)

    support = analysis.get("support", {})
    for item in support.get("unsupportedSample", []):
        add(item, 2)
    for item in support.get("gravityIssues", []):
        add(item, 3)
    for item in support.get("thinCantileverSample", []):
        add(item, 4)

    consistency = analysis.get("interiorExterior", {})
    for item in consistency.get("windowsWithoutInterior", []):
        add(item, 5)
    for item in consistency.get("exteriorDoorsWithoutInterior", []):
        add(item, 6)
    for item in consistency.get("floorWindowConflictSample", []):
        add(item, 7)
    for item in consistency.get("possibleInaccessibleBalconySample", []):
        add(item, 8)

    for patch in analysis.get("facade", {}).get("largestFlatPatches", []):
        if not isinstance(patch, dict):
            continue
        direction = str(patch.get("direction", ""))
        depth = int(patch.get("depth", 0))
        for y in range(int(patch.get("yMin", 0)), int(patch.get("yMax", -1)) + 1):
            for u in range(int(patch.get("uMin", 0)), int(patch.get("uMax", -1)) + 1):
                if direction in {"north", "south"}:
                    add([u, y, depth], 9)
                elif direction in {"east", "west"}:
                    add([depth, y, u], 9)
    return result


def snapshot_run(
    run_root: str | Path,
    *,
    resource_pack: str | Path | None = None,
    views: tuple[str, ...] = ("global", "layers", "slices"),
    size: tuple[int, int] = (768, 768),
    pixels_per_block: int = 8,
    strict_textures: bool = False,
) -> list[dict[str, Any]]:
    root = Path(run_root)
    document = load_document(root)
    pack = open_resource_pack(resource_pack)
    job = JobRecord.create(
        "snapshot", {"build": document.content_hash, "resource_pack": pack.pack_hash if pack else "none"},
        {"views": list(views), "size": list(size), "pixels_per_block": pixels_per_block, "strict_textures": strict_textures},
    )
    job.state = JobState.RUNNING
    job.stage = "rendering"
    job.persist(root)
    manifests: list[dict[str, Any]] = []
    aggregate_fallbacks: list[dict[str, Any]] = []
    aggregate_unsupported: list[dict[str, Any]] = []
    aggregate_asset_diagnostics: list[dict[str, Any]] = []
    render_mode = "software-textured" if pack else "software-flat"
    render_tier = 2 if pack else 0
    try:
        renderer = SoftwareRenderer(document, resource_pack=pack, strict_textures=strict_textures)
        issue_coordinates = _issue_coordinates(analyze_document(document))
        if "global" in views:
            directions = ("north", "south", "east", "west", "top", "bottom", "isometric_ne", "isometric_nw", "isometric_se", "isometric_sw")
            for direction in directions:
                result = renderer.render(
                    root,
                    camera=CameraSpec.preset(direction),
                    size=size,
                    mode="textured" if pack else "flat",
                    name=f"global_{direction}",
                )
                manifests.append(result.manifest)
                aggregate_fallbacks.extend(result.diagnostics.get("fallbacks", []))
                aggregate_unsupported.extend(result.diagnostics.get("unsupported_models", []))
                aggregate_asset_diagnostics.extend(result.diagnostics.get("asset_diagnostics", []))
            if issue_coordinates:
                issue_result = renderer.render(
                    root,
                    camera=CameraSpec.preset("isometric_ne"),
                    size=size,
                    mode="textured" if pack else "flat",
                    lighting_preset="diff-highlight",
                    issue_coordinates=issue_coordinates,
                    name="global_issues",
                )
                issue_result.manifest["issue_categories"] = {
                    "1": "renderer-fallback",
                    "2": "unsupported-structure",
                    "3": "gravity-support",
                    "4": "thin-cantilever",
                    "5": "window-without-interior",
                    "6": "exterior-door-without-interior",
                    "7": "floor-window-conflict",
                    "8": "possibly-inaccessible-balcony",
                    "9": "large-flat-facade",
                }
                atomic_write_json(issue_result.manifest_path, issue_result.manifest)
                manifests.append(issue_result.manifest)
        if "layers" in views:
            for y in _occupied_layers(document):
                result = renderer.render_slice(
                    root,
                    axis="y",
                    minimum=y,
                    pixels_per_block=pixels_per_block,
                    mode="textured" if pack else "flat",
                    name=f"layer_y_{y}",
                )
                manifests.append(result.manifest)
                aggregate_fallbacks.extend(result.diagnostics.get("fallbacks", []))
        if "slices" in views:
            x = (document.bounds.min.x + document.bounds.max.x) // 2
            z = (document.bounds.min.z + document.bounds.max.z) // 2
            for axis, value in (("x", x), ("z", z)):
                result = renderer.render_slice(
                    root,
                    axis=axis,
                    minimum=value,
                    pixels_per_block=pixels_per_block,
                    mode="textured" if pack else "flat",
                    name=f"slice_{axis}_{value}",
                )
                manifests.append(result.manifest)
        atomic_write_json(
            root / "snapshots" / "manifest.json",
            {
                "schema": "mbi.snapshot-manifest.v1",
                "build_hash": document.content_hash,
                "render_mode": render_mode,
                "resource_pack_hash": pack.pack_hash if pack else None,
                "snapshots": sorted(manifests, key=lambda item: item["snapshot_id"]),
            },
        )
        def unique_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
            seen: set[str] = set()
            result: list[dict[str, Any]] = []
            for row in rows:
                key = json.dumps(row, sort_keys=True, separators=(",", ":"), default=str)
                if key not in seen:
                    seen.add(key)
                    result.append(row)
            return result
        aggregate_fallbacks = unique_rows(aggregate_fallbacks)
        aggregate_unsupported = unique_rows(aggregate_unsupported)
        aggregate_asset_diagnostics = unique_rows(aggregate_asset_diagnostics)
        write_diagnostics(
            root,
            document,
            render={
                "render_mode": render_mode,
                "render_tier": render_tier,
                "resource_pack": {"provided": pack is not None, "content_hash": pack.pack_hash if pack else None},
                "fallbacks": aggregate_fallbacks,
                "unsupported_models": aggregate_unsupported,
                "asset_diagnostics": aggregate_asset_diagnostics,
            },
        )
        job.state = JobState.SUCCEEDED
        job.stage = "complete"
        job.progress = 1.0
        job.result_refs = ["snapshots/manifest.json", "semantic_maps/"]
        job.persist(root)
        return manifests
    except Exception as exc:
        job.state = JobState.FAILED
        job.error = {"code": getattr(exc, "code", "RENDER_FAILED"), "message": str(exc), "details": getattr(exc, "details", {})}
        job.persist(root)
        raise
    finally:
        if pack:
            pack.close()


def export_run(run_root: str | Path, *, format_name: str, verify: bool = True) -> dict[str, Any]:
    root = Path(run_root)
    document = load_document(root)
    job = JobRecord.create("export", {"build": document.content_hash}, {"format": format_name, "verify": verify})
    job.state = JobState.RUNNING
    job.stage = "exporting"
    job.persist(root)
    if format_name in {"schem", "schem_v3", "sponge"}:
        data = export_sponge_v3(document)
        filename = "out.schem"
        normalized_format = "schem_v3"
    elif format_name in {"litematic", "lite"}:
        data = export_litematic(document)
        filename = "out.litematic"
        normalized_format = "litematic"
    else:
        raise AppError("EXPORT_FORMAT", "Unsupported export format.", {"format": format_name}, 50)
    path = root / "export" / filename
    atomic_write_bytes(path, data)
    report = verify_round_trip(document, data, filename) if verify else None
    reparsed = import_build(data, filename) if verify else None
    payload = {
        "passed": bool(report.valid) if report else None,
        "source_version": "ver_" + document.content_hash[:20],
        "export_format": normalized_format,
        "artifact": f"export/{filename}",
        "artifact_sha256": hashlib.sha256(data).hexdigest(),
        "block_count_source": len(document.blocks),
        "block_count_reimported": len(reparsed.blocks) if reparsed else None,
        "bounds_mismatches": report.bounds_mismatches if report else None,
        "coordinate_mismatches": report.coordinate_mismatches if report else None,
        "state_mismatches": report.state_mismatches if report else None,
        "region_mismatches": report.region_mismatches if report else None,
        "block_entity_mismatches": report.block_entity_mismatches if report else None,
        "entity_mismatches": report.entity_mismatches if report else None,
        "accepted_loss": [],
        "messages": list(report.messages) if report else [],
        "hashes": {"source": document.content_hash, "reimported": report.exported_hash if report else None},
    }
    atomic_write_json(root / "export" / "verify_report.json", payload)
    if report and not report.valid:
        raise AppError("EXPORT_ROUNDTRIP_MISMATCH", "Export failed exact re-import verification.", payload, 51)
    return payload

def pipeline(
    source: str | Path,
    output_root: str | Path,
    *,
    resource_pack: str | Path | None = None,
    export_format: str = "schem",
    size: tuple[int, int] = (512, 512),
) -> dict[str, Any]:
    document = import_file(source, output_root)
    analysis = analyze_run(output_root)
    snapshots = snapshot_run(output_root, resource_pack=resource_pack, size=size)
    export_report = export_run(output_root, format_name=export_format, verify=True)
    return {
        "build": document.to_summary(),
        "analysis_path": "analysis.json",
        "snapshot_count": len(snapshots),
        "export": export_report,
    }


def _patch_from_payload(
    engine: PatchEngine,
    document: BuildDocument,
    payload: dict[str, Any],
    *,
    run_root: str | Path | None = None,
):
    bounds_raw = payload.get("bounds") or payload.get("intended_bounds") or payload.get("intendedBounds")
    if not isinstance(bounds_raw, dict):
        raise AppError("PATCH_BOUNDS", "Patch requires bounds object.", exit_code=40)
    minimum = IntVector3(*[int(value) for value in bounds_raw["min"]])
    maximum = IntVector3(*[int(value) for value in bounds_raw["max"]])
    operations = payload.get("operations")
    if operations is None and isinstance(payload.get("operation"), dict):
        operations = [payload["operation"]]
    if not isinstance(operations, list):
        raise AppError("PATCH_OPERATIONS", "Patch requires operations array.", exit_code=40)
    normalized_operations = [dict(item) for item in operations]
    if run_root is not None:
        from app.authoring import resolve_anchored_operations

        normalized_operations = resolve_anchored_operations(
            run_root, normalized_operations
        )
    patch = engine.create_patch(
        str(payload.get("reason", "External agent patch")),
        str(payload.get("author", "external_agent")),
        IntBoundingBox(minimum, maximum),
        int(payload.get("max_affected_blocks", payload.get("maxAffectedBlocks", 100_000))),
        normalized_operations,
        coordinate_space=str(payload.get("coordinate_space", payload.get("coordinateSpace", "document"))),
        preconditions=list(payload.get("preconditions", [])),
        expected_parent_hash=str(payload.get("expected_parent_hash", payload.get("expectedParentHash", document.content_hash))),
        target_region=payload.get("target_region", payload.get("targetRegion")),
        evidence_refs=[str(item) for item in payload.get("evidence_refs", payload.get("evidenceRefs", []))],
    )
    return patch


def _quality_metrics(document: BuildDocument) -> dict[str, int]:
    analysis = analyze_document(document)
    rooms = analysis.get("rooms", {}).get("rooms", [])
    return {
        "floating_components": int(analysis.get("components", {}).get("floatingCount", 0)),
        "unsupported_blocks": int(analysis.get("support", {}).get("unsupportedBlockCount", 0)),
        "gravity_issues": int(analysis.get("support", {}).get("gravityIssueCount", 0)),
        "sealed_rooms": sum(1 for room in rooms if room.get("sealed")),
        "navigation_components": int(analysis.get("navigation", {}).get("componentCount", 0)),
        "navigation_dead_ends": int(analysis.get("navigation", {}).get("deadEndCount", 0)),
        "dark_cells": int(analysis.get("lighting", {}).get("darkCellCount", 0)),
        "large_flat_patches": int(analysis.get("facade", {}).get("largeFlatPatchCount", 0)),
        "windows_without_interior": int(analysis.get("interiorExterior", {}).get("windowsWithoutInteriorCount", 0)),
        "exterior_doors_without_interior": int(analysis.get("interiorExterior", {}).get("exteriorDoorsWithoutInteriorCount", 0)),
        "floor_window_conflicts": int(analysis.get("interiorExterior", {}).get("floorWindowConflictCount", 0)),
    }


def _quality_delta(before: BuildDocument, after: BuildDocument) -> dict[str, Any]:
    before_metrics = _quality_metrics(before)
    after_metrics = _quality_metrics(after)
    changed = {
        key: {"before": before_metrics[key], "after": after_metrics[key], "delta": after_metrics[key] - before_metrics[key]}
        for key in before_metrics
        if before_metrics[key] != after_metrics[key]
    }
    return {
        "before": before_metrics,
        "after": after_metrics,
        "improvements": {key: value for key, value in changed.items() if value["delta"] < 0},
        "regressions": {key: value for key, value in changed.items() if value["delta"] > 0},
        "neutral_changes": {key: value for key, value in changed.items() if value["delta"] == 0},
        "heuristic_notice": "Lower issue counts are treated as improvements; lighting and navigation remain documented heuristics.",
    }


def patch_action(
    run_root: str | Path,
    patch_file: str | Path,
    *,
    action: str,
    resource_pack: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(run_root)
    engine = load_patch_engine(root)
    document = engine.active.document
    payload = json.loads(Path(patch_file).read_text("utf-8"))
    patch = _patch_from_payload(engine, document, payload, run_root=root)
    engine.validate(patch)
    preview = engine.preview(patch)
    patch_record = {
        "patch_id": patch.patch_id,
        "status": patch.status.value,
        "parent_version_id": patch.parent_version_id,
        "parent_hash": document.content_hash,
        "author": patch.author,
        "reason": patch.reason,
        "bounds": asdict(patch.intended_bounds),
        "max_affected_blocks": patch.max_affected_blocks,
        "operations": patch.operations,
        "preconditions": patch.preconditions,
        "evidence_refs": patch.evidence_refs,
        "validation": patch.validation_report,
        "preview": patch.preview_report,
        "changes": [
            {"position": list(change.position.as_tuple()), "before": change.old_state, "after": change.new_state}
            for change in patch.changes
        ],
    }
    preview_dir = root / "patches" / "previews" / patch.patch_id
    preview_dir.mkdir(parents=True, exist_ok=True)
    # Changed-area before and after renders are mandatory preview evidence.
    pack = open_resource_pack(resource_pack)
    try:
        before_result = SoftwareRenderer(document, resource_pack=pack).render(
            preview_dir, camera=CameraSpec.preset("isometric_ne"), crop=patch.intended_bounds,
            size=(512, 512), mode="textured" if pack else "flat", name="before",
        )
        after_result = SoftwareRenderer(preview, resource_pack=pack).render(
            preview_dir, camera=CameraSpec.preset("isometric_ne"), crop=patch.intended_bounds,
            size=(512, 512), mode="textured" if pack else "flat", name="after",
            changed_coordinates=frozenset(change.position for change in patch.changes),
        )
    finally:
        if pack:
            pack.close()
    patch_record["before_snapshot"] = str(before_result.manifest_path.relative_to(root))
    patch_record["after_snapshot"] = str(after_result.manifest_path.relative_to(root))
    patch_record["analysis_delta"] = _quality_delta(document, preview)
    patch_record["estimated_export_impact"] = {
        "changed_blocks": len(patch.changes),
        "block_entity_changes": len(patch.block_entity_changes),
        "palette_entries_before": len(document.palette),
        "palette_entries_after": len(preview.palette),
        "requires_repacking": bool(patch.changes),
        "round_trip_verification_required": True,
    }
    if action == "validate":
        patch_record["status"] = "validated"
    elif action == "preview":
        patch_record["status"] = "previewed"
    elif action == "commit":
        version = engine.commit(patch)
        persist_patch_engine(root, engine)
        version_id = version.version_id
        patch_record.update({"status": "committed", "new_version_id": version_id, "after_hash": version.document.content_hash})
    elif action == "reject":
        engine.reject(patch, reason=str(payload.get("rejection_reason", "Rejected by operator")))
        patch_record.update({"status": "rejected", "rejection_reason": patch.validation_report.get("rejectionReason")})
    else:
        raise AppError("PATCH_ACTION", "Unsupported patch action.", {"action": action}, 40)
    atomic_write_json(root / "patches" / f"{patch.patch_id}.json", patch_record)
    return patch_record


def rollback_patch(run_root: str | Path, patch_id: str) -> dict[str, Any]:
    root = Path(run_root)
    record_path = root / "patches" / f"{patch_id}.json"
    record = json.loads(record_path.read_text("utf-8"))
    parent_id = str(record["parent_version_id"])
    engine = load_patch_engine(root)
    parent = engine.checkout(parent_id)
    persist_patch_engine(root, engine)
    record["status"] = "rolled_back"
    atomic_write_json(record_path, record)
    return {"patch_id": patch_id, "status": "rolled_back", "active_version_id": parent_id, "content_hash": parent.document.content_hash}


def create_build_plan(brief_path: str | Path, output_root: str | Path, *, source_run: str | Path | None = None) -> dict[str, Any]:
    raw = json.loads(Path(brief_path).read_text("utf-8"))
    brief = ConstructionBrief(**raw)
    width, height, length = brief.dimensions
    source_context = None
    if source_run is not None and (Path(source_run) / "canonical.json").is_file():
        source_document = load_document(source_run)
        source_context = {
            "run": str(Path(source_run)),
            "content_hash": source_document.content_hash,
            "summary": source_document.to_summary(),
        }
    plan = {
        "schema": "mbi.build-plan.v1",
        "brief": asdict(brief),
        "source_context": source_context,
        "design": {
            "concept": f"{brief.style} {brief.build_type}",
            "dimensions": [width, height, length],
            "primary_axis": brief.primary_axis,
            "floors": brief.floors,
            "palette": brief.palette,
            "detail_hierarchy": ["macro", "meso", "micro"],
            "construction_phases": ["massing", "layout", "facade", "interior", "detail", "critique", "verification"],
        },
    }
    root = Path(output_root)
    initialize_layout(root)
    atomic_write_json(root / "build_plan.json", plan)
    return plan


def apply_build_plan(plan_path: str | Path, output_root: str | Path, *, resource_pack: str | Path | None = None, source_run: str | Path | None = None) -> dict[str, Any]:
    raw = json.loads(Path(plan_path).read_text("utf-8"))
    source_context = raw.get("source_context")
    if source_context and source_run is not None and (Path(source_run) / "canonical.json").is_file():
        actual_hash = load_document(source_run).content_hash
        expected_hash = source_context.get("content_hash")
        if expected_hash and expected_hash != actual_hash:
            raise AppError(
                "BUILD_PLAN_SOURCE_STALE",
                "Build plan source context no longer matches the selected run.",
                {"expected": expected_hash, "actual": actual_hash},
                41,
            )
    brief = ConstructionBrief(**raw.get("brief", raw))
    executor = AutonomousConstructionExecutor(brief)
    run = executor.execute(critique_iterations=int(raw.get("critique_iterations", 2)))
    document = executor.document
    root = Path(output_root)
    initialize_layout(root)

    # Preserve and visually inspect every committed construction stage. This is
    # the deterministic no-provider equivalent of the perceive→critique loop;
    # an external model can consume the same stage evidence and add revisions.
    pack = open_resource_pack(resource_pack)
    stage_evidence: list[dict[str, Any]] = []
    try:
        for order, report in enumerate(run.stage_reports):
            version_id = report.get("versionId")
            if not version_id or version_id not in executor.engine.versions:
                continue
            version = executor.engine.versions[str(version_id)]
            save_document(root, version.document, active_version_id=version.version_id, parent_version_id=version.parent_version_id, patch_id=version.patch_id, branch_name=version.branch_name, metadata=version.metadata)
            stage_value = report.get("stage")
            stage_name = getattr(stage_value, "value", str(stage_value)).replace("ConstructionStage.", "").lower()
            stage_root = root / "construction_stages" / f"{order:02d}_{stage_name}"
            stage_root.mkdir(parents=True, exist_ok=True)
            stage_analysis = analyze_document(version.document)
            atomic_write_json(stage_root / "analysis.json", {
                "schema_version": "mbi.construction-stage-analysis.v1",
                "stage": stage_name,
                "version_id": version.version_id,
                "build_hash": version.document.content_hash,
                "results": stage_analysis,
            })
            if stage_name == "massing":
                views = ("north", "south", "east", "west", "top", "isometric_ne", "isometric_sw")
            elif stage_name in {"layout", "interior"}:
                views = ("top", "north", "isometric_ne")
            else:
                views = ("north", "south", "isometric_ne")
            renderer = SoftwareRenderer(version.document, resource_pack=pack)
            rendered = []
            for view in views:
                result = renderer.render(
                    stage_root,
                    camera=CameraSpec.preset(view),
                    size=(384, 384),
                    mode="textured" if pack else "flat",
                    name=f"{stage_name}_{view}",
                )
                rendered.append({
                    "evidence_id": f"stage:{stage_name}:{view}:{version.version_id}",
                    "png": str(result.png_path.relative_to(root)),
                    "manifest": str(result.manifest_path.relative_to(root)),
                })
            if stage_name in {"layout", "interior"}:
                occupied = sorted({position.y for position in version.document.blocks})
                for y in occupied[: min(8, len(occupied))]:
                    result = renderer.render_slice(
                        stage_root, axis="y", minimum=y, pixels_per_block=6,
                        mode="textured" if pack else "flat", name=f"{stage_name}_layer_{y}",
                    )
                    rendered.append({
                        "evidence_id": f"stage:{stage_name}:layer:{y}:{version.version_id}",
                        "png": str(result.png_path.relative_to(root)),
                        "manifest": str(result.manifest_path.relative_to(root)),
                    })
            report["visual_evidence"] = rendered
            stage_evidence.append({"stage": stage_name, "version_id": version.version_id, "evidence": rendered})
    finally:
        if pack:
            pack.close()

    # Restore the final version as active after writing intermediate versions.
    persist_patch_engine(root, executor.engine)
    final_analysis = analyze_run(root)
    atomic_write_json(root / "construction_run.json", asdict(run))
    atomic_write_json(root / "construction_stages" / "manifest.json", {"schema": "mbi.construction-evidence.v1", "stages": stage_evidence})
    snapshot_run(root, resource_pack=resource_pack, views=("global", "layers", "slices"), size=(512, 512))
    export_report = export_run(root, format_name=brief.export_format, verify=True)
    results = final_analysis["results"]
    quality_gates = {
        "schema": "mbi.quality-gates.v1",
        "passed": True,
        "checks": {
            "interior_detected": (not brief.interior_required) or results["rooms"].get("interiorVolumeCount", 0) > 0,
            "block_states_valid": not any(item.code.endswith("INVALID") for item in document.diagnostics),
            "export_round_trip": bool(export_report["passed"]),
            "visual_evidence_stages": len(stage_evidence) > 0,
            "exact_coordinate_loss": export_report["coordinate_mismatches"] == 0,
            "exact_state_loss": export_report["state_mismatches"] == 0,
        },
        "heuristic_warnings": {
            "floating_components": results["components"].get("floatingCount", 0),
            "navigation_components": results["navigation"].get("componentCount", 0),
            "dark_cells": results["lighting"].get("darkCellCount", 0),
            "large_flat_patches": results["facade"].get("largeFlatPatchCount", 0),
            "consistency_findings": sum(value for key, value in results["interiorExterior"].items() if key.endswith("Count") and isinstance(value, int)),
        },
    }
    quality_gates["passed"] = all(quality_gates["checks"].values())
    atomic_write_json(root / "quality_gates.json", quality_gates)
    if not quality_gates["passed"]:
        raise AppError("CONSTRUCTION_QUALITY_GATE", "Generated build failed mandatory deterministic quality gates.", quality_gates, 40)
    return {
        "run_id": run.run_id,
        "stage": run.stage.value,
        "versions": run.version_ids,
        "summary": document.to_summary(),
        "quality_gates": quality_gates,
        "stage_evidence_count": sum(len(item["evidence"]) for item in stage_evidence),
    }
