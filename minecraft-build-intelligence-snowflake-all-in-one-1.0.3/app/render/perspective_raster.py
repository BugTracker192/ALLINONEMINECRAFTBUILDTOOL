from __future__ import annotations

import math
from collections.abc import Mapping

import numpy as np

from mbi.canonical import IntVector3

from .semantic import SemanticBuffers
from .perspective_primitives import _PerspectiveTriangle, _brightness


class PerspectiveRasterMixin:
    @staticmethod
    def _sample(texture: np.ndarray | None, uv_u: np.ndarray, uv_v: np.ndarray, flat: tuple[int, int, int, int]) -> np.ndarray:
        if texture is None:
            color = np.empty((*uv_u.shape, 4), dtype=np.uint8)
            color[...] = flat
            return color
        height, width = texture.shape[:2]
        u = np.floor(np.mod(uv_u, 16.0) / 16.0 * width).astype(np.int64)
        v = np.floor(np.mod(uv_v, 16.0) / 16.0 * height).astype(np.int64)
        u = np.clip(u, 0, width - 1)
        v = np.clip(v, 0, height - 1)
        return texture[v, u].copy()

    def _raster_perspective_triangle(
        self,
        triangle: _PerspectiveTriangle,
        color: np.ndarray,
        zbuffer: np.ndarray,
        semantics: SemanticBuffers,
        *,
        translucent: bool,
        lighting_preset: str,
        changed_coordinates: frozenset[IntVector3],
        issue_coordinates: Mapping[IntVector3, int],
    ) -> bool:
        points = triangle.screen
        minimum_x = max(0, int(math.floor(float(points[:, 0].min()))))
        maximum_x = min(color.shape[1] - 1, int(math.ceil(float(points[:, 0].max()))))
        minimum_y = max(0, int(math.floor(float(points[:, 1].min()))))
        maximum_y = min(color.shape[0] - 1, int(math.ceil(float(points[:, 1].max()))))
        if minimum_x > maximum_x or minimum_y > maximum_y:
            return False
        x0, y0 = points[0]
        x1, y1 = points[1]
        x2, y2 = points[2]
        denominator = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(float(denominator)) < 1e-12:
            return False
        xs = np.arange(minimum_x, maximum_x + 1, dtype=np.float64) + 0.5
        ys = np.arange(minimum_y, maximum_y + 1, dtype=np.float64) + 0.5
        xx, yy = np.meshgrid(xs, ys)
        w0 = ((y1 - y2) * (xx - x2) + (x2 - x1) * (yy - y2)) / denominator
        w1 = ((y2 - y0) * (xx - x2) + (x0 - x2) * (yy - y2)) / denominator
        w2 = 1.0 - w0 - w1
        inside = (w0 >= -1e-9) & (w1 >= -1e-9) & (w2 >= -1e-9)
        if not inside.any():
            return False

        vertex_depth = triangle.camera[:, 2]
        inv_vertex_depth = 1.0 / vertex_depth
        inv_depth = w0 * inv_vertex_depth[0] + w1 * inv_vertex_depth[1] + w2 * inv_vertex_depth[2]
        depth = 1.0 / np.maximum(inv_depth, 1e-15)
        view = np.s_[minimum_y : maximum_y + 1, minimum_x : maximum_x + 1]
        if translucent:
            depth_pass = depth <= zbuffer[view] + 1e-6
        else:
            depth_pass = depth < zbuffer[view]

        uv_u = (
            w0 * triangle.uv[0, 0] * inv_vertex_depth[0]
            + w1 * triangle.uv[1, 0] * inv_vertex_depth[1]
            + w2 * triangle.uv[2, 0] * inv_vertex_depth[2]
        ) / inv_depth
        uv_v = (
            w0 * triangle.uv[0, 1] * inv_vertex_depth[0]
            + w1 * triangle.uv[1, 1] * inv_vertex_depth[1]
            + w2 * triangle.uv[2, 1] * inv_vertex_depth[2]
        ) / inv_depth
        sampled = self._sample(triangle.texture, uv_u, uv_v, triangle.flat_color)
        brightness = _brightness(triangle.normal, lighting_preset, emissive=triangle.emissive)
        issue_code = int(issue_coordinates.get(IntVector3(*triangle.coordinate), 0))
        sampled[..., :3] = np.clip(
            sampled[..., :3].astype(np.float32)
            * np.asarray(triangle.tint, dtype=np.float32)[None, None, :]
            * brightness,
            0,
            255,
        ).astype(np.uint8)
        if lighting_preset == "diff-highlight" and issue_code:
            highlight = np.asarray((255, min(220, 48 + issue_code * 14), 24), dtype=np.float32)
            sampled[..., :3] = np.clip(sampled[..., :3].astype(np.float32) * 0.38 + highlight[None, None, :] * 0.62, 0, 255).astype(np.uint8)
        alpha = sampled[..., 3]
        alpha_pass = alpha >= 128 if triangle.category == "cutout" else alpha > 0
        mask = inside & depth_pass & alpha_pass
        if not mask.any():
            return False
        target = color[view]
        if translucent:
            source_alpha = sampled[..., 3:4].astype(np.float32) / 255.0
            destination_alpha = target[..., 3:4].astype(np.float32) / 255.0
            output_alpha = source_alpha + destination_alpha * (1.0 - source_alpha)
            output_rgb = (
                sampled[..., :3].astype(np.float32) * source_alpha
                + target[..., :3].astype(np.float32) * destination_alpha * (1.0 - source_alpha)
            ) / np.maximum(output_alpha, 1e-8)
            blended = np.concatenate((np.clip(output_rgb, 0, 255), np.clip(output_alpha * 255, 0, 255)), axis=2).astype(np.uint8)
            target[mask] = blended[mask]
        else:
            target[mask] = sampled[mask]
            zbuffer_view = zbuffer[view]
            zbuffer_view[mask] = depth[mask]

        semantic_depth = semantics.depth[view]
        semantic_update = mask & (depth < semantic_depth)
        if semantic_update.any():
            semantic_depth[semantic_update] = depth[semantic_update].astype(np.float32)
            semantics.palette[view][semantic_update] = triangle.palette_id
            semantics.coordinates[view][semantic_update] = np.asarray(triangle.coordinate, dtype=np.int32)
            semantics.normals[view][semantic_update] = np.clip(np.rint(triangle.normal * 127), -127, 127).astype(np.int8)
            semantics.regions[view][semantic_update] = triangle.region_id
            semantics.occupancy[view][semantic_update] = 1
            if IntVector3(*triangle.coordinate) in changed_coordinates:
                semantics.changed[view][semantic_update] = 1
            grounded_issue = issue_code
            if triangle.fallback:
                grounded_issue = max(grounded_issue, 1)
            if grounded_issue:
                semantics.issues[view][semantic_update] = min(255, grounded_issue)
        return True
