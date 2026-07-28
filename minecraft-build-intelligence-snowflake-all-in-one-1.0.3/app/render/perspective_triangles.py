from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import numpy as np

from mbi.canonical import IntBoundingBox, IntVector3
from mbi.snapshot.raster import palette_color

from app.errors import AppError

from .geometry import is_full_cube
from .software import RenderDiagnostics, _NEIGHBOR, _state_matches
from .perspective_primitives import (
    PerspectiveTransform, _PerspectiveTriangle, clip_triangle_to_depth, _EMISSIVE_TOKENS,
)


class PerspectiveTriangleMixin:
    def _perspective_triangles(
        self,
        transform: PerspectiveTransform,
        bounds: IntBoundingBox,
        diagnostics: RenderDiagnostics,
        changed_coordinates: frozenset[IntVector3],
        issue_coordinates: Mapping[IntVector3, int],
        include_regions: frozenset[str],
        include_states: frozenset[str],
        exclude_states: frozenset[str],
        hidden_coordinates: frozenset[IntVector3],
    ) -> tuple[list[_PerspectiveTriangle], list[_PerspectiveTriangle]]:
        opaque: list[_PerspectiveTriangle] = []
        translucent: list[_PerspectiveTriangle] = []
        region_positions: set[IntVector3] | None = None
        if include_regions:
            unknown = sorted(include_regions - set(self._region_names))
            if unknown:
                raise AppError("RENDER_REGION_NOT_FOUND", "One or more requested render regions do not exist.", {"regions": unknown}, 30)
            region_positions = set()
            for name in sorted(include_regions):
                values = self.document.region_blocks.get(name)
                if values is not None:
                    region_positions.update(values)
                else:
                    region = next(item for item in self.document.regions if item.name == name)
                    region_positions.update(position for position in self.document.blocks if region.bounds.contains(position))

        visible_blocks: list[tuple[IntVector3, int]] = []
        for position, palette_id in sorted(self.document.blocks.items()):
            if not bounds.contains(position) or position in hidden_coordinates:
                continue
            if region_positions is not None and position not in region_positions:
                continue
            entry = self._palette[palette_id]
            if include_states and not _state_matches(entry, include_states):
                continue
            if exclude_states and _state_matches(entry, exclude_states):
                continue
            visible_blocks.append((position, palette_id))
        diagnostics.blocks_considered = len(visible_blocks)
        if len(visible_blocks) > self.config.max_visible_blocks:
            raise AppError("RENDER_BLOCK_LIMIT", "Render exceeds configured visible-block limit.", {"actual": len(visible_blocks), "limit": self.config.max_visible_blocks}, 30)

        for block_index, (position, palette_id) in enumerate(visible_blocks):
            entry = self._palette[palette_id]
            if entry.is_air_like:
                continue
            emitted_for_block = 0
            model_groups = self._block_models(entry, position, diagnostics)
            all_full = len(model_groups) == 1 and is_full_cube(model_groups[0][0])
            base = f"{entry.namespace}:{entry.block_name}"
            emissive = any(token in base for token in _EMISSIVE_TOKENS)
            for group_index, (quads, textures, fallback) in enumerate(model_groups):
                for face_index, quad in enumerate(quads):
                    world_quad = quad.vertices + np.asarray(position.as_tuple(), dtype=np.float64)[None, :]
                    center = world_quad.mean(axis=0)
                    if float(quad.normal @ (transform.position - center)) <= 1e-9:
                        diagnostics.faces_culled += 1
                        continue
                    if all_full and quad.cullface in _NEIGHBOR:
                        neighbor = position + _NEIGHBOR[quad.cullface]
                        neighbor_id = self.document.blocks.get(neighbor)
                        if neighbor_id is not None and neighbor not in hidden_coordinates:
                            neighbor_entry = self._palette[neighbor_id]
                            if not neighbor_entry.is_air_like and neighbor_entry.render_category == "opaque":
                                diagnostics.faces_culled += 1
                                continue
                    texture = self._texture(textures, quad.texture_ref, entry.namespace, diagnostics)
                    camera_quad = transform.camera_space(world_quad)
                    for triangle_index, indices in enumerate(((0, 1, 2), (0, 2, 3))):
                        raw_world = world_quad[np.asarray(indices)]
                        raw_camera = camera_quad[np.asarray(indices)]
                        raw_uv = quad.uv[np.asarray(indices)]
                        clipped = clip_triangle_to_depth(raw_world, raw_camera, raw_uv, near=transform.near, far=transform.far)
                        for clip_index, (world, camera, uv) in enumerate(clipped):
                            screen, _ = transform.project_camera(camera)
                            if (
                                float(screen[:, 0].max()) < 0
                                or float(screen[:, 1].max()) < 0
                                or float(screen[:, 0].min()) >= transform.width
                                or float(screen[:, 1].min()) >= transform.height
                            ):
                                diagnostics.faces_culled += 1
                                continue
                            triangle = _PerspectiveTriangle(
                                world,
                                camera,
                                screen,
                                uv,
                                quad.normal,
                                texture,
                                palette_color(palette_id),
                                self._tint_for_entry(entry, quad.tint_index),
                                palette_id,
                                position.as_tuple(),
                                self._regions.get(position, 0xFFFF),
                                entry.render_category,
                                fallback,
                                emissive,
                                (block_index, group_index, face_index, triangle_index, clip_index),
                            )
                            if entry.render_category == "translucent" or (
                                texture is not None and int(texture[..., 3].min()) < 255 and int(texture[..., 3].max()) > 0
                            ):
                                translucent.append(triangle)
                            else:
                                opaque.append(triangle)
                    emitted_for_block += 1
                    diagnostics.faces_emitted += 1
            if emitted_for_block:
                diagnostics.blocks_visible += 1
        opaque.sort(key=lambda item: item.stable_key)
        translucent.sort(key=lambda item: (-float(item.camera[:, 2].mean()), item.stable_key))
        diagnostics.peak_estimated_working_memory = (
            transform.width * transform.height * (4 + 4 + 12 + 4 + 3 + 2 + 1 + 1)
            + (len(opaque) + len(translucent)) * 768
        )
        return opaque, translucent

    @staticmethod
    def _tint_for_entry(entry: Any, tint_index: int | None) -> tuple[float, float, float]:
        from .software import _tint

        return _tint(entry, tint_index)
