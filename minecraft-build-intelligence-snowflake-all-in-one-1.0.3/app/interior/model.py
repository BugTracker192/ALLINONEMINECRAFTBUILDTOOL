from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from mbi.canonical import BuildDocument, IntBoundingBox, IntVector3

from app.errors import AppError


@dataclass(frozen=True, slots=True)
class RoomCameraChoice:
    room_id: str
    shot: str
    position: tuple[float, float, float]
    target: tuple[float, float, float]
    bounds: IntBoundingBox
    candidate_count: int
    feature_target: tuple[float, float, float] | None = None


def _point_from_mapping(value: Any) -> IntVector3:
    if isinstance(value, dict):
        return IntVector3(int(value["x"]), int(value["y"]), int(value["z"]))
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return IntVector3(*(int(item) for item in value))
    raise AppError("ROOM_BOUNDS_INVALID", "Room bounds contain an invalid coordinate.", {"value": value}, 20)


def room_bounds(room: dict[str, Any]) -> IntBoundingBox:
    raw = room.get("bounds")
    if not isinstance(raw, dict):
        raise AppError("ROOM_BOUNDS_INVALID", "Room result has no bounds object.", {"room": room.get("id", room.get("volume_id"))}, 20)
    return IntBoundingBox(_point_from_mapping(raw["min"]), _point_from_mapping(raw["max"]))


def load_rooms(run: str | Path) -> list[dict[str, Any]]:
    root = Path(run)
    analysis_path = root / "analysis.json"
    if not analysis_path.is_file():
        from app.workflows import analyze_run

        analyze_run(root)
    payload = json.loads(analysis_path.read_text("utf-8"))
    results = payload.get("results", payload)
    room_result = results.get("rooms", {})
    rooms = room_result.get("rooms", room_result.get("interiorVolumes", []))
    normalized: list[dict[str, Any]] = []
    for index, room in enumerate(rooms):
        item = dict(room)
        item.setdefault("id", str(item.get("volume_id", index)))
        normalized.append(item)
    return normalized


def get_room(run: str | Path, room_id: str) -> dict[str, Any]:
    rooms = load_rooms(run)
    room = next((item for item in rooms if str(item.get("id", item.get("volume_id"))) == str(room_id)), None)
    if room is None:
        raise AppError("ROOM_NOT_FOUND", "Room was not found.", {"id": room_id, "available": [str(item.get("id")) for item in rooms]}, 20)
    return room


def _is_air(document: BuildDocument, point: IntVector3) -> bool:
    palette_id = document.blocks.get(point)
    return palette_id is None or document.palette_by_id()[palette_id].is_air_like


def walkable_eye_positions(document: BuildDocument, bounds: IntBoundingBox, *, eye_height: float = 1.62) -> list[tuple[float, float, float]]:
    result: list[tuple[float, float, float]] = []
    for y in range(bounds.min.y, bounds.max.y + 1):
        for z in range(bounds.min.z, bounds.max.z + 1):
            for x in range(bounds.min.x, bounds.max.x + 1):
                feet = IntVector3(x, y, z)
                head = IntVector3(x, y + 1, z)
                below = IntVector3(x, y - 1, z)
                if _is_air(document, feet) and _is_air(document, head) and not _is_air(document, below):
                    result.append((x + 0.5, y + eye_height, z + 0.5))
    return result


def _center(bounds: IntBoundingBox) -> tuple[float, float, float]:
    return (
        (bounds.min.x + bounds.max.x + 1) / 2.0,
        (bounds.min.y + bounds.max.y + 1) / 2.0,
        (bounds.min.z + bounds.max.z + 1) / 2.0,
    )


def _distance(a: tuple[float, float, float], b: tuple[float, float, float]) -> float:
    return math.sqrt(sum((a[index] - b[index]) ** 2 for index in range(3)))


def _feature_targets(document: BuildDocument, bounds: IntBoundingBox) -> list[tuple[int, tuple[float, float, float], str]]:
    palette = document.palette_by_id()
    expanded = IntBoundingBox(
        IntVector3(bounds.min.x - 1, bounds.min.y - 1, bounds.min.z - 1),
        IntVector3(bounds.max.x + 1, bounds.max.y + 1, bounds.max.z + 1),
    )
    targets: list[tuple[int, tuple[float, float, float], str]] = []
    for entity in document.block_entities:
        if expanded.contains(entity.position):
            targets.append((100, tuple(value + 0.5 for value in entity.position.as_tuple()), "block-entity"))
    for position, palette_id in document.blocks.items():
        if not expanded.contains(position):
            continue
        state = palette[palette_id].canonical_state
        priority = 0
        if any(token in state for token in ("lantern", "froglight", "glowstone", "sea_lantern", "shroomlight")):
            priority = 90
        elif any(token in state for token in ("sign", "lectern", "chest", "bookshelf", "banner", "skull", "head")):
            priority = 75
        elif any(token in state for token in ("stairs", "trapdoor", "fence_gate")):
            priority = 25
        if priority:
            targets.append((priority, tuple(value + 0.5 for value in position.as_tuple()), state))
    targets.sort(key=lambda item: (-item[0], item[1], item[2]))
    return targets


def choose_room_camera(
    document: BuildDocument,
    room: dict[str, Any],
    *,
    shot: str = "auto",
    eye_height: float = 1.62,
    fov: float = 70.0,
    near: float = 0.05,
    far: float = 4096.0,
) -> RoomCameraChoice:
    bounds = room_bounds(room)
    candidates = walkable_eye_positions(document, bounds, eye_height=eye_height)
    if not candidates:
        center = _center(bounds)
        candidates = [(center[0], min(bounds.max.y + 0.75, bounds.min.y + eye_height), center[2])]
    center = _center(bounds)
    features = _feature_targets(document, bounds)
    feature_target = features[0][1] if features else None
    target = feature_target if shot == "feature" and feature_target is not None else center

    def boundary_distance(point: tuple[float, float, float]) -> float:
        return min(
            point[0] - bounds.min.x,
            bounds.max.x + 1 - point[0],
            point[2] - bounds.min.z,
            bounds.max.z + 1 - point[2],
        )

    if shot == "center":
        position = min(candidates, key=lambda point: (_distance(point, center), point))
    elif shot == "doorway":
        position = min(candidates, key=lambda point: (boundary_distance(point), -_distance(point, center), point))
    elif shot == "feature" and feature_target is not None:
        position = max(candidates, key=lambda point: (_distance(point, feature_target), -boundary_distance(point), point))
    elif shot in {"corner", "auto", "coverage", "walkthrough"}:
        position = max(candidates, key=lambda point: (_distance(point, target), -boundary_distance(point), point))
    elif shot == "low":
        base = max(candidates, key=lambda point: (_distance(point, target), point))
        position = (base[0], max(bounds.min.y + 0.8, base[1] - 0.65), base[2])
    elif shot == "upper":
        base = max(candidates, key=lambda point: (_distance(point, target), point))
        position = (base[0], min(bounds.max.y + 0.75, base[1] + 1.25), base[2])
    else:
        raise AppError("INTERIOR_SHOT", "Unknown interior shot preset.", {"shot": shot}, 2)
    if _distance(position, target) < 0.1:
        target = (target[0] + 1.0, target[1], target[2])
    return RoomCameraChoice(
        str(room.get("id", room.get("volume_id"))),
        shot,
        position,
        target,
        bounds,
        len(candidates),
        feature_target,
    )


def cutaway_mask(document: BuildDocument, choice: RoomCameraChoice, mode: str) -> frozenset[IntVector3]:
    if mode == "physical":
        return frozenset()
    if mode not in {"cutaway", "hybrid"}:
        raise AppError("INTERIOR_OCCLUSION", "Unknown interior occlusion mode.", {"mode": mode}, 2)
    bounds = choice.bounds
    distances = {
        "west": abs(choice.position[0] - bounds.min.x),
        "east": abs(bounds.max.x + 1 - choice.position[0]),
        "north": abs(choice.position[2] - bounds.min.z),
        "south": abs(bounds.max.z + 1 - choice.position[2]),
    }
    side = min(distances, key=distances.get)
    plane = {
        "west": (0, bounds.min.x - 1),
        "east": (0, bounds.max.x + 1),
        "north": (2, bounds.min.z - 1),
        "south": (2, bounds.max.z + 1),
    }[side]
    hidden: set[IntVector3] = set()
    expanded_y = range(bounds.min.y - 1, bounds.max.y + 2)
    if plane[0] == 0:
        for y in expanded_y:
            for z in range(bounds.min.z - 1, bounds.max.z + 2):
                point = IntVector3(plane[1], y, z)
                if point in document.blocks:
                    hidden.add(point)
    else:
        for y in expanded_y:
            for x in range(bounds.min.x - 1, bounds.max.x + 2):
                point = IntVector3(x, y, plane[1])
                if point in document.blocks:
                    hidden.add(point)
    if mode == "hybrid" and len(hidden) > max(32, (bounds.dimensions.x + bounds.dimensions.z) * 2):
        return frozenset()
    return frozenset(hidden)
