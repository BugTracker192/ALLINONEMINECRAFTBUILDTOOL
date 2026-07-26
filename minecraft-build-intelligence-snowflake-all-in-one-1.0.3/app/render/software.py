from __future__ import annotations

import hashlib
import json
import math
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from collections.abc import Mapping
from typing import Any, Iterable

import numpy as np
from PIL import Image

from mbi.canonical import BuildDocument, IntBoundingBox, IntVector3, PaletteEntry
from mbi.snapshot.raster import palette_color

from app.assets import ModelInstance, ResolvedModel, ResourcePackSource, open_resource_pack
from app.config import RuntimeConfig
from app.errors import AppError
from app.storage import atomic_write_json

from .camera import CameraSpec, CameraTransform, camera_transform
from .geometry import Quad, fallback_cube, is_full_cube, model_quads
from .semantic import NO_COORDINATE, NO_PALETTE, SemanticBuffers, load_map


@dataclass(slots=True)
class RenderDiagnostics:
    render_mode: str
    render_tier: int
    blocks_considered: int = 0
    blocks_visible: int = 0
    faces_emitted: int = 0
    faces_culled: int = 0
    triangles_rasterized: int = 0
    texture_cache_hits: int = 0
    fallback_count: int = 0
    unsupported_models: list[dict[str, Any]] = field(default_factory=list)
    fallbacks: list[dict[str, Any]] = field(default_factory=list)
    asset_diagnostics: list[dict[str, Any]] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    peak_estimated_working_memory: int = 0


@dataclass(frozen=True, slots=True)
class RenderResult:
    png_path: Path
    manifest_path: Path
    semantic_metadata_path: Path
    snapshot_id: str
    manifest: dict[str, Any]
    diagnostics: dict[str, Any]


@dataclass(slots=True)
class _Triangle:
    world: np.ndarray
    screen: np.ndarray
    depth: np.ndarray
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
    stable_key: tuple[Any, ...]


_NEIGHBOR = {
    "down": IntVector3(0, -1, 0), "up": IntVector3(0, 1, 0),
    "north": IntVector3(0, 0, -1), "south": IntVector3(0, 0, 1),
    "west": IntVector3(-1, 0, 0), "east": IntVector3(1, 0, 0),
}


def _tint(entry: PaletteEntry, tint_index: int | None) -> tuple[float, float, float]:
    if tint_index is None:
        return 1.0, 1.0, 1.0
    base = f"{entry.namespace}:{entry.block_name}"
    if "redstone" in base:
        power = int(entry.properties.get("power", "0") or 0)
        ratio = max(0.0, min(1.0, power / 15.0))
        return 0.3 + 0.7 * ratio, 0.02 + 0.18 * ratio, 0.02 + 0.08 * ratio
    if base in {"minecraft:water", "minecraft:bubble_column"} or "water" in base:
        return 0.247, 0.463, 0.894
    if any(token in base for token in ("grass", "fern")):
        return 0.36, 0.64, 0.27
    if any(token in base for token in ("leaves", "vine")):
        return 0.30, 0.55, 0.22
    if "stem" in base:
        age = int(entry.properties.get("age", "0") or 0)
        return 0.35 + age * 0.07, 0.55 - age * 0.035, 0.15
    return 0.72, 0.82, 0.62


def _directional_brightness(normal: np.ndarray, preset: str) -> float:
    if preset in {"unlit-texture", "flat-semantic"}:
        return 1.0
    key = np.asarray((-0.35, 0.82, -0.45), dtype=np.float64)
    key /= np.linalg.norm(key)
    dot = max(0.0, float(normal @ key))
    if preset == "presentation-soft":
        return min(1.2, 0.56 + 0.58 * dot)
    if preset == "diff-highlight":
        return min(1.15, 0.62 + 0.48 * dot)
    return min(1.1, 0.58 + 0.48 * dot)


def _region_ids(document: BuildDocument) -> tuple[dict[str, int], dict[IntVector3, int]]:
    names = sorted(region.name for region in document.regions)
    ids = {name: index for index, name in enumerate(names)}
    positions: dict[IntVector3, int] = {}
    for name in names:
        values = document.region_blocks.get(name)
        if values:
            for position in values:
                positions.setdefault(position, ids[name])
        else:
            region = next(item for item in document.regions if item.name == name)
            for position in document.blocks:
                if region.bounds.contains(position):
                    positions.setdefault(position, ids[name])
    return ids, positions


def _crop_document_bounds(document: BuildDocument, crop: IntBoundingBox | None) -> IntBoundingBox:
    if crop is None:
        return document.bounds
    intersection = document.bounds.intersection(crop)
    if intersection is None:
        raise AppError("RENDER_EMPTY_CROP", "Render crop does not intersect the build.", exit_code=30)
    return intersection


def _state_matches(entry: PaletteEntry, selectors: frozenset[str]) -> bool:
    if not selectors:
        return True
    base = f"{entry.namespace}:{entry.block_name}"
    return entry.canonical_state in selectors or base in selectors


def _checker_texture() -> np.ndarray:
    image = np.zeros((16, 16, 4), dtype=np.uint8)
    for y in range(16):
        for x in range(16):
            if ((x // 4) + (y // 4)) % 2:
                image[y, x] = (255, 0, 255, 255)
            else:
                image[y, x] = (20, 20, 20, 255)
    return image


_MISSING_TEXTURE = _checker_texture()


class SoftwareRenderer:
    def __init__(
        self,
        document: BuildDocument,
        *,
        resource_pack: ResourcePackSource | None = None,
        config: RuntimeConfig | None = None,
        strict_textures: bool = False,
        seed: int = 0,
    ) -> None:
        self.document = document
        self.pack = resource_pack
        self.config = config or RuntimeConfig()
        self.strict_textures = strict_textures
        self.seed = seed
        self._texture_arrays: dict[tuple[str, str], np.ndarray] = {}
        self._model_cache: dict[tuple[str, tuple[int, int, int]], list[tuple[list[Quad], dict[str, str], bool]]] = {}
        self._palette = document.palette_by_id()
        self._region_names, self._regions = _region_ids(document)

    def _texture(self, textures: dict[str, str], reference: str | None, namespace: str, diagnostics: RenderDiagnostics) -> np.ndarray | None:
        if self.pack is None or reference is None:
            return None
        try:
            ns, path = self.pack.resolve_texture_ref(textures, reference, namespace)
            key = (ns, path)
            if key in self._texture_arrays:
                diagnostics.texture_cache_hits += 1
                return self._texture_arrays[key]
            image = self.pack.texture(ns, path)
            array = np.asarray(image, dtype=np.uint8)
            self._texture_arrays[key] = array
            return array
        except Exception as exc:
            if self.strict_textures:
                if isinstance(exc, AppError):
                    raise
                raise AppError("TEXTURE_RESOLUTION_FAILED", "Texture resolution failed.", {"reference": reference}, 31) from exc
            diagnostics.fallback_count += 1
            diagnostics.fallbacks.append({"type": "missing_texture", "reference": reference, "error": str(exc)})
            return _MISSING_TEXTURE

    def _block_models(self, entry: PaletteEntry, position: IntVector3, diagnostics: RenderDiagnostics) -> list[tuple[list[Quad], dict[str, str], bool]]:
        cache_key = (entry.canonical_state, position.as_tuple())
        if cache_key in self._model_cache:
            return self._model_cache[cache_key]
        if self.pack is None:
            result = [(fallback_cube(), {}, True)]
            self._model_cache[cache_key] = result
            return result
        result: list[tuple[list[Quad], dict[str, str], bool]] = []
        if entry.is_fluid:
            base = f"{entry.namespace}:{entry.block_name}"
            level = int(entry.properties.get("level", "0") or 0)
            falling = level >= 8
            effective_level = level % 8
            height = 1.0 if falling or effective_level == 0 else max(0.125, 1.0 - effective_level / 8.0)
            texture_base = "lava" if "lava" in base else "water"
            fluid_model = ResolvedModel(
                ({
                    "from": [0, 0, 0], "to": [16, round(height * 16, 6), 16],
                    "faces": {
                        "up": {"texture": "#still"}, "down": {"texture": "#still"},
                        "north": {"texture": "#flow"}, "south": {"texture": "#flow"},
                        "west": {"texture": "#flow"}, "east": {"texture": "#flow"},
                    },
                },),
                {"still": f"minecraft:block/{texture_base}_still", "flow": f"minecraft:block/{texture_base}_flow"},
                False,
                ("builtin:fluid",),
            )
            result = [(model_quads(fluid_model, ModelInstance("builtin:fluid")), fluid_model.textures, False)]
            self._model_cache[cache_key] = result
            return result
        try:
            instances = self.pack.select_models(entry.canonical_state, position.as_tuple(), self.seed)
            if not instances:
                raise AppError("BLOCKSTATE_NO_MODEL", "No matching blockstate model was found.", {"state": entry.canonical_state}, 31)
            for instance in instances:
                model = self.pack.resolve_model(instance.model)
                quads = model_quads(model, instance)
                if not quads:
                    raise AppError("MODEL_NO_ELEMENTS", "Resolved model has no static elements.", {"model": instance.model}, 31)
                result.append((quads, model.textures, False))
        except Exception as exc:
            if self.strict_textures:
                if isinstance(exc, AppError):
                    raise
                raise AppError("MODEL_RESOLUTION_FAILED", "Block model resolution failed.", {"state": entry.canonical_state}, 31) from exc
            diagnostics.fallback_count += 1
            item = {"state": entry.canonical_state, "coordinate": position.as_tuple(), "reason": str(exc), "tier": 0}
            diagnostics.unsupported_models.append(item)
            diagnostics.fallbacks.append({"type": "model_fallback", **item})
            result = [(fallback_cube(), {}, True)]
        self._model_cache[cache_key] = result
        return result

    def _triangles(
        self,
        transform: CameraTransform,
        bounds: IntBoundingBox,
        diagnostics: RenderDiagnostics,
        changed_coordinates: frozenset[IntVector3],
        issue_coordinates: Mapping[IntVector3, int],
        include_regions: frozenset[str],
        include_states: frozenset[str],
        exclude_states: frozenset[str],
    ) -> tuple[list[_Triangle], list[_Triangle]]:
        opaque: list[_Triangle] = []
        translucent: list[_Triangle] = []
        region_positions: set[IntVector3] | None = None
        if include_regions:
            unknown = sorted(include_regions - set(self._region_names))
            if unknown:
                raise AppError(
                    "RENDER_REGION_NOT_FOUND",
                    "One or more requested render regions do not exist.",
                    {"regions": unknown},
                    30,
                )
            region_positions = set()
            for name in sorted(include_regions):
                values = self.document.region_blocks.get(name)
                if values is not None:
                    region_positions.update(values)
                else:
                    region = next(item for item in self.document.regions if item.name == name)
                    region_positions.update(position for position in self.document.blocks if region.bounds.contains(position))
        visible_blocks = []
        for position, pid in sorted(self.document.blocks.items()):
            if not bounds.contains(position):
                continue
            if region_positions is not None and position not in region_positions:
                continue
            entry = self._palette[pid]
            if include_states and not _state_matches(entry, include_states):
                continue
            if exclude_states and _state_matches(entry, exclude_states):
                continue
            visible_blocks.append((position, pid))
        diagnostics.blocks_considered = len(visible_blocks)
        if len(visible_blocks) > self.config.max_visible_blocks:
            raise AppError(
                "RENDER_BLOCK_LIMIT",
                "Render exceeds configured visible-block limit.",
                {"actual": len(visible_blocks), "limit": self.config.max_visible_blocks},
                30,
            )
        for block_index, (position, palette_id) in enumerate(visible_blocks):
            entry = self._palette[palette_id]
            if entry.is_air_like:
                continue
            emitted_for_block = 0
            model_groups = self._block_models(entry, position, diagnostics)
            all_full = len(model_groups) == 1 and is_full_cube(model_groups[0][0])
            for group_index, (quads, textures, fallback) in enumerate(model_groups):
                for face_index, quad in enumerate(quads):
                    normal = quad.normal
                    if float(normal @ transform.forward) >= -1e-9:
                        diagnostics.faces_culled += 1
                        continue
                    if all_full and quad.cullface in _NEIGHBOR:
                        neighbor = position + _NEIGHBOR[quad.cullface]
                        neighbor_id = self.document.blocks.get(neighbor)
                        if neighbor_id is not None:
                            neighbor_entry = self._palette[neighbor_id]
                            if not neighbor_entry.is_air_like and neighbor_entry.render_category == "opaque":
                                diagnostics.faces_culled += 1
                                continue
                    world = quad.vertices + np.asarray(position.as_tuple(), dtype=np.float64)[None, :]
                    screen, depth = transform.project(world)
                    if (
                        float(screen[:, 0].max()) < 0 or float(screen[:, 1].max()) < 0
                        or float(screen[:, 0].min()) >= transform.width or float(screen[:, 1].min()) >= transform.height
                    ):
                        diagnostics.faces_culled += 1
                        continue
                    texture = self._texture(textures, quad.texture_ref, entry.namespace, diagnostics)
                    base_color = palette_color(palette_id)
                    tint = _tint(entry, quad.tint_index)
                    category = entry.render_category
                    for tri_index, indices in enumerate(((0, 1, 2), (0, 2, 3))):
                        triangle = _Triangle(
                            world[np.asarray(indices)],
                            screen[np.asarray(indices)],
                            depth[np.asarray(indices)],
                            quad.uv[np.asarray(indices)],
                            normal,
                            texture,
                            base_color,
                            tint,
                            palette_id,
                            position.as_tuple(),
                            self._regions.get(position, 0xFFFF),
                            category,
                            fallback,
                            (block_index, group_index, face_index, tri_index),
                        )
                        if category == "translucent" or (texture is not None and int(texture[..., 3].min()) < 255 and int(texture[..., 3].max()) > 0):
                            translucent.append(triangle)
                        else:
                            opaque.append(triangle)
                    emitted_for_block += 1
                    diagnostics.faces_emitted += 1
            if emitted_for_block:
                diagnostics.blocks_visible += 1
        opaque.sort(key=lambda item: item.stable_key)
        translucent.sort(key=lambda item: (-float(item.depth.mean()), item.stable_key))
        diagnostics.peak_estimated_working_memory = (
            transform.width * transform.height * (4 + 4 + 12 + 4 + 3 + 2 + 1 + 1)
            + (len(opaque) + len(translucent)) * 640
        )
        return opaque, translucent

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

    def _raster_triangle(
        self,
        triangle: _Triangle,
        color: np.ndarray,
        zbuffer: np.ndarray,
        semantics: SemanticBuffers,
        *,
        translucent: bool,
        lighting_preset: str,
        changed_coordinates: frozenset[IntVector3],
        issue_coordinates: Mapping[IntVector3, int],
    ) -> bool:
        p = triangle.screen
        minimum_x = max(0, int(math.floor(float(p[:, 0].min()))))
        maximum_x = min(color.shape[1] - 1, int(math.ceil(float(p[:, 0].max()))))
        minimum_y = max(0, int(math.floor(float(p[:, 1].min()))))
        maximum_y = min(color.shape[0] - 1, int(math.ceil(float(p[:, 1].max()))))
        if minimum_x > maximum_x or minimum_y > maximum_y:
            return False
        x0, y0 = p[0]
        x1, y1 = p[1]
        x2, y2 = p[2]
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
        depth = w0 * triangle.depth[0] + w1 * triangle.depth[1] + w2 * triangle.depth[2]
        view = np.s_[minimum_y : maximum_y + 1, minimum_x : maximum_x + 1]
        if translucent:
            depth_pass = depth <= zbuffer[view] + 1e-6
        else:
            depth_pass = depth < zbuffer[view]
        uv_u = w0 * triangle.uv[0, 0] + w1 * triangle.uv[1, 0] + w2 * triangle.uv[2, 0]
        uv_v = w0 * triangle.uv[0, 1] + w1 * triangle.uv[1, 1] + w2 * triangle.uv[2, 1]
        sampled = self._sample(triangle.texture, uv_u, uv_v, triangle.flat_color)
        brightness = _directional_brightness(triangle.normal, lighting_preset)
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
            sampled[..., :3] = np.clip(
                sampled[..., :3].astype(np.float32) * 0.38 + highlight[None, None, :] * 0.62,
                0,
                255,
            ).astype(np.uint8)
        alpha = sampled[..., 3]
        if triangle.category == "cutout":
            alpha_pass = alpha >= 128
        else:
            alpha_pass = alpha > 0
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
            if triangle.fallback:
                issue_code = max(issue_code, 1)
            if issue_code:
                semantics.issues[view][semantic_update] = min(255, issue_code)
        return True

    def render(
        self,
        output_root: str | Path,
        *,
        camera: CameraSpec | None = None,
        crop: IntBoundingBox | None = None,
        size: tuple[int, int] = (1024, 1024),
        mode: str = "textured",
        lighting_preset: str = "analysis-neutral",
        background: tuple[int, int, int, int] = (0, 0, 0, 0),
        changed_coordinates: frozenset[IntVector3] = frozenset(),
        issue_coordinates: Mapping[IntVector3, int] | None = None,
        include_regions: Iterable[str] = (),
        include_states: Iterable[str] = (),
        exclude_states: Iterable[str] = (),
        name: str | None = None,
    ) -> RenderResult:
        started = time.perf_counter()
        width, height = size
        if width < 1 or height < 1 or width > self.config.max_render_size or height > self.config.max_render_size:
            raise AppError("RENDER_SIZE_LIMIT", "Render size is outside configured bounds.", {"size": size}, 30)
        bounds = _crop_document_bounds(self.document, crop)
        camera = camera or CameraSpec()
        transform = camera_transform(bounds, size, camera)
        use_textures = mode == "textured" and self.pack is not None
        diagnostics = RenderDiagnostics("software-textured" if use_textures else "software-flat", 2 if use_textures else 0)
        issue_coordinates = issue_coordinates or {}
        include_regions_set = frozenset(str(item) for item in include_regions)
        include_states_set = frozenset(str(item) for item in include_states)
        exclude_states_set = frozenset(str(item) for item in exclude_states)
        if mode == "textured" and self.pack is None:
            diagnostics.limitations.append("No resource pack was supplied; deterministic flat colors were used.")
        # Temporarily disable pack sampling for explicit semantic/flat modes.
        original_pack = self.pack
        if not use_textures:
            self.pack = None
            self._model_cache.clear()
        try:
            opaque, translucent = self._triangles(
                transform,
                bounds,
                diagnostics,
                changed_coordinates,
                issue_coordinates,
                include_regions_set,
                include_states_set,
                exclude_states_set,
            )
        finally:
            self.pack = original_pack
        color = np.empty((height, width, 4), dtype=np.uint8)
        color[...] = background
        zbuffer = np.full((height, width), np.inf, dtype=np.float32)
        semantics = SemanticBuffers.create(width, height)
        for triangle in opaque:
            if self._raster_triangle(
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
            if self._raster_triangle(
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
        diagnostics.limitations.append("Intersecting translucent surfaces use deterministic stable back-to-front triangle sorting.")
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
        config_payload = {
            "build_hash": self.document.content_hash,
            "camera": asdict(camera),
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
            "issue_coordinates_hash": hashlib.sha256(
                json.dumps(
                    sorted((point.as_tuple(), int(code)) for point, code in issue_coordinates.items()),
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
            "renderer": "python-cpu-rasterizer-v1",
        }
        snapshot_id = "snap_" + hashlib.sha256(json.dumps(config_payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()[:24]
        stem = name or snapshot_id
        png_path = snapshots / f"{stem}.png"
        Image.fromarray(color, "RGBA").save(png_path, format="PNG", compress_level=9, optimize=False)
        maps = semantics.write(semantic_root, snapshot_id)
        persisted_diagnostics = asdict(diagnostics)
        # Wall-clock duration is operational telemetry, not deterministic evidence.
        # Keep it in the in-memory result while excluding it from persisted manifests.
        persisted_diagnostics.pop("duration_seconds", None)
        manifest = {
            "snapshot_id": snapshot_id,
            "build_version_id": "ver_" + self.document.content_hash[:20],
            "type": "orthographic",
            "direction": name,
            "resolution": [width, height],
            "coordinate_space": "document",
            "visible_bounds": {"min": list(bounds.min.as_tuple()), "max": list(bounds.max.as_tuple())},
            "camera": asdict(camera),
            "view_matrix": list(transform.view_matrix),
            "projection_matrix": list(transform.projection_matrix),
            "lighting_preset": lighting_preset,
            "render_mode": diagnostics.render_mode,
            "render_tier": diagnostics.render_tier,
            "resource_pack_hash": self.pack.pack_hash if self.pack is not None else None,
            "renderer_version": "python-cpu-rasterizer-v1",
            "background": list(background),
            "content_hash": hashlib.sha256(png_path.read_bytes()).hexdigest(),
            "semantic_maps": {key: f"../semantic_maps/{value}" for key, value in maps.items()},
            "filters": config_payload["filters"],
            "issue_categories": {
                "0": "none",
                "1": "renderer-fallback",
                "2-255": "caller-defined-grounded-analysis-category",
            },
            "diagnostics": persisted_diagnostics,
        }
        manifest_path = snapshots / f"{stem}.manifest.json"
        atomic_write_json(manifest_path, manifest)
        return RenderResult(
            png_path,
            manifest_path,
            semantic_root / maps["metadata"],
            snapshot_id,
            manifest,
            asdict(diagnostics),
        )

    def render_slice(
        self,
        output_root: str | Path,
        *,
        axis: str,
        minimum: int,
        maximum: int | None = None,
        pixels_per_block: int = 8,
        mode: str = "textured",
        issue_coordinates: Mapping[IntVector3, int] | None = None,
        include_regions: Iterable[str] = (),
        include_states: Iterable[str] = (),
        exclude_states: Iterable[str] = (),
        name: str | None = None,
    ) -> RenderResult:
        maximum = minimum if maximum is None else maximum
        if axis not in {"x", "y", "z"} or minimum > maximum:
            raise AppError("SLICE_SPEC_INVALID", "Slice specification is invalid.", exit_code=30)
        b = self.document.bounds
        if axis == "y":
            width_cells, height_cells = b.dimensions.x, b.dimensions.z
            u_values = range(b.min.x, b.max.x + 1)
            v_values = range(b.min.z, b.max.z + 1)
            scan = range(maximum, minimum - 1, -1)
            point = lambda u, v, w: IntVector3(u, w, v)
            face = "up"
        elif axis == "x":
            width_cells, height_cells = b.dimensions.z, b.dimensions.y
            u_values = range(b.min.z, b.max.z + 1)
            v_values = range(b.max.y, b.min.y - 1, -1)
            scan = range(minimum, maximum + 1)
            point = lambda u, v, w: IntVector3(w, v, u)
            face = "west"
        else:
            width_cells, height_cells = b.dimensions.x, b.dimensions.y
            u_values = range(b.min.x, b.max.x + 1)
            v_values = range(b.max.y, b.min.y - 1, -1)
            scan = range(minimum, maximum + 1)
            point = lambda u, v, w: IntVector3(u, v, w)
            face = "north"
        width, height = width_cells * pixels_per_block, height_cells * pixels_per_block
        if width > self.config.max_render_size or height > self.config.max_render_size:
            raise AppError("RENDER_SIZE_LIMIT", "Slice render exceeds dimension limit.", {"size": [width, height]}, 30)
        color = np.zeros((height, width, 4), dtype=np.uint8)
        semantics = SemanticBuffers.create(width, height)
        diagnostics = RenderDiagnostics("software-textured" if mode == "textured" and self.pack else "software-flat", 1 if mode == "textured" and self.pack else 0)
        issue_coordinates = issue_coordinates or {}
        include_regions_set = frozenset(str(item) for item in include_regions)
        include_states_set = frozenset(str(item) for item in include_states)
        exclude_states_set = frozenset(str(item) for item in exclude_states)
        region_positions: set[IntVector3] | None = None
        if include_regions_set:
            unknown = sorted(include_regions_set - set(self._region_names))
            if unknown:
                raise AppError("RENDER_REGION_NOT_FOUND", "One or more requested render regions do not exist.", {"regions": unknown}, 30)
            region_positions = set()
            for region_name in sorted(include_regions_set):
                values = self.document.region_blocks.get(region_name)
                if values is not None:
                    region_positions.update(values)
                else:
                    region = next(item for item in self.document.regions if item.name == region_name)
                    region_positions.update(position for position in self.document.blocks if region.bounds.contains(position))
        for row, v in enumerate(v_values):
            for column, u in enumerate(u_values):
                hit: tuple[IntVector3, int] | None = None
                for w in scan:
                    candidate = point(u, v, w)
                    pid = self.document.blocks.get(candidate)
                    if pid is None:
                        continue
                    entry = self._palette[pid]
                    if entry.is_air_like:
                        continue
                    if region_positions is not None and candidate not in region_positions:
                        continue
                    if include_states_set and not _state_matches(entry, include_states_set):
                        continue
                    if exclude_states_set and _state_matches(entry, exclude_states_set):
                        continue
                    if pid is not None and not entry.is_air_like:
                        hit = candidate, pid
                        break
                if hit is None:
                    continue
                position, pid = hit
                entry = self._palette[pid]
                tile = np.empty((pixels_per_block, pixels_per_block, 4), dtype=np.uint8)
                tile[...] = palette_color(pid)
                fallback = False
                if mode == "textured" and self.pack is not None:
                    try:
                        groups = self._block_models(entry, position, diagnostics)
                        selected_texture: np.ndarray | None = None
                        for quads, textures, group_fallback in groups:
                            fallback = fallback or group_fallback
                            matching = next((quad for quad in quads if quad.face_name == face), quads[0] if quads else None)
                            if matching:
                                selected_texture = self._texture(textures, matching.texture_ref, entry.namespace, diagnostics)
                                if selected_texture is not None:
                                    tint = np.asarray(_tint(entry, matching.tint_index), dtype=np.float32)
                                    selected_texture = selected_texture.copy()
                                    selected_texture[..., :3] = np.clip(selected_texture[..., :3] * tint, 0, 255).astype(np.uint8)
                                    break
                        if selected_texture is not None:
                            tile = np.asarray(Image.fromarray(selected_texture, "RGBA").resize((pixels_per_block, pixels_per_block), Image.Resampling.NEAREST))
                    except Exception as exc:
                        if self.strict_textures:
                            raise
                        fallback = True
                        diagnostics.fallbacks.append({"type": "slice_texture_fallback", "state": entry.canonical_state, "error": str(exc)})
                y0, x0 = row * pixels_per_block, column * pixels_per_block
                color[y0:y0 + pixels_per_block, x0:x0 + pixels_per_block] = tile
                semantics.palette[y0:y0 + pixels_per_block, x0:x0 + pixels_per_block] = pid
                semantics.coordinates[y0:y0 + pixels_per_block, x0:x0 + pixels_per_block] = position.as_tuple()
                semantics.depth[y0:y0 + pixels_per_block, x0:x0 + pixels_per_block] = 0.0
                semantics.regions[y0:y0 + pixels_per_block, x0:x0 + pixels_per_block] = self._regions.get(position, 0xFFFF)
                semantics.occupancy[y0:y0 + pixels_per_block, x0:x0 + pixels_per_block] = 1
                if fallback:
                    semantics.issues[y0:y0 + pixels_per_block, x0:x0 + pixels_per_block] = 1
                issue_code = int(issue_coordinates.get(position, 0))
                if issue_code:
                    semantics.issues[y0:y0 + pixels_per_block, x0:x0 + pixels_per_block] = min(255, issue_code)
        root = Path(output_root)
        (root / "snapshots").mkdir(parents=True, exist_ok=True)
        (root / "semantic_maps").mkdir(parents=True, exist_ok=True)
        payload = {
            "build": self.document.content_hash,
            "axis": axis,
            "min": minimum,
            "max": maximum,
            "ppb": pixels_per_block,
            "mode": diagnostics.render_mode,
            "filters": {
                "regions": sorted(include_regions_set),
                "include_states": sorted(include_states_set),
                "exclude_states": sorted(exclude_states_set),
            },
        }
        snapshot_id = "snap_" + hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:24]
        stem = name or f"slice_{axis}_{minimum}" + (f"_{maximum}" if maximum != minimum else "")
        png_path = root / "snapshots" / f"{stem}.png"
        Image.fromarray(color, "RGBA").save(png_path, format="PNG", compress_level=9, optimize=False)
        maps = semantics.write(root / "semantic_maps", snapshot_id)
        manifest = {
            "snapshot_id": snapshot_id,
            "build_version_id": "ver_" + self.document.content_hash[:20],
            "type": "slice",
            "slice": {"axis": axis, "minimum": minimum, "maximum": maximum},
            "resolution": [width, height],
            "pixels_per_block": pixels_per_block,
            "coordinate_space": "document",
            "axis_orientation": {"image_x": "increasing-x" if axis != "x" else "increasing-z", "image_y": "increasing-z" if axis == "y" else "decreasing-y"},
            "render_mode": diagnostics.render_mode,
            "render_tier": diagnostics.render_tier,
            "resource_pack_hash": self.pack.pack_hash if self.pack else None,
            "renderer_version": "python-cpu-rasterizer-v1",
            "semantic_maps": {key: f"../semantic_maps/{value}" for key, value in maps.items()},
            "filters": payload["filters"],
            "diagnostics": asdict(diagnostics),
        }
        manifest_path = root / "snapshots" / f"{stem}.manifest.json"
        atomic_write_json(manifest_path, manifest)
        return RenderResult(png_path, manifest_path, root / "semantic_maps" / maps["metadata"], snapshot_id, manifest, asdict(diagnostics))


def pixel_to_block(snapshot_manifest: str | Path | dict[str, Any], px: int, py: int) -> dict[str, Any] | None:
    if isinstance(snapshot_manifest, dict):
        manifest = snapshot_manifest
        manifest_path = None
    else:
        manifest_path = Path(snapshot_manifest)
        manifest = json.loads(manifest_path.read_text("utf-8"))
    width, height = manifest["resolution"]
    if px < 0 or py < 0 or px >= width or py >= height:
        return None
    metadata_ref = manifest["semantic_maps"]["metadata"]
    if manifest_path is None:
        raise ValueError("pixel_to_block requires a manifest path to load semantic maps")
    metadata_path = (manifest_path.parent / metadata_ref).resolve()
    coordinates = load_map(metadata_path, "coordinate")
    palette = load_map(metadata_path, "palette")
    depth = load_map(metadata_path, "depth")
    regions = load_map(metadata_path, "region")
    value = coordinates[py, px]
    if int(value[0]) == NO_COORDINATE:
        return None
    return {
        "coordinate": [int(item) for item in value],
        "palette_id": int(palette[py, px]),
        "depth": float(depth[py, px]),
        "region_id": int(regions[py, px]),
    }


def block_to_pixel(snapshot_manifest: str | Path, x: int, y: int, z: int) -> list[dict[str, Any]]:
    path = Path(snapshot_manifest)
    manifest = json.loads(path.read_text("utf-8"))
    metadata_path = (path.parent / manifest["semantic_maps"]["metadata"]).resolve()
    coordinates = load_map(metadata_path, "coordinate")
    mask = np.all(coordinates == np.asarray((x, y, z), dtype=np.int32), axis=2)
    ys, xs = np.where(mask)
    return [{"px": int(px), "py": int(py)} for py, px in zip(ys.tolist(), xs.tolist(), strict=True)]


def render(
    build: BuildDocument,
    camera: dict[str, Any] | None = None,
    slice_spec: str | None = None,
    crop: IntBoundingBox | None = None,
    size: tuple[int, int] = (1536, 1536),
    mode: str = "textured",
    *,
    output_root: str | Path = ".",
    resource_pack: str | Path | None = None,
) -> RenderResult:
    pack = open_resource_pack(resource_pack)
    try:
        renderer = SoftwareRenderer(build, resource_pack=pack)
        if slice_spec:
            axis, values = slice_spec.split(":", 1)
            if ".." in values:
                minimum, maximum = (int(value) for value in values.split("..", 1))
            else:
                minimum = maximum = int(values)
            return renderer.render_slice(output_root, axis=axis, minimum=minimum, maximum=maximum, mode=mode)
        return renderer.render(output_root, camera=CameraSpec(**(camera or {})), crop=crop, size=size, mode=mode)
    finally:
        if pack:
            pack.close()
