from __future__ import annotations

import math
from collections import Counter, deque
from dataclasses import asdict, dataclass, field
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
    "bluet",
    "orchid",
    "tulip",
    "dandelion",
    "poppy",
    "allium",
    "cornflower",
    "daisy",
    "rose",
    "lilac",
    "peony",
    "sunflower",
    "torchflower",
    "pitcher_plant",
    "pink_petals",
    "spore_blossom",
    "seagrass",
    "kelp",
    "sugar_cane",
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
    structure_kind: str = "building"
    classification_evidence: dict[str, Any] = field(default_factory=dict)
    room_count: int | None = None
    method: str = "above-terrain-connectivity-evidence-v2"


def block_classification_report(
    document: BuildDocument,
    *,
    counts: Counter[str] | None = None,
    streaming: dict[str, Any] | None = None,
    thresholds: dict[str, Any] | None = None,
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
        "method": "state-plus-cluster-context-evidence-v2",
        "classes": ("terrain", "terrain_detail", "built", "vegetation", "prop"),
        "counts": dict(sorted(counts.items())),
        "stateClassifications": dict(sorted(state_classes.items())),
        "coordinateLabelRule": (
            "Plants use state identity. Crafted forms are resolved per spatial "
            "cluster using terrain-relative verticality, enclosure, regularity, "
            "and surface embedding; material identity alone never decides."
        ),
        "thresholds": thresholds or {
            "surfaceEmbeddingDistanceBlocks": 2,
            "coreColumnVerticalSpanBlocks": 3,
            "buildingEnclosureMinimum": 0.05,
            "buildingRegularityMinimum": 0.35,
            "mapFootprintMergeWarningRatio": 0.75,
        },
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
    classification_config: dict[str, Any] | None = None,
) -> tuple[list[StructureRecord], dict[str, Any]]:
    """Separate structures by connectivity above a terrain-surface reference."""
    if window_edge < 8:
        raise ValueError("analysis window edge must be at least 8 blocks")
    thresholds = {
        "surfaceEmbeddingDistanceBlocks": 2,
        "coreColumnVerticalSpanBlocks": 3,
        "buildingEnclosureMinimum": 0.05,
        "buildingRegularityMinimum": 0.35,
        "mapFootprintMergeWarningRatio": 0.75,
    }
    if classification_config:
        unknown = sorted(set(classification_config) - set(thresholds))
        if unknown:
            raise ValueError(
                "unknown structure classification thresholds: "
                + ", ".join(unknown)
            )
        thresholds.update(classification_config)
    surface_distance = int(thresholds["surfaceEmbeddingDistanceBlocks"])
    core_span = int(thresholds["coreColumnVerticalSpanBlocks"])
    enclosure_minimum = float(thresholds["buildingEnclosureMinimum"])
    regularity_minimum = float(thresholds["buildingRegularityMinimum"])
    footprint_warning = float(thresholds["mapFootprintMergeWarningRatio"])
    palette = document.palette_by_id()
    state_classes = {
        entry.palette_id: classify_block_name(entry.block_name)
        for entry in document.palette
    }
    solid_top: dict[tuple[int, int], int] = {}
    for position, palette_id in document.blocks.items():
        if not palette[palette_id].is_air_like:
            column = (position.x, position.z)
            solid_top[column] = max(position.y, solid_top.get(column, position.y))
    terrain_top: dict[tuple[int, int], int] = {}
    for (x, z), top in solid_top.items():
        neighbors = [
            solid_top[(x + dx, z + dz)]
            for dx in (-1, 0, 1)
            for dz in (-1, 0, 1)
            if (dx or dz) and (x + dx, z + dz) in solid_top
        ]
        terrain_top[(x, z)] = int(median(neighbors)) if neighbors else top

    crafted_columns: dict[tuple[int, int], list[IntVector3]] = {}
    vegetation_columns: dict[tuple[int, int], list[IntVector3]] = {}
    classification_counts: Counter[str] = Counter()
    window_counts: Counter[tuple[int, int]] = Counter()
    for position, palette_id in document.blocks.items():
        entry = palette[palette_id]
        if entry.is_air_like:
            continue
        category = state_classes[palette_id]
        local_surface = terrain_top.get((position.x, position.z), position.y)
        cavity_boundary = (
            category == "terrain"
            and position.y < solid_top.get((position.x, position.z), position.y) - 2
            and any(
                IntVector3(position.x + dx, position.y, position.z + dz)
                not in document.blocks
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
            )
        )
        geometric_terrain_candidate = (
            category == "terrain"
            and (
                position.y > local_surface + max(0, surface_distance - 1)
                or cavity_boundary
            )
        )
        if category == "built":
            classification_counts["terrain_detail"] += 1
            crafted_columns.setdefault((position.x, position.z), []).append(position)
        elif geometric_terrain_candidate:
            classification_counts[category] += 1
            crafted_columns.setdefault((position.x, position.z), []).append(position)
        else:
            classification_counts[category] += 1
        if category == "vegetation" and any(
            token in entry.block_name
            for token in ("log", "wood", "leaves", "stem", "mangrove_roots")
        ):
            vegetation_columns.setdefault((position.x, position.z), []).append(position)
        window_counts[
            (
                (position.x - document.bounds.min.x) // window_edge,
                (position.z - document.bounds.min.z) // window_edge,
            )
        ] += 1
    streaming = {
        "method": "terrain-reference-plus-column-connectivity-v2",
        "windowEdgeBlocks": window_edge,
        "windowCount": len(window_counts),
        "peakPlacedBlocksInWindow": max(window_counts.values(), default=0),
        "processedPlacedBlocks": sum(classification_counts.values()),
        "additionalCoordinateClassificationMap": False,
        "persistentDetectionState": (
            "terrain tops plus crafted/structural-vegetation columns; no "
            "document-sized Python coordinate label map"
        ),
        "completed": True,
    }

    def components_for(
        columns: set[tuple[int, int]],
        radius: int,
    ) -> list[set[tuple[int, int]]]:
        offsets = [
            (dx, dz)
            for dx in range(-radius, radius + 1)
            for dz in range(-radius, radius + 1)
            if max(abs(dx), abs(dz)) <= radius
        ]
        unseen = set(columns)
        components: list[set[tuple[int, int]]] = []
        for start in sorted(unseen):
            if start not in unseen:
                continue
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
        return components

    core_columns = {
        column
        for column, points in crafted_columns.items()
        if (
            max(point.y for point in points) - min(point.y for point in points) >= core_span - 1
            or max(point.y for point in points)
            > terrain_top.get(column, max(point.y for point in points)) + surface_distance
            or min(point.y for point in points)
            < terrain_top.get(column, min(point.y for point in points)) - surface_distance
            or any(
                point.y > document.bounds.min.y + 1
                and IntVector3(point.x, point.y - 1, point.z)
                not in document.blocks
                for point in points
            )
        )
    }
    components = components_for(core_columns, separation)

    # Floor plates and thin trim inherit the envelope of nearby vertical cores,
    # but a map-wide surface skin outside that envelope cannot bridge objects.
    assigned: set[tuple[int, int]] = set()
    for component in components:
        min_x = min(point[0] for point in component) - 1
        max_x = max(point[0] for point in component) + 1
        min_z = min(point[1] for point in component) - 1
        max_z = max(point[1] for point in component) + 1
        additions = {
            column
            for column in crafted_columns
            if min_x <= column[0] <= max_x
            and min_z <= column[1] <= max_z
            and column not in assigned
        }
        component.update(additions)
        assigned.update(additions)

    vegetation_components = components_for(set(vegetation_columns), 1)

    records: list[StructureRecord] = []
    names = names or {}
    candidates = [
        (component, "crafted")
        for component in components
    ] + [
        (component, "vegetation")
        for component in vegetation_components
    ]
    merge_split_diagnostics: list[dict[str, Any]] = []
    for component, source_kind in candidates:
        source_columns = (
            crafted_columns if source_kind == "crafted" else vegetation_columns
        )
        built_points = [
            point for column in component for point in source_columns.get(column, ())
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
        candidate_points = set(built_points)
        points = (
            [
                position
                for position, palette_id in document.blocks.items()
                if preliminary.contains(position)
                and (
                    position in candidate_points
                    or state_classes[palette_id] == "prop"
                )
            ]
            if source_kind == "crafted"
            else [
                position
                for position, palette_id in document.blocks.items()
                if preliminary.contains(position)
                and state_classes[palette_id] == "vegetation"
            ]
        )
        if not points:
            continue
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
            column: min(source_columns[column], key=lambda point: point.y)
            for column in component
            if source_columns.get(column)
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
        surface_embedded = sum(
            abs(point.y - terrain_top.get((point.x, point.z), point.y))
            <= surface_distance
            for point in built_points
        ) / max(1, len(built_points))
        verticality = dimensions.y / max(1, max(dimensions.x, dimensions.z))
        columns = set(component)
        neighbor_hits = sum(
            sum(
                (x + dx, z + dz) in columns
                for dx, dz in ((1, 0), (-1, 0), (0, 1), (0, -1))
            )
            for x, z in columns
        )
        regularity = neighbor_hits / max(1, len(columns) * 4)
        by_y: dict[int, set[tuple[int, int]]] = {}
        for point in built_points:
            by_y.setdefault(point.y, set()).add((point.x, point.z))
        enclosure_pairs = 0
        possible_pairs = 0
        for layer in by_y.values():
            rows: dict[int, list[int]] = {}
            columns_by_x: dict[int, list[int]] = {}
            for x, z in layer:
                rows.setdefault(z, []).append(x)
                columns_by_x.setdefault(x, []).append(z)
            for values in (*rows.values(), *columns_by_x.values()):
                possible_pairs += 1
                if max(values) - min(values) >= 3 and len(values) >= 2:
                    enclosure_pairs += 1
        enclosure = enclosure_pairs / max(1, possible_pairs)
        aspect = max(dimensions.x, dimensions.z) / max(
            1,
            min(dimensions.x, dimensions.z),
        )
        prop_count = sum(state_classes[document.blocks[point]] == "prop" for point in points)
        architectural_ratio = sum(
            any(
                token in palette[document.blocks[point]].block_name
                for token in (
                    "planks",
                    "glass",
                    "door",
                    "window",
                    "wool",
                    "concrete",
                    "terracotta",
                )
            )
            for point in built_points
        ) / max(1, len(built_points))
        if source_kind == "vegetation":
            structure_kind = "vegetation"
        elif (
            enclosure >= enclosure_minimum
            or prop_count > 0
            or architectural_ratio >= 0.05
            or (
                regularity >= regularity_minimum
                and aspect >= 2.0
                and verticality >= 0.05
            )
        ):
            structure_kind = "building"
        else:
            structure_kind = "rock_formation"
        evidence = {
            "verticality": round(verticality, 6),
            "enclosure": round(enclosure, 6),
            "regularity": round(regularity, 6),
            "surface_embedding": round(surface_embedded, 6),
            "architectural_material_ratio": round(architectural_ratio, 6),
            "terrain_reference_column_count": sum(
                column in terrain_top for column in component
            ),
            "decision": structure_kind,
        }
        if structure_kind == "building":
            promoted = Counter(
                state_classes[document.blocks[point]]
                for point in built_points
            )
            for original, count in promoted.items():
                source_class = (
                    "terrain_detail" if original == "built" else original
                )
                classification_counts[source_class] -= count
                classification_counts["built"] += count
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
                len(built_points) if structure_kind == "building" else 0,
                prop_count,
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
                structure_kind,
                evidence,
            )
        )
        footprint_ratio = (
            dimensions.x
            * dimensions.z
            / max(1, document.bounds.dimensions.x * document.bounds.dimensions.z)
        )
        if footprint_ratio >= footprint_warning:
            merge_split_diagnostics.append(
                {
                    "code": "STRUCTURE_MAP_FOOTPRINT_WARNING",
                    "structure_id": structure_id,
                    "footprint_ratio": round(footprint_ratio, 6),
                    "action": "review-merge-or-split",
                }
            )
    records.sort(key=lambda item: (-item.block_count, item.bounds.min))
    streaming["mergeSplitDiagnostics"] = merge_split_diagnostics
    streaming["structureCountByKind"] = dict(
        sorted(Counter(item.structure_kind for item in records).items())
    )
    return records, block_classification_report(
        document,
        counts=classification_counts,
        streaming=streaming,
        thresholds=thresholds,
    )


def structure_inventory_payload(
    document: BuildDocument,
    *,
    separation: int = 2,
    minimum_blocks: int = 24,
    names: dict[str, str] | None = None,
    window_edge: int = 64,
    classification_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    structures, classification = detect_structures(
        document,
        separation=separation,
        minimum_blocks=minimum_blocks,
        names=names,
        window_edge=window_edge,
        classification_config=classification_config,
    )
    return {
        "schema": "mbi.structure-inventory.v1",
        "content_hash": document.content_hash,
        "method": "above-terrain-connectivity-evidence-v2",
        "configuration": {
            "column_separation": separation,
            "minimum_built_blocks": minimum_blocks,
            "analysis_window_edge_blocks": window_edge,
            "classification_thresholds": classification_config or {},
        },
        "classification": classification,
        "structureCount": len(structures),
        "structureCountByKind": dict(
            sorted(Counter(item.structure_kind for item in structures).items())
        ),
        "structures": [asdict(item) for item in structures],
    }
