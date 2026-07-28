from __future__ import annotations

import math
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

import numpy as np
from mbi.canonical import BuildDocument, IntVector3

from app.render.semantic import load_map

from .model import FeatureCandidate, RoomCameraChoice, RoomGeometry

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
_PROFILE_THRESHOLDS: dict[str, dict[str, float]] = {
    "physical_first_person": {
        "min_room_pixel_ratio": 0.12,
        "max_dominant_coordinate_ratio": 0.78,
        "min_depth_spread": 0.30,
    },
    "physical_third_person": {
        "min_room_pixel_ratio": 0.10,
        "max_dominant_coordinate_ratio": 0.78,
        "min_depth_spread": 0.25,
    },
    "feature_closeup": {
        "min_room_pixel_ratio": 0.08,
        "max_dominant_coordinate_ratio": 0.84,
        "min_depth_spread": 0.18,
    },
    "room_coverage": {
        "min_room_pixel_ratio": 0.18,
        "max_dominant_coordinate_ratio": 0.68,
        "min_depth_spread": 0.35,
    },
    "third_person_cutaway": {
        "min_room_pixel_ratio": 0.15,
        "max_dominant_coordinate_ratio": 0.72,
        "min_depth_spread": 0.25,
    },
    "roof_off": {
        "min_room_pixel_ratio": 0.14,
        "max_dominant_coordinate_ratio": 0.72,
        "min_depth_spread": 0.20,
    },
    "presentation": {
        "min_room_pixel_ratio": 0.20,
        "max_dominant_coordinate_ratio": 0.62,
        "min_depth_spread": 0.40,
    },
}


@dataclass(frozen=True, slots=True)
class FrameQuality:
    accepted: bool
    profile: str
    score: float
    rejection_reasons: tuple[str, ...]
    occupied_pixel_ratio: float
    room_pixel_ratio: float
    room_boundary_pixel_ratio: float
    unrelated_terrain_pixel_ratio: float
    visible_floor_ratio: float
    visible_ceiling_ratio: float
    visible_wall_count: int
    visible_opening_count: int
    visible_feature_ratio: float
    dominant_coordinate_ratio: float
    dominant_plane_ratio: float
    dominant_material_ratio: float
    depth_percentiles: tuple[float, float, float]
    depth_spread: float
    depth_entropy: float
    material_entropy: float
    edge_density: float
    foreground_obstruction_ratio: float
    background_ratio: float
    clipped_triangle_count: int
    fallback_model_pixel_ratio: float
    visible_room_coordinate_ratio: float
    visible_coordinate_count: int
    visible_feature_count: int
    camera_visible_sample_ratio: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _entropy(counts: Iterable[int]) -> float:
    values = np.asarray(list(counts), dtype=np.float64)
    total = float(values.sum())
    if total <= 0:
        return 0.0
    probabilities = values[values > 0] / total
    return float(-(probabilities * np.log2(probabilities)).sum())


def evaluate_frame(
    semantic_metadata_path: str | Path,
    geometry: RoomGeometry,
    features: list[FeatureCandidate],
    choice: RoomCameraChoice,
    *,
    document: BuildDocument | None = None,
    profile: str = "physical_first_person",
    min_room_coverage: float | None = None,
    max_obstruction: float | None = None,
    diagnostics: dict[str, Any] | None = None,
) -> FrameQuality:
    """Measure whether a render actually communicates the selected interior."""
    metadata_path = Path(semantic_metadata_path)
    occupancy = load_map(metadata_path, "occupancy").astype(bool)
    coordinates = load_map(metadata_path, "coordinate")
    depth = load_map(metadata_path, "depth")
    palette_map = load_map(metadata_path, "palette")
    normals = load_map(metadata_path, "normal")
    issues = load_map(metadata_path, "issue")
    pixel_count = max(1, occupancy.size)
    occupied_count = int(occupancy.sum())
    occupied_ratio = occupied_count / pixel_count

    coordinate_counts: Counter[tuple[int, int, int]] = Counter()
    if occupied_count:
        coordinate_counts.update((int(row[0]), int(row[1]), int(row[2])) for row in coordinates[occupancy])
    visible = {IntVector3(*coordinate) for coordinate in coordinate_counts}
    visible_room = visible & set(geometry.boundary)
    room_pixel_count = sum(
        count
        for coordinate, count in coordinate_counts.items()
        if IntVector3(*coordinate) in geometry.boundary
    )
    room_pixel_ratio = room_pixel_count / max(1, occupied_count)
    room_coordinate_ratio = len(visible_room) / max(1, len(geometry.boundary))
    dominant_ratio = max(coordinate_counts.values(), default=0) / max(1, occupied_count)

    finite_depth = depth[occupancy & np.isfinite(depth)]
    if finite_depth.size:
        p10 = float(np.percentile(finite_depth, 10))
        p50 = float(np.percentile(finite_depth, 50))
        p90 = float(np.percentile(finite_depth, 90))
        depth_percentiles = (round(p10, 6), round(p50, 6), round(p90, 6))
        depth_spread = p90 - p10
        histogram = np.histogram(finite_depth, bins=min(32, max(4, int(math.sqrt(finite_depth.size)))))[0]
        depth_entropy = _entropy(int(value) for value in histogram)
        foreground = occupancy & np.isfinite(depth) & (depth <= p10)
    else:
        depth_percentiles = (0.0, 0.0, 0.0)
        depth_spread = 0.0
        depth_entropy = 0.0
        foreground = np.zeros_like(occupancy)

    palette_counts = Counter(int(value) for value in palette_map[occupancy])
    dominant_material_ratio = max(palette_counts.values(), default=0) / max(1, occupied_count)
    material_entropy = _entropy(palette_counts.values())
    normal_counts = Counter(tuple(int(value) for value in row) for row in normals[occupancy])
    dominant_plane_ratio = max(normal_counts.values(), default=0) / max(1, occupied_count)

    feature_coordinates = {item.coordinate for item in features}
    visible_feature_count = len(visible & feature_coordinates)
    visible_feature_ratio = visible_feature_count / max(1, len(feature_coordinates))
    visible_floor_ratio = len(visible & set(geometry.floor)) / max(1, len(geometry.floor))
    visible_ceiling_ratio = len(visible & set(geometry.ceiling)) / max(1, len(geometry.ceiling))
    visible_wall_count = sum(
        bool(visible & set(geometry.boundary_classes.get(name, frozenset())))
        for name in ("north_wall", "south_wall", "east_wall", "west_wall")
    )
    visible_opening_count = len(visible & set(geometry.openings))

    unrelated_terrain_pixels = 0
    if document is not None:
        palette = document.palette_by_id()
        room_boundary = set(geometry.boundary)
        for coordinate, count in coordinate_counts.items():
            point = IntVector3(*coordinate)
            palette_id = document.blocks.get(point)
            if point in room_boundary or palette_id is None:
                continue
            if any(token in palette[palette_id].block_name for token in _NATURAL_TOKENS):
                unrelated_terrain_pixels += count
    unrelated_terrain_ratio = unrelated_terrain_pixels / max(1, occupied_count)

    horizontal_edges = np.any(coordinates[:, 1:] != coordinates[:, :-1], axis=2)
    vertical_edges = np.any(coordinates[1:, :] != coordinates[:-1, :], axis=2)
    edge_density = (int(horizontal_edges.sum()) + int(vertical_edges.sum())) / max(
        1, horizontal_edges.size + vertical_edges.size
    )
    foreground_counts = Counter((int(row[0]), int(row[1]), int(row[2])) for row in coordinates[foreground])
    foreground_obstruction_ratio = max(foreground_counts.values(), default=0) / max(1, int(foreground.sum()))
    fallback_model_pixel_ratio = int((issues[occupancy] == 1).sum()) / max(1, occupied_count)
    clipped_triangle_count = int((diagnostics or {}).get("triangles_clipped", 0))

    thresholds = _PROFILE_THRESHOLDS.get(profile, _PROFILE_THRESHOLDS["physical_first_person"])
    minimum_room = thresholds["min_room_pixel_ratio"] if min_room_coverage is None else min_room_coverage
    maximum_obstruction = (
        thresholds["max_dominant_coordinate_ratio"] if max_obstruction is None else max_obstruction
    )
    reasons: list[str] = []
    if occupied_ratio < 0.04:
        reasons.append("mostly-empty-frame")
    if len(coordinate_counts) < min(6, max(2, len(geometry.boundary))):
        reasons.append("insufficient-architectural-detail")
    if dominant_ratio > maximum_obstruction:
        reasons.append("single-surface-obstruction")
    if room_pixel_ratio < minimum_room:
        reasons.append("room-not-prominent")
    if depth_spread < thresholds["min_depth_spread"] and len(geometry.cells) >= 12:
        reasons.append("insufficient-depth-separation")
    if choice.visible_sample_ratio < 0.5 and profile != "third_person_cutaway":
        reasons.append("camera-line-of-sight-failed")
    if unrelated_terrain_ratio > 0.55:
        reasons.append("unrelated-terrain-dominates")

    detail_score = min(1.0, len(coordinate_counts) / 24.0)
    depth_score = min(1.0, depth_spread / 4.0)
    prominence_score = min(1.0, room_pixel_ratio / 0.7)
    anti_obstruction = max(0.0, 1.0 - dominant_ratio)
    score = (
        0.24 * detail_score
        + 0.22 * depth_score
        + 0.22 * prominence_score
        + 0.18 * anti_obstruction
        + 0.14 * choice.visible_sample_ratio
        - 0.10 * len(reasons)
    )
    return FrameQuality(
        not reasons,
        profile,
        round(max(0.0, min(1.0, score)), 6),
        tuple(reasons),
        round(occupied_ratio, 6),
        round(room_pixel_ratio, 6),
        round(room_pixel_ratio, 6),
        round(unrelated_terrain_ratio, 6),
        round(visible_floor_ratio, 6),
        round(visible_ceiling_ratio, 6),
        visible_wall_count,
        visible_opening_count,
        round(visible_feature_ratio, 6),
        round(dominant_ratio, 6),
        round(dominant_plane_ratio, 6),
        round(dominant_material_ratio, 6),
        depth_percentiles,
        round(depth_spread, 6),
        round(depth_entropy, 6),
        round(material_entropy, 6),
        round(edge_density, 6),
        round(foreground_obstruction_ratio, 6),
        round(1.0 - occupied_ratio, 6),
        clipped_triangle_count,
        round(fallback_model_pixel_ratio, 6),
        round(room_coordinate_ratio, 6),
        len(coordinate_counts),
        visible_feature_count,
        round(choice.visible_sample_ratio, 6),
    )
