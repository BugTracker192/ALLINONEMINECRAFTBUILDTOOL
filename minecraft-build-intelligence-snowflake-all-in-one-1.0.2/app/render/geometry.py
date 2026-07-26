from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

import numpy as np

from app.assets import ModelInstance, ResolvedModel


_FACE_VERTICES: dict[str, tuple[tuple[int, int, int], ...]] = {
    "down": ((0, 0, 1), (1, 0, 1), (1, 0, 0), (0, 0, 0)),
    "up": ((0, 1, 0), (1, 1, 0), (1, 1, 1), (0, 1, 1)),
    "north": ((1, 0, 0), (0, 0, 0), (0, 1, 0), (1, 1, 0)),
    "south": ((0, 0, 1), (1, 0, 1), (1, 1, 1), (0, 1, 1)),
    "west": ((0, 0, 0), (0, 0, 1), (0, 1, 1), (0, 1, 0)),
    "east": ((1, 0, 1), (1, 0, 0), (1, 1, 0), (1, 1, 1)),
}

_FACE_NORMALS: dict[str, np.ndarray] = {
    "down": np.asarray((0.0, -1.0, 0.0)),
    "up": np.asarray((0.0, 1.0, 0.0)),
    "north": np.asarray((0.0, 0.0, -1.0)),
    "south": np.asarray((0.0, 0.0, 1.0)),
    "west": np.asarray((-1.0, 0.0, 0.0)),
    "east": np.asarray((1.0, 0.0, 0.0)),
}

_FACE_DEFAULT_UV: dict[str, tuple[float, float, float, float]] = {
    "down": (0, 0, 16, 16), "up": (0, 0, 16, 16),
    "north": (0, 0, 16, 16), "south": (0, 0, 16, 16),
    "west": (0, 0, 16, 16), "east": (0, 0, 16, 16),
}


@dataclass(frozen=True, slots=True)
class Quad:
    vertices: np.ndarray
    uv: np.ndarray
    normal: np.ndarray
    texture_ref: str | None
    tint_index: int | None
    face_name: str
    cullface: str | None


def _rotation_matrix(axis: str, degrees: float) -> np.ndarray:
    radians = math.radians(degrees)
    c, s = math.cos(radians), math.sin(radians)
    if axis == "x":
        return np.asarray(((1, 0, 0), (0, c, -s), (0, s, c)), dtype=np.float64)
    if axis == "y":
        return np.asarray(((c, 0, s), (0, 1, 0), (-s, 0, c)), dtype=np.float64)
    if axis == "z":
        return np.asarray(((c, -s, 0), (s, c, 0), (0, 0, 1)), dtype=np.float64)
    raise ValueError(f"unsupported rotation axis {axis}")


def _apply_rotation(points: np.ndarray, origin: np.ndarray, axis: str, degrees: float, *, rescale: bool = False) -> np.ndarray:
    matrix = _rotation_matrix(axis, degrees)
    rotated = (points - origin[None, :]) @ matrix.T + origin[None, :]
    if rescale and abs(degrees) in {22.5, 45.0}:
        scale = 1.0 / max(1e-9, math.cos(math.radians(abs(degrees))))
        axes = {"x": (1, 2), "y": (0, 2), "z": (0, 1)}[axis]
        for component in axes:
            rotated[:, component] = origin[component] + (rotated[:, component] - origin[component]) * scale
    return rotated


def _default_uv(face: str, raw_from: list[float], raw_to: list[float]) -> tuple[float, float, float, float]:
    fx, fy, fz = (float(value) for value in raw_from)
    tx, ty, tz = (float(value) for value in raw_to)
    return {
        "down": (fx, 16 - tz, tx, 16 - fz),
        "up": (fx, fz, tx, tz),
        "north": (16 - tx, 16 - ty, 16 - fx, 16 - fy),
        "south": (fx, 16 - ty, tx, 16 - fy),
        "west": (fz, 16 - ty, tz, 16 - fy),
        "east": (16 - tz, 16 - ty, 16 - fz, 16 - fy),
    }[face]


def _rotate_direction(face: str, x_rotation: int, y_rotation: int) -> str:
    vector = _FACE_NORMALS[face]
    if x_rotation:
        vector = vector @ _rotation_matrix("x", x_rotation).T
    if y_rotation:
        vector = vector @ _rotation_matrix("y", y_rotation).T
    directions = {name: normal for name, normal in _FACE_NORMALS.items()}
    return max(directions, key=lambda name: float(vector @ directions[name]))


def _uv_corners(rect: tuple[float, float, float, float], rotation: int) -> np.ndarray:
    u1, v1, u2, v2 = rect
    values = np.asarray(((u1, v2), (u2, v2), (u2, v1), (u1, v1)), dtype=np.float64)
    turns = (rotation // 90) % 4
    return np.roll(values, turns, axis=0)


def model_quads(model: ResolvedModel, instance: ModelInstance) -> list[Quad]:
    quads: list[Quad] = []
    for element in model.elements:
        raw_from = element.get("from", [0, 0, 0])
        raw_to = element.get("to", [16, 16, 16])
        if not (
            isinstance(raw_from, list) and len(raw_from) == 3 and isinstance(raw_to, list) and len(raw_to) == 3
        ):
            continue
        minimum = np.asarray([float(value) / 16.0 for value in raw_from], dtype=np.float64)
        maximum = np.asarray([float(value) / 16.0 for value in raw_to], dtype=np.float64)
        faces = element.get("faces")
        if not isinstance(faces, dict):
            continue
        element_rotation = element.get("rotation") if isinstance(element.get("rotation"), dict) else None
        for face_name, face in faces.items():
            if face_name not in _FACE_VERTICES or not isinstance(face, dict):
                continue
            points = []
            for selector in _FACE_VERTICES[face_name]:
                points.append(
                    [maximum[axis] if selector[axis] else minimum[axis] for axis in range(3)]
                )
            vertices = np.asarray(points, dtype=np.float64)
            normal = _FACE_NORMALS[face_name].copy()
            if element_rotation:
                axis = str(element_rotation.get("axis", "y"))
                angle = float(element_rotation.get("angle", 0.0))
                origin_raw = element_rotation.get("origin", [8, 8, 8])
                origin = np.asarray([float(value) / 16.0 for value in origin_raw], dtype=np.float64)
                vertices = _apply_rotation(vertices, origin, axis, angle, rescale=bool(element_rotation.get("rescale", False)))
                normal = normal @ _rotation_matrix(axis, angle).T
            if instance.x_rotation:
                vertices = _apply_rotation(vertices, np.asarray((0.5, 0.5, 0.5)), "x", instance.x_rotation)
                normal = normal @ _rotation_matrix("x", instance.x_rotation).T
            if instance.y_rotation:
                vertices = _apply_rotation(vertices, np.asarray((0.5, 0.5, 0.5)), "y", instance.y_rotation)
                normal = normal @ _rotation_matrix("y", instance.y_rotation).T
            uv_raw = face.get("uv")
            if not isinstance(uv_raw, list) or len(uv_raw) != 4:
                uv_raw = list(_default_uv(face_name, [float(value) for value in raw_from], [float(value) for value in raw_to]))
            uv = _uv_corners(tuple(float(value) for value in uv_raw), int(face.get("rotation", 0)))
            if instance.uvlock:
                turns = (instance.y_rotation // 90) % 4
                if face_name in {"up", "down"}:
                    uv = np.roll(uv, -turns, axis=0)
                elif instance.x_rotation and face_name in {"north", "south", "east", "west"}:
                    uv = np.roll(uv, -(instance.x_rotation // 90) % 4, axis=0)
            quads.append(
                Quad(
                    vertices,
                    uv,
                    normal / max(1e-12, float(np.linalg.norm(normal))),
                    str(face.get("texture")) if face.get("texture") is not None else None,
                    int(face["tintindex"]) if isinstance(face.get("tintindex"), int) else None,
                    face_name,
                    _rotate_direction(str(face.get("cullface")), instance.x_rotation, instance.y_rotation) if face.get("cullface") in _FACE_NORMALS else None,
                )
            )
    return quads


def fallback_cube() -> list[Quad]:
    model = ResolvedModel(
        (
            {
                "from": [0, 0, 0],
                "to": [16, 16, 16],
                "faces": {name: {"cullface": name} for name in _FACE_VERTICES},
            },
        ),
        {},
        True,
        ("builtin:fallback_cube",),
    )
    return model_quads(model, ModelInstance("builtin:fallback_cube"))


def is_full_cube(quads: list[Quad]) -> bool:
    if len(quads) != 6:
        return False
    names = {quad.face_name for quad in quads}
    if names != set(_FACE_VERTICES):
        return False
    for quad in quads:
        if float(quad.vertices.min()) < -1e-9 or float(quad.vertices.max()) > 1 + 1e-9:
            return False
    return True
