from __future__ import annotations

import heapq
import json
import math
from pathlib import Path
from typing import Any

from mbi.analysis import analyze_document
from mbi.analysis.structures import structure_inventory_payload
from mbi.canonical import IntBoundingBox, IntVector3
from mbi.scoping import scoped_document
from PIL import Image, ImageDraw, ImageFont

from app.jobs import JobRecord, JobState
from app.project import initialize_layout, load_document, save_document, write_diagnostics
from app.storage import atomic_write_json
from app.workflows import export_run

_STRUCTURE_ANALYSIS_CHECKPOINT_VERSION = 7


def _manifest_path(run: str | Path) -> Path:
    return Path(run) / "structures.json"


def _existing_names(run: str | Path) -> dict[str, str]:
    path = _manifest_path(run)
    if not path.is_file():
        return {}
    payload = json.loads(path.read_text("utf-8"))
    return {
        str(item["structure_id"]): str(item["name"])
        for item in payload.get("structures", [])
        if item.get("name")
    }


def inventory_structures(
    run: str | Path,
    *,
    separation: int = 2,
    minimum_blocks: int = 24,
    window_edge: int = 64,
    classification_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    root = Path(run)
    document = load_document(root)
    job = JobRecord.create(
        "structure-inventory",
        {"build": document.content_hash},
        {
            "separation": separation,
            "minimum_blocks": minimum_blocks,
            "window_edge": window_edge,
            "classification_config": classification_config or {},
        },
    )
    job.state = JobState.RUNNING
    job.stage = "streaming-classification"
    job.progress = 0.0
    job.persist(root)
    payload = structure_inventory_payload(
        document,
        separation=separation,
        minimum_blocks=minimum_blocks,
        names=_existing_names(root),
        window_edge=window_edge,
        classification_config=classification_config,
    )
    analysis_path = root / "analysis.json"
    if analysis_path.is_file():
        existing_analysis = json.loads(analysis_path.read_text("utf-8"))
        room_rows = (
            existing_analysis.get("results", {})
            .get("rooms", {})
            .get("rooms", [])
        )
        for structure in payload["structures"]:
            bounds = IntBoundingBox(
                IntVector3(**structure["bounds"]["min"]),
                IntVector3(**structure["bounds"]["max"]),
            )
            structure["room_count"] = sum(
                bounds.contains(
                    IntVector3(**room["seed"])
                )
                for room in room_rows
                if isinstance(room.get("seed"), dict)
            )
            structure["room_count_source"] = (
                "existing-whole-document-analysis-seed-membership"
            )
    atomic_write_json(_manifest_path(root), payload)
    job.state = JobState.SUCCEEDED
    job.stage = "complete"
    job.progress = 1.0
    job.result_refs = [str(_manifest_path(root))]
    job.persist(root)
    return payload


def load_structure_inventory(run: str | Path) -> dict[str, Any]:
    path = _manifest_path(run)
    document = load_document(run)
    if not path.is_file():
        return inventory_structures(run)
    payload = json.loads(path.read_text("utf-8"))
    if payload.get("content_hash") != document.content_hash:
        return inventory_structures(run)
    return payload


def _find_structure(run: str | Path, identifier: str) -> dict[str, Any]:
    inventory = load_structure_inventory(run)
    matches = [
        item
        for item in inventory["structures"]
        if item["structure_id"] == identifier or item.get("name") == identifier
    ]
    if not matches:
        raise ValueError(f"structure not found: {identifier}")
    if len(matches) > 1:
        raise ValueError(f"structure name is ambiguous: {identifier}")
    return matches[0]


def resolve_structure_bounds(run: str | Path, identifier: str) -> IntBoundingBox:
    item = _find_structure(run, identifier)
    bounds = item["bounds"]
    return IntBoundingBox(
        IntVector3(**bounds["min"]),
        IntVector3(**bounds["max"]),
    )


def name_structure(run: str | Path, identifier: str, name: str) -> dict[str, Any]:
    root = Path(run)
    payload = load_structure_inventory(root)
    if any(
        item.get("name") == name and item["structure_id"] != identifier
        for item in payload["structures"]
    ):
        raise ValueError(f"structure name already exists: {name}")
    target = _find_structure(root, identifier)
    for item in payload["structures"]:
        if item["structure_id"] == target["structure_id"]:
            item["name"] = name
    atomic_write_json(_manifest_path(root), payload)
    return {
        "structure_id": target["structure_id"],
        "name": name,
        "registry": str(_manifest_path(root)),
    }


def extract_structure(
    run: str | Path,
    identifier: str,
    output: str | Path,
    *,
    format_name: str = "schem",
) -> dict[str, Any]:
    root = Path(output)
    structure = _find_structure(run, identifier)
    document = load_document(
        run,
        bounds=resolve_structure_bounds(run, identifier),
    )
    document.metadata = {
        **document.metadata,
        "structure": {
            "id": structure["structure_id"],
            "name": structure.get("name"),
        },
    }
    initialize_layout(root)
    save_document(root, document)
    write_diagnostics(root, document)
    export = export_run(root, format_name=format_name, verify=True)
    return {
        "structure": structure,
        "run": str(root),
        "content_hash": document.content_hash,
        "export": export,
    }


def analyze_all_structures(
    run: str | Path,
    *,
    resume: bool = False,
    lighting_max_cells: int | None = 10_000_000,
) -> dict[str, Any]:
    root = Path(run)
    inventory = load_structure_inventory(root)
    document = load_document(root)
    checkpoint_root = root / "analysis_artifacts" / "structures"
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    job = JobRecord.create(
        "map-structure-analysis",
        {"build": document.content_hash},
        {
            "structure_count": len(inventory["structures"]),
            "lighting_max_cells": lighting_max_cells,
            "seal_structure_envelope": True,
            "checkpoint_version": _STRUCTURE_ANALYSIS_CHECKPOINT_VERSION,
        },
    )
    job.state = JobState.RUNNING
    job.stage = "per-structure-analysis"
    job.progress = 0.0
    job.persist(root)
    reports = []
    for index, structure in enumerate(inventory["structures"], start=1):
        path = checkpoint_root / f"{structure['structure_id']}.json"
        checkpoint = {
            "version": _STRUCTURE_ANALYSIS_CHECKPOINT_VERSION,
            "structure_id": structure["structure_id"],
            "bounds": structure["bounds"],
            "lighting_max_cells": lighting_max_cells,
        }
        if resume and path.is_file():
            existing = json.loads(path.read_text("utf-8"))
            if (
                existing.get("parent_content_hash") == document.content_hash
                and existing.get("checkpoint") == checkpoint
            ):
                reports.append(existing)
                job.progress = index / max(1, len(inventory["structures"]))
                job.stage = f"resumed-{structure['structure_id']}"
                job.persist(root)
                continue
        bounds = resolve_structure_bounds(root, structure["structure_id"])
        scoped = scoped_document(document, bounds)
        analysis = analyze_document(
            scoped,
            lighting_max_cells=lighting_max_cells,
            seal_structure_envelope=True,
        )
        report = {
            "schema": "mbi.structure-analysis.v1",
            "parent_content_hash": document.content_hash,
            "checkpoint": checkpoint,
            "structure": structure,
            "progress": {"index": index, "total": len(inventory["structures"])},
            "analysis": analysis,
        }
        room_rows = analysis.get("rooms", {}).get("rooms", [])
        light_by_room = {
            str(item["roomId"]): item
            for item in analysis.get("lighting", {}).get("rooms", [])
        }
        reachability_by_room = {
            str(item["roomId"]): item
            for item in analysis.get("navigation", {}).get(
                "roomReachability",
                [],
            )
        }
        hollow_count = sum(
            bool(item.get("furnishing", {}).get("is_hollow")) for item in room_rows
        )
        lit_count = sum(
            float(light_by_room.get(str(item.get("volume_id")), {}).get("darkCellRatio", 1.0))
            < 0.5
            for item in room_rows
        )
        report["room_program"] = [
            {
                "room_id": item.get("volume_id"),
                "name": (
                    f"{structure.get('name') or structure['structure_id']}_"
                    f"{item.get('classification', 'room')}_{room_index + 1}"
                ),
                "type": item.get("classification", "unknown"),
                "furnishing": item.get("furnishing", {}),
                "lighting": light_by_room.get(str(item.get("volume_id"))),
                "reachability": reachability_by_room.get(
                    str(item.get("volume_id"))
                ),
            }
            for room_index, item in enumerate(room_rows)
        ]
        reachable_count = sum(
            bool(
                reachability_by_room.get(
                    str(item.get("volume_id")),
                    {},
                ).get("exteriorConnected")
            )
            for item in room_rows
        )
        report["interior_completeness"] = {
            "room_count": len(room_rows),
            "furnished_room_count": len(room_rows) - hollow_count,
            "hollow_room_count": hollow_count,
            "lit_room_count": lit_count,
            "reachable_room_count": reachable_count,
            "sealed_room_count": len(room_rows) - reachable_count,
            "score": round(
                (
                    (len(room_rows) - hollow_count)
                    / max(1, len(room_rows))
                    * 0.45
                    + lit_count
                    / max(1, len(room_rows))
                    * 0.3
                    + reachable_count
                    / max(1, len(room_rows))
                    * 0.25
                )
                * 100.0,
                3,
            ),
        }
        structure["room_count"] = len(room_rows)
        structure["room_count_source"] = "scoped-structure-analysis"
        atomic_write_json(path, report)
        reports.append(report)
        job.progress = index / max(1, len(inventory["structures"]))
        job.stage = f"completed-{structure['structure_id']}"
        job.persist(root)
    aggregate = {
        "schema": "mbi.map-structure-report.v1",
        "content_hash": document.content_hash,
        "structure_count": len(reports),
        "checkpointed": True,
        "checkpoint_version": _STRUCTURE_ANALYSIS_CHECKPOINT_VERSION,
        "structures": reports,
        "comparison": {
            "weakest_foundation": sorted(
                (
                    {
                        "structure_id": item["structure"]["structure_id"],
                        "foundation_contact_ratio": item["structure"][
                            "foundation_contact_ratio"
                        ],
                    }
                    for item in reports
                ),
                key=lambda item: item["foundation_contact_ratio"],
            )[:10],
            "style_classes": {
                item["structure"]["structure_id"]: item["structure"]["style_class"]
                for item in reports
            },
            "interior_completeness": {
                item["structure"]["structure_id"]: item["interior_completeness"]
                for item in reports
            },
        },
    }
    atomic_write_json(_manifest_path(root), inventory)
    atomic_write_json(root / "map_structure_report.json", aggregate)
    job.state = JobState.SUCCEEDED
    job.stage = "complete"
    job.progress = 1.0
    job.result_refs = [str(root / "map_structure_report.json")]
    job.persist(root)
    return aggregate


def compare_structures(run: str | Path, first: str, second: str) -> dict[str, Any]:
    left = _find_structure(run, first)
    right = _find_structure(run, second)
    left_palette = set(left["palette_summary"])
    right_palette = set(right["palette_summary"])
    union = left_palette | right_palette
    return {
        "schema": "mbi.structure-compare.v1",
        "left": left,
        "right": right,
        "block_count_delta": right["block_count"] - left["block_count"],
        "bounds_dimension_delta": {
            axis: right["bounds"]["max"][axis]
            - right["bounds"]["min"][axis]
            - left["bounds"]["max"][axis]
            + left["bounds"]["min"][axis]
            for axis in ("x", "y", "z")
        },
        "palette_jaccard": round(
            len(left_palette & right_palette) / max(1, len(union)), 6
        ),
        "style_match": left["style_class"] == right["style_class"],
    }


def render_site_plan(
    run: str | Path,
    *,
    output: str | Path | None = None,
    pixels_per_block: int = 3,
) -> dict[str, Any]:
    root = Path(run)
    destination = Path(output) if output else root / "site_plan.png"
    inventory = load_structure_inventory(root)
    document = load_document(root)
    width = document.bounds.dimensions.x * pixels_per_block
    height = document.bounds.dimensions.z * pixels_per_block
    image = Image.new("RGBA", (width, height), (18, 24, 22, 255))
    draw = ImageDraw.Draw(image)
    palette = document.palette_by_id()
    colors = {
        "terrain": (83, 112, 68, 255),
        "built": (178, 164, 137, 255),
        "vegetation": (55, 139, 64, 255),
        "prop": (213, 142, 57, 255),
    }
    from mbi.analysis.structures import classify_block_name

    tops: dict[tuple[int, int], tuple[int, str]] = {}
    for point, palette_id in document.blocks.items():
        key = (point.x, point.z)
        if key not in tops or point.y > tops[key][0]:
            tops[key] = (point.y, classify_block_name(palette[palette_id].block_name))
    for (x, z), (_, category) in tops.items():
        px = (x - document.bounds.min.x) * pixels_per_block
        py = (z - document.bounds.min.z) * pixels_per_block
        draw.rectangle(
            (px, py, px + pixels_per_block - 1, py + pixels_per_block - 1),
            fill=colors[category],
        )
    font = ImageFont.load_default()
    for index, structure in enumerate(inventory["structures"], start=1):
        bounds = structure["bounds"]
        x0 = (bounds["min"]["x"] - document.bounds.min.x) * pixels_per_block
        z0 = (bounds["min"]["z"] - document.bounds.min.z) * pixels_per_block
        x1 = (bounds["max"]["x"] - document.bounds.min.x + 1) * pixels_per_block - 1
        z1 = (bounds["max"]["z"] - document.bounds.min.z + 1) * pixels_per_block - 1
        draw.rectangle((x0, z0, x1, z1), outline=(255, 214, 64, 255), width=2)
        label = structure.get("name") or f"S{index}"
        draw.text((x0 + 3, z0 + 3), label, fill=(255, 255, 255, 255), font=font)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "PNG", compress_level=9)
    manifest = {
        "schema": "mbi.labelled-site-plan.v1",
        "png": str(destination),
        "content_hash": document.content_hash,
        "resolution": [width, height],
        "pixels_per_block": pixels_per_block,
        "origin": document.bounds.min.as_tuple(),
        "structures": inventory["structures"],
        "legend": colors,
    }
    atomic_write_json(destination.with_suffix(".manifest.json"), manifest)
    return manifest


def _column_top(document: Any, x: int, z: int) -> int | None:
    values = [
        point.y
        for point in document.blocks
        if point.x == x and point.z == z
    ]
    return max(values) if values else None


def _sample_sightline(
    document: Any,
    start: tuple[float, float, float],
    target: tuple[float, float, float],
    target_bounds: IntBoundingBox,
) -> dict[str, Any]:
    distance = math.dist(start, target)
    sample_count = max(2, math.ceil(distance * 4.0))
    blockers: list[IntVector3] = []
    blocked_samples = 0
    previous: IntVector3 | None = None
    for index in range(1, sample_count):
        ratio = index / sample_count
        point = IntVector3(
            math.floor(start[0] + (target[0] - start[0]) * ratio),
            math.floor(start[1] + (target[1] - start[1]) * ratio),
            math.floor(start[2] + (target[2] - start[2]) * ratio),
        )
        if target_bounds.contains(point):
            break
        if point in document.blocks:
            blocked_samples += 1
            if point != previous:
                blockers.append(point)
            previous = point
    unique_blockers = sorted(set(blockers))
    return {
        "visible": not unique_blockers,
        "sampleCount": sample_count,
        "blockedSampleCount": blocked_samples,
        "occlusionRatio": round(
            blocked_samples / max(1, sample_count - 1),
            6,
        ),
        "blockerCount": len(unique_blockers),
        "blockers": [
            list(point.as_tuple())
            for point in unique_blockers[:64]
        ],
        "blockerListCapped": len(unique_blockers) > 64,
    }


def _structure_approaches(
    document: Any,
    structure: dict[str, Any],
) -> dict[str, Any]:
    raw = structure["bounds"]
    bounds = IntBoundingBox(
        IntVector3(**raw["min"]),
        IntVector3(**raw["max"]),
    )
    center_x = (bounds.min.x + bounds.max.x + 1) / 2.0
    center_z = (bounds.min.z + bounds.max.z + 1) / 2.0
    candidates = (
        ("north", center_x, bounds.min.z - 24.0, center_x, bounds.min.z),
        ("south", center_x, bounds.max.z + 25.0, center_x, bounds.max.z + 1.0),
        ("west", bounds.min.x - 24.0, center_z, bounds.min.x, center_z),
        ("east", bounds.max.x + 25.0, center_z, bounds.max.x + 1.0, center_z),
    )
    targets = []
    for direction, camera_x, camera_z, target_x, target_z in candidates:
        column_y = _column_top(
            document,
            math.floor(camera_x),
            math.floor(camera_z),
        )
        camera_y = (
            float(column_y) + 1.62
            if column_y is not None
            else float(bounds.min.y) + 2.0
        )
        target_y = min(
            float(bounds.max.y) + 0.5,
            max(
                float(bounds.min.y) + 2.5,
                camera_y,
            ),
        )
        camera = (camera_x, camera_y, camera_z)
        target = (target_x, target_y, target_z)
        targets.append(
            {
                "direction": direction,
                "camera": list(camera),
                "target": list(target),
                "sightline": _sample_sightline(
                    document,
                    camera,
                    target,
                    bounds,
                ),
            }
        )
    return {
        "structure_id": structure["structure_id"],
        "targets": targets,
        "visibleApproachCount": sum(
            item["sightline"]["visible"] for item in targets
        ),
        "meanOcclusionRatio": round(
            sum(item["sightline"]["occlusionRatio"] for item in targets)
            / len(targets),
            6,
        ),
        "method": "cardinal-player-eye-voxel-ray-v1",
    }


def _terrain_surface(document: Any) -> dict[tuple[int, int], int]:
    palette = document.palette_by_id()
    from mbi.analysis.structures import classify_block_name

    candidates: dict[tuple[int, int], int] = {}
    for point, palette_id in document.blocks.items():
        if classify_block_name(palette[palette_id].block_name) != "terrain":
            continue
        column = (point.x, point.z)
        candidates[column] = max(
            point.y,
            candidates.get(column, point.y),
        )
    surface: dict[tuple[int, int], int] = {}
    def passable(point: IntVector3) -> bool:
        palette_id = document.blocks.get(point)
        if palette_id is None:
            return True
        block_name = palette[palette_id].block_name
        return any(
            token in block_name
            for token in (
                "carpet",
                "fern",
                "flower",
                "short_grass",
                "snow",
                "vine",
            )
        )

    for column, y in candidates.items():
        x, z = column
        if (
            passable(IntVector3(x, y + 1, z))
            and passable(IntVector3(x, y + 2, z))
        ):
            surface[column] = y
    return surface


def _nearest_surface(
    surface: dict[tuple[int, int], int],
    target: tuple[float, float],
    *,
    radius: int = 12,
) -> tuple[int, int] | None:
    tx, tz = target
    candidates = [
        (math.dist((x, z), (tx, tz)), (x, z))
        for x, z in surface
        if abs(x - tx) <= radius and abs(z - tz) <= radius
    ]
    return min(candidates, default=(0.0, None))[1]


def _surface_route(
    surface: dict[tuple[int, int], int],
    start: tuple[int, int],
    goal: tuple[int, int],
) -> dict[str, Any]:
    frontier: list[tuple[float, float, tuple[int, int]]] = [
        (math.dist(start, goal), 0.0, start)
    ]
    costs = {start: 0.0}
    previous: dict[tuple[int, int], tuple[int, int]] = {}
    visited = 0
    while frontier:
        _, cost, current = heapq.heappop(frontier)
        if cost != costs.get(current):
            continue
        visited += 1
        if current == goal:
            break
        current_y = surface[current]
        for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            neighbor = (current[0] + dx, current[1] + dz)
            if neighbor not in surface:
                continue
            step = abs(surface[neighbor] - current_y)
            if step > 1:
                continue
            candidate = cost + 1.0 + step * 0.5
            if candidate < costs.get(neighbor, math.inf):
                costs[neighbor] = candidate
                previous[neighbor] = current
                priority = candidate + math.dist(neighbor, goal)
                heapq.heappush(
                    frontier,
                    (priority, candidate, neighbor),
                )
    if goal not in costs:
        return {
            "reachable": False,
            "visitedNodeCount": visited,
            "path": [],
            "pathLengthBlocks": None,
        }
    path = [goal]
    while path[-1] != start:
        path.append(previous[path[-1]])
    path.reverse()
    return {
        "reachable": True,
        "visitedNodeCount": visited,
        "path": [
            [x, surface[(x, z)] + 1, z]
            for x, z in path
        ],
        "pathLengthBlocks": len(path) - 1,
        "elevationChange": surface[goal] - surface[start],
        "travelCost": round(costs[goal], 3),
    }


def map_composition_report(run: str | Path) -> dict[str, Any]:
    root = Path(run)
    inventory = load_structure_inventory(root)
    structures = inventory["structures"]
    centers = {
        item["structure_id"]: (
            (item["bounds"]["min"]["x"] + item["bounds"]["max"]["x"]) / 2.0,
            (item["bounds"]["min"]["y"] + item["bounds"]["max"]["y"]) / 2.0,
            (item["bounds"]["min"]["z"] + item["bounds"]["max"]["z"]) / 2.0,
        )
        for item in structures
    }
    unvisited = set(centers)
    path_edges = []
    if unvisited:
        visited = {min(unvisited)}
        unvisited -= visited
        while unvisited:
            distance, left, right = min(
                (
                    (
                        math.dist(
                            (centers[source][0], centers[source][2]),
                            (centers[target][0], centers[target][2]),
                        ),
                        source,
                        target,
                    )
                    for source in visited
                    for target in unvisited
                ),
                default=(0.0, "", ""),
            )
            path_edges.append(
                {
                    "from": left,
                    "to": right,
                    "distance": round(distance, 3),
                    "status": "candidate-inter-structure-route",
                }
            )
            visited.add(right)
            unvisited.remove(right)
    document = load_document(root)
    surface = _terrain_surface(document)
    for edge in path_edges:
        left_center = centers[edge["from"]]
        right_center = centers[edge["to"]]
        start = _nearest_surface(
            surface,
            (left_center[0], left_center[2]),
        )
        goal = _nearest_surface(
            surface,
            (right_center[0], right_center[2]),
        )
        if start is None or goal is None:
            edge["navigation"] = {
                "reachable": False,
                "reason": "NO_NEARBY_WALKABLE_TERRAIN_SURFACE",
                "path": [],
            }
        else:
            edge["navigation"] = _surface_route(surface, start, goal)
    style_pairs = []
    for left_index, left in enumerate(structures):
        for right in structures[left_index + 1 :]:
            left_palette = set(left["palette_summary"])
            right_palette = set(right["palette_summary"])
            union = left_palette | right_palette
            style_pairs.append(
                {
                    "left": left["structure_id"],
                    "right": right["structure_id"],
                    "palette_jaccard": round(
                        len(left_palette & right_palette) / max(1, len(union)), 6
                    ),
                    "style_class_match": left["style_class"] == right["style_class"],
                    "roof_pitch_delta_degrees": (
                        round(
                            abs(
                                float(left["roof_pitch_estimate_degrees"])
                                - float(right["roof_pitch_estimate_degrees"])
                            ),
                            3,
                        )
                        if left.get("roof_pitch_estimate_degrees") is not None
                        and right.get("roof_pitch_estimate_degrees") is not None
                        else None
                    ),
                    "trim_block_ratio_delta": round(
                        abs(
                            float(left.get("trim_block_ratio", 0.0))
                            - float(right.get("trim_block_ratio", 0.0))
                        ),
                        6,
                    ),
                    "proportion_deltas": {
                        key: round(
                            abs(
                                float(
                                    left.get("proportions", {}).get(key, 0.0)
                                )
                                - float(
                                    right.get("proportions", {}).get(key, 0.0)
                                )
                            ),
                            6,
                        )
                        for key in (
                            "width_to_height",
                            "length_to_height",
                            "footprint_aspect_ratio",
                        )
                    },
                }
            )
    report = {
        "schema": "mbi.map-composition.v1",
        "content_hash": inventory["content_hash"],
        "structure_count": len(structures),
        "terrain_integration": [
            {
                "structure_id": item["structure_id"],
                "name": item.get("name"),
                "foundation_contact_ratio": item["foundation_contact_ratio"],
                "buried_block_ratio": item["buried_block_ratio"],
                "floating_bottom_column_count": item[
                    "floating_bottom_column_count"
                ],
            }
            for item in structures
        ],
        "settlement_navigation": {
            "method": (
                "center-distance-minimum-spanning-network-plus-"
                "terrain-surface-a-star-v1"
            ),
            "route_count": len(path_edges),
            "candidate_routes": path_edges,
            "walkableSurfaceNodeCount": len(surface),
            "reachableRouteCount": sum(
                item.get("navigation", {}).get("reachable", False)
                for item in path_edges
            ),
        },
        "cross_structure_style_consistency": {
            "pairs": style_pairs,
            "mean_palette_jaccard": round(
                sum(item["palette_jaccard"] for item in style_pairs)
                / max(1, len(style_pairs)),
                6,
            ),
        },
        "approach_sightlines": [
            _structure_approaches(document, item)
            for item in structures
        ],
    }
    atomic_write_json(root / "map_composition_report.json", report)
    return report


def render_structure_lod(
    run: str | Path,
    *,
    output: str | Path | None = None,
    resource_pack: str | Path | None = None,
    accuracy: str = "fast",
    resume: bool = False,
    size: tuple[int, int] = (640, 480),
) -> dict[str, Any]:
    from app.assets import open_resource_pack
    from app.render import CameraSpec, SoftwareRenderer

    root = Path(run)
    destination = Path(output) if output else root / "structure_lod"
    destination.mkdir(parents=True, exist_ok=True)
    inventory = load_structure_inventory(root)
    document = load_document(root)
    overview = render_site_plan(
        root,
        output=destination / "overview.png",
        pixels_per_block=2,
    )
    pack = open_resource_pack(resource_pack) if accuracy == "exact" else None
    details = []
    try:
        renderer = SoftwareRenderer(document, resource_pack=pack)
        for structure in inventory["structures"]:
            name = structure.get("name") or structure["structure_id"]
            expected = destination / "snapshots" / f"{name}.png"
            if not (resume and expected.is_file()):
                bounds = resolve_structure_bounds(root, structure["structure_id"])
                result = renderer.render(
                    destination,
                    camera=CameraSpec.preset("isometric_ne"),
                    crop=bounds,
                    size=size,
                    mode="textured" if pack else "flat",
                    name=name,
                )
                manifest_path = result.manifest_path
            else:
                manifest_path = destination / "snapshots" / f"{name}.manifest.json"
            details.append(
                {
                    "structure_id": structure["structure_id"],
                    "name": structure.get("name"),
                    "png": str(expected),
                    "manifest": str(manifest_path),
                }
            )
    finally:
        if pack:
            pack.close()
    report = {
        "schema": "mbi.structure-lod-scene.v1",
        "content_hash": document.content_hash,
        "overview": overview,
        "details": details,
        "accuracy": {
            "profile": accuracy,
            "texture_exact": accuracy == "exact",
            "contract": (
                "resource-pack exact detail renders"
                if accuracy == "exact"
                else "flat semantic preview; not texture-exact"
            ),
        },
        "resume": resume,
    }
    atomic_write_json(destination / "lod_manifest.json", report)
    return report


def batch_structure_interiors(
    run: str | Path,
    *,
    output: str | Path | None = None,
    resource_pack: str | Path | None = None,
    resume: bool = False,
    max_rooms_per_structure: int = 8,
    min_cumulative_coverage: float = 0.0,
    size: tuple[int, int] = (640, 400),
) -> dict[str, Any]:
    from app.interior import render_room_packet
    from app.workflows import analyze_run

    root = Path(run)
    destination = Path(output) if output else root / "structure_interior_packets"
    destination.mkdir(parents=True, exist_ok=True)
    document = load_document(root)
    inventory = load_structure_inventory(root)
    structures = []
    for structure in inventory["structures"]:
        structure_root = destination / structure["structure_id"] / "run"
        canonical = structure_root / "canonical.json"
        if not (resume and canonical.is_file()):
            scoped = scoped_document(
                document,
                resolve_structure_bounds(root, structure["structure_id"]),
            )
            initialize_layout(structure_root)
            save_document(structure_root, scoped)
            write_diagnostics(structure_root, scoped)
            analyze_run(structure_root)
        analysis = json.loads((structure_root / "analysis.json").read_text("utf-8"))
        rooms = [
            item
            for item in analysis["results"]["rooms"]["rooms"]
            if item.get("room_like")
        ][:max_rooms_per_structure]
        packets = []
        for room_index, room in enumerate(rooms):
            room_id = str(room["volume_id"])
            packet_path = (
                destination
                / structure["structure_id"]
                / f"room-{room_id}"
                / "interior_packet.json"
            )
            if resume and packet_path.is_file():
                packets.append(json.loads(packet_path.read_text("utf-8")))
                continue
            try:
                packet = render_room_packet(
                    structure_root,
                    room_id,
                    out=packet_path.parent,
                    resource_pack=resource_pack,
                    size=size,
                    min_cumulative_coverage=min_cumulative_coverage,
                )
                packet["program_name"] = (
                    f"{structure.get('name') or structure['structure_id']}_"
                    f"{room.get('classification', 'room')}_{room_index + 1}"
                )
                atomic_write_json(packet_path, packet)
                packets.append(packet)
            except Exception as exc:
                packets.append(
                    {
                        "room_id": room_id,
                        "status": "rejected",
                        "error": str(exc),
                    }
                )
        accepted = sum(
            item.get("coverage", {}).get("passed", False) for item in packets
        )
        structures.append(
            {
                "structure": structure,
                "room_count": len(rooms),
                "packet_count": len(packets),
                "accepted_packet_count": accepted,
                "quality_gate_passed": accepted == len(rooms),
                "packets": packets,
            }
        )
    report = {
        "schema": "mbi.multi-structure-interior-sweep.v1",
        "content_hash": document.content_hash,
        "structure_count": len(structures),
        "quality_gate_passed": all(
            item["quality_gate_passed"] for item in structures
        ),
        "resume": resume,
        "structures": structures,
    }
    atomic_write_json(destination / "structure_interior_packets.json", report)
    return report
