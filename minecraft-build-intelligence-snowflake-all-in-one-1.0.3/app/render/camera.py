from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from mbi.canonical import IntBoundingBox


@dataclass(frozen=True, slots=True)
class CameraSpec:
    azimuth_degrees: float = 45.0
    elevation_degrees: float = 30.0
    roll_degrees: float = 0.0
    zoom: float = 1.0
    target: tuple[float, float, float] | None = None
    fit_bounds: bool = True
    margin_blocks: float = 1.0
    near: float = -1_000_000.0
    far: float = 1_000_000.0

    @classmethod
    def preset(cls, name: str) -> "CameraSpec":
        values = {
            "north": (0.0, 0.0),
            "south": (180.0, 0.0),
            "east": (90.0, 0.0),
            "west": (270.0, 0.0),
            "top": (0.0, 90.0),
            "bottom": (0.0, -90.0),
            "isometric_ne": (45.0, 35.26438968),
            "isometric_nw": (315.0, 35.26438968),
            "isometric_se": (135.0, 35.26438968),
            "isometric_sw": (225.0, 35.26438968),
        }
        if name not in values:
            raise ValueError(f"unknown camera preset {name}")
        azimuth, elevation = values[name]
        return cls(azimuth, elevation)


@dataclass(frozen=True, slots=True)
class CameraTransform:
    target: np.ndarray
    right: np.ndarray
    up: np.ndarray
    forward: np.ndarray
    scale: float
    center_x: float
    center_y: float
    width: int
    height: int
    view_matrix: tuple[float, ...]
    projection_matrix: tuple[float, ...]

    def project(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        relative = points - self.target[None, :]
        x = relative @ self.right
        y = relative @ self.up
        depth = relative @ self.forward
        screen = np.column_stack((self.center_x + x * self.scale, self.center_y - y * self.scale))
        return screen, depth


def _normalize(value: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(value))
    if norm < 1e-12:
        raise ValueError("camera basis vector is degenerate")
    return value / norm


def bounds_corners(bounds: IntBoundingBox) -> np.ndarray:
    xs = (bounds.min.x, bounds.max.x + 1)
    ys = (bounds.min.y, bounds.max.y + 1)
    zs = (bounds.min.z, bounds.max.z + 1)
    return np.asarray([(x, y, z) for x in xs for y in ys for z in zs], dtype=np.float64)


def camera_transform(bounds: IntBoundingBox, size: tuple[int, int], spec: CameraSpec) -> CameraTransform:
    width, height = size
    if width < 1 or height < 1:
        raise ValueError("render dimensions must be positive")
    azimuth = math.radians(spec.azimuth_degrees)
    elevation = math.radians(max(-89.999999, min(89.999999, spec.elevation_degrees)))
    camera_from_target = np.asarray(
        [math.sin(azimuth) * math.cos(elevation), math.sin(elevation), -math.cos(azimuth) * math.cos(elevation)],
        dtype=np.float64,
    )
    forward = _normalize(-camera_from_target)
    reference_up = np.asarray([0.0, 1.0, 0.0], dtype=np.float64)
    if abs(float(forward @ reference_up)) > 0.999:
        reference_up = np.asarray([0.0, 0.0, 1.0], dtype=np.float64)
    right = _normalize(np.cross(forward, reference_up))
    up = _normalize(np.cross(right, forward))
    if spec.roll_degrees:
        roll = math.radians(spec.roll_degrees)
        old_right = right.copy()
        right = old_right * math.cos(roll) + up * math.sin(roll)
        up = -old_right * math.sin(roll) + up * math.cos(roll)

    if spec.target is None:
        target = np.asarray(
            [
                (bounds.min.x + bounds.max.x + 1) / 2.0,
                (bounds.min.y + bounds.max.y + 1) / 2.0,
                (bounds.min.z + bounds.max.z + 1) / 2.0,
            ],
            dtype=np.float64,
        )
    else:
        target = np.asarray(spec.target, dtype=np.float64)
    corners = bounds_corners(bounds)
    relative = corners - target[None, :]
    xs = relative @ right
    ys = relative @ up
    extent_x = max(1e-6, float(xs.max() - xs.min()) + 2.0 * spec.margin_blocks)
    extent_y = max(1e-6, float(ys.max() - ys.min()) + 2.0 * spec.margin_blocks)
    scale = min((width - 1) / extent_x, (height - 1) / extent_y) * max(1e-6, spec.zoom)
    scale = round(scale, 9)
    x_center_world = float((xs.min() + xs.max()) / 2.0)
    y_center_world = float((ys.min() + ys.max()) / 2.0)
    center_x = round((width - 1) / 2.0 - x_center_world * scale, 9)
    center_y = round((height - 1) / 2.0 + y_center_world * scale, 9)

    view = np.eye(4, dtype=np.float64)
    view[0, :3] = right
    view[1, :3] = up
    view[2, :3] = forward
    view[0, 3] = -float(right @ target)
    view[1, 3] = -float(up @ target)
    view[2, 3] = -float(forward @ target)
    projection = np.asarray(
        [
            [2 * scale / max(1, width), 0, 0, 0],
            [0, 2 * scale / max(1, height), 0, 0],
            [0, 0, 2 / (spec.far - spec.near), -(spec.far + spec.near) / (spec.far - spec.near)],
            [0, 0, 0, 1],
        ],
        dtype=np.float64,
    )
    return CameraTransform(
        target,
        right,
        up,
        forward,
        scale,
        center_x,
        center_y,
        width,
        height,
        tuple(round(float(value), 12) for value in view.reshape(-1)),
        tuple(round(float(value), 12) for value in projection.reshape(-1)),
    )
