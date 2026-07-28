from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.errors import AppError


@dataclass(frozen=True, slots=True)
class PerspectiveCameraSpec:
    position: tuple[float, float, float]
    target: tuple[float, float, float] | None = None
    yaw_degrees: float | None = None
    pitch_degrees: float | None = None
    roll_degrees: float = 0.0
    vertical_fov_degrees: float = 70.0
    near: float = 0.05
    far: float = 4096.0
    projection: str = "perspective"

    def validate(self) -> None:
        values = (*self.position, self.vertical_fov_degrees, self.near, self.far)
        if not all(math.isfinite(float(value)) for value in values):
            raise AppError("CAMERA_NONFINITE", "Perspective camera values must be finite.", exit_code=30)
        if self.target is None and (self.yaw_degrees is None or self.pitch_degrees is None):
            raise AppError(
                "CAMERA_AIM_REQUIRED",
                "Perspective camera requires either target or both yaw and pitch.",
                exit_code=30,
            )
        if self.target is not None and not all(math.isfinite(float(value)) for value in self.target):
            raise AppError("CAMERA_NONFINITE", "Perspective camera target must be finite.", exit_code=30)
        if not (1.0 <= self.vertical_fov_degrees < 179.0):
            raise AppError("CAMERA_FOV", "Vertical FOV must be in [1, 179).", exit_code=30)
        if self.near <= 0 or self.far <= self.near:
            raise AppError("CAMERA_CLIP", "Perspective camera requires 0 < near < far.", exit_code=30)


@dataclass(frozen=True, slots=True)
class PerspectiveTransform:
    position: np.ndarray
    right: np.ndarray
    up: np.ndarray
    forward: np.ndarray
    focal: float
    center_x: float
    center_y: float
    width: int
    height: int
    near: float
    far: float
    view_matrix: tuple[float, ...]
    projection_matrix: tuple[float, ...]

    @property
    def projection(self) -> str:
        return "perspective"

    def camera_space(self, points: np.ndarray) -> np.ndarray:
        relative = points - self.position[None, :]
        return np.column_stack((relative @ self.right, relative @ self.up, relative @ self.forward))

    def project_camera(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        depth = points[:, 2]
        screen = np.column_stack(
            (
                self.center_x + self.focal * points[:, 0] / depth,
                self.center_y - self.focal * points[:, 1] / depth,
            )
        )
        return screen, depth

    def project(self, points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
        return self.project_camera(self.camera_space(points))


def _normalize(value: np.ndarray) -> np.ndarray:
    norm = float(np.linalg.norm(value))
    if norm < 1e-12:
        raise AppError("CAMERA_DEGENERATE", "Camera direction is degenerate.", exit_code=30)
    return value / norm


def perspective_transform(size: tuple[int, int], spec: PerspectiveCameraSpec) -> PerspectiveTransform:
    spec.validate()
    width, height = size
    if width < 1 or height < 1:
        raise AppError("RENDER_SIZE_LIMIT", "Render dimensions must be positive.", exit_code=30)
    position = np.asarray(spec.position, dtype=np.float64)
    if spec.target is not None:
        forward = _normalize(np.asarray(spec.target, dtype=np.float64) - position)
    else:
        yaw = math.radians(float(spec.yaw_degrees))
        pitch = math.radians(float(spec.pitch_degrees))
        forward = _normalize(
            np.asarray(
                [math.sin(yaw) * math.cos(pitch), -math.sin(pitch), math.cos(yaw) * math.cos(pitch)],
                dtype=np.float64,
            )
        )
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
    focal = (height / 2.0) / math.tan(math.radians(spec.vertical_fov_degrees) / 2.0)
    center_x = (width - 1) / 2.0
    center_y = (height - 1) / 2.0

    view = np.eye(4, dtype=np.float64)
    view[0, :3] = right
    view[1, :3] = up
    view[2, :3] = forward
    view[0, 3] = -float(right @ position)
    view[1, 3] = -float(up @ position)
    view[2, 3] = -float(forward @ position)
    aspect = width / height
    f = 1.0 / math.tan(math.radians(spec.vertical_fov_degrees) / 2.0)
    projection = np.asarray(
        [
            [f / aspect, 0, 0, 0],
            [0, f, 0, 0],
            [0, 0, spec.far / (spec.far - spec.near), -(spec.far * spec.near) / (spec.far - spec.near)],
            [0, 0, 1, 0],
        ],
        dtype=np.float64,
    )
    return PerspectiveTransform(
        position,
        right,
        up,
        forward,
        float(focal),
        float(center_x),
        float(center_y),
        width,
        height,
        float(spec.near),
        float(spec.far),
        tuple(round(float(value), 12) for value in view.reshape(-1)),
        tuple(round(float(value), 12) for value in projection.reshape(-1)),
    )


@dataclass(slots=True)
class _ClipVertex:
    world: np.ndarray
    camera: np.ndarray
    uv: np.ndarray


@dataclass(slots=True)
class _PerspectiveTriangle:
    world: np.ndarray
    camera: np.ndarray
    screen: np.ndarray
    uv: np.ndarray
    normal: np.ndarray
    texture: np.ndarray | None
    flat_color: tuple[int, int, int, int]
    tint: tuple[float, float, float]
    palette_id: int
    coordinate: tuple[int, int, int]
    region_id: int
    category: str
    fallback: bool
    emissive: bool
    stable_key: tuple[Any, ...]


def _interpolate_vertex(a: _ClipVertex, b: _ClipVertex, t: float) -> _ClipVertex:
    return _ClipVertex(a.world + (b.world - a.world) * t, a.camera + (b.camera - a.camera) * t, a.uv + (b.uv - a.uv) * t)


def _clip_polygon(vertices: list[_ClipVertex], *, axis: int, limit: float, keep_greater: bool) -> list[_ClipVertex]:
    if not vertices:
        return []
    result: list[_ClipVertex] = []
    previous = vertices[-1]
    previous_inside = previous.camera[axis] >= limit if keep_greater else previous.camera[axis] <= limit
    for current in vertices:
        current_inside = current.camera[axis] >= limit if keep_greater else current.camera[axis] <= limit
        if current_inside != previous_inside:
            denominator = current.camera[axis] - previous.camera[axis]
            if abs(float(denominator)) > 1e-15:
                t = (limit - previous.camera[axis]) / denominator
                result.append(_interpolate_vertex(previous, current, float(t)))
        if current_inside:
            result.append(current)
        previous = current
        previous_inside = current_inside
    return result


def clip_triangle_to_depth(
    world: np.ndarray,
    camera: np.ndarray,
    uv: np.ndarray,
    *,
    near: float,
    far: float,
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    polygon = [_ClipVertex(world[index].copy(), camera[index].copy(), uv[index].copy()) for index in range(3)]
    polygon = _clip_polygon(polygon, axis=2, limit=near, keep_greater=True)
    polygon = _clip_polygon(polygon, axis=2, limit=far, keep_greater=False)
    if len(polygon) < 3:
        return []
    triangles: list[tuple[np.ndarray, np.ndarray, np.ndarray]] = []
    for index in range(1, len(polygon) - 1):
        selected = (polygon[0], polygon[index], polygon[index + 1])
        triangles.append(
            (
                np.asarray([item.world for item in selected], dtype=np.float64),
                np.asarray([item.camera for item in selected], dtype=np.float64),
                np.asarray([item.uv for item in selected], dtype=np.float64),
            )
        )
    return triangles


def _brightness(normal: np.ndarray, preset: str, *, emissive: bool) -> float:
    if emissive or preset in {"unlit-texture", "flat-semantic"}:
        return 1.0
    key = np.asarray((-0.35, 0.82, -0.45), dtype=np.float64)
    key /= np.linalg.norm(key)
    dot = max(0.0, float(normal @ key))
    if preset == "interior-soft":
        return min(1.15, 0.72 + 0.36 * dot)
    if preset == "interior-neutral":
        return min(1.1, 0.66 + 0.40 * dot)
    if preset == "interior-emissive":
        return min(1.2, 0.76 + 0.32 * dot)
    if preset == "presentation-soft":
        return min(1.2, 0.56 + 0.58 * dot)
    if preset == "diff-highlight":
        return min(1.15, 0.62 + 0.48 * dot)
    return min(1.1, 0.58 + 0.48 * dot)


_EMISSIVE_TOKENS = (
    "lantern",
    "glowstone",
    "sea_lantern",
    "froglight",
    "shroomlight",
    "ochre_froglight",
    "pearlescent_froglight",
    "verdant_froglight",
    "redstone_lamp",
    "campfire",
    "torch",
    "fire",
)
