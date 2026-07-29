from __future__ import annotations

from collections import deque
from pathlib import Path
from typing import Any

from mbi.analysis.block_profiles import block_profile
from mbi.canonical import IntBoundingBox, IntVector3

from app.project import load_document
from app.storage import atomic_write_json

from .model import feature_candidates, get_room, room_geometry, voxel_ray

_HORIZONTAL = (
    IntVector3(1, 0, 0),
    IntVector3(-1, 0, 0),
    IntVector3(0, 0, 1),
    IntVector3(0, 0, -1),
)


def _standable_points(document, cells: set[IntVector3]) -> set[IntVector3]:
    palette = document.palette_by_id()
    result = set()
    for point in cells:
        below_id = document.blocks.get(IntVector3(point.x, point.y - 1, point.z))
        head = IntVector3(point.x, point.y + 1, point.z)
        if (
            below_id is not None
            and block_profile(palette[below_id]).supports_player
            and head in cells
        ):
            result.add(point)
    return result


def _graph(points: set[IntVector3]) -> dict[IntVector3, list[IntVector3]]:
    graph = {point: [] for point in points}
    for point in points:
        for offset in _HORIZONTAL:
            for dy in (0, 1, -1, -2, -3):
                candidate = IntVector3(
                    point.x + offset.x,
                    point.y + dy,
                    point.z + offset.z,
                )
                if candidate in points:
                    graph[point].append(candidate)
                    break
    return graph


def _farthest(
    graph: dict[IntVector3, list[IntVector3]],
    start: IntVector3,
) -> tuple[IntVector3, dict[IntVector3, IntVector3 | None]]:
    parents: dict[IntVector3, IntVector3 | None] = {start: None}
    distances = {start: 0}
    queue = deque([start])
    while queue:
        point = queue.popleft()
        for neighbor in graph[point]:
            if neighbor in distances:
                continue
            parents[neighbor] = point
            distances[neighbor] = distances[point] + 1
            queue.append(neighbor)
    return max(distances, key=lambda point: (distances[point], point)), parents


def interior_walkthrough(
    run: str | Path,
    room_id: str,
    *,
    spacing: int = 6,
    output: str | Path | None = None,
    render_frames: bool = False,
    resource_pack: str | Path | None = None,
    size: tuple[int, int] = (640, 400),
    resume: bool = False,
) -> dict[str, Any]:
    root = Path(run)
    document = load_document(root)
    room = get_room(root, room_id)
    geometry = room_geometry(document, room)
    standable = _standable_points(document, set(geometry.cells))
    graph = _graph(standable)
    if not graph:
        report = {
            "schema": "mbi.interior-walkthrough.v1",
            "room_id": room_id,
            "status": "unavailable",
            "reason": "no-standable-navigation-cells",
            "shots": [],
        }
    else:
        start = min(graph)
        first, _ = _farthest(graph, start)
        end, parents = _farthest(graph, first)
        path = []
        cursor: IntVector3 | None = end
        while cursor is not None:
            path.append(cursor)
            cursor = parents[cursor]
        path.reverse()
        indices = list(range(0, len(path), max(1, spacing)))
        if indices[-1] != len(path) - 1:
            indices.append(len(path) - 1)
        features = feature_candidates(document, geometry)
        shots = []
        for shot_index, path_index in enumerate(indices):
            feet = path[path_index]
            next_point = path[min(len(path) - 1, path_index + max(1, spacing))]
            position = (feet.x + 0.5, feet.y + 1.62, feet.z + 0.5)
            target = (
                next_point.x + 0.5,
                next_point.y + 1.35,
                next_point.z + 0.5,
            )
            visible_features = []
            for feature in features:
                ray = voxel_ray(
                    document,
                    position,
                    feature.target,
                    acceptable_hit=feature.coordinate,
                )
                if ray.visible:
                    visible_features.append(feature.state)
            shots.append(
                {
                    "index": shot_index,
                    "path_index": path_index,
                    "feet": feet.as_tuple(),
                    "camera_position": position,
                    "camera_target": target,
                    "visible_feature_count": len(visible_features),
                    "visible_features": visible_features,
                }
            )
        report = {
            "schema": "mbi.interior-walkthrough.v1",
            "room_id": room_id,
            "status": "complete",
            "navigation_node_count": len(graph),
            "path_cell_count": len(path),
            "path_length_blocks": len(path) - 1,
            "shot_spacing": spacing,
            "shots": shots,
            "path": [point.as_tuple() for point in path],
            "method": "room-navigation-diameter-path-v1",
        }
    destination = (
        Path(output)
        if output
        else root / f"room_{room_id}_walkthrough.json"
    )
    if render_frames and report["status"] == "complete":
        from app.assets import open_resource_pack
        from app.render import PerspectiveCameraSpec, PerspectiveRenderer

        raw_bounds = room["bounds"]
        room_bounds = IntBoundingBox(
            IntVector3(**raw_bounds["min"]),
            IntVector3(**raw_bounds["max"]),
        )
        crop = IntBoundingBox(
            IntVector3(
                room_bounds.min.x - 2,
                room_bounds.min.y - 2,
                room_bounds.min.z - 2,
            ),
            IntVector3(
                room_bounds.max.x + 2,
                room_bounds.max.y + 2,
                room_bounds.max.z + 2,
            ),
        )
        frame_root = destination.parent / f"{destination.stem}_frames"
        pack = open_resource_pack(resource_pack)
        try:
            renderer = PerspectiveRenderer(document, resource_pack=pack)
            for shot in report["shots"]:
                frame_name = f"walkthrough_{int(shot['index']):03d}"
                expected = frame_root / "snapshots" / f"{frame_name}.png"
                manifest = (
                    frame_root
                    / "snapshots"
                    / f"{frame_name}.manifest.json"
                )
                if not (resume and expected.is_file() and manifest.is_file()):
                    result = renderer.render(
                        frame_root,
                        camera=PerspectiveCameraSpec(
                            position=tuple(shot["camera_position"]),
                            target=tuple(shot["camera_target"]),
                        ),
                        crop=crop,
                        size=size,
                        mode="textured",
                        lighting_preset="interior-soft",
                        name=frame_name,
                    )
                    expected = result.png_path
                    manifest = result.manifest_path
                shot["png"] = str(expected)
                shot["manifest"] = str(manifest)
        finally:
            if pack:
                pack.close()
        report["rendering"] = {
            "enabled": True,
            "frameCount": len(report["shots"]),
            "frameRoot": str(frame_root),
            "size": list(size),
            "textureExact": pack is not None,
            "resume": resume,
        }
    else:
        report["rendering"] = {
            "enabled": False,
            "frameCount": 0,
        }
    atomic_write_json(destination, report)
    return report


def room_sightlines(
    run: str | Path,
    room_id: str,
    *,
    output: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(run)
    document = load_document(root)
    room = get_room(root, room_id)
    geometry = room_geometry(document, room)
    features = feature_candidates(document, geometry)
    standable = _standable_points(document, set(geometry.cells))
    entries = sorted(
        point
        for point in standable
        if any(
            abs(point.x - opening.x)
            + abs(point.y - opening.y)
            + abs(point.z - opening.z)
            <= 2
            for opening in geometry.openings
        )
    )
    if not entries and standable:
        entries = [min(standable)]
    rows = []
    for entry in entries[:32]:
        origin = (entry.x + 0.5, entry.y + 1.62, entry.z + 0.5)
        visible = []
        blocked = []
        for feature in features:
            ray = voxel_ray(
                document,
                origin,
                feature.target,
                acceptable_hit=feature.coordinate,
            )
            item = {
                "coordinate": feature.coordinate.as_tuple(),
                "state": feature.state,
            }
            if ray.visible:
                visible.append(item)
            else:
                blocked.append(
                    {
                        **item,
                        "first_blocker": (
                            ray.first_blocker.as_tuple()
                            if ray.first_blocker is not None
                            else None
                        ),
                    }
                )
        rows.append(
            {
                "entry": entry.as_tuple(),
                "visible_feature_count": len(visible),
                "feature_visibility_ratio": round(
                    len(visible) / max(1, len(features)), 6
                ),
                "visible": visible,
                "blocked": blocked,
            }
        )
    report = {
        "schema": "mbi.room-sightlines.v1",
        "room_id": room_id,
        "entry_count": len(rows),
        "feature_count": len(features),
        "mean_entry_feature_visibility": round(
            sum(item["feature_visibility_ratio"] for item in rows)
            / max(1, len(rows)),
            6,
        ),
        "entries": rows,
        "method": "entry-to-feature-voxel-ray-v1",
    }
    destination = (
        Path(output) if output else root / f"room_{room_id}_sightlines.json"
    )
    atomic_write_json(destination, report)
    return report
