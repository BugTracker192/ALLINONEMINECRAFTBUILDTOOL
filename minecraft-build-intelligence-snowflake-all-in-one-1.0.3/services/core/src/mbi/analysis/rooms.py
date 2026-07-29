from __future__ import annotations

import math
from collections import Counter, deque
from collections.abc import Callable
from dataclasses import asdict, dataclass, field, replace
from itertools import pairwise
from typing import Any

from ..canonical import BuildDocument, IntBoundingBox, IntVector3
from .block_profiles import block_profile
from .structures import classify_block_name

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
_DECORATIVE_TOKENS = (
    "banner",
    "carpet",
    "candle",
    "flower_pot",
    "head",
    "painting",
    "skull",
    "sign",
    "tapestry",
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
    allowed_air: Callable[[IntVector3], bool] | None = None,
) -> tuple[set[IntVector3], bool]:
    seed = volume.seed
    if (
        seed is None
        or not _is_air(document, seed)
        or (allowed_air is not None and not allowed_air(seed))
    ):
        seed = next(
            (
                point
                for point in volume.bounds.iter_points()
                if _is_air(document, point)
                and (allowed_air is None or allowed_air(point))
            ),
            None,
        )
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
            if (
                neighbor in seen
                or not volume.bounds.contains(neighbor)
                or not _is_air(document, neighbor)
                or (allowed_air is not None and not allowed_air(neighbor))
            ):
                continue
            seen.add(neighbor)
            queue.append(neighbor)
    return seen, complete


def _classify_volume(
    document: BuildDocument,
    volume: AirVolume,
    *,
    allowed_air: Callable[[IntVector3], bool] | None = None,
) -> AirVolume:
    cells, complete = _component_cells(
        document,
        volume,
        allowed_air=allowed_air,
    )
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
    decorative_count = sum(
        any(token in base for token in _DECORATIVE_TOKENS) for base in bases
    )
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
    dimensions = volume.bounds.dimensions
    furnishing_count = functional_count + decorative_count
    furnishing_density = furnishing_count / max(1, len(walkable))
    detail_levels = {
        point.y
        for point in boundary
        if point in document.blocks
        and (
            any(token in palette[document.blocks[point]].block_name for token in _FUNCTIONAL_TOKENS)
            or any(
                token in palette[document.blocks[point]].block_name
                for token in _DECORATIVE_TOKENS
            )
        )
    }
    vertical_detail_occupancy = len(detail_levels) / max(1, dimensions.y)
    dead_cells = sum(
        all(
            IntVector3(
                point.x + offset.x * distance,
                point.y + offset.y * distance,
                point.z + offset.z * distance,
            )
            in cells
            for offset in _NEIGHBORS
            for distance in (1, 2)
        )
        for point in cells
    )
    dead_volume_ratio = dead_cells / max(1, len(cells))
    is_hollow = (
        len(walkable) >= 20
        and furnishing_density < 0.02
        and vertical_detail_occupancy < 0.2
        and (dead_volume_ratio >= 0.1 or len(walkable) >= 100)
    )
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
        "furnishing": {
            "functional_block_count": functional_count,
            "decorative_block_count": decorative_count,
            "furnishing_block_count": furnishing_count,
            "walkable_cell_count": len(walkable),
            "density_per_walkable_cell": round(furnishing_density, 6),
            "vertical_detail_occupancy": round(vertical_detail_occupancy, 6),
            "dead_volume_ratio": round(dead_volume_ratio, 6),
            "is_hollow": is_hollow,
            "method": "boundary-fixture-and-two-cell-dead-volume-v1",
        },
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


def _structure_envelope(
    document: BuildDocument,
) -> tuple[
    dict[tuple[int, int], tuple[tuple[int, int], ...]],
    dict[str, int | str],
]:
    """Derive covered constructed columns for structure-scoped room sealing.

    A vertical air run belongs to the floodable envelope when it is bracketed
    by real solid surfaces and at least one of those surfaces is constructed.
    This admits a terrain floor beneath a constructed roof but rejects natural
    subsurface cavities. Restricting fills to those runs closes exterior doors
    and façade openings without turning open courtyards into rooms. The
    separate enclosed void count remains useful evidence about the 2D
    footprint.
    """

    palette = document.palette_by_id()
    column_solids: dict[tuple[int, int], dict[int, bool]] = {}
    constructed_columns: set[tuple[int, int]] = set()
    for point, palette_id in document.blocks.items():
        entry = palette[palette_id]
        if entry.is_air_like:
            continue
        column = (point.x, point.z)
        built = classify_block_name(entry.block_name) == "built"
        levels = column_solids.setdefault(column, {})
        levels[point.y] = levels.get(point.y, False) or built
        if built:
            constructed_columns.add(column)

    min_x = document.bounds.min.x
    max_x = document.bounds.max.x
    min_z = document.bounds.min.z
    max_z = document.bounds.max.z
    exterior_void: set[tuple[int, int]] = set()
    queue: deque[tuple[int, int]] = deque()

    def enqueue(column: tuple[int, int]) -> None:
        if column not in constructed_columns and column not in exterior_void:
            exterior_void.add(column)
            queue.append(column)

    for x in range(min_x, max_x + 1):
        enqueue((x, min_z))
        enqueue((x, max_z))
    for z in range(min_z, max_z + 1):
        enqueue((min_x, z))
        enqueue((max_x, z))
    while queue:
        x, z = queue.popleft()
        for neighbor in ((x - 1, z), (x + 1, z), (x, z - 1), (x, z + 1)):
            if (
                min_x <= neighbor[0] <= max_x
                and min_z <= neighbor[1] <= max_z
            ):
                enqueue(neighbor)

    enclosed_void = {
        (x, z)
        for x in range(min_x, max_x + 1)
        for z in range(min_z, max_z + 1)
        if (x, z) not in constructed_columns
        and (x, z) not in exterior_void
    }
    footprint = constructed_columns | enclosed_void
    spans: dict[tuple[int, int], tuple[tuple[int, int], ...]] = {}
    vertical_run_count = 0
    for column, levels in column_solids.items():
        ordered_levels = sorted(levels)
        runs = tuple(
            (lower, upper)
            for lower, upper in pairwise(ordered_levels)
            if upper - lower >= 2
            and (levels[lower] or levels[upper])
        )
        if runs:
            spans[column] = runs
            vertical_run_count += len(runs)
    return spans, {
        "method": "constructed-column-envelope-seal-v1",
        "constructed_column_count": len(constructed_columns),
        "enclosed_void_column_count": len(enclosed_void),
        "envelope_footprint_column_count": len(footprint),
        "covered_column_count": len(spans),
        "covered_vertical_span_count": vertical_run_count,
    }


def _classify_air_volumes(
    document: BuildDocument,
    *,
    max_cells: int = 20_000_000,
    seal_structure_envelope: bool = False,
) -> list[AirVolume]:
    """Classify air with a compact integer-index flood fill.

    The previous implementation materialized every air cell as an ``IntVector3``
    inside a Python set.  That was exact but prohibitively expensive for sparse
    structures near one million cells.  This implementation uses one byte per
    expanded cell and integer queue entries while preserving the same 6-neighbor
    semantics and deterministic component order.
    """

    envelope_spans: dict[
        tuple[int, int],
        tuple[tuple[int, int], ...],
    ] = {}
    envelope_evidence: dict[str, int | str] = {}
    if seal_structure_envelope:
        envelope_spans, envelope_evidence = _structure_envelope(document)
        expanded = document.bounds
    else:
        expanded = IntBoundingBox(
            IntVector3(
                document.bounds.min.x - 1,
                document.bounds.min.y - 1,
                document.bounds.min.z - 1,
            ),
            IntVector3(
                document.bounds.max.x + 1,
                document.bounds.max.y + 1,
                document.bounds.max.z + 1,
            ),
        )
    dx, dy, dz = expanded.dimensions.as_tuple()
    volume = dx * dy * dz
    if volume > max_cells:
        return []

    plane = dx * dz
    visited = bytearray(volume)
    allowed: bytearray | None = None

    def index_of(point: IntVector3) -> int:
        return int(
            point.x - expanded.min.x + (point.z - expanded.min.z) * dx + (point.y - expanded.min.y) * plane
        )

    if seal_structure_envelope:
        allowed = bytearray(volume)
        visited[:] = b"\x01" * volume
        for (x, z), spans in envelope_spans.items():
            for minimum_y, maximum_y in spans:
                minimum_y = max(minimum_y, expanded.min.y)
                maximum_y = min(maximum_y, expanded.max.y)
                for y in range(minimum_y, maximum_y + 1):
                    index = index_of(IntVector3(x, y, z))
                    allowed[index] = 1
                    visited[index] = 0

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
        sealed_opening_count = 0
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
            if not seal_structure_envelope:
                exterior |= (
                    local_x in {0, dx - 1}
                    or local_y in {0, dy - 1}
                    or local_z in {0, dz - 1}
                )
            column = (x, z)
            previous = columns.get(column)
            columns[column] = (y, y) if previous is None else (min(previous[0], y), max(previous[1], y))

            if local_x > 0:
                neighbor = current - 1
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
                elif (
                    allowed is not None
                    and not allowed[neighbor]
                    and _is_air(document, IntVector3(x - 1, y, z))
                ):
                    sealed_opening_count += 1
            elif seal_structure_envelope and _is_air(
                document,
                IntVector3(x - 1, y, z),
            ):
                sealed_opening_count += 1
            if local_x + 1 < dx:
                neighbor = current + 1
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
                elif (
                    allowed is not None
                    and not allowed[neighbor]
                    and _is_air(document, IntVector3(x + 1, y, z))
                ):
                    sealed_opening_count += 1
            elif seal_structure_envelope and _is_air(
                document,
                IntVector3(x + 1, y, z),
            ):
                sealed_opening_count += 1
            if local_z > 0:
                neighbor = current - dx
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
                elif (
                    allowed is not None
                    and not allowed[neighbor]
                    and _is_air(document, IntVector3(x, y, z - 1))
                ):
                    sealed_opening_count += 1
            elif seal_structure_envelope and _is_air(
                document,
                IntVector3(x, y, z - 1),
            ):
                sealed_opening_count += 1
            if local_z + 1 < dz:
                neighbor = current + dx
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
                elif (
                    allowed is not None
                    and not allowed[neighbor]
                    and _is_air(document, IntVector3(x, y, z + 1))
                ):
                    sealed_opening_count += 1
            elif seal_structure_envelope and _is_air(
                document,
                IntVector3(x, y, z + 1),
            ):
                sealed_opening_count += 1
            if local_y > 0:
                neighbor = current - plane
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
                elif (
                    allowed is not None
                    and not allowed[neighbor]
                    and _is_air(document, IntVector3(x, y - 1, z))
                ):
                    sealed_opening_count += 1
            elif seal_structure_envelope and _is_air(
                document,
                IntVector3(x, y - 1, z),
            ):
                sealed_opening_count += 1
            if local_y + 1 < dy:
                neighbor = current + plane
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
                elif (
                    allowed is not None
                    and not allowed[neighbor]
                    and _is_air(document, IntVector3(x, y + 1, z))
                ):
                    sealed_opening_count += 1
            elif seal_structure_envelope and _is_air(
                document,
                IntVector3(x, y + 1, z),
            ):
                sealed_opening_count += 1

        heights = [maximum - minimum + 1 for minimum, maximum in columns.values()]
        volume_result = AirVolume(
            len(result),
            size,
            IntBoundingBox(
                IntVector3(min_x, min_y, min_z),
                IntVector3(max_x, max_y, max_z),
            ),
            exterior,
            len(columns),
            min(heights),
            max(heights),
            seed,
        )
        if seal_structure_envelope:
            volume_result = replace(
                volume_result,
                evidence={
                    **envelope_evidence,
                    "structure_envelope_sealed": True,
                    "sealed_opening_count": sealed_opening_count,
                },
            )
        result.append(volume_result)
    ordered = sorted(result, key=lambda item: (item.exterior, -item.size, item.bounds.min))

    def allowed_air(point: IntVector3) -> bool:
        spans = envelope_spans.get((point.x, point.z), ())
        return any(
            minimum_y <= point.y <= maximum_y
            for minimum_y, maximum_y in spans
        )

    classified = []
    for item in ordered:
        if item.exterior or item.size < 2:
            classified.append(item)
            continue
        evidence = item.evidence
        item = _classify_volume(
            document,
            item,
            allowed_air=allowed_air if seal_structure_envelope else None,
        )
        if evidence:
            item = replace(item, evidence={**item.evidence, **evidence})
        classified.append(item)
    return classified


def classify_air_volumes(
    document: BuildDocument,
    *,
    max_cells: int = 20_000_000,
    seal_structure_envelope: bool = False,
) -> list[AirVolume]:
    """Classify ordinary interiors and optionally recover rooms behind openings.

    Structure mode deliberately preserves all ordinary outside-flood results.
    It then runs the constructed-column envelope as a second pass and accepts
    only plausible room volumes separated by doorway-scale boundaries. This
    avoids replacing trustworthy enclosed rooms with hundreds of façade,
    terrain, and roof micro-voids.
    """

    ordinary = _classify_air_volumes(
        document,
        max_cells=max_cells,
        seal_structure_envelope=False,
    )
    if not seal_structure_envelope:
        return ordinary
    sealed = _classify_air_volumes(
        document,
        max_cells=max_cells,
        seal_structure_envelope=True,
    )
    ordinary_interiors = [
        item
        for item in ordinary
        if not item.exterior and item.size >= 2
    ]

    def covered_by_ordinary(item: AirVolume) -> bool:
        return any(
            existing.bounds.contains(item.bounds.min)
            and existing.bounds.contains(item.bounds.max)
            for existing in ordinary_interiors
        )

    accepted = []
    for item in sealed:
        opening_faces = int(item.evidence.get("sealed_opening_count", 0))
        opening_limit = max(12, math.ceil(item.size * 0.25))
        if (
            item.exterior
            or not item.room_like
            or item.size < 8
            or item.walkable_cell_count < 4
            or item.min_ceiling_height < 2
            or opening_faces <= 0
            or opening_faces > opening_limit
            or covered_by_ordinary(item)
        ):
            continue
        accepted.append(
            replace(
                item,
                evidence={
                    **item.evidence,
                    "automatic_structure_envelope_candidate": True,
                    "opening_face_acceptance_limit": opening_limit,
                    "acceptance_method": (
                        "room-like-covered-volume-with-doorway-scale-opening-v1"
                    ),
                },
            )
        )
    next_id = max((item.volume_id for item in ordinary), default=-1) + 1
    accepted = [
        replace(item, volume_id=next_id + index)
        for index, item in enumerate(
            sorted(accepted, key=lambda row: (-row.size, row.bounds.min))
        )
    ]
    combined = ordinary + accepted
    return sorted(
        combined,
        key=lambda item: (item.exterior, -item.size, item.bounds.min),
    )


def classify_manual_room(
    document: BuildDocument,
    bounds: IntBoundingBox,
    *,
    seed: IntVector3 | None = None,
    room_id: int = 0,
) -> AirVolume:
    """Seed-and-clip an air volume, sealing exits at the requested bounds."""
    clipped = document.bounds.intersection(bounds)
    if clipped is None:
        raise ValueError("manual room bounds do not intersect the document")
    if seed is None:
        seed = next((point for point in clipped.iter_points() if _is_air(document, point)), None)
    if seed is None or not clipped.contains(seed) or not _is_air(document, seed):
        raise ValueError("manual room seed must be an air cell inside the room bounds")
    seen = {seed}
    parents: dict[IntVector3, IntVector3 | None] = {seed: None}
    queue: deque[IntVector3] = deque([seed])
    leak: IntVector3 | None = None
    sealed_openings: set[tuple[IntVector3, IntVector3]] = set()
    columns: dict[tuple[int, int], tuple[int, int]] = {}
    while queue:
        point = queue.popleft()
        previous = columns.get((point.x, point.z))
        columns[(point.x, point.z)] = (
            (point.y, point.y)
            if previous is None
            else (min(previous[0], point.y), max(previous[1], point.y))
        )
        for offset in _NEIGHBORS:
            neighbor = point + offset
            if not clipped.contains(neighbor):
                if _is_air(document, neighbor):
                    sealed_openings.add((point, neighbor))
                    if leak is None:
                        leak = point
                continue
            if neighbor in seen or not _is_air(document, neighbor):
                continue
            seen.add(neighbor)
            parents[neighbor] = point
            queue.append(neighbor)
    leak_path: list[tuple[int, int, int]] = []
    cursor = leak
    while cursor is not None:
        leak_path.append(cursor.as_tuple())
        cursor = parents.get(cursor)
    leak_path.reverse()
    heights = [maximum - minimum + 1 for minimum, maximum in columns.values()]
    base = AirVolume(
        room_id,
        len(seen),
        IntBoundingBox(
            IntVector3(
                min(point.x for point in seen),
                min(point.y for point in seen),
                min(point.z for point in seen),
            ),
            IntVector3(
                max(point.x for point in seen),
                max(point.y for point in seen),
                max(point.z for point in seen),
            ),
        ),
        False,
        len(columns),
        min(heights),
        max(heights),
        seed,
    )
    classified = _classify_volume(document, base)
    return AirVolume(
        classified.volume_id,
        classified.size,
        classified.bounds,
        classified.exterior,
        classified.floor_area,
        classified.min_ceiling_height,
        classified.max_ceiling_height,
        classified.seed,
        classified.classification,
        classified.classification_confidence,
        classified.architectural_score,
        classified.natural_score,
        classified.decorative_void_score,
        classified.room_like,
        classified.walkable_cell_count,
        {
            **classified.evidence,
            "manual_seed_and_clip": True,
            "requested_bounds": {
                "min": clipped.min.as_tuple(),
                "max": clipped.max.as_tuple(),
            },
            "sealed_opening_count": len(sealed_openings),
            "leak_detected": leak is not None,
            "leak_path": leak_path[:500],
            "leak_path_truncated": len(leak_path) > 500,
        },
    )


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
    room_payloads = [asdict(item) for item in interiors]
    for payload in room_payloads:
        payload["furnishing"] = payload.get("evidence", {}).get("furnishing", {})
    return {
        "analysisSkipped": not volumes and expanded_volume > max_cells,
        "enclosedSpaceCount": len(interiors),
        "interiorVolumeCount": len(interiors),
        "roomLikeCount": sum(item.room_like for item in interiors),
        "classificationCounts": dict(sorted(Counter(item.classification for item in interiors).items())),
        "rooms": room_payloads,
    }
