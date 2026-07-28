from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Iterable, Mapping
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image

from mbi.canonical import IntBoundingBox, IntVector3

from app.errors import AppError
from app.storage import atomic_write_json

from .semantic import SemanticBuffers
from .software import RenderDiagnostics, RenderResult
from .perspective_primitives import PerspectiveCameraSpec, perspective_transform


class PerspectiveOutputMixin:
    def render(
        self,
        output_root: str | Path,
        *,
        camera: PerspectiveCameraSpec,
        crop: IntBoundingBox | None = None,
        size: tuple[int, int] = (1024, 1024),
        mode: str = "textured",
        lighting_preset: str = "interior-soft",
        background: tuple[int, int, int, int] = (0, 0, 0, 0),
        changed_coordinates: frozenset[IntVector3] = frozenset(),
        issue_coordinates: Mapping[IntVector3, int] | None = None,
        include_regions: Iterable[str] = (),
        include_states: Iterable[str] = (),
        exclude_states: Iterable[str] = (),
        hidden_coordinates: Iterable[IntVector3] = (),
        name: str | None = None,
    ) -> RenderResult:
        started = time.perf_counter()
        width, height = size
        if width < 1 or height < 1 or width > self.config.max_render_size or height > self.config.max_render_size:
            raise AppError("RENDER_SIZE_LIMIT", "Render size is outside configured bounds.", {"size": size}, 30)
        bounds = self.document.bounds if crop is None else self.document.bounds.intersection(crop)
        if bounds is None:
            raise AppError("RENDER_EMPTY_CROP", "Render crop does not intersect the build.", exit_code=30)
        transform = perspective_transform(size, camera)
        use_textures = mode == "textured" and self.pack is not None
        diagnostics = RenderDiagnostics("software-textured" if use_textures else "software-flat", 3 if use_textures else 0)
        issue_coordinates = issue_coordinates or {}
        include_regions_set = frozenset(str(item) for item in include_regions)
        include_states_set = frozenset(str(item) for item in include_states)
        exclude_states_set = frozenset(str(item) for item in exclude_states)
        hidden_set = frozenset(hidden_coordinates)
        if mode == "textured" and self.pack is None:
            diagnostics.limitations.append("No resource pack was supplied; deterministic flat colors were used.")
        original_pack = self.pack
        if not use_textures:
            self.pack = None
            self._model_cache.clear()
        try:
            opaque, translucent = self._perspective_triangles(
                transform,
                bounds,
                diagnostics,
                changed_coordinates,
                issue_coordinates,
                include_regions_set,
                include_states_set,
                exclude_states_set,
                hidden_set,
            )
        finally:
            self.pack = original_pack
        color = np.empty((height, width, 4), dtype=np.uint8)
        color[...] = background
        zbuffer = np.full((height, width), np.inf, dtype=np.float32)
        semantics = SemanticBuffers.create(width, height)
        for triangle in opaque:
            if self._raster_perspective_triangle(
                triangle,
                color,
                zbuffer,
                semantics,
                translucent=False,
                lighting_preset=lighting_preset,
                changed_coordinates=changed_coordinates,
                issue_coordinates=issue_coordinates,
            ):
                diagnostics.triangles_rasterized += 1
        for triangle in translucent:
            if self._raster_perspective_triangle(
                triangle,
                color,
                zbuffer,
                semantics,
                translucent=True,
                lighting_preset=lighting_preset,
                changed_coordinates=changed_coordinates,
                issue_coordinates=issue_coordinates,
            ):
                diagnostics.triangles_rasterized += 1
        diagnostics.duration_seconds = round(time.perf_counter() - started, 6)
        diagnostics.limitations.append("Perspective interiors use deterministic near/far clipping and stable translucent sorting.")
        if self.pack is not None:
            for item in self.pack.diagnostics:
                if item.get("code") == "ANIMATED_TEXTURE_FIRST_FRAME":
                    fallback = {"type": "animated_texture_first_frame", **item}
                    if fallback not in diagnostics.fallbacks:
                        diagnostics.fallbacks.append(fallback)
                        diagnostics.fallback_count += 1
                elif item not in diagnostics.asset_diagnostics:
                    diagnostics.asset_diagnostics.append(item)

        root = Path(output_root)
        snapshots = root / "snapshots"
        semantic_root = root / "semantic_maps"
        snapshots.mkdir(parents=True, exist_ok=True)
        semantic_root.mkdir(parents=True, exist_ok=True)
        camera_payload = asdict(camera)
        config_payload = {
            "build_hash": self.document.content_hash,
            "projection": "perspective",
            "camera": camera_payload,
            "bounds": {"min": bounds.min.as_tuple(), "max": bounds.max.as_tuple()},
            "size": size,
            "mode": diagnostics.render_mode,
            "lighting": lighting_preset,
            "pack_hash": self.pack.pack_hash if self.pack is not None else None,
            "filters": {
                "regions": sorted(include_regions_set),
                "include_states": sorted(include_states_set),
                "exclude_states": sorted(exclude_states_set),
            },
            "hidden_coordinates_hash": hashlib.sha256(json.dumps(sorted(point.as_tuple() for point in hidden_set), separators=(",", ":")).encode()).hexdigest(),
            "renderer": "python-cpu-perspective-rasterizer-v1",
        }
        snapshot_id = "snap_" + hashlib.sha256(json.dumps(config_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
        stem = name or snapshot_id
        png_path = snapshots / f"{stem}.png"
        Image.fromarray(color, "RGBA").save(png_path, format="PNG", compress_level=9, optimize=False)
        maps = semantics.write(semantic_root, snapshot_id)
        persisted_diagnostics = asdict(diagnostics)
        persisted_diagnostics.pop("duration_seconds", None)
        manifest = {
            "snapshot_id": snapshot_id,
            "build_version_id": "ver_" + self.document.content_hash[:20],
            "type": "perspective",
            "projection": "perspective",
            "direction": name,
            "resolution": [width, height],
            "coordinate_space": "document",
            "visible_bounds": {"min": list(bounds.min.as_tuple()), "max": list(bounds.max.as_tuple())},
            "camera": camera_payload,
            "view_matrix": list(transform.view_matrix),
            "projection_matrix": list(transform.projection_matrix),
            "lighting_preset": lighting_preset,
            "render_mode": diagnostics.render_mode,
            "render_tier": diagnostics.render_tier,
            "resource_pack_hash": self.pack.pack_hash if self.pack is not None else None,
            "renderer_version": "python-cpu-perspective-rasterizer-v1",
            "background": list(background),
            "content_hash": hashlib.sha256(png_path.read_bytes()).hexdigest(),
            "semantic_maps": {key: f"../semantic_maps/{value}" for key, value in maps.items()},
            "filters": config_payload["filters"],
            "temporary_visibility_mask": {
                "reason": "interior-cutaway" if hidden_set else None,
                "coordinate_count": len(hidden_set),
                "coordinates": [list(point.as_tuple()) for point in sorted(hidden_set)],
            },
            "issue_categories": {
                "0": "none",
                "1": "renderer-fallback",
                "2-255": "caller-defined-grounded-analysis-category",
            },
            "diagnostics": persisted_diagnostics,
        }
        manifest_path = snapshots / f"{stem}.manifest.json"
        atomic_write_json(manifest_path, manifest)
        return RenderResult(png_path, manifest_path, semantic_root / maps["metadata"], snapshot_id, manifest, asdict(diagnostics))
