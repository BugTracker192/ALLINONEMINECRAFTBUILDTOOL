from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import asdict, dataclass
from hashlib import sha256
from statistics import median
from typing import Any

from ..canonical import BuildDocument, IntBoundingBox, IntVector3

_VEGETATION = (
    "azalea",
    "bamboo",
    "cactus",
    "fern",
    "flower",
    "grass",
    "leaves",
    "lily",
    "log",
    "mushroom",
    "roots",
    "sapling",
    "stem",
    "vine",
)
_TERRAIN = (
    "andesite",
    "basalt",
    "calcite",
    "clay",
    "deepslate",
    "diorite",
    "dirt",
    "dripstone",
    "granite",
    "gravel",
    "ice",
    "mud",
    "mycelium",
    "netherrack",
    "ore",
    "sand",
    "snow",
    "stone",
    "tuff",
    "water",
)
_PROP = (
    "anvil",
    "armor_stand",
    "banner",
    "barrel",
    "bed",
    "brewing_stand",
    "button",
    "campfire",
    "candle",
    "carpet",
    "cauldron",
    "chest",
    "crafting_table",
    "flower_pot",
    "furnace",
    "grindstone",
    "head",
    "lantern",
    "lever",
    "loom",
    "painting",
    "pressure_plate",
    "sign",
    "skull",
    "smithing_table",
    "smoker",
    "stonecutter",
    "torch",
)
_CONSTRUCTED = (
    "brick",
    "concrete",
    "copper",
    "door",
    "fence",
    "glass",
    "ladder",
    "planks",
    "polished",
    "quartz",
    "railing",
    "shingle",
    "slab",
    "stairs",
    "terracotta",
    "tiles",
    "trapdoor",
    "wall",
    "wool",
)


def classify_block_name(block_name: str) -> str:
    """Classify a base block ID by architectural role.

    More specific crafted forms deliberately take precedence over material
    substrings.  For example, ``bamboo_trapdoor`` is constructed rather than
    vegetation, and ``sandstone_wall`` is constructed rather than terrain.
    """
    if block_name in {
        "dirt_path",
        "grass_block",
        "moss_block",
        "mycelium",
        "podzol",
    }:
        return "terrain"
    if any(token in block_name for token in _PROP):
        return "prop"
    if block_name.startswith("stripped_") or block_name.endswith("_wood"):
        return "built"
    if any(token in block_name for token in _CONSTRUCTED):
        return "built"
    if any(token in block_name for token in _VEGETATION):
        return "vegetation"
    if any(token in block_name for token in _TERRAIN):
        return "terrain"
    return "built"


@dataclass(frozen=True, slots=True)
class StructureRecord:
    structure_id: str
    name: str | None
    bounds: IntBoundingBox
    volume: int
    block_count: int
    built_block_count: int
    prop_block_count: int
    palette_summary: dict[str, int]
    storey_count_estimate: int
    style_class: str
    proportions: dict[str, float]
    roof_pitch_estimate_degrees: float | None
    trim_block_ratio: float
    foundation_contact_ratio: float
    buried_block_ratio: float
    floating_bottom_column_count: int
    confidence: float
    room_count: int | None = None
    method: str = "built-column-density-clustering-v1"


def block_classification_report(
    document: BuildDocument,
    *,
    counts: Counter[str] | None = None,
    streaming: dict[str, Any] | None = None,
) -> dict[str, Any]:
    state_classes = {
        entry.canonical_state: classify_block_name(entry.block_name)
        for entry in document.palette
        if not entry.is_air_like
    }
    palette = document.palette_by_id()
    if counts is None:
        counts = Counter(
            classify_block_name(palette[palette_id].block_name)
            for palette_id in document.blocks.values()
            if not palette[palette_id].is_air_like
        )
    return {
        "method": "state-and-material-profile-v1",
        "classes": ("terrain", "built", "vegetation", "prop"),
        "counts": dict(sorted(counts.items())),
        "stateClassifications": dict(sorted(state_classes.items())),
        "coordinateLabelRule": "Each coordinate inherits its exact canonical state's classification.",
        "streaming": streaming,
    }


def _style_class(counts: Counter[str]) -> str:
    names = " ".join(counts)
    if any(token in names for token in ("deepslate", "blackstone", "dark_oak")):
        return "dark-medieval"
    if any(token in names for token in ("quartz", "concrete", "iron_block")):
        return "formal-modern"
    if any(token in names for token in ("sandstone", "terracotta", "mud_brick")):
        return "earthen"
    if any(token in names for token in ("planks", "log", "wood")):
        return "timber-vernacular"
    if any(token in names for token in ("stone_brick", "cobblestone", "brick")):
        return "masonry"
    return "mixed"


def roof_pitch_estimate_degrees(
    document: BuildDocument,
    points: list[IntVector3],
) -> float | None:
    palette = document.palette_by_id()
    roof_tops: dict[tuple[int, int], int] = {}
    for point in points:
        block_name = palette[document.blocks[point]].block_name
        if not any(
            token in block_name
            for token in (
                "shingle",
                "slab",
                "stairs",
                "tile",
                "trapdoor",
            )
        ):
            continue
        column = (point.x, point.z)
        roof_tops[column] = max(
            point.y,
            roof_tops.get(column, point.y),
        )
    rises = []
    for (x, z), y in roof_tops.items():
        for neighbor in ((x + 1, z), (x, z + 1)):
            if neighbor not in roof_tops:
                continue
            rise = abs(roof_tops[neighbor] - y)
            if 0 < rise <= 4:
                rises.append(rise)
    if not rises:
        return None
    return round(math.degrees(math.atan(float(median(rises)))), 3)


def detect_structures(
    document: BuildDocument,
    *,
    separation: int = 2,
    minimum_blocks: int = 24,
    names: dict[str, str] | None = None,
    window_edge: int = 64,
) -> tuple[list[StructureRecord], dict[str, Any]]:
    """Cluster structures using a streamed classification and dense columns.

    Classification is consumed once and aggregated by spatial window; no
    document-sized coordinate-to-class map is created.  The persistent
    detection state contains only constructed columns required by the
    separation/enclosure algorithm.
    """
    if window_edge < 8:
        raise ValueError("analysis window edge must be at least 8 blocks")
    palette = document.palette_by_id()
    built_columns: dict[tuple[int, int], list[IntVector3]] = {}
    classification_counts: Counter[str] = Counter()
    window_counts: Counter[tuple[int, int]] = Counter()
    for position, palette_id in document.blocks.items():
        entry = palette[palette_id]
        if entry.is_air_like:
            continue
        category = classify_block_name(entry.block_name)
        classification_counts[category] += 1
        window_counts[
            (
                (position.x - document.bounds.min.x) // window_edge,
                (position.z - document.bounds.min.z) // window_edge,
            )
        ] += 1
        if category == "built":
            built_columns.setdefault((position.x, position.z), []).append(position)
    streaming = {
        "method": "single-pass-spatial-window-aggregation-v1",
        "windowEdgeBlocks": window_edge,
        "windowCount": len(window_counts),
        "peakPlacedBlocksInWindow": max(window_counts.values(), default=0),
        "processedPlacedBlocks": sum(classification_counts.values()),
        "additionalCoordinateClassificationMap": False,
        "persistentDetectionState": "constructed-column coordinates only",
        "completed": True,
    }
    core_columns = {
        column
        for column, points in built_columns.items()
        if len(points) >= 2
        or max(point.y for point in points) - min(point.y for point in points) >= 2
    }
    offsets = [
        (dx, dz)
        for dx in range(-separation, separation + 1)
        for dz in range(-separation, separation + 1)
        if max(abs(dx), abs(dz)) <= separation
    ]
    components: list[set[tuple[int, int]]] = []
    unseen = set(core_columns)
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        queue = deque([start])
        component = {start}
        while queue:
            x, z = queue.popleft()
            for dx, dz in offsets:
                neighbor = (x + dx, z + dz)
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    component.add(neighbor)
                    queue.append(neighbor)
        components.append(component)

    # Attach one-layer trim/roof columns to the nearest dense component.
    for column in sorted(set(built_columns) - core_columns):
        candidates = [
            (max(abs(column[0] - point[0]), abs(column[1] - point[1])), index)
            for index, component in enumerate(components)
            for point in component
            if max(abs(column[0] - point[0]), abs(column[1] - point[1]))
            <= separation + 1
        ]
        if candidates:
            _, index = min(candidates)
            components[index].add(column)

    # A floor plate, facade shell, and roof can be distinct dense column
    # components while clearly occupying the same building envelope. Merge
    # strongly overlapping envelopes before computing records.
    merged = True
    while merged:
        merged = False
        for left_index in range(len(components)):
            left = components[left_index]
            left_box = (
                min(point[0] for point in left),
                max(point[0] for point in left),
                min(point[1] for point in left),
                max(point[1] for point in left),
            )
            for right_index in range(left_index + 1, len(components)):
                right = components[right_index]
                right_box = (
                    min(point[0] for point in right),
                    max(point[0] for point in right),
                    min(point[1] for point in right),
                    max(point[1] for point in right),
                )
                overlap_x = max(
                    0,
                    min(left_box[1], right_box[1])
                    - max(left_box[0], right_box[0])
                    + 1,
                )
                overlap_z = max(
                    0,
                    min(left_box[3], right_box[3])
                    - max(left_box[2], right_box[2])
                    + 1,
                )
                overlap = overlap_x * overlap_z
                left_area = (left_box[1] - left_box[0] + 1) * (
                    left_box[3] - left_box[2] + 1
                )
                right_area = (right_box[1] - right_box[0] + 1) * (
                    right_box[3] - right_box[2] + 1
                )
                if overlap / max(1, min(left_area, right_area)) >= 0.2:
                    components[left_index] = left | right
                    components.pop(right_index)
                    merged = True
                    break
            if merged:
                break

    records: list[StructureRecord] = []
    names = names or {}
    for component in components:
        built_points = [
            point for column in component for point in built_columns.get(column, ())
        ]
        if len(built_points) < minimum_blocks:
            continue
        preliminary = IntBoundingBox(
            IntVector3(
                min(point.x for point in built_points),
                min(point.y for point in built_points),
                min(point.z for point in built_points),
            ),
            IntVector3(
                max(point.x for point in built_points),
                max(point.y for point in built_points),
                max(point.z for point in built_points),
            ),
        )
        points = [
            position
            for position, palette_id in document.blocks.items()
            if preliminary.contains(position)
            and classify_block_name(palette[palette_id].block_name)
            in {"built", "prop"}
        ]
        bounds = IntBoundingBox(
            IntVector3(
                min(point.x for point in points),
                min(point.y for point in points),
                min(point.z for point in points),
            ),
            IntVector3(
                max(point.x for point in points),
                max(point.y for point in points),
                max(point.z for point in points),
            ),
        )
        states = Counter(
            palette[document.blocks[point]].canonical_state.split("[", 1)[0]
            for point in points
        )
        bottom_by_column = {
            column: min(built_columns[column], key=lambda point: point.y)
            for column in component
            if built_columns.get(column)
        }
        contacting = 0
        floating = 0
        for point in bottom_by_column.values():
            below = IntVector3(point.x, point.y - 1, point.z)
            if below in document.blocks:
                contacting += 1
            else:
                floating += 1
        buried = sum(
            sum(
                (
                    (neighbor := IntVector3(
                        point.x + dx,
                        point.y,
                        point.z + dz,
                    ))
                    in document.blocks
                    and classify_block_name(
                        palette[document.blocks[neighbor]].block_name
                    )
                    == "terrain"
                )
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
            )
            >= 3
            for point in points
        )
        significant_layers = Counter(point.y for point in built_points)
        peak = max(significant_layers.values(), default=1)
        floor_candidates = [
            y for y, count in significant_layers.items() if count >= max(4, peak * 0.35)
        ]
        floor_groups = 0
        previous: int | None = None
        for y in sorted(floor_candidates):
            if previous is None or y > previous + 1:
                floor_groups += 1
            previous = y
        fingerprint = (
            f"{bounds.min.as_tuple()}|{bounds.max.as_tuple()}|"
            f"{round((bounds.min.x + bounds.max.x) / 2)}|"
            f"{round((bounds.min.z + bounds.max.z) / 2)}"
        )
        structure_id = "structure_" + sha256(fingerprint.encode()).hexdigest()[:12]
        density = len(built_points) / max(1, bounds.volume)
        dimensions = bounds.dimensions
        trim_count = sum(
            any(
                token
                in palette[document.blocks[point]].block_name
                for token in (
                    "fence",
                    "slab",
                    "stairs",
                    "trapdoor",
                    "wall",
                )
            )
            for point in points
        )
        records.append(
            StructureRecord(
                structure_id,
                names.get(structure_id),
                bounds,
                bounds.volume,
                len(points),
                sum(
                    classify_block_name(
                        palette[document.blocks[point]].block_name
                    )
                    == "built"
                    for point in points
                ),
                sum(
                    classify_block_name(
                        palette[document.blocks[point]].block_name
                    )
                    == "prop"
                    for point in points
                ),
                dict(states.most_common(12)),
                max(1, floor_groups),
                _style_class(states),
                {
                    "width_to_height": round(
                        dimensions.x / max(1, dimensions.y),
                        6,
                    ),
                    "length_to_height": round(
                        dimensions.z / max(1, dimensions.y),
                        6,
                    ),
                    "footprint_aspect_ratio": round(
                        max(dimensions.x, dimensions.z)
                        / max(1, min(dimensions.x, dimensions.z)),
                        6,
                    ),
                },
                roof_pitch_estimate_degrees(document, points),
                round(trim_count / max(1, len(points)), 6),
                round(contacting / max(1, len(bottom_by_column)), 6),
                round(buried / max(1, len(points)), 6),
                floating,
                round(min(1.0, 0.55 + min(0.35, density * 5.0)), 6),
            )
        )
    records.sort(key=lambda item: (-item.block_count, item.bounds.min))
    return records, block_classification_report(
        document,
        counts=classification_counts,
        streaming=streaming,
    )


def structure_inventory_payload(
    document: BuildDocument,
    *,
    separation: int = 2,
    minimum_blocks: int = 24,
    names: dict[str, str] | None = None,
    window_edge: int = 64,
) -> dict[str, Any]:
    structures, classification = detect_structures(
        document,
        separation=separation,
        minimum_blocks=minimum_blocks,
        names=names,
        window_edge=window_edge,
    )
    return {
        "schema": "mbi.structure-inventory.v1",
        "content_hash": document.content_hash,
        "method": "built-density-enclosure-separation-v1",
        "configuration": {
            "column_separation": separation,
            "minimum_built_blocks": minimum_blocks,
            "analysis_window_edge_blocks": window_edge,
        },
        "classification": classification,
        "structureCount": len(structures),
        "structures": [asdict(item) for item in structures],
    }
