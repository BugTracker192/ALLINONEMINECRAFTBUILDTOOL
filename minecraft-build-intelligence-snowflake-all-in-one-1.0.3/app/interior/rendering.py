from __future__ import annotations

import json
import shutil
from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mbi.canonical import IntBoundingBox, IntVector3

from app.assets import open_resource_pack
from app.project import load_document
from app.render.perspective import PerspectiveCameraSpec, PerspectiveRenderer
from app.render.semantic import load_map
from app.render.software import SoftwareRenderer
from app.storage import atomic_write_json

from .model import (
    CameraCandidate,
    RoomCameraChoice,
    camera_candidates,
    cutaway_mask,
    get_room,
    load_rooms,
    room_bounds,
    room_geometry,
    voxel_ray,
)
from .quality import evaluate_frame


def _bounds_payload(bounds: IntBoundingBox) -> dict[str, list[int]]:
    return {"min": list(bounds.min.as_tuple()), "max": list(bounds.max.as_tuple())}


def _room_purpose(features: list[Any]) -> dict[str, Any]:
    rules = {
        "storage": ("chest", "barrel", "shulker_box"),
        "workshop": ("crafting_table", "furnace", "anvil", "stonecutter", "grindstone"),
        "library_or_study": ("bookshelf", "lectern", "enchanting_table"),
        "bedroom": ("bed",),
        "kitchen_or_brewery": ("smoker", "campfire", "brewing_stand", "cauldron"),
    }
    states = [item.state for item in features]
    scores = {
        purpose: sum(any(token in state for token in tokens) for state in states)
        for purpose, tokens in rules.items()
    }
    purpose, score = max(scores.items(), key=lambda item: (item[1], item[0]))
    if score == 0:
        return {
            "label": "undetermined",
            "confidence": 0.0,
            "evidence": [],
            "heuristic": True,
        }
    evidence = [state for state in states if any(token in state for token in rules[purpose])]
    return {
        "label": purpose,
        "confidence": round(min(0.85, 0.35 + 0.15 * score), 6),
        "evidence": evidence,
        "heuristic": True,
    }


def _choice(
    room_id: str,
    shot: str,
    bounds: IntBoundingBox,
    candidate: CameraCandidate,
    count: int,
    feature_target: tuple[float, float, float] | None,
    diagnostics: dict[str, Any],
) -> RoomCameraChoice:
    return RoomCameraChoice(
        room_id,
        shot,
        candidate.position,
        candidate.target,
        bounds,
        count,
        feature_target,
        candidate.mode,
        candidate.score,
        candidate.accepted,
        candidate.visible_sample_ratio,
        candidate.rejection_reasons,
        diagnostics,
    )


def inspect_room(run: str | Path, room_id: str) -> dict[str, Any]:
    root = Path(run)
    document = load_document(root)
    room = get_room(root, room_id)
    candidates, geometry, features = camera_candidates(document, room)
    selected_position = candidates[0].position if candidates else None
    feature_analysis: list[dict[str, Any]] = []
    for feature in features:
        item = asdict(feature)
        item["distance_to_room"] = 0.0
        if selected_position is not None:
            visibility = voxel_ray(
                document,
                selected_position,
                feature.target,
                acceptable_hit=feature.coordinate,
            )
            item["line_of_sight_from_selected_camera"] = visibility.visible
            item["first_blocker"] = (
                list(visibility.first_blocker.as_tuple()) if visibility.first_blocker is not None else None
            )
        feature_analysis.append(item)
    return {
        "room_id": str(room.get("id", room.get("volume_id"))),
        "classification": room.get("classification", "unknown_enclosed_space"),
        "classification_confidence": room.get("classification_confidence", 0.0),
        "room_like": room.get("room_like", False),
        "bounds": _bounds_payload(room_bounds(room)),
        "component_cell_count": len(geometry.cells),
        "component_complete": geometry.complete,
        "boundary": {
            "block_count": len(geometry.boundary),
            "floor_count": len(geometry.floor),
            "ceiling_count": len(geometry.ceiling),
            "wall_count": len(geometry.walls),
            "opening_count": len(geometry.openings),
            "protected_count": len(geometry.protected),
            "classifications": {name: len(points) for name, points in geometry.boundary_classes.items()},
        },
        "features": feature_analysis,
        "room_purpose_inference": _room_purpose(features),
        "navigation": {
            "walkable_camera_count": sum(item.reachability == "reachable" for item in candidates),
            "elevated_evidence_count": sum(
                item.reachability == "physically-valid-unreachable" for item in candidates
            ),
            "non_physical_evidence_count": sum(
                item.reachability == "non-physical-evidence" for item in candidates
            ),
        },
        "camera_candidates": [asdict(item) for item in candidates],
        "source_evidence": room.get("evidence", {}),
    }


def diagnose_room(run: str | Path, room_id: str) -> dict[str, Any]:
    report = inspect_room(run, room_id)
    accepted = [item for item in report["camera_candidates"] if item["accepted"]]
    report["diagnosis"] = {
        "physical_camera_available": any(item["mode"].startswith("physical") for item in accepted),
        "accepted_camera_count": len(accepted),
        "recommended_mode": accepted[0]["mode"] if accepted else "visibility-aware-orbit-with-cutaway",
        "warnings": (
            []
            if accepted
            else ["No physical candidate passed collision and line-of-sight checks; use a temporary cutaway."]
        ),
    }
    return report


def render_room(
    run: str | Path,
    room_id: str,
    *,
    shot: str = "auto",
    resource_pack: str | Path | None = None,
    size: tuple[int, int] = (1280, 800),
    fov: float = 70.0,
    near: float = 0.05,
    far: float = 4096.0,
    eye_height: float = 1.62,
    lighting: str = "interior-soft",
    occlusion: str = "physical",
    out: str | Path | None = None,
    name: str | None = None,
    max_attempts: int = 8,
    camera_mode: str = "auto",
    cutaway_strategy: str = "minimal-ray",
    quality_profile: str = "auto",
    min_room_coverage: float | None = None,
    max_obstruction: float | None = None,
) -> dict[str, Any]:
    root = Path(run)
    document = load_document(root)
    room = get_room(root, room_id)
    candidates, geometry, features = camera_candidates(document, room, shot=shot, eye_height=eye_height)
    requested_candidates = {
        "auto": candidates,
        "physical-first-person": [item for item in candidates if item.mode == "physical-first-person"],
        "physical-third-person": [item for item in candidates if item.mode == "physical-elevated"],
        "third-person-orbit": [item for item in candidates if item.mode == "visibility-aware-orbit"],
    }
    if camera_mode not in requested_candidates:
        raise ValueError(f"unknown camera mode: {camera_mode}")
    candidates = requested_candidates[camera_mode] or candidates
    bounds = room_bounds(room)
    crop = IntBoundingBox(
        IntVector3(bounds.min.x - 2, bounds.min.y - 2, bounds.min.z - 2),
        IntVector3(bounds.max.x + 2, bounds.max.y + 2, bounds.max.z + 2),
    )
    output = Path(out) if out else root
    output.mkdir(parents=True, exist_ok=True)
    feature_target = features[0].target if features else None
    camera_diagnostics = {
        "component_cell_count": len(geometry.cells),
        "component_complete": geometry.complete,
        "boundary_block_count": len(geometry.boundary),
        "feature_candidate_count": len(features),
    }
    attempts: list[dict[str, Any]] = []
    rendered: list[tuple[Any, RoomCameraChoice, str, frozenset[IntVector3], Any]] = []
    candidate_plans: list[tuple[CameraCandidate, str | None]] = [
        (candidate, None) for candidate in candidates[: max(1, max_attempts)]
    ]
    orbit = next(
        (item for item in candidates if item.mode == "visibility-aware-orbit"),
        None,
    )
    if orbit is not None and cutaway_strategy == "minimal-ray" and max_attempts >= 3:
        candidate_plans = candidate_plans[: max(1, max_attempts - 2)]
        candidate_plans.extend(((orbit, "wall-off"), (orbit, "roof-off")))
    pack = open_resource_pack(resource_pack)
    try:
        renderer = PerspectiveRenderer(document, resource_pack=pack)
        for index, (candidate, forced_occlusion) in enumerate(candidate_plans):
            choice = _choice(
                str(room.get("id", room.get("volume_id"))),
                shot,
                bounds,
                candidate,
                len(candidates),
                feature_target,
                camera_diagnostics,
            )
            effective_occlusion = occlusion
            if candidate.mode == "visibility-aware-orbit" and occlusion == "physical":
                effective_occlusion = {
                    "minimal-ray": "cutaway",
                    "roof": "roof-off",
                    "wall": "wall-off",
                }.get(cutaway_strategy, cutaway_strategy)
            if forced_occlusion is not None:
                effective_occlusion = forced_occlusion
            hidden = cutaway_mask(document, choice, effective_occlusion, geometry=geometry)
            camera = PerspectiveCameraSpec(
                position=choice.position,
                target=choice.target,
                vertical_fov_degrees=fov,
                near=near,
                far=far,
            )
            stem = name or f"room_{choice.room_id}_{shot}_perspective"
            attempt_name = stem if index == 0 else f"{stem}_attempt_{index + 1}"
            result = renderer.render(
                output,
                camera=camera,
                crop=crop,
                size=size,
                mode="textured",
                lighting_preset=lighting,
                hidden_coordinates=hidden,
                name=attempt_name,
            )
            effective_profile = quality_profile
            if effective_profile == "auto":
                effective_profile = (
                    "third_person_cutaway"
                    if candidate.mode == "visibility-aware-orbit"
                    else "feature_closeup"
                    if shot == "feature"
                    else "room_coverage"
                    if shot == "coverage"
                    else "physical_third_person"
                    if candidate.mode == "physical-elevated"
                    else "physical_first_person"
                )
            quality = evaluate_frame(
                result.semantic_metadata_path,
                geometry,
                features,
                choice,
                document=document,
                profile=effective_profile,
                min_room_coverage=min_room_coverage,
                max_obstruction=max_obstruction,
                diagnostics=result.diagnostics,
            )
            attempt = {
                "attempt": index + 1,
                "camera_mode": candidate.mode,
                "camera": asdict(camera),
                "camera_score": candidate.score,
                "camera_accepted": candidate.accepted,
                "camera_rejection_reasons": list(candidate.rejection_reasons),
                "requested_occlusion": occlusion,
                "effective_occlusion": effective_occlusion,
                "hidden_coordinate_count": len(hidden),
                "quality": quality.as_dict(),
                "png": str(result.png_path),
                "manifest": str(result.manifest_path),
                "snapshot_id": result.snapshot_id,
            }
            attempts.append(attempt)
            rendered.append((result, choice, effective_occlusion, hidden, quality))
            evidence_accepted = quality.accepted and (candidate.accepted or effective_occlusion != "physical")
            attempt["evidence_accepted"] = evidence_accepted
            if evidence_accepted:
                break
    finally:
        if pack:
            pack.close()

    selected_index = next(
        (
            index
            for index, (_, choice, effective, _, quality) in enumerate(rendered)
            if quality.accepted and (choice.accepted or effective != "physical")
        ),
        max(range(len(rendered)), key=lambda index: rendered[index][4].score),
    )
    result, choice, effective_occlusion, hidden, quality = rendered[selected_index]
    manifest = json.loads(result.manifest_path.read_text("utf-8"))
    manifest["interior_intelligence"] = {
        "schema": "mbi.interior-render.v2",
        "room_id": choice.room_id,
        "classification": room.get("classification", "unknown_enclosed_space"),
        "classification_confidence": room.get("classification_confidence", 0.0),
        "room_bounds": _bounds_payload(bounds),
        "component_cell_count": len(geometry.cells),
        "component_complete": geometry.complete,
        "camera_mode": choice.camera_mode,
        "camera_reachability": next(
            item.reachability
            for item in candidates
            if item.position == choice.position and item.mode == choice.camera_mode
        ),
        "camera_score": choice.score,
        "camera_visible_sample_ratio": choice.visible_sample_ratio,
        "requested_occlusion": occlusion,
        "effective_occlusion": effective_occlusion,
        "protected_coordinate_count": len(geometry.protected),
        "hidden_boundary_classification": {
            name: [list(point.as_tuple()) for point in sorted(hidden & coordinates)]
            for name, coordinates in geometry.boundary_classes.items()
            if hidden & coordinates
        },
        "quality": quality.as_dict(),
        "selected_attempt": selected_index + 1,
        "attempt_count": len(attempts),
    }
    atomic_write_json(result.manifest_path, manifest)
    report = {
        "room_id": choice.room_id,
        "shot": shot,
        "projection": "perspective",
        "camera": asdict(
            PerspectiveCameraSpec(
                position=choice.position,
                target=choice.target,
                vertical_fov_degrees=fov,
                near=near,
                far=far,
            )
        ),
        "camera_mode": choice.camera_mode,
        "camera_reachability": next(
            item.reachability
            for item in candidates
            if item.position == choice.position and item.mode == choice.camera_mode
        ),
        "camera_score": choice.score,
        "camera_accepted": choice.accepted,
        "camera_rejection_reasons": list(choice.rejection_reasons),
        "candidate_count": choice.candidate_count,
        "room_bounds": _bounds_payload(bounds),
        "crop_bounds": _bounds_payload(crop),
        "occlusion": occlusion,
        "effective_occlusion": effective_occlusion,
        "cutaway_strategy": cutaway_strategy,
        "hidden_coordinate_count": len(hidden),
        "quality_status": (
            "accepted"
            if quality.accepted and (choice.accepted or effective_occlusion != "physical")
            else "degraded"
        ),
        "quality": quality.as_dict(),
        "selected_attempt": selected_index + 1,
        "attempt_count": len(attempts),
        "attempts": attempts,
        "png": str(result.png_path),
        "manifest": str(result.manifest_path),
        "snapshot_id": result.snapshot_id,
        "diagnostics": result.diagnostics,
    }
    atomic_write_json(output / f"room_{choice.room_id}_{shot}_interior-report.json", report)
    return report


def render_gallery(
    run: str | Path,
    *,
    room_ids: Iterable[str] | None = None,
    shots: Iterable[str] = ("doorway", "corner", "feature"),
    resource_pack: str | Path | None = None,
    size: tuple[int, int] = (1280, 800),
    fov: float = 70.0,
    near: float = 0.05,
    far: float = 4096.0,
    eye_height: float = 1.62,
    lighting: str = "interior-soft",
    occlusion: str = "physical",
    out: str | Path | None = None,
    include_non_rooms: bool = False,
) -> dict[str, Any]:
    root = Path(run)
    destination = Path(out) if out else root / "interior-gallery"
    destination.mkdir(parents=True, exist_ok=True)
    rooms = load_rooms(root)
    selected = {str(value) for value in room_ids} if room_ids else None
    outputs: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for room in rooms:
        room_id = str(room.get("id", room.get("volume_id")))
        if selected is not None and room_id not in selected:
            continue
        if (
            selected is None
            and not include_non_rooms
            and room.get("classification")
            in {
                "decorative_void",
                "vegetation_void",
                "roof_void",
                "wall_void",
                "natural_cavity",
                "terrain_void",
                "fluid_cavity",
            }
        ):
            skipped.append({"room_id": room_id, "classification": room.get("classification")})
            continue
        for shot in shots:
            outputs.append(
                render_room(
                    root,
                    room_id,
                    shot=shot,
                    resource_pack=resource_pack,
                    size=size,
                    fov=fov,
                    near=near,
                    far=far,
                    eye_height=eye_height,
                    lighting=lighting,
                    occlusion=occlusion,
                    out=destination,
                )
            )
    report = {
        "schema": "mbi.interior-gallery.v2",
        "projection": "perspective",
        "room_count": len({item["room_id"] for item in outputs}),
        "render_count": len(outputs),
        "accepted_render_count": sum(item["quality_status"] == "accepted" for item in outputs),
        "degraded_render_count": sum(item["quality_status"] != "accepted" for item in outputs),
        "shots": list(shots),
        "skipped_non_rooms": skipped,
        "outputs": outputs,
    }
    atomic_write_json(destination / "interior-gallery.json", report)
    return report


def render_room_packet(
    run: str | Path,
    room_id: str,
    *,
    shots: Iterable[str] = ("auto", "corner", "feature"),
    out: str | Path | None = None,
    **render_options: Any,
) -> dict[str, Any]:
    root = Path(run)
    destination = Path(out) if out else root / f"room-{room_id}-packet"
    destination.mkdir(parents=True, exist_ok=True)
    inspection = inspect_room(root, room_id)
    document = load_document(root)
    room = get_room(root, room_id)
    bounds = room_bounds(room)
    geometry = room_geometry(document, room)
    common_options = dict(render_options)
    requested_camera_mode = common_options.pop("camera_mode", "auto")
    common_options.pop("occlusion", None)
    cutaway_strategy = common_options.pop("cutaway_strategy", "minimal-ray")
    common_options.pop("quality_profile", None)
    configured_fallback = tuple(
        common_options.pop("fallback", ("physical", "third-person", "cutaway", "slices"))
    )
    slice_fallback = common_options.pop("slice_fallback", "auto")
    min_cumulative_coverage = float(
        common_options.pop("min_cumulative_coverage", 0.0)
    )

    physical = render_room(
        root,
        room_id,
        shot="auto",
        out=destination,
        name="physical_first_person",
        camera_mode="physical-first-person",
        occlusion="physical",
        **common_options,
    )
    cutaway = render_room(
        root,
        room_id,
        shot="coverage",
        out=destination,
        name="third_person_cutaway",
        camera_mode="third-person-orbit",
        occlusion="physical",
        cutaway_strategy=cutaway_strategy,
        quality_profile="third_person_cutaway",
        **common_options,
    )
    renders = [physical, cutaway]
    for shot in shots:
        if shot in {"auto", "coverage"}:
            continue
        renders.append(
            render_room(
                root,
                room_id,
                shot=shot,
                out=destination,
                **common_options,
            )
        )

    def copy_evidence(source: dict[str, Any], stem: str) -> dict[str, str]:
        png = destination / f"{stem}.png"
        manifest = destination / f"{stem}.manifest.json"
        shutil.copyfile(source["png"], png)
        shutil.copyfile(source["manifest"], manifest)
        return {"png": str(png), "manifest": str(manifest)}

    named_views = {
        "physical_first_person": copy_evidence(physical, "physical_first_person"),
        "third_person_cutaway": copy_evidence(cutaway, "third_person_cutaway"),
    }
    crop = IntBoundingBox(
        IntVector3(bounds.min.x - 1, bounds.min.y - 1, bounds.min.z - 1),
        IntVector3(bounds.max.x + 1, bounds.max.y + 1, bounds.max.z + 1),
    )
    features = inspection["features"]
    feature_x = (
        int(features[0]["coordinate"]["x"])
        if features and isinstance(features[0]["coordinate"], dict)
        else int(features[0]["coordinate"][0])
        if features
        else (bounds.min.x + bounds.max.x) // 2
    )
    slice_specs = (
        ("top_plan", "y", bounds.min.y),
        ("central_slice_x", "x", (bounds.min.x + bounds.max.x) // 2),
        ("central_slice_z", "z", (bounds.min.z + bounds.max.z) // 2),
        ("feature_slice", "x", feature_x),
    )
    slice_outputs: list[dict[str, Any]] = []
    should_render_slices = slice_fallback == "always" or (
        slice_fallback == "auto" and "slices" in configured_fallback
    )
    if should_render_slices:
        pack = open_resource_pack(render_options.get("resource_pack"))
        try:
            renderer = SoftwareRenderer(document, resource_pack=pack)
            for stem, axis, coordinate in slice_specs:
                result = renderer.render_slice(
                    destination,
                    axis=axis,
                    minimum=coordinate,
                    crop=crop,
                    pixels_per_block=12,
                    mode="textured",
                    name=stem,
                )
                slice_png = destination / f"{stem}.png"
                slice_manifest = destination / f"{stem}.manifest.json"
                shutil.copyfile(result.png_path, slice_png)
                shutil.copyfile(result.manifest_path, slice_manifest)
                slice_outputs.append(
                    {
                        "name": stem,
                        "axis": axis,
                        "coordinate": coordinate,
                        "crop_bounds": _bounds_payload(crop),
                        "png": str(slice_png),
                        "manifest": str(slice_manifest),
                        "snapshot_id": result.snapshot_id,
                    }
                )
        finally:
            if pack:
                pack.close()

    accepted_views = [
        {
            "kind": item["camera_mode"],
            "shot": item["shot"],
            "quality": item["quality"],
            "png": item["png"],
            "manifest": item["manifest"],
        }
        for item in renders
        if item["quality_status"] == "accepted"
    ]
    failed_views = [
        {
            "kind": item["camera_mode"],
            "shot": item["shot"],
            "quality": item["quality"],
            "attempts": item["attempts"],
        }
        for item in renders
        if item["quality_status"] != "accepted"
    ]
    all_candidates = inspection["camera_candidates"]
    accepted_candidates = [item for item in all_candidates if item["accepted"]]
    rejected_candidates = [item for item in all_candidates if not item["accepted"]]
    quality_metrics = [
        {
            "shot": item["shot"],
            "camera_mode": item["camera_mode"],
            "status": item["quality_status"],
            **item["quality"],
        }
        for item in renders
    ]
    diagnostics = {
        "candidate_count": len(all_candidates),
        "accepted_candidate_count": len(accepted_candidates),
        "rejected_candidate_count": len(rejected_candidates),
        "render_attempt_count": sum(item["attempt_count"] for item in renders),
        "failed_evidence_count": len(failed_views),
        "fallback_path": [
            "physical-first-person",
            "physical-elevated",
            f"third-person-orbit:{cutaway_strategy}",
            "room-bounded-slices",
        ],
        "requested_camera_mode": requested_camera_mode,
        "configured_fallback": list(configured_fallback),
        "unresolved_limitations": (
            [] if accepted_views else ["No perspective view passed the selected exact quality thresholds."]
        ),
    }
    room_boundary = set(geometry.boundary)
    visible_by_render: list[tuple[int, set[IntVector3]]] = []
    for index, rendered in enumerate(renders):
        if rendered["quality_status"] != "accepted":
            continue
        manifest_path = Path(rendered["manifest"])
        manifest = json.loads(manifest_path.read_text("utf-8"))
        metadata_path = (
            manifest_path.parent / manifest["semantic_maps"]["metadata"]
        ).resolve()
        coordinates = load_map(metadata_path, "coordinate").reshape(-1, 3)
        visible = {
            IntVector3(int(row[0]), int(row[1]), int(row[2]))
            for row in coordinates
            if int(row[0]) != -(1 << 31)
        }
        visible_by_render.append((index, visible & room_boundary))
    selected_indices: list[int] = []
    cumulative_visible: set[IntVector3] = set()
    remaining = list(visible_by_render)
    while remaining:
        best_index, best_visible = max(
            remaining,
            key=lambda item: (len(item[1] - cumulative_visible), -item[0]),
        )
        gain = best_visible - cumulative_visible
        if not gain:
            break
        selected_indices.append(best_index)
        cumulative_visible.update(best_visible)
        remaining = [item for item in remaining if item[0] != best_index]
    cumulative_coverage = len(cumulative_visible) / max(1, len(room_boundary))
    coverage_gate = {
        "metric": "visible-room-boundary-coordinate-union",
        "minimum": round(min_cumulative_coverage, 6),
        "achieved": round(cumulative_coverage, 6),
        "passed": cumulative_coverage >= min_cumulative_coverage,
        "visible_coordinate_count": len(cumulative_visible),
        "room_boundary_coordinate_count": len(room_boundary),
        "selected_render_indices": selected_indices,
        "selected_shots": [renders[index]["shot"] for index in selected_indices],
        "solver": "greedy-maximum-marginal-union-v1",
    }
    if not coverage_gate["passed"]:
        diagnostics["unresolved_limitations"].append(
            "Cumulative room coverage "
            f"{cumulative_coverage:.3f} is below the required "
            f"{min_cumulative_coverage:.3f}."
        )
    atomic_write_json(destination / "room_summary.json", inspection)
    atomic_write_json(destination / "camera_candidates.json", accepted_candidates)
    atomic_write_json(destination / "camera_rejections.json", rejected_candidates)
    atomic_write_json(destination / "accepted_views.json", accepted_views)
    atomic_write_json(destination / "quality_metrics.json", quality_metrics)
    atomic_write_json(destination / "diagnostics.json", diagnostics)
    packet = {
        "schema": "mbi.interior-packet.v2",
        "room_id": room_id,
        "source": {
            "build_id": document.build_id,
            "content_hash": document.content_hash,
            "schema_version": document.schema_version,
        },
        "classification": inspection["classification"],
        "classification_confidence": inspection["classification_confidence"],
        "room_purpose_inference": inspection["room_purpose_inference"],
        "features": inspection["features"],
        "navigation": inspection["navigation"],
        "named_views": named_views,
        "render_count": len(renders),
        "accepted_render_count": sum(item["quality_status"] == "accepted" for item in renders),
        "accepted_evidence": accepted_views,
        "failed_evidence": failed_views,
        "fallback_path": diagnostics["fallback_path"],
        "unresolved_limitations": diagnostics["unresolved_limitations"],
        "coverage": coverage_gate,
        "slice_count": len(slice_outputs),
        "slices": slice_outputs,
        "artifacts": {
            name: str(destination / name)
            for name in (
                "room_summary.json",
                "camera_candidates.json",
                "camera_rejections.json",
                "accepted_views.json",
                "quality_metrics.json",
                "diagnostics.json",
            )
        },
    }
    atomic_write_json(destination / "interior_packet.json", packet)
    return packet
