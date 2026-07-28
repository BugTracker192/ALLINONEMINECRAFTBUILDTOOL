from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
from typing import Any

from ..canonical import BuildDocument, IntBoundingBox, IntVector3
from .block_profiles import block_profile

_NEIGHBORS = (
    IntVector3(1, 0, 0),
    IntVector3(-1, 0, 0),
    IntVector3(0, 1, 0),
    IntVector3(0, -1, 0),
    IntVector3(0, 0, 1),
    IntVector3(0, 0, -1),
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
_VEGETATION_TOKENS = (
    "leaves",
    "log",
    "stem",
    "vine",
    "roots",
    "grass",
    "flower",
    "sapling",
    "mushroom",
)
_CONSTRUCTION_TOKENS = (
    "planks",
    "wood",
    "bricks",
    "brick",
    "concrete",
    "terracotta",
    "glass",
    "wool",
    "copper",
    "quartz",
    "prismarine",
    "purpur",
    "tiles",
    "polished",
    "chiseled",
)
_FUNCTIONAL_TOKENS = (
    "chest",
    "barrel",
    "furnace",
    "smoker",
    "blast_furnace",
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
)
_LIGHT_TOKENS = (
    "torch",
    "lantern",
    "glowstone",
    "froglight",
    "sea_lantern",
    "shroomlight",
    "campfire",
    "end_rod",
)
_ROOF_TOKENS = (
    "stairs",
    "slab",
    "tile",
    "shingle",
    "trapdoor",
)


@dataclass(frozen=True, slots=True)
class AirVolume:
    volume_id: int
    size: int
    bounds: IntBoundingBox
    exterior: bool
    floor_area: int
    min_ceiling_height: int
    max_ceiling_height: int
    seed: IntVector3 | None = None
    classification: str = "unknown_enclosed_space"
    classification_confidence: float = 0.0
    architectural_score: float = 0.0
    natural_score: float = 0.0
    decorative_void_score: float = 0.0
    room_like: bool = False
    walkable_cell_count: int = 0
    evidence: dict[str, Any] = field(default_factory=dict)


def _is_air(document: BuildDocument, point: IntVector3) -> bool:
    palette_id = document.blocks.get(point)
    return palette_id is None or document.palette_by_id()[palette_id].is_air_like


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _component_cells(
    document: BuildDocument,
    volume: AirVolume,
    *,
    max_cells: int = 500_000,
) -> tuple[set[IntVector3], bool]:
    seed = volume.seed
    if seed is None or not _is_air(document, seed):
        seed = next((point for point in volume.bounds.iter_points() if _is_air(document, point)), None)
    if seed is None:
        return set(), True
    seen = {seed}
    queue: deque[IntVector3] = deque([seed])
    complete = True
    while queue:
        point = queue.popleft()
        if len(seen) >= max_cells:
            complete = False
            break
        for offset in _NEIGHBORS:
            neighbor = point + offset
            if neighbor in seen or not volume.bounds.contains(neighbor) or not _is_air(document, neighbor):
                continue
            seen.add(neighbor)
            queue.append(neighbor)
    return seen, complete


def _classify_volume(document: BuildDocument, volume: AirVolume) -> AirVolume:
    cells, complete = _component_cells(document, volume)
    if not cells:
        return volume
    palette = document.palette_by_id()
    boundary: set[IntVector3] = set()
    walkable: list[IntVector3] = []
    floor_levels: Counter[int] = Counter()
    column_tops: dict[tuple[int, int], int] = {}
    for point in cells:
        column_tops[(point.x, point.z)] = max(column_tops.get((point.x, point.z), point.y), point.y)
        below = IntVector3(point.x, point.y - 1, point.z)
        head = IntVector3(point.x, point.y + 1, point.z)
        below_id = document.blocks.get(below)
        if (
            below_id is not None
            and block_profile(palette[below_id]).supports_player
            and _is_air(document, head)
        ):
            walkable.append(point)
            floor_levels[point.y] += 1
        for offset in _NEIGHBORS:
            neighbor = point + offset
            if not _is_air(document, neighbor):
                boundary.add(neighbor)

    states = [
        palette[document.blocks[point]].canonical_state
        for point in sorted(boundary)
        if point in document.blocks
    ]
    bases = [state.split("[", 1)[0] for state in states]
    boundary_count = max(1, len(bases))
    natural_count = sum(any(token in base for token in _NATURAL_TOKENS) for base in bases)
    vegetation_count = sum(any(token in base for token in _VEGETATION_TOKENS) for base in bases)
    construction_count = sum(any(token in base for token in _CONSTRUCTION_TOKENS) for base in bases)
    functional_count = sum(any(token in base for token in _FUNCTIONAL_TOKENS) for base in bases)
    light_count = sum(any(token in base for token in _LIGHT_TOKENS) for base in bases)
    roof_material_count = sum(any(token in base for token in _ROOF_TOKENS) for base in bases)
    stair_count = sum("stairs" in base or "ladder" in base for base in bases)
    storage_count = sum("chest" in base or "barrel" in base or "shulker_box" in base for base in bases)
    workshop_count = sum(
        any(
            token in base
            for token in (
                "crafting_table",
                "furnace",
                "anvil",
                "stonecutter",
                "grindstone",
                "smithing_table",
            )
        )
        for base in bases
    )
    opening_count = sum(
        block_profile(palette[document.blocks[point]]).doorway
        or block_profile(palette[document.blocks[point]]).window
        for point in boundary
        if point in document.blocks
    )
    fluid_count = sum(
        palette[document.blocks[point]].is_fluid for point in boundary if point in document.blocks
    )

    planar_floor_ratio = (max(floor_levels.values()) / len(walkable)) if walkable else 0.0
    roof_covered = sum(
        not _is_air(document, IntVector3(x, top + 1, z)) for (x, z), top in column_tops.items()
    )
    roof_coverage = roof_covered / max(1, len(column_tops))
    horizontal_boundary = sum(
        point.x in {volume.bounds.min.x - 1, volume.bounds.max.x + 1}
        or point.z in {volume.bounds.min.z - 1, volume.bounds.max.z + 1}
        for point in boundary
    )
    wall_planarity = horizontal_boundary / max(1, len(boundary))
    fill_ratio = volume.size / max(1, volume.bounds.volume)
    headroom_ratio = len(walkable) / max(1, volume.floor_area)
    surface_to_volume_ratio = len(boundary) / max(1, volume.size)
    construction_ratio = construction_count / boundary_count
    natural_ratio = natural_count / boundary_count
    vegetation_ratio = vegetation_count / boundary_count
    fluid_ratio = fluid_count / boundary_count
    functional_signal = min(1.0, functional_count / 4.0)
    light_signal = min(1.0, light_count / 3.0)
    opening_signal = min(1.0, opening_count / 2.0)
    regularity_score = _clamp(
        0.55 * fill_ratio
        + 0.30 * planar_floor_ratio
        + 0.15 * min(1.0, min(volume.bounds.dimensions.x, volume.bounds.dimensions.z) / 4.0)
    )
    architectural_score = _clamp(
        0.23 * planar_floor_ratio
        + 0.15 * wall_planarity
        + 0.12 * roof_coverage
        + 0.12 * regularity_score
        + 0.10 * min(1.0, headroom_ratio)
        + 0.10 * construction_ratio
        + 0.08 * functional_signal
        + 0.06 * light_signal
        + 0.04 * opening_signal
    )
    natural_score = _clamp(
        0.48 * natural_ratio
        + 0.18 * (1.0 - planar_floor_ratio)
        + 0.14 * (1.0 - regularity_score)
        + 0.10 * vegetation_ratio
        + 0.05 * fluid_ratio
        + 0.05 * min(1.0, math.log10(max(10, volume.size)) / 5.0)
    )
    decorative_void_score = _clamp(
        0.40 * (1.0 if volume.size <= 8 else max(0.0, 1.0 - volume.size / 64.0))
        + 0.30 * (1.0 if not walkable else 0.0)
        + 0.20 * min(1.0, surface_to_volume_ratio / 2.0)
        + 0.10 * vegetation_ratio
    )

    dimensions = volume.bounds.dimensions
    classification = "unknown_enclosed_space"
    room_like = False
    if decorative_void_score >= 0.62:
        if vegetation_ratio >= 0.35:
            classification = "vegetation_void"
        elif roof_material_count / boundary_count >= 0.30:
            classification = "roof_void"
        elif min(dimensions.x, dimensions.z) <= 2 and dimensions.y >= 3:
            classification = "wall_void"
        else:
            classification = "decorative_void"
    elif fluid_ratio >= 0.25:
        classification = "fluid_cavity"
    elif natural_score >= 0.48 and natural_score >= architectural_score:
        classification = "natural_cavity" if walkable else "terrain_void"
    elif architectural_score >= 0.42 and architectural_score >= natural_score + 0.04:
        room_like = True
        horizontal = sorted((dimensions.x, dimensions.z))
        if storage_count >= 2 and storage_count >= workshop_count:
            classification = "storage"
        elif workshop_count >= 2:
            classification = "workshop"
        elif stair_count >= 3 and dimensions.y >= 4:
            classification = "stairwell"
        elif opening_count >= 4 and roof_coverage >= 0.65 and wall_planarity < 0.35:
            classification = "pavilion"
        elif horizontal[0] <= 4 and horizontal[1] >= max(8, horizontal[0] * 3):
            classification = "corridor"
        elif dimensions.y <= 5 and roof_material_count >= max(2, light_count):
            classification = "attic"
        elif dimensions.y >= 9 and horizontal[0] <= 9:
            classification = "tower_interior"
        elif volume.size >= 800:
            classification = "architectural_hall"
        else:
            classification = "architectural_room"
    confidence = _clamp(
        max(
            decorative_void_score,
            architectural_score,
            natural_score,
        )
        * (0.92 if complete else 0.75)
    )
    evidence = {
        "analysis_complete": complete,
        "sampled_cell_count": len(cells),
        "planar_floor_ratio": round(planar_floor_ratio, 6),
        "wall_planarity": round(wall_planarity, 6),
        "roof_coverage": round(roof_coverage, 6),
        "opening_count": opening_count,
        "functional_block_count": functional_count,
        "storage_block_count": storage_count,
        "workshop_block_count": workshop_count,
        "stair_or_ladder_count": stair_count,
        "light_source_count": light_count,
        "walkable_cell_count": len(walkable),
        "regularity_score": round(regularity_score, 6),
        "construction_boundary_ratio": round(construction_ratio, 6),
        "natural_boundary_ratio": round(natural_ratio, 6),
        "vegetation_boundary_ratio": round(vegetation_ratio, 6),
        "fluid_boundary_ratio": round(fluid_ratio, 6),
        "surface_to_volume_ratio": round(surface_to_volume_ratio, 6),
    }
    return AirVolume(
        volume.volume_id,
        volume.size,
        volume.bounds,
        volume.exterior,
        volume.floor_area,
        volume.min_ceiling_height,
        volume.max_ceiling_height,
        volume.seed,
        classification,
        round(confidence, 6),
        round(architectural_score, 6),
        round(natural_score, 6),
        round(decorative_void_score, 6),
        room_like,
        len(walkable),
        evidence,
    )


def classify_air_volumes(document: BuildDocument, *, max_cells: int = 20_000_000) -> list[AirVolume]:
    """Classify air with a compact integer-index flood fill.

    The previous implementation materialized every air cell as an ``IntVector3``
    inside a Python set.  That was exact but prohibitively expensive for sparse
    structures near one million cells.  This implementation uses one byte per
    expanded cell and integer queue entries while preserving the same 6-neighbor
    semantics and deterministic component order.
    """

    expanded = IntBoundingBox(
        IntVector3(document.bounds.min.x - 1, document.bounds.min.y - 1, document.bounds.min.z - 1),
        IntVector3(document.bounds.max.x + 1, document.bounds.max.y + 1, document.bounds.max.z + 1),
    )
    dx, dy, dz = expanded.dimensions.as_tuple()
    volume = dx * dy * dz
    if volume > max_cells:
        return []

    plane = dx * dz
    visited = bytearray(volume)

    def index_of(point: IntVector3) -> int:
        return int(
            point.x - expanded.min.x + (point.z - expanded.min.z) * dx + (point.y - expanded.min.y) * plane
        )

    palette = document.palette_by_id()
    for point, palette_id in document.blocks.items():
        if expanded.contains(point) and not palette[palette_id].is_air_like:
            visited[index_of(point)] = 1

    result: list[AirVolume] = []
    for start in range(volume):
        if visited[start]:
            continue
        visited[start] = 1
        queue: deque[int] = deque([start])
        size = 0
        exterior = False
        min_x = min_y = min_z = 1 << 60
        max_x = max_y = max_z = -(1 << 60)
        columns: dict[tuple[int, int], tuple[int, int]] = {}
        seed: IntVector3 | None = None
        while queue:
            current = queue.popleft()
            local_y, rem = divmod(current, plane)
            local_z, local_x = divmod(rem, dx)
            x = expanded.min.x + local_x
            y = expanded.min.y + local_y
            z = expanded.min.z + local_z
            if seed is None:
                seed = IntVector3(x, y, z)
            size += 1
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            min_z, max_z = min(min_z, z), max(max_z, z)
            exterior |= local_x in {0, dx - 1} or local_y in {0, dy - 1} or local_z in {0, dz - 1}
            column = (x, z)
            previous = columns.get(column)
            columns[column] = (y, y) if previous is None else (min(previous[0], y), max(previous[1], y))

            if local_x > 0:
                neighbor = current - 1
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if local_x + 1 < dx:
                neighbor = current + 1
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if local_z > 0:
                neighbor = current - dx
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if local_z + 1 < dz:
                neighbor = current + dx
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if local_y > 0:
                neighbor = current - plane
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if local_y + 1 < dy:
                neighbor = current + plane
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)

        heights = [maximum - minimum + 1 for minimum, maximum in columns.values()]
        result.append(
            AirVolume(
                len(result),
                size,
                IntBoundingBox(IntVector3(min_x, min_y, min_z), IntVector3(max_x, max_y, max_z)),
                exterior,
                len(columns),
                min(heights),
                max(heights),
                seed,
            )
        )
    ordered = sorted(result, key=lambda item: (item.exterior, -item.size, item.bounds.min))
    return [
        _classify_volume(document, item) if not item.exterior and item.size >= 2 else item for item in ordered
    ]


def room_report(
    document: BuildDocument,
    *,
    volumes: list[AirVolume] | None = None,
    max_cells: int = 20_000_000,
) -> dict[str, object]:
    volumes = classify_air_volumes(document, max_cells=max_cells) if volumes is None else volumes
    interiors = [item for item in volumes if not item.exterior and item.size >= 2]
    expanded_volume = (
        (document.bounds.dimensions.x + 2)
        * (document.bounds.dimensions.y + 2)
        * (document.bounds.dimensions.z + 2)
    )
    return {
        "analysisSkipped": not volumes and expanded_volume > max_cells,
        "enclosedSpaceCount": len(interiors),
        "interiorVolumeCount": len(interiors),
        "roomLikeCount": sum(item.room_like for item in interiors),
        "classificationCounts": dict(sorted(Counter(item.classification for item in interiors).items())),
        "rooms": [asdict(item) for item in interiors],
    }
