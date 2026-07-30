from __future__ import annotations

import hashlib
import json
import math
import time
from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Iterable

import numpy as np
from mbi.canonical import BuildDocument, IntBoundingBox, IntVector3, PaletteEntry
from mbi.snapshot.raster import palette_color
from mbi.voxel import iter_items_sorted
from PIL import Image

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
    entity_rendered_models: list[dict[str, Any]] = field(default_factory=list)
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

_ENTITY_RENDERED_SUFFIXES = (
    "_banner",
    "_bed",
    "_head",
    "_shulker_box",
    "_sign",
    "_skull",
    "_wall_banner",
    "_wall_head",
    "_wall_sign",
    "_wall_skull",
)

_DYE_RGB: dict[str, tuple[int, int, int]] = {
    "white": (249, 255, 254),
    "orange": (249, 128, 29),
    "magenta": (199, 78, 189),
    "light_blue": (58, 179, 218),
    "yellow": (254, 216, 61),
    "lime": (128, 199, 31),
    "pink": (243, 139, 170),
    "gray": (71, 79, 82),
    "light_gray": (157, 157, 151),
    "cyan": (22, 156, 156),
    "purple": (137, 50, 184),
    "blue": (60, 68, 170),
    "brown": (131, 84, 50),
    "green": (94, 124, 22),
    "red": (176, 46, 38),
    "black": (29, 29, 33),
}

_LEGACY_BANNER_PATTERNS: dict[str, str] = {
    "b": "base",
    "bl": "square_bottom_left",
    "br": "square_bottom_right",
    "tl": "square_top_left",
    "tr": "square_top_right",
    "bs": "stripe_bottom",
    "ts": "stripe_top",
    "ls": "stripe_left",
    "rs": "stripe_right",
    "cs": "stripe_center",
    "ms": "stripe_middle",
    "drs": "stripe_downright",
    "dls": "stripe_downleft",
    "ss": "small_stripes",
    "cr": "cross",
    "sc": "straight_cross",
    "ld": "diagonal_left",
    "rud": "diagonal_up_right",
    "lud": "diagonal_up_left",
    "rd": "diagonal_right",
    "vh": "half_vertical",
    "vhr": "half_vertical_right",
    "hh": "half_horizontal",
    "hhb": "half_horizontal_bottom",
    "bo": "border",
    "cbo": "curly_border",
    "gra": "gradient",
    "gru": "gradient_up",
    "bri": "bricks",
    "glb": "globe",
    "cre": "creeper",
    "sku": "skull",
    "flo": "flower",
    "moj": "mojang",
    "pig": "piglin",
}


def _requires_entity_renderer(block_name: str) -> bool:
    return (
        block_name == "shulker_box"
        or block_name.endswith(_ENTITY_RENDERED_SUFFIXES)
    )


def _dye_name(block_name: str) -> str:
    for name in sorted(_DYE_RGB, key=len, reverse=True):
        if block_name == name or block_name.startswith(f"{name}_"):
            return name
    return "white"


def _entity_rotation(entry: PaletteEntry) -> int:
    facing = entry.properties.get("facing")
    if facing is not None:
        return {"north": 0, "east": 90, "south": 180, "west": 270}.get(facing, 0)
    return int(round(int(entry.properties.get("rotation", "0") or 0) * 22.5)) % 360


def _box(
    minimum: tuple[float, float, float],
    maximum: tuple[float, float, float],
    texture: str,
    *,
    uv: dict[str, list[float]] | None = None,
) -> dict[str, Any]:
    faces: dict[str, dict[str, Any]] = {}
    for face in ("down", "up", "north", "south", "west", "east"):
        face_payload: dict[str, Any] = {"texture": texture}
        if uv is not None and face in uv:
            face_payload["uv"] = uv[face]
        faces[face] = face_payload
    return {
        "from": [float(value) for value in minimum],
        "to": [float(value) for value in maximum],
        "faces": faces,
    }


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
        self.config = config or RuntimeConfig.from_environment()
        self.strict_textures = strict_textures
        self.seed = seed
        self._texture_arrays: dict[tuple[str, str], np.ndarray] = {}
        self._model_cache: dict[
            tuple[str, tuple[int, int, int] | None],
            list[tuple[list[Quad], dict[str, str], bool]],
        ] = {}
        self._entity_model_diagnostics: dict[
            tuple[str, tuple[int, int, int] | None],
            dict[str, Any],
        ] = {}
        self._palette = document.palette_by_id()
        self._region_names, self._regions = _region_ids(document)
        self._block_entities = {entity.position: entity for entity in document.block_entities}

    def _store_texture(
        self,
        key: tuple[str, str],
        value: np.ndarray,
    ) -> None:
        if (
            key not in self._texture_arrays
            and len(self._texture_arrays) >= self.config.texture_cache_items
        ):
            self._texture_arrays.pop(next(iter(self._texture_arrays)))
        self._texture_arrays[key] = value

    def _store_model(
        self,
        key: tuple[str, tuple[int, int, int] | None],
        value: list[tuple[list[Quad], dict[str, str], bool]],
    ) -> None:
        if (
            key not in self._model_cache
            and len(self._model_cache) >= self.config.model_cache_items
        ):
            oldest = next(iter(self._model_cache))
            self._model_cache.pop(oldest)
            self._entity_model_diagnostics.pop(oldest, None)
        self._model_cache[key] = value

    @staticmethod
    def _tint_entity_layer(image: np.ndarray, color: tuple[int, int, int]) -> np.ndarray:
        result = image.copy()
        luminance = result[..., :3].astype(np.float32) / 255.0
        dye = np.asarray(color, dtype=np.float32)[None, None, :]
        result[..., :3] = np.clip(luminance * dye, 0, 255).astype(np.uint8)
        return result

    def _banner_texture(self, entry: PaletteEntry, position: IntVector3) -> tuple[str, tuple[str, ...]]:
        assert self.pack is not None
        dye_name = _dye_name(entry.block_name)
        base = np.asarray(self.pack.texture("minecraft", "entity/banner/base"), dtype=np.uint8)
        composed = self._tint_entity_layer(base, _DYE_RGB[dye_name])
        applied = [f"minecraft:entity/banner/base@{dye_name}"]
        block_entity = self._block_entities.get(position)
        raw_patterns = block_entity.data.get("Patterns", block_entity.data.get("patterns", [])) if block_entity else []
        if isinstance(raw_patterns, list):
            for raw in raw_patterns:
                if not isinstance(raw, dict):
                    continue
                pattern_value = raw.get("Pattern", raw.get("pattern"))
                if isinstance(pattern_value, dict):
                    pattern_value = pattern_value.get("value")
                if not isinstance(pattern_value, str):
                    continue
                pattern_name = pattern_value.split(":", 1)[-1]
                pattern_name = _LEGACY_BANNER_PATTERNS.get(pattern_name, pattern_name)
                color_value = raw.get("Color", raw.get("color", "white"))
                if isinstance(color_value, int):
                    legacy_dyes = tuple(_DYE_RGB)
                    color_name = legacy_dyes[color_value % len(legacy_dyes)]
                else:
                    color_name = str(color_value).split(":", 1)[-1]
                color = _DYE_RGB.get(color_name, _DYE_RGB["white"])
                try:
                    mask = np.asarray(
                        self.pack.texture("minecraft", f"entity/banner/{pattern_name}"),
                        dtype=np.uint8,
                    )
                except AppError:
                    continue
                if mask.shape != composed.shape:
                    continue
                layer = self._tint_entity_layer(mask, color)
                alpha = layer[..., 3:4].astype(np.float32) / 255.0
                composed[..., :3] = np.clip(
                    layer[..., :3].astype(np.float32) * alpha
                    + composed[..., :3].astype(np.float32) * (1.0 - alpha),
                    0,
                    255,
                ).astype(np.uint8)
                composed[..., 3] = np.maximum(composed[..., 3], layer[..., 3])
                applied.append(f"minecraft:entity/banner/{pattern_name}@{color_name}")
        digest = hashlib.sha256(
            entry.canonical_state.encode("utf-8")
            + b"\0"
            + json.dumps(raw_patterns, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()[:20]
        resource = f"generated/entity/banner/{digest}"
        self._store_texture(("minecraft", resource), composed)
        return resource, tuple(applied)

    def _entity_model(
        self,
        entry: PaletteEntry,
        position: IntVector3,
    ) -> tuple[ResolvedModel, ModelInstance, tuple[str, ...]] | None:
        """Resolve block-entity geometry and entity-atlas textures.

        Vanilla deliberately supplies empty ``builtin/entity`` block models for
        these states.  The software renderer uses compact, deterministic proxy
        meshes with the real entity texture atlases, preserving semantic
        coordinate identity while making banners, skulls, signs, beds and
        shulker boxes visually distinguishable.
        """
        block = entry.block_name
        rotation = _entity_rotation(entry)
        if block.endswith("_banner"):
            entity_texture, applied = self._banner_texture(entry, position)
            cloth_uv = {
                "north": [0.25, 0.25, 5.25, 10.25],
                "south": [0.25, 0.25, 5.25, 10.25],
            }
            model = ResolvedModel(
                (
                    _box((3, 0, 14.75), (13, 15, 15.25), "#entity", uv=cloth_uv),
                    _box((2, 14.5, 14), (14, 16, 16), "#wood"),
                ),
                {
                    "entity": f"minecraft:{entity_texture}",
                    "wood": "minecraft:block/oak_planks",
                },
                False,
                ("builtin:entity/banner",),
            )
            return model, ModelInstance("builtin:entity/banner", y_rotation=rotation), applied
        if block.endswith(("_skull", "_head")):
            head_kind = block
            for suffix in ("_wall_skull", "_wall_head", "_skull", "_head"):
                if head_kind.endswith(suffix):
                    head_kind = head_kind[: -len(suffix)]
                    break
            texture = {
                "skeleton": "entity/skeleton/skeleton",
                "wither_skeleton": "entity/skeleton/wither_skeleton",
                "zombie": "entity/zombie/zombie",
                "creeper": "entity/creeper/creeper",
                "piglin": "entity/piglin/piglin",
                "dragon": "entity/enderdragon/dragon",
                "player": "entity/player/wide/steve",
            }.get(head_kind, "entity/skeleton/skeleton")
            head_uv = {
                "north": [2, 4, 4, 8],
                "south": [6, 4, 8, 8],
                "west": [0, 4, 2, 8],
                "east": [4, 4, 6, 8],
                "up": [2, 0, 4, 4],
                "down": [4, 0, 6, 4],
            }
            wall = "_wall_" in block
            minimum = (4, 4, 8) if wall else (4, 0, 4)
            maximum = (12, 12, 16) if wall else (12, 8, 12)
            model = ResolvedModel(
                (_box(minimum, maximum, "#entity", uv=head_uv),),
                {"entity": f"minecraft:{texture}"},
                False,
                ("builtin:entity/skull",),
            )
            return model, ModelInstance("builtin:entity/skull", y_rotation=rotation), (f"minecraft:{texture}",)
        if block == "shulker_box" or block.endswith("_shulker_box"):
            color = _dye_name(block)
            suffix = "" if block == "shulker_box" else f"_{color}"
            texture = f"entity/shulker/shulker{suffix}"
            model = ResolvedModel(
                (_box((0, 0, 0), (16, 16, 16), "#entity"),),
                {"entity": f"minecraft:{texture}"},
                False,
                ("builtin:entity/shulker_box",),
            )
            return model, ModelInstance("builtin:entity/shulker_box", y_rotation=rotation), (f"minecraft:{texture}",)
        if block.endswith("_bed"):
            color = _dye_name(block)
            texture = f"entity/bed/{color}"
            model = ResolvedModel(
                (_box((0, 3, 0), (16, 9, 16), "#entity"),),
                {"entity": f"minecraft:{texture}"},
                False,
                ("builtin:entity/bed",),
            )
            return model, ModelInstance("builtin:entity/bed", y_rotation=rotation), (f"minecraft:{texture}",)
        if block.endswith(("_sign", "_wall_sign")):
            wood = block
            for suffix in ("_wall_hanging_sign", "_hanging_sign", "_wall_sign", "_sign"):
                if wood.endswith(suffix):
                    wood = wood[: -len(suffix)]
                    break
            texture = f"entity/signs/{wood}"
            wall = "_wall_" in block
            if wall:
                plate = (2, 4, 14.25), (14, 13, 15.75)
            else:
                plate = (2, 7, 7.25), (14, 16, 8.75)
            elements = [_box(plate[0], plate[1], "#entity")]
            if not wall:
                elements.append(_box((7, 0, 7), (9, 8, 9), "#entity"))
            model = ResolvedModel(
                tuple(elements),
                {"entity": f"minecraft:{texture}"},
                False,
                ("builtin:entity/sign",),
            )
            return model, ModelInstance("builtin:entity/sign", y_rotation=rotation), (f"minecraft:{texture}",)
        return None

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
            self._store_texture(key, array)
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
        # No-pack fallback geometry is coordinate-independent. Sharing it by
        # state prevents a multi-million-coordinate cache. Resource-pack model
        # selection may be seeded by position, so that cache remains
        # coordinate-aware but is strictly bounded by RuntimeConfig.
        cache_key = (
            entry.canonical_state,
            position.as_tuple() if self.pack is not None else None,
        )
        if cache_key in self._model_cache:
            entity_diagnostic = self._entity_model_diagnostics.get(cache_key)
            if entity_diagnostic is not None:
                diagnostics.entity_rendered_models.append(dict(entity_diagnostic))
            return self._model_cache[cache_key]
        if self.pack is None:
            result = [(fallback_cube(), {}, True)]
            self._store_model(cache_key, result)
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
            self._store_model(cache_key, result)
            return result
        try:
            instances = self.pack.select_models(entry.canonical_state, position.as_tuple(), self.seed)
            if not instances:
                raise AppError("BLOCKSTATE_NO_MODEL", "No matching blockstate model was found.", {"state": entry.canonical_state}, 31)
            for instance in instances:
                model = self.pack.resolve_model(instance.model)
                quads = model_quads(model, instance)
                if not quads:
                    entity = self._entity_model(entry, position) if _requires_entity_renderer(entry.block_name) else None
                    if entity is None:
                        raise AppError("MODEL_NO_ELEMENTS", "Resolved model has no static elements.", {"model": instance.model}, 31)
                    entity_model, entity_instance, texture_paths = entity
                    entity_quads = model_quads(entity_model, entity_instance)
                    entity_diagnostic = {
                        "code": "ENTITY_RENDERED",
                        "state": entry.canonical_state,
                        "coordinate": position.as_tuple(),
                        "representation": "entity_texture_proxy",
                        "textures": list(texture_paths),
                        "tier": 2,
                    }
                    diagnostics.entity_rendered_models.append(entity_diagnostic)
                    self._entity_model_diagnostics[cache_key] = entity_diagnostic
                    result.append((entity_quads, entity_model.textures, False))
                    continue
                result.append((quads, model.textures, False))
            if entry.properties.get("waterlogged") == "true":
                fluid_model = ResolvedModel(
                    ({
                        "from": [0, 0, 0],
                        "to": [16, 15.5, 16],
                        "faces": {
                            "up": {"texture": "#still"},
                            "down": {"texture": "#still"},
                            "north": {"texture": "#flow"},
                            "south": {"texture": "#flow"},
                            "west": {"texture": "#flow"},
                            "east": {"texture": "#flow"},
                        },
                    },),
                    {
                        "still": "minecraft:block/water_still",
                        "flow": "minecraft:block/water_flow",
                    },
                    False,
                    ("builtin:fluid-overlay",),
                )
                result.append(
                    (
                        model_quads(
                            fluid_model,
                            ModelInstance("builtin:fluid-overlay"),
                        ),
                        fluid_model.textures,
                        False,
                    )
                )
        except Exception as exc:
            if self.strict_textures:
                if isinstance(exc, AppError):
                    raise
                raise AppError("MODEL_RESOLUTION_FAILED", "Block model resolution failed.", {"state": entry.canonical_state}, 31) from exc
            diagnostics.fallback_count += 1
            entity_rendered = (
                _requires_entity_renderer(entry.block_name)
                and isinstance(exc, AppError)
                and exc.code == "MODEL_NO_ELEMENTS"
            )
            item = {
                "code": "ENTITY_RENDERED" if entity_rendered else "MODEL_FALLBACK",
                "state": entry.canonical_state,
                "coordinate": position.as_tuple(),
                "reason": str(exc),
                "tier": 0,
            }
            if entity_rendered:
                item["representation"] = "symbolic_geometry_proxy"
                diagnostics.entity_rendered_models.append(item)
                diagnostics.fallbacks.append({"type": "entity_rendered_proxy", **item})
            else:
                diagnostics.unsupported_models.append(item)
                diagnostics.fallbacks.append({"type": "model_fallback", **item})
            result = [(fallback_cube(), {}, True)]
        self._store_model(cache_key, result)
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
        viewport: tuple[int, int, int, int] | None = None,
        block_limit: int | None = None,
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
        considered_count = 0
        visible_count = 0
        cube = np.asarray(
            [
                (0, 0, 0),
                (0, 0, 1),
                (0, 1, 0),
                (0, 1, 1),
                (1, 0, 0),
                (1, 0, 1),
                (1, 1, 0),
                (1, 1, 1),
            ],
            dtype=np.float64,
        )
        for block_index, (position, pid) in enumerate(
            iter_items_sorted(self.document.blocks)
        ):
            if not bounds.contains(position):
                continue
            if region_positions is not None and position not in region_positions:
                continue
            entry = self._palette[pid]
            if include_states and not _state_matches(entry, include_states):
                continue
            if exclude_states and _state_matches(entry, exclude_states):
                continue
            if viewport is not None:
                screen_bounds, _ = transform.project(
                    cube
                    + np.asarray(position.as_tuple(), dtype=np.float64)[None, :]
                )
                x0, y0, x1, y1 = viewport
                if (
                    float(screen_bounds[:, 0].max()) < x0
                    or float(screen_bounds[:, 1].max()) < y0
                    or float(screen_bounds[:, 0].min()) >= x1
                    or float(screen_bounds[:, 1].min()) >= y1
                ):
                    continue
            considered_count += 1
            palette_id = pid
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
                visible_count += 1
                diagnostics.blocks_visible += 1
                effective_limit = (
                    self.config.max_visible_blocks
                    if block_limit is None
                    else block_limit
                )
                if effective_limit > 0 and visible_count > effective_limit:
                    raise AppError(
                        "RENDER_BLOCK_LIMIT",
                        "Render tile exceeds configured visible-block limit.",
                        {
                            "actualAtLeast": visible_count,
                            "limit": effective_limit,
                            "scope": "tile" if viewport is not None else "frame",
                            "viewport": viewport,
                        },
                        30,
                    )
        diagnostics.blocks_considered += considered_count
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
        screen_offset: tuple[int, int] = (0, 0),
    ) -> bool:
        p = triangle.screen - np.asarray(screen_offset, dtype=np.float64)[None, :]
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

    def render_tiled(
        self,
        output_root: str | Path,
        *,
        camera: CameraSpec | None = None,
        crop: IntBoundingBox | None = None,
        size: tuple[int, int] = (4096, 4096),
        tile_size: int = 512,
        resume: bool = False,
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
        """Render exact screen-space tiles with durable per-tile checkpoints.

        Geometry and camera transforms are identical to :meth:`render`.  Only
        raster buffers are tiled; semantic binary maps are disk-backed memmaps,
        so peak RAM scales with one tile instead of the full output resolution.
        A tile marker is written only after its PNG and every semantic slice are
        flushed, making ``--resume`` safe after an interrupted process.
        """
        started = time.perf_counter()
        width, height = size
        if (
            width < 1
            or height < 1
            or width > self.config.max_render_size
            or height > self.config.max_render_size
        ):
            raise AppError(
                "RENDER_SIZE_LIMIT",
                "Render size is outside configured bounds.",
                {"size": size},
                30,
            )
        if tile_size < 32 or tile_size > self.config.max_render_size:
            raise AppError(
                "RENDER_TILE_SIZE",
                "Tile size must be between 32 and the configured render-size limit.",
                {"tile_size": tile_size},
                2,
            )
        tile_count = (
            math.ceil(width / tile_size)
            * math.ceil(height / tile_size)
        )
        total_tile_work = width * height * tile_count
        if total_tile_work > self.config.max_total_tile_work:
            raise AppError(
                "RENDER_TOTAL_TILE_WORK_LIMIT",
                "Render exceeds the configured total pixel-by-tile safety ceiling.",
                {
                    "actual": total_tile_work,
                    "limit": self.config.max_total_tile_work,
                    "resolution": [width, height],
                    "tile_count": tile_count,
                },
                30,
            )

        bounds = _crop_document_bounds(self.document, crop)
        camera = camera or CameraSpec()
        transform = camera_transform(bounds, size, camera)
        use_textures = mode == "textured" and self.pack is not None
        diagnostics = RenderDiagnostics(
            "software-textured-tiled" if use_textures else "software-flat-tiled",
            2 if use_textures else 0,
        )
        issue_coordinates = issue_coordinates or {}
        include_regions_set = frozenset(str(item) for item in include_regions)
        include_states_set = frozenset(str(item) for item in include_states)
        exclude_states_set = frozenset(str(item) for item in exclude_states)
        if mode == "textured" and self.pack is None:
            diagnostics.limitations.append(
                "No resource pack was supplied; deterministic flat colors were used."
            )

        config_payload = {
            "build_hash": self.document.content_hash,
            "camera": asdict(camera),
            "bounds": {
                "min": bounds.min.as_tuple(),
                "max": bounds.max.as_tuple(),
            },
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
                    sorted(
                        (point.as_tuple(), int(code))
                        for point, code in issue_coordinates.items()
                    ),
                    separators=(",", ":"),
                ).encode()
            ).hexdigest(),
            "renderer": "python-cpu-rasterizer-v1-tiled",
            "tile_size": tile_size,
        }
        snapshot_id = "snap_" + hashlib.sha256(
            json.dumps(
                config_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()[:24]
        root = Path(output_root)
        snapshots = root / "snapshots"
        semantic_root = root / "semantic_maps"
        checkpoint_root = root / "render_checkpoints" / snapshot_id
        snapshots.mkdir(parents=True, exist_ok=True)
        semantic_root.mkdir(parents=True, exist_ok=True)
        checkpoint_root.mkdir(parents=True, exist_ok=True)
        stem = name or snapshot_id
        png_path = snapshots / f"{stem}.png"
        manifest_path = snapshots / f"{stem}.manifest.json"
        semantic_metadata_path = semantic_root / f"{snapshot_id}.metadata.json"
        if (
            resume
            and png_path.is_file()
            and manifest_path.is_file()
            and semantic_metadata_path.is_file()
        ):
            manifest = json.loads(manifest_path.read_text("utf-8"))
            tile_count = (
                math.ceil(width / tile_size)
                * math.ceil(height / tile_size)
            )
            manifest.setdefault("tiled", {})["completed_tiles"] = tile_count
            manifest["tiled"]["resumed_tiles"] = tile_count
            manifest["tiled"]["resume_source"] = "finalized-output"
            atomic_write_json(manifest_path, manifest)
            persisted = dict(manifest.get("diagnostics", {}))
            persisted["duration_seconds"] = round(
                time.perf_counter() - started,
                6,
            )
            return RenderResult(
                png_path,
                manifest_path,
                semantic_metadata_path,
                snapshot_id,
                manifest,
                persisted,
            )

        original_pack = self.pack
        if not use_textures:
            self.pack = None
            self._model_cache.clear()
        array_specs: dict[str, tuple[np.dtype[Any], tuple[int, ...], Any]] = {
            "palette": (np.dtype("<u4"), (height, width), NO_PALETTE),
            "coordinate": (
                np.dtype("<i4"),
                (height, width, 3),
                NO_COORDINATE,
            ),
            "depth": (np.dtype("<f4"), (height, width), np.inf),
            "normal": (np.dtype("i1"), (height, width, 3), 0),
            "region": (
                np.dtype("<u2"),
                (height, width),
                np.iinfo(np.uint16).max,
            ),
            "occupancy": (np.dtype("u1"), (height, width), 0),
            "changed": (np.dtype("u1"), (height, width), 0),
            "issue": (np.dtype("u1"), (height, width), 0),
        }
        mapped: dict[str, np.memmap[Any, Any]] = {}
        all_maps_reused = True
        for map_name, (dtype, shape, fill_value) in array_specs.items():
            path = semantic_root / f"{snapshot_id}.{map_name}.bin"
            expected_bytes = int(np.prod(shape)) * dtype.itemsize
            reuse = resume and path.is_file() and path.stat().st_size == expected_bytes
            all_maps_reused = all_maps_reused and reuse
            mapped_array = np.memmap(
                path,
                dtype=dtype,
                mode="r+" if reuse else "w+",
                shape=shape,
                order="C",
            )
            if not reuse:
                mapped_array[...] = fill_value
                mapped_array.flush()
            mapped[map_name] = mapped_array

        final_image = Image.new("RGBA", (width, height), background)
        palette_image = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        completed_tiles = 0
        resumed_tiles = 0
        peak_triangle_count = 0
        scene_visible_blocks = sum(
            1
            for point, palette_id in iter_items_sorted(self.document.blocks)
            if bounds.contains(point)
            and not self._palette[palette_id].is_air_like
        )
        if scene_visible_blocks > self.config.max_visible_blocks:
            diagnostics.limitations.append(
                "Scene visible-block count exceeds the per-tile budget; "
                "screen-space tiling is enforcing the budget independently."
            )
        for y0 in range(0, height, tile_size):
            y1 = min(height, y0 + tile_size)
            for x0 in range(0, width, tile_size):
                x1 = min(width, x0 + tile_size)
                tile_key = f"x{x0:06d}_y{y0:06d}_{x1 - x0}x{y1 - y0}"
                tile_path = checkpoint_root / f"{tile_key}.png"
                marker_path = checkpoint_root / f"{tile_key}.done.json"
                tile_complete = False
                if (
                    resume
                    and all_maps_reused
                    and tile_path.is_file()
                    and marker_path.is_file()
                ):
                    try:
                        marker = json.loads(marker_path.read_text("utf-8"))
                        tile_complete = (
                            marker.get("snapshot_id") == snapshot_id
                            and marker.get("sha256")
                            == hashlib.sha256(tile_path.read_bytes()).hexdigest()
                        )
                    except (OSError, json.JSONDecodeError):
                        tile_complete = False
                if tile_complete:
                    final_image.paste(
                        Image.open(tile_path).convert("RGBA"),
                        (x0, y0),
                    )
                    resumed_tiles += 1
                else:
                    self.pack = original_pack if use_textures else None
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
                            viewport=(x0, y0, x1, y1),
                            block_limit=self.config.max_visible_blocks,
                        )
                    finally:
                        self.pack = original_pack
                    peak_triangle_count = max(
                        peak_triangle_count,
                        len(opaque) + len(translucent),
                    )
                    tile_width = x1 - x0
                    tile_height = y1 - y0
                    color = np.empty(
                        (tile_height, tile_width, 4),
                        dtype=np.uint8,
                    )
                    color[...] = background
                    zbuffer = np.full(
                        (tile_height, tile_width),
                        np.inf,
                        dtype=np.float32,
                    )
                    semantics = SemanticBuffers.create(tile_width, tile_height)
                    for triangle in opaque:
                        if (
                            float(triangle.screen[:, 0].max()) < x0
                            or float(triangle.screen[:, 1].max()) < y0
                            or float(triangle.screen[:, 0].min()) >= x1
                            or float(triangle.screen[:, 1].min()) >= y1
                        ):
                            continue
                        if self._raster_triangle(
                            triangle,
                            color,
                            zbuffer,
                            semantics,
                            translucent=False,
                            lighting_preset=lighting_preset,
                            changed_coordinates=changed_coordinates,
                            issue_coordinates=issue_coordinates,
                            screen_offset=(x0, y0),
                        ):
                            diagnostics.triangles_rasterized += 1
                    for triangle in translucent:
                        if (
                            float(triangle.screen[:, 0].max()) < x0
                            or float(triangle.screen[:, 1].max()) < y0
                            or float(triangle.screen[:, 0].min()) >= x1
                            or float(triangle.screen[:, 1].min()) >= y1
                        ):
                            continue
                        if self._raster_triangle(
                            triangle,
                            color,
                            zbuffer,
                            semantics,
                            translucent=True,
                            lighting_preset=lighting_preset,
                            changed_coordinates=changed_coordinates,
                            issue_coordinates=issue_coordinates,
                            screen_offset=(x0, y0),
                        ):
                            diagnostics.triangles_rasterized += 1
                    mapped["palette"][y0:y1, x0:x1] = semantics.palette
                    mapped["coordinate"][y0:y1, x0:x1] = semantics.coordinates
                    mapped["depth"][y0:y1, x0:x1] = semantics.depth
                    mapped["normal"][y0:y1, x0:x1] = semantics.normals
                    mapped["region"][y0:y1, x0:x1] = semantics.regions
                    mapped["occupancy"][y0:y1, x0:x1] = semantics.occupancy
                    mapped["changed"][y0:y1, x0:x1] = semantics.changed
                    mapped["issue"][y0:y1, x0:x1] = semantics.issues
                    for mapped_array in mapped.values():
                        mapped_array.flush()
                    tile_image = Image.fromarray(color, "RGBA")
                    tile_image.save(
                        tile_path,
                        format="PNG",
                        compress_level=9,
                        optimize=False,
                    )
                    atomic_write_json(
                        marker_path,
                        {
                            "schema": "mbi.render-tile-checkpoint.v1",
                            "snapshot_id": snapshot_id,
                            "bounds": [x0, y0, x1, y1],
                            "sha256": hashlib.sha256(
                                tile_path.read_bytes()
                            ).hexdigest(),
                        },
                    )
                    final_image.paste(tile_image, (x0, y0))
                    del opaque, translucent, color, zbuffer, semantics
                    self._model_cache.clear()
                    self._entity_model_diagnostics.clear()
                palette_values = np.asarray(
                    mapped["palette"][y0:y1, x0:x1]
                )
                palette_rgba = np.zeros(
                    (y1 - y0, x1 - x0, 4),
                    dtype=np.uint8,
                )
                occupied = palette_values != NO_PALETTE
                palette_rgba[..., 0] = (
                    (palette_values >> 16) & 0xFF
                ).astype(np.uint8)
                palette_rgba[..., 1] = (
                    (palette_values >> 8) & 0xFF
                ).astype(np.uint8)
                palette_rgba[..., 2] = (palette_values & 0xFF).astype(
                    np.uint8
                )
                palette_rgba[..., 3] = occupied.astype(np.uint8) * 255
                palette_image.paste(
                    Image.fromarray(palette_rgba, "RGBA"),
                    (x0, y0),
                )
                completed_tiles += 1

        final_image.save(
            png_path,
            format="PNG",
            compress_level=9,
            optimize=False,
        )
        palette_png = f"{snapshot_id}.palette.png"
        palette_image.save(
            semantic_root / palette_png,
            format="PNG",
            compress_level=9,
            optimize=False,
        )
        semantic_metadata: dict[str, Any] = {
            "schema": "mbi.semantic-maps.v1",
            "storage": "disk-backed-tiled",
            "tile_size": tile_size,
            "arrays": {},
        }
        maps: dict[str, str] = {}
        for map_name, (dtype, shape, _) in array_specs.items():
            filename = f"{snapshot_id}.{map_name}.bin"
            maps[map_name] = filename
            semantic_metadata["arrays"][map_name] = {
                "path": filename,
                "dtype": dtype.str,
                "shape": list(shape),
                "order": "C",
                "endianness": "little",
            }
        atomic_write_json(semantic_metadata_path, semantic_metadata)
        maps["palette_png"] = palette_png
        maps["metadata"] = semantic_metadata_path.name

        diagnostics.duration_seconds = round(
            time.perf_counter() - started,
            6,
        )
        diagnostics.peak_estimated_working_memory = (
            tile_size * tile_size * (4 + 4 + 12 + 4 + 3 + 2 + 1 + 1)
            + peak_triangle_count * 640
            + width * height * 8
        )
        diagnostics.limitations.append(
            "Intersecting translucent surfaces use deterministic stable "
            "back-to-front triangle sorting."
        )
        if self.pack is not None:
            for item in self.pack.diagnostics:
                if (
                    item.get("code") != "ANIMATED_TEXTURE_FIRST_FRAME"
                    and item not in diagnostics.asset_diagnostics
                ):
                    diagnostics.asset_diagnostics.append(item)
        persisted_diagnostics = asdict(diagnostics)
        persisted_diagnostics.pop("duration_seconds", None)
        manifest = {
            "snapshot_id": snapshot_id,
            "build_version_id": "ver_" + self.document.content_hash[:20],
            "type": "orthographic",
            "direction": name,
            "resolution": [width, height],
            "coordinate_space": "document",
            "visible_bounds": {
                "min": list(bounds.min.as_tuple()),
                "max": list(bounds.max.as_tuple()),
            },
            "camera": asdict(camera),
            "view_matrix": list(transform.view_matrix),
            "projection_matrix": list(transform.projection_matrix),
            "lighting_preset": lighting_preset,
            "render_mode": diagnostics.render_mode,
            "render_tier": diagnostics.render_tier,
            "resource_pack_hash": (
                self.pack.pack_hash if self.pack is not None else None
            ),
            "renderer_version": "python-cpu-rasterizer-v1-tiled",
            "background": list(background),
            "content_hash": hashlib.sha256(png_path.read_bytes()).hexdigest(),
            "semantic_maps": {
                key: f"../semantic_maps/{value}"
                for key, value in maps.items()
            },
            "filters": config_payload["filters"],
            "issue_categories": {
                "0": "none",
                "1": "renderer-fallback",
                "2-255": "caller-defined-grounded-analysis-category",
            },
            "tiled": {
                "schema": "mbi.tiled-render.v1",
                "tile_size": tile_size,
                "tile_count": tile_count,
                "completed_tiles": completed_tiles,
                "resumed_tiles": resumed_tiles,
                "checkpoint_directory": str(checkpoint_root),
                "exact_screen_space": True,
                "scene_visible_blocks": scene_visible_blocks,
                "per_tile_visible_block_limit": self.config.max_visible_blocks,
                "scene_limit_advisory": (
                    scene_visible_blocks > self.config.max_visible_blocks
                ),
                "total_pixel_tile_work": total_tile_work,
                "total_pixel_tile_work_limit": self.config.max_total_tile_work,
            },
            "diagnostics": persisted_diagnostics,
        }
        atomic_write_json(manifest_path, manifest)
        return RenderResult(
            png_path,
            manifest_path,
            semantic_metadata_path,
            snapshot_id,
            manifest,
            asdict(diagnostics),
        )

    def render_lod(
        self,
        output_root: str | Path,
        *,
        camera: CameraSpec | None = None,
        crop: IntBoundingBox | None = None,
        size: tuple[int, int] = (4096, 4096),
        background: tuple[int, int, int, int] = (0, 0, 0, 0),
        include_regions: Iterable[str] = (),
        include_states: Iterable[str] = (),
        exclude_states: Iterable[str] = (),
        name: str | None = None,
        resume: bool = False,
        **_: Any,
    ) -> RenderResult:
        """Render a bounded-memory one-sample-per-output-pixel overview.

        This is intentionally non-exact. It projects block centers, keeps the
        nearest sample per pixel, and records that LOD contract in the manifest.
        """
        started = time.perf_counter()
        width, height = size
        if (
            width < 1
            or height < 1
            or width > self.config.max_render_size
            or height > self.config.max_render_size
        ):
            raise AppError(
                "RENDER_SIZE_LIMIT",
                "Render size is outside configured bounds.",
                {"size": size},
                30,
            )
        bounds = _crop_document_bounds(self.document, crop)
        camera = camera or CameraSpec()
        transform = camera_transform(bounds, size, camera)
        include_regions_set = frozenset(str(item) for item in include_regions)
        include_states_set = frozenset(str(item) for item in include_states)
        exclude_states_set = frozenset(str(item) for item in exclude_states)
        config_payload = {
            "build_hash": self.document.content_hash,
            "camera": asdict(camera),
            "bounds": {
                "min": bounds.min.as_tuple(),
                "max": bounds.max.as_tuple(),
            },
            "size": size,
            "filters": {
                "regions": sorted(include_regions_set),
                "include_states": sorted(include_states_set),
                "exclude_states": sorted(exclude_states_set),
            },
            "renderer": "python-cpu-lod-center-sampler-v1",
        }
        snapshot_id = "snap_" + hashlib.sha256(
            json.dumps(
                config_payload,
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()[:24]
        root = Path(output_root)
        snapshots = root / "snapshots"
        semantic_root = root / "semantic_maps"
        snapshots.mkdir(parents=True, exist_ok=True)
        semantic_root.mkdir(parents=True, exist_ok=True)
        stem = name or snapshot_id
        png_path = snapshots / f"{stem}.png"
        manifest_path = snapshots / f"{stem}.manifest.json"
        metadata_path = semantic_root / f"{snapshot_id}.metadata.json"
        if resume and png_path.is_file() and manifest_path.is_file() and metadata_path.is_file():
            manifest = json.loads(manifest_path.read_text("utf-8"))
            diagnostics = dict(manifest.get("diagnostics", {}))
            diagnostics["duration_seconds"] = round(time.perf_counter() - started, 6)
            return RenderResult(
                png_path,
                manifest_path,
                metadata_path,
                snapshot_id,
                manifest,
                diagnostics,
            )

        array_specs: dict[str, tuple[np.dtype[Any], tuple[int, ...], Any]] = {
            "palette": (np.dtype("<u4"), (height, width), NO_PALETTE),
            "coordinate": (
                np.dtype("<i4"),
                (height, width, 3),
                NO_COORDINATE,
            ),
            "depth": (np.dtype("<f4"), (height, width), np.inf),
            "normal": (np.dtype("i1"), (height, width, 3), 0),
            "region": (
                np.dtype("<u2"),
                (height, width),
                np.iinfo(np.uint16).max,
            ),
            "occupancy": (np.dtype("u1"), (height, width), 0),
            "changed": (np.dtype("u1"), (height, width), 0),
            "issue": (np.dtype("u1"), (height, width), 0),
        }
        mapped: dict[str, np.memmap[Any, Any]] = {}
        for map_name, (dtype, shape, fill_value) in array_specs.items():
            mapped_array = np.memmap(
                semantic_root / f"{snapshot_id}.{map_name}.bin",
                dtype=dtype,
                mode="w+",
                shape=shape,
                order="C",
            )
            mapped_array[...] = fill_value
            mapped_array.flush()
            mapped[map_name] = mapped_array

        region_positions: set[IntVector3] | None = None
        if include_regions_set:
            region_positions = set()
            for region_name in sorted(include_regions_set):
                values = self.document.region_blocks.get(region_name)
                if values is None:
                    raise AppError(
                        "RENDER_REGION_NOT_FOUND",
                        "Requested render region does not exist.",
                        {"region": region_name},
                        30,
                    )
                region_positions.update(values)
        considered = accepted = replacements = 0
        for point, palette_id in iter_items_sorted(self.document.blocks):
            if not bounds.contains(point):
                continue
            if region_positions is not None and point not in region_positions:
                continue
            entry = self._palette[palette_id]
            if entry.is_air_like:
                continue
            if include_states_set and not _state_matches(entry, include_states_set):
                continue
            if exclude_states_set and _state_matches(entry, exclude_states_set):
                continue
            considered += 1
            screen, depths = transform.project(
                np.asarray(
                    [[point.x + 0.5, point.y + 0.5, point.z + 0.5]],
                    dtype=np.float64,
                )
            )
            px = int(round(float(screen[0, 0])))
            py = int(round(float(screen[0, 1])))
            if not (0 <= px < width and 0 <= py < height):
                continue
            depth = float(depths[0])
            if depth >= float(mapped["depth"][py, px]):
                continue
            replacements += int(mapped["occupancy"][py, px] != 0)
            mapped["palette"][py, px] = palette_id
            mapped["coordinate"][py, px] = point.as_tuple()
            mapped["depth"][py, px] = depth
            mapped["region"][py, px] = self._regions.get(
                point,
                np.iinfo(np.uint16).max,
            )
            mapped["occupancy"][py, px] = 1
            accepted += 1
        for mapped_array in mapped.values():
            mapped_array.flush()

        palette_values = np.asarray(mapped["palette"])
        image = np.empty((height, width, 4), dtype=np.uint8)
        image[...] = background
        occupied = palette_values != NO_PALETTE
        for palette_id in np.unique(palette_values[occupied]):
            image[palette_values == palette_id] = palette_color(int(palette_id))
        Image.fromarray(image, "RGBA").save(
            png_path,
            format="PNG",
            compress_level=9,
            optimize=False,
        )
        palette_png = f"{snapshot_id}.palette.png"
        Image.fromarray(image, "RGBA").save(
            semantic_root / palette_png,
            format="PNG",
            compress_level=9,
            optimize=False,
        )
        semantic_metadata = {
            "schema": "mbi.semantic-maps.v1",
            "storage": "disk-backed-lod",
            "arrays": {
                map_name: {
                    "path": f"{snapshot_id}.{map_name}.bin",
                    "dtype": dtype.str,
                    "shape": list(shape),
                    "order": "C",
                    "endianness": "little",
                }
                for map_name, (dtype, shape, _) in array_specs.items()
            },
        }
        atomic_write_json(metadata_path, semantic_metadata)
        maps = {
            map_name: f"../semantic_maps/{snapshot_id}.{map_name}.bin"
            for map_name in array_specs
        }
        maps["palette_png"] = f"../semantic_maps/{palette_png}"
        maps["metadata"] = f"../semantic_maps/{metadata_path.name}"
        diagnostics = {
            "render_mode": "software-lod-flat",
            "render_tier": -1,
            "blocks_considered": considered,
            "samples_accepted": accepted,
            "samples_replaced_by_nearer_block": replacements,
            "duration_seconds": round(time.perf_counter() - started, 6),
            "peak_estimated_working_memory": (
                width * height * 4
                + max(dtype.itemsize * int(np.prod(shape)) for dtype, shape, _ in array_specs.values())
            ),
            "limitations": [
                "Non-exact LOD: block centers are merged to the nearest sample per output pixel.",
                "Textures, model silhouettes, translucent blending, and sub-pixel blocks are not exact.",
            ],
        }
        persisted_diagnostics = dict(diagnostics)
        persisted_diagnostics.pop("duration_seconds", None)
        manifest = {
            "snapshot_id": snapshot_id,
            "build_version_id": "ver_" + self.document.content_hash[:20],
            "type": "orthographic-lod",
            "resolution": [width, height],
            "coordinate_space": "document",
            "visible_bounds": {
                "min": list(bounds.min.as_tuple()),
                "max": list(bounds.max.as_tuple()),
            },
            "camera": asdict(camera),
            "renderer_version": "python-cpu-lod-center-sampler-v1",
            "background": list(background),
            "content_hash": hashlib.sha256(png_path.read_bytes()).hexdigest(),
            "semantic_maps": maps,
            "filters": config_payload["filters"],
            "accuracy": {
                "profile": "lod",
                "exact": False,
                "texture_exact": False,
                "model_shape_exact": False,
                "contract": "nearest-block-center sample per output pixel",
            },
            "lod": {
                "enabled": True,
                "method": "nearest-depth-block-center-per-pixel-v1",
                "source_block_count": considered,
                "accepted_sample_count": accepted,
            },
            "diagnostics": persisted_diagnostics,
        }
        atomic_write_json(manifest_path, manifest)
        return RenderResult(
            png_path,
            manifest_path,
            metadata_path,
            snapshot_id,
            manifest,
            diagnostics,
        )

    def render_slice(
        self,
        output_root: str | Path,
        *,
        axis: str,
        minimum: int,
        maximum: int | None = None,
        crop: IntBoundingBox | None = None,
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
        b = self.document.bounds if crop is None else self.document.bounds.intersection(crop)
        if b is None:
            raise AppError("RENDER_EMPTY_CROP", "Slice crop does not intersect the build.", exit_code=30)
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
            "crop": {"min": b.min.as_tuple(), "max": b.max.as_tuple()},
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
            "visible_bounds": {"min": list(b.min.as_tuple()), "max": list(b.max.as_tuple())},
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
