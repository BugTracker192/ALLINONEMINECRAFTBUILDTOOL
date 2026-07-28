from __future__ import annotations

import json
import math
from collections import deque
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from mbi.analysis.block_profiles import block_profile
from mbi.canonical import BuildDocument, IntBoundingBox, IntVector3, PaletteEntry

from app.errors import AppError

_NEIGHBORS = (
    IntVector3(1, 0, 0),
    IntVector3(-1, 0, 0),
    IntVector3(0, 1, 0),
    IntVector3(0, -1, 0),
    IntVector3(0, 0, 1),
    IntVector3(0, 0, -1),
)
_FUNCTIONAL_TOKENS = (
    "chest",
    "barrel",
    "furnace",
    "crafting_table",
    "lectern",
    "bed",
    "anvil",
    "brewing_stand",
    "cauldron",
    "loom",
    "stonecutter",
    "grindstone",
    "cartography_table",
    "smithing_table",
    "fletching_table",
    "bookshelf",
    "jukebox",
    "enchanting_table",
)
_FEATURE_TOKENS = (
    "lantern",
    "froglight",
    "glowstone",
    "sea_lantern",
    "shroomlight",
    "sign",
    "banner",
    "skull",
    "head",
    "painting",
    "armor_stand",
    *_FUNCTIONAL_TOKENS,
)
_PROTECTED_TOKENS = (
    "chest",
    "barrel",
    "shulker_box",
    "spawner",
    "command_block",
    "structure_block",
    "jigsaw",
    "end_portal",
    "nether_portal",
    "bedrock",
)
_NATURAL_TOKENS = (
    "stone",
    "deepslate",
    "dirt",
    "mud",
    "gravel",
    "sand",
    "clay",
    "moss",
    "dripstone",
    "tuff",
    "netherrack",
    "basalt",
    "calcite",
    "ore",
)


@dataclass(frozen=True, slots=True)
class RoomGeometry:
    cells: frozenset[IntVector3]
    boundary: frozenset[IntVector3]
    floor: frozenset[IntVector3]
    ceiling: frozenset[IntVector3]
    walls: frozenset[IntVector3]
    openings: frozenset[IntVector3]
    protected: frozenset[IntVector3]
    complete: bool
    boundary_classes: dict[str, frozenset[IntVector3]] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FeatureCandidate:
    coordinate: IntVector3
    target: tuple[float, float, float]
    state: str
    kind: str
    priority: int
    membership: str


@dataclass(frozen=True, slots=True)
class RayHit:
    visible: bool
    first_blocker: IntVector3 | None
    traversed_voxels: int
    distance: float


@dataclass(frozen=True, slots=True)
class CameraCandidate:
    position: tuple[float, float, float]
    target: tuple[float, float, float]
    mode: str
    score: float
    accepted: bool
    visible_sample_ratio: float
    clearance: float
    rejection_reasons: tuple[str, ...] = ()
    reachability: str = "unknown"


@dataclass(frozen=True, slots=True)
class RoomCameraChoice:
    # The first seven fields retain the original constructor contract.
    room_id: str
    shot: str
    position: tuple[float, float, float]
    target: tuple[float, float, float]
    bounds: IntBoundingBox
    candidate_count: int
    feature_target: tuple[float, float, float] | None = None
    camera_mode: str = "physical-first-person"
    score: float = 0.0
    accepted: bool = True
    visible_sample_ratio: float = 0.0
    rejection_reasons: tuple[str, ...] = ()
    diagnostics: dict[str, Any] = field(default_factory=dict)


def _point_from_mapping(value: Any) -> IntVector3:
    if isinstance(value, IntVector3):
        return value
    if isinstance(value, dict):
        return IntVector3(int(value["x"]), int(value["y"]), int(value["z"]))
    if isinstance(value, (list, tuple)) and len(value) == 3:
        return IntVector3(*(int(item) for item in value))
    raise AppError("ROOM_BOUNDS_INVALID", "Room bounds contain an invalid coordinate.", {"value": value}, 20)


def room_bounds(room: dict[str, Any]) -> IntBoundingBox:
    raw = room.get("bounds")
    if not isinstance(raw, dict):
        raise AppError(
            "ROOM_BOUNDS_INVALID",
            "Room result has no bounds object.",
            {"room": room.get("id", room.get("volume_id"))},
            20,
        )
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
    room = next(
        (item for item in rooms if str(item.get("id", item.get("volume_id"))) == str(room_id)),
        None,
    )
    if room is None:
        raise AppError(
            "ROOM_NOT_FOUND",
            "Room was not found.",
            {"id": room_id, "available": [str(item.get("id")) for item in rooms]},
            20,
        )
    return room


def _entry(document: BuildDocument, point: IntVector3) -> PaletteEntry | None:
    palette_id = document.blocks.get(point)
    return None if palette_id is None else document.palette_by_id()[palette_id]


def _is_air(document: BuildDocument, point: IntVector3) -> bool:
    entry = _entry(document, point)
    return entry is None or entry.is_air_like


def _is_passable(document: BuildDocument, point: IntVector3) -> bool:
    entry = _entry(document, point)
    return entry is None or block_profile(entry).passable


def _is_transparent(document: BuildDocument, point: IntVector3) -> bool:
    entry = _entry(document, point)
    return entry is None or block_profile(entry).transparent


def room_geometry(
    document: BuildDocument,
    room: dict[str, Any],
    *,
    max_cells: int = 750_000,
) -> RoomGeometry:
    """Recover exact component membership and grounded architectural boundaries."""
    bounds = room_bounds(room)
    seed_value = room.get("seed")
    seed = _point_from_mapping(seed_value) if seed_value is not None else None
    if seed is None or not bounds.contains(seed) or not _is_air(document, seed):
        center = IntVector3(
            (bounds.min.x + bounds.max.x) // 2,
            (bounds.min.y + bounds.max.y) // 2,
            (bounds.min.z + bounds.max.z) // 2,
        )
        candidates = (center, *bounds.iter_points())
        seed = next((point for point in candidates if _is_air(document, point)), None)
    if seed is None:
        empty: frozenset[IntVector3] = frozenset()
        return RoomGeometry(empty, empty, empty, empty, empty, empty, empty, True, {})

    cells = {seed}
    queue: deque[IntVector3] = deque([seed])
    complete = True
    while queue:
        point = queue.popleft()
        if len(cells) >= max_cells:
            complete = False
            break
        for offset in _NEIGHBORS:
            neighbor = point + offset
            if neighbor in cells or not bounds.contains(neighbor) or not _is_air(document, neighbor):
                continue
            cells.add(neighbor)
            queue.append(neighbor)

    boundary: set[IntVector3] = set()
    floor: set[IntVector3] = set()
    ceiling: set[IntVector3] = set()
    walls: set[IntVector3] = set()
    openings: set[IntVector3] = set()
    for point in cells:
        for offset in _NEIGHBORS:
            neighbor = point + offset
            if neighbor in cells:
                continue
            entry = _entry(document, neighbor)
            if entry is None or entry.is_air_like:
                openings.add(neighbor)
                continue
            boundary.add(neighbor)
            if offset.y < 0:
                floor.add(neighbor)
            elif offset.y > 0:
                ceiling.add(neighbor)
            else:
                walls.add(neighbor)
            if block_profile(entry).doorway or block_profile(entry).window:
                openings.add(neighbor)
    protected: set[IntVector3] = set()
    for point in boundary:
        entry = _entry(document, point)
        if entry is not None and any(token in entry.block_name for token in _PROTECTED_TOKENS):
            protected.add(point)
    protected.update(entity.position for entity in document.block_entities if entity.position in boundary)
    boundary_classes: dict[str, set[IntVector3]] = {
        "floor": set(floor),
        "ceiling": set(ceiling),
        "north_wall": set(),
        "south_wall": set(),
        "east_wall": set(),
        "west_wall": set(),
        "internal_partition": set(),
        "column_or_support": set(),
        "door_window_opening_frame": set(),
        "terrain_shell": set(),
        "roof_structure": set(ceiling),
        "functional_or_feature": set(),
    }
    for point in walls:
        adjacent = {offset for offset in _NEIGHBORS if offset.y == 0 and point - offset in cells}
        if any(offset.x < 0 for offset in adjacent):
            boundary_classes["west_wall"].add(point)
        if any(offset.x > 0 for offset in adjacent):
            boundary_classes["east_wall"].add(point)
        if any(offset.z < 0 for offset in adjacent):
            boundary_classes["north_wall"].add(point)
        if any(offset.z > 0 for offset in adjacent):
            boundary_classes["south_wall"].add(point)
        if bounds.contains(point):
            boundary_classes["internal_partition"].add(point)
        entry = _entry(document, point)
        if entry is None:
            continue
        profile = block_profile(entry)
        if profile.doorway or profile.window:
            boundary_classes["door_window_opening_frame"].add(point)
        if any(token in entry.block_name for token in _NATURAL_TOKENS):
            boundary_classes["terrain_shell"].add(point)
        if any(token in entry.block_name for token in _FUNCTIONAL_TOKENS + _FEATURE_TOKENS):
            boundary_classes["functional_or_feature"].add(point)
    for point in boundary:
        horizontal_air_sides = sum(
            _is_air(document, point + offset) for offset in _NEIGHBORS if offset.y == 0
        )
        if horizontal_air_sides >= 2 and point not in openings:
            boundary_classes["column_or_support"].add(point)
    return RoomGeometry(
        frozenset(cells),
        frozenset(boundary),
        frozenset(floor),
        frozenset(ceiling),
        frozenset(walls),
        frozenset(openings),
        frozenset(protected),
        complete,
        {name: frozenset(points) for name, points in boundary_classes.items()},
    )


def walkable_eye_positions(
    document: BuildDocument,
    bounds: IntBoundingBox,
    *,
    eye_height: float = 1.62,
    cells: Iterable[IntVector3] | None = None,
) -> list[tuple[float, float, float]]:
    allowed = set(cells) if cells is not None else None
    result: list[tuple[float, float, float]] = []
    for y in range(bounds.min.y, bounds.max.y + 1):
        for z in range(bounds.min.z, bounds.max.z + 1):
            for x in range(bounds.min.x, bounds.max.x + 1):
                feet = IntVector3(x, y, z)
                head = IntVector3(x, y + 1, z)
                below = IntVector3(x, y - 1, z)
                if allowed is not None and feet not in allowed:
                    continue
                if (
                    _is_passable(document, feet)
                    and _is_passable(document, head)
                    and not _is_passable(document, below)
                ):
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


def _voxel(value: tuple[float, float, float]) -> IntVector3:
    return IntVector3(*(math.floor(item) for item in value))


def voxel_ray(
    document: BuildDocument,
    start: tuple[float, float, float],
    end: tuple[float, float, float],
    *,
    acceptable_hit: IntVector3 | None = None,
    transparent_blocks_occlude: bool = False,
) -> RayHit:
    """Deterministic Amanatides-Woo traversal through the document voxel field."""
    direction = tuple(end[index] - start[index] for index in range(3))
    distance = _distance(start, end)
    if distance <= 1e-9:
        return RayHit(True, None, 0, 0.0)
    current = [math.floor(value) for value in start]
    target = [math.floor(value) for value in end]
    step = [1 if value > 0 else -1 if value < 0 else 0 for value in direction]
    t_delta = [abs(1.0 / value) if value else math.inf for value in direction]
    t_max: list[float] = []
    for axis in range(3):
        if step[axis] > 0:
            t_max.append((current[axis] + 1.0 - start[axis]) / direction[axis])
        elif step[axis] < 0:
            t_max.append((start[axis] - current[axis]) / -direction[axis])
        else:
            t_max.append(math.inf)
    traversed = 0
    limit = sum(abs(target[index] - current[index]) for index in range(3)) + 4
    while traversed <= limit:
        point = IntVector3(*current)
        if traversed > 0:
            entry = _entry(document, point)
            blocking = entry is not None and not entry.is_air_like
            if blocking and not transparent_blocks_occlude:
                assert entry is not None
                blocking = not block_profile(entry).transparent
            if blocking:
                return RayHit(point == acceptable_hit, point, traversed, distance)
        if current == target:
            break
        axis = min(range(3), key=lambda index: (t_max[index], index))
        current[axis] += step[axis]
        t_max[axis] += t_delta[axis]
        traversed += 1
    return RayHit(True, None, traversed, distance)


def feature_candidates(
    document: BuildDocument,
    geometry: RoomGeometry,
) -> list[FeatureCandidate]:
    palette = document.palette_by_id()
    entities = {entity.position: entity for entity in document.block_entities}
    result: list[FeatureCandidate] = []
    for position in sorted(geometry.boundary | geometry.cells):
        palette_id = document.blocks.get(position)
        if palette_id is None:
            continue
        entry = palette[palette_id]
        state = entry.canonical_state
        is_entity = position in entities
        if not is_entity and not any(token in entry.block_name for token in _FEATURE_TOKENS):
            continue
        membership = "component" if position in geometry.cells else "architectural-boundary"
        kind = (
            "block-entity"
            if is_entity
            else (
                "functional"
                if any(token in entry.block_name for token in _FUNCTIONAL_TOKENS)
                else "decorative"
            )
        )
        priority = 100 if is_entity else 85 if kind == "functional" else 65
        x, y, z = position.as_tuple()
        result.append(
            FeatureCandidate(
                position,
                (x + 0.5, y + 0.5, z + 0.5),
                state,
                kind,
                priority,
                membership,
            )
        )
    result.sort(key=lambda item: (-item.priority, item.coordinate, item.state))
    return result


def _camera_clearance(document: BuildDocument, position: tuple[float, float, float]) -> float:
    point = _voxel(position)
    if not _is_passable(document, point):
        return 0.0
    distances: list[float] = []
    for offset in _NEIGHBORS:
        for step in range(1, 5):
            probe = IntVector3(
                point.x + offset.x * step,
                point.y + offset.y * step,
                point.z + offset.z * step,
            )
            if not _is_passable(document, probe):
                distances.append(step - 0.5)
                break
    return min(distances, default=4.0)


def _target_samples(
    bounds: IntBoundingBox,
    target: tuple[float, float, float],
    feature: FeatureCandidate | None,
) -> tuple[tuple[tuple[float, float, float], IntVector3 | None], ...]:
    center = _center(bounds)
    low = (center[0], bounds.min.y + 1.0, center[2])
    upper = (center[0], min(bounds.max.y + 0.5, bounds.min.y + 2.75), center[2])
    samples: list[tuple[tuple[float, float, float], IntVector3 | None]] = [
        (target, feature.coordinate if feature and target == feature.target else None),
        (center, None),
        (low, None),
        (upper, None),
    ]
    return tuple(samples)


def camera_candidates(
    document: BuildDocument,
    room: dict[str, Any],
    *,
    shot: str = "auto",
    eye_height: float = 1.62,
) -> tuple[list[CameraCandidate], RoomGeometry, list[FeatureCandidate]]:
    bounds = room_bounds(room)
    geometry = room_geometry(document, room)
    walkable = walkable_eye_positions(document, bounds, eye_height=eye_height, cells=geometry.cells)
    center = _center(bounds)
    if not walkable:
        fallback = (center[0], min(bounds.max.y + 0.75, bounds.min.y + eye_height), center[2])
        walkable = [fallback]
    features = feature_candidates(document, geometry)
    feature = features[0] if features else None
    target = feature.target if shot == "feature" and feature is not None else center
    if shot not in {
        "auto",
        "doorway",
        "corner",
        "center",
        "feature",
        "low",
        "upper",
        "coverage",
        "walkthrough",
    }:
        raise AppError("INTERIOR_SHOT", "Unknown interior shot preset.", {"shot": shot}, 2)

    # Evaluate all physical positions. Ordering is only a tie-breaker; it never
    # substitutes for visibility and collision checks.
    candidates: list[CameraCandidate] = []
    room_diagonal = max(
        1.0,
        _distance(
            (bounds.min.x, bounds.min.y, bounds.min.z),
            (bounds.max.x + 1, bounds.max.y + 1, bounds.max.z + 1),
        ),
    )
    position_modes: list[tuple[tuple[float, float, float], str]] = [
        (base, "physical-first-person") for base in walkable
    ]
    if bounds.dimensions.y >= 5 or shot == "upper":
        for base in walkable:
            elevated = (base[0], min(bounds.max.y + 0.75, base[1] + 1.25), base[2])
            if _is_passable(document, _voxel(elevated)):
                position_modes.append((elevated, "physical-elevated"))
    if shot == "low":
        position_modes = [
            ((base[0], max(bounds.min.y + 0.8, base[1] - 0.65), base[2]), "physical-low") for base in walkable
        ]
    orbit_height = min(bounds.max.y + 0.5, max(bounds.min.y + 1.62, center[1]))
    orbit_distance = max(2.0, min(8.0, max(bounds.dimensions.x, bounds.dimensions.z) * 0.35))
    position_modes.extend(
        (
            ((bounds.min.x - orbit_distance, orbit_height, center[2]), "visibility-aware-orbit"),
            ((bounds.max.x + 1 + orbit_distance, orbit_height, center[2]), "visibility-aware-orbit"),
            ((center[0], orbit_height, bounds.min.z - orbit_distance), "visibility-aware-orbit"),
            ((center[0], orbit_height, bounds.max.z + 1 + orbit_distance), "visibility-aware-orbit"),
        )
    )
    position_modes = list(dict.fromkeys(position_modes))
    for position, mode in position_modes:
        clearance = _camera_clearance(document, position)
        sample_results = [
            voxel_ray(document, position, sample, acceptable_hit=acceptable)
            for sample, acceptable in _target_samples(bounds, target, feature)
        ]
        visible_ratio = sum(item.visible for item in sample_results) / len(sample_results)
        rejection: list[str] = []
        if clearance <= 0:
            rejection.append("camera-collision")
        if visible_ratio < 0.5:
            rejection.append("insufficient-line-of-sight")
        if _distance(position, target) < 0.75:
            rejection.append("target-too-close")
        boundary_distance = min(
            position[0] - bounds.min.x,
            bounds.max.x + 1 - position[0],
            position[2] - bounds.min.z,
            bounds.max.z + 1 - position[2],
        )
        distance_score = min(1.0, _distance(position, target) / room_diagonal)
        framing_bias = 0.0
        if shot == "center":
            framing_bias = 1.0 - min(1.0, _distance(position, center) / room_diagonal)
        elif shot == "doorway":
            framing_bias = 1.0 - min(1.0, max(0.0, boundary_distance) / 4.0)
        else:
            framing_bias = distance_score
        score = (
            0.50 * visible_ratio
            + 0.20 * min(1.0, clearance / 2.5)
            + 0.20 * framing_bias
            + 0.10 * min(1.0, boundary_distance / 2.0)
            - 0.25 * len(rejection)
        )
        if mode == "visibility-aware-orbit" and visible_ratio < 0.75:
            rejection.append("orbit-requires-cutaway")
        candidates.append(
            CameraCandidate(
                position,
                target,
                mode,
                round(score, 6),
                not rejection,
                round(visible_ratio, 6),
                round(clearance, 6),
                tuple(rejection),
                (
                    "reachable"
                    if mode in {"physical-first-person", "physical-low"}
                    else "physically-valid-unreachable"
                    if mode == "physical-elevated"
                    else "non-physical-evidence"
                ),
            )
        )
    candidates.sort(key=lambda item: (-item.accepted, -item.score, item.position, item.target))
    return candidates, geometry, features


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
    del fov, near, far  # Retained as a stable API; rendering owns projection validation.
    candidates, geometry, features = camera_candidates(document, room, shot=shot, eye_height=eye_height)
    selected = candidates[0]
    bounds = room_bounds(room)
    feature_target = features[0].target if features else None
    diagnostics = {
        "component_cell_count": len(geometry.cells),
        "component_complete": geometry.complete,
        "boundary_block_count": len(geometry.boundary),
        "feature_candidate_count": len(features),
        "feature_candidates": [asdict(item) for item in features[:20]],
        "accepted_candidate_count": sum(item.accepted for item in candidates),
        "rejected_candidate_count": sum(not item.accepted for item in candidates),
        "ranked_candidates": [asdict(item) for item in candidates[:50]],
    }
    return RoomCameraChoice(
        str(room.get("id", room.get("volume_id"))),
        shot,
        selected.position,
        selected.target,
        bounds,
        len(candidates),
        feature_target,
        selected.mode,
        selected.score,
        selected.accepted,
        selected.visible_sample_ratio,
        selected.rejection_reasons,
        diagnostics,
    )


def cutaway_mask(
    document: BuildDocument,
    choice: RoomCameraChoice,
    mode: str,
    *,
    geometry: RoomGeometry | None = None,
) -> frozenset[IntVector3]:
    if mode == "physical":
        return frozenset()
    if mode not in {"cutaway", "hybrid", "roof-off", "wall-off"}:
        raise AppError("INTERIOR_OCCLUSION", "Unknown interior occlusion mode.", {"mode": mode}, 2)
    bounds = choice.bounds
    protected = (
        geometry.protected if geometry else frozenset(entity.position for entity in document.block_entities)
    )
    if mode == "roof-off":
        roof = geometry.boundary_classes.get("roof_structure", geometry.ceiling) if geometry else frozenset()
        return frozenset(point for point in roof if point not in protected)
    if mode == "wall-off":
        if geometry is None:
            mode = "cutaway"
        else:
            distances = {
                "west_wall": abs(choice.position[0] - bounds.min.x),
                "east_wall": abs(bounds.max.x + 1 - choice.position[0]),
                "north_wall": abs(choice.position[2] - bounds.min.z),
                "south_wall": abs(bounds.max.z + 1 - choice.position[2]),
            }
            wall = min(distances, key=lambda item: distances[item])
            return frozenset(
                point
                for point in geometry.boundary_classes.get(wall, frozenset())
                if point not in protected
                and point not in geometry.boundary_classes.get("column_or_support", frozenset())
                and point not in geometry.boundary_classes.get("door_window_opening_frame", frozenset())
            )
    targets = (
        choice.target,
        _center(bounds),
        (bounds.min.x + 0.5, bounds.min.y + 1.25, bounds.min.z + 0.5),
        (bounds.max.x + 0.5, bounds.min.y + 1.25, bounds.max.z + 0.5),
    )
    hidden: set[IntVector3] = set()
    for target in targets:
        hit = voxel_ray(document, choice.position, target, transparent_blocks_occlude=True)
        if hit.first_blocker is not None and hit.first_blocker not in protected:
            hidden.add(hit.first_blocker)

    # Exterior/orbit cameras can need a wall aperture even when center rays end
    # just before the wall. Keep this fallback deliberately local, not a full plane.
    if not hidden:
        distances = {
            "west": abs(choice.position[0] - bounds.min.x),
            "east": abs(bounds.max.x + 1 - choice.position[0]),
            "north": abs(choice.position[2] - bounds.min.z),
            "south": abs(bounds.max.z + 1 - choice.position[2]),
        }
        side = min(distances, key=lambda item: distances[item])
        center = _center(bounds)
        for vertical in range(
            max(bounds.min.y - 1, math.floor(center[1]) - 1),
            min(bounds.max.y + 1, math.floor(center[1]) + 1) + 1,
        ):
            for lateral in range(-1, 2):
                if side in {"west", "east"}:
                    point = IntVector3(
                        bounds.min.x - 1 if side == "west" else bounds.max.x + 1,
                        vertical,
                        math.floor(center[2]) + lateral,
                    )
                else:
                    point = IntVector3(
                        math.floor(center[0]) + lateral,
                        vertical,
                        bounds.min.z - 1 if side == "north" else bounds.max.z + 1,
                    )
                if point in document.blocks and point not in protected:
                    hidden.add(point)
    if mode == "hybrid" and len(hidden) > 12:
        return frozenset()
    return frozenset(hidden)
