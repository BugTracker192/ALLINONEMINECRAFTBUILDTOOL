from __future__ import annotations

import hashlib
import io
import json
import math
import os
import posixpath
import stat
import zipfile
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Iterable

from PIL import Image

from app.assets.bundled import ensure_bundled_asset
from app.assets.legacy_ids import migrate_asset_state
from app.config import RuntimeConfig
from app.errors import AppError


def bundled_resource_pack_path() -> Path | None:
    """Return the verified bundle or reconstruct it from ordinary-Git parts."""
    return ensure_bundled_asset()


def resolve_resource_pack_path(source: str | Path | None = None) -> Path | None:
    """Resolve resource assets without routine human configuration.

    Precedence: explicit argument, ``MBI_RESOURCE_PACK``, private bundled pack,
    then common workspace locations. Use the literal value ``none`` or set
    ``MBI_DISABLE_BUNDLED_ASSETS=1`` to intentionally request flat rendering.
    """
    if source is not None:
        value = str(source).strip()
        if value.lower() in {"none", "off", "flat"}:
            return None
        candidate = Path(value).expanduser().resolve()
        if not candidate.exists():
            raise AppError("RESOURCE_PACK_NOT_FOUND", "Resource-pack path does not exist.", {"path": value}, 31)
        return candidate
    env_value = os.environ.get("MBI_RESOURCE_PACK", "").strip()
    if env_value:
        return resolve_resource_pack_path(env_value)
    if os.environ.get("MBI_DISABLE_BUNDLED_ASSETS", "").strip().lower() not in {"1", "true", "yes", "on"}:
        bundled = bundled_resource_pack_path()
        if bundled is not None:
            return bundled
    common = (
        Path.cwd() / "minecraft.zip",
        Path.cwd() / "resourcepack.zip",
        Path.cwd().parent / "minecraft.zip",
    )
    return next((candidate.resolve() for candidate in common if candidate.is_file()), None)


def open_resource_pack(source: str | Path | None = None, config: RuntimeConfig | None = None) -> "ResourcePackSource | None":
    resolved = resolve_resource_pack_path(source)
    return ResourcePackSource(resolved, config=config) if resolved is not None else None


@dataclass(frozen=True, slots=True)
class ModelInstance:
    model: str
    x_rotation: int = 0
    y_rotation: int = 0
    uvlock: bool = False
    weight: int = 1


@dataclass(frozen=True, slots=True)
class ResolvedModel:
    elements: tuple[dict[str, Any], ...]
    textures: dict[str, str]
    ambient_occlusion: bool
    source_models: tuple[str, ...]


class _LRU:
    def __init__(self, maximum: int) -> None:
        self.maximum = maximum
        self.values: OrderedDict[Any, Any] = OrderedDict()

    def get(self, key: Any) -> Any | None:
        value = self.values.get(key)
        if value is not None:
            self.values.move_to_end(key)
        return value

    def put(self, key: Any, value: Any) -> Any:
        self.values[key] = value
        self.values.move_to_end(key)
        while len(self.values) > self.maximum:
            self.values.popitem(last=False)
        return value


class ResourcePackSource:
    """Safe read-only resource-pack/JAR/directory adapter.

    ZIP members are indexed without extraction. Only assets under an allowlisted
    namespace tree can be read, and aggregate/member limits are enforced up front.
    """

    def __init__(self, source: str | Path, config: RuntimeConfig | None = None) -> None:
        self.source = Path(source)
        self.config = config or RuntimeConfig()
        self._zip: zipfile.ZipFile | None = None
        self._members: dict[str, zipfile.ZipInfo] = {}
        self._json_cache = _LRU(self.config.model_cache_items)
        self._model_cache = _LRU(self.config.model_cache_items)
        self._texture_cache = _LRU(self.config.texture_cache_items)
        self.diagnostics: list[dict[str, Any]] = []
        self._diagnostic_keys: set[tuple[str, str, str]] = set()
        self.pack_hash = self._hash_source()
        if self.source.is_file():
            try:
                self._zip = zipfile.ZipFile(self.source)
            except zipfile.BadZipFile as exc:
                raise AppError("RESOURCE_PACK_INVALID", "Resource pack is not a valid ZIP/JAR.", exit_code=31) from exc
            self._index_zip()
        elif not self.source.is_dir():
            raise AppError("RESOURCE_PACK_NOT_FOUND", "Resource-pack path does not exist.", {"path": str(source)}, 31)

    def close(self) -> None:
        if self._zip is not None:
            self._zip.close()

    def __enter__(self) -> "ResourcePackSource":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def _hash_source(self) -> str:
        digest = hashlib.sha256()
        if self.source.is_file():
            with self.source.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
        elif self.source.is_dir():
            for path in sorted(item for item in self.source.rglob("*") if item.is_file()):
                relative = path.relative_to(self.source).as_posix()
                digest.update(relative.encode("utf-8") + b"\0")
                digest.update(hashlib.sha256(path.read_bytes()).digest())
        else:
            digest.update(str(self.source).encode())
        return digest.hexdigest()

    @staticmethod
    def _normalize_member(name: str) -> str:
        normalized = posixpath.normpath(name.replace("\\", "/"))
        if normalized.startswith("/") or normalized.startswith("../") or "/../" in f"/{normalized}/":
            raise AppError("RESOURCE_PACK_PATH_TRAVERSAL", "Resource pack contains an unsafe path.", {"entry": name}, 31)
        return normalized

    def _index_zip(self) -> None:
        assert self._zip is not None
        total = 0
        if len(self._zip.infolist()) > self.config.max_resource_members:
            raise AppError("RESOURCE_PACK_MEMBER_LIMIT", "Resource pack contains too many archive members.", exit_code=31)
        for info in self._zip.infolist():
            name = self._normalize_member(info.filename)
            if name in self._members:
                raise AppError("RESOURCE_PACK_DUPLICATE", "Resource pack contains duplicate paths.", {"entry": name}, 31)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise AppError("RESOURCE_PACK_SYMLINK", "Resource pack contains a symbolic link.", {"entry": name}, 31)
            if info.flag_bits & 1:
                raise AppError("RESOURCE_PACK_ENCRYPTED", "Encrypted resource-pack members are unsupported.", {"entry": name}, 31)
            total += max(0, info.file_size)
            if total > self.config.max_resource_bytes:
                raise AppError("RESOURCE_PACK_SIZE_LIMIT", "Resource pack exceeds the decompressed-size limit.", exit_code=31)
            if info.file_size > 0 and info.compress_size == 0:
                raise AppError("RESOURCE_PACK_RATIO", "Resource pack contains an invalid compression ratio.", {"entry": name}, 31)
            if info.compress_size and info.file_size / info.compress_size > 1000:
                raise AppError("RESOURCE_PACK_RATIO", "Resource-pack member exceeds compression-ratio limit.", {"entry": name}, 31)
            self._members[name] = info

    @staticmethod
    def split_resource(value: str, default_namespace: str = "minecraft") -> tuple[str, str]:
        if ":" in value:
            namespace, resource = value.split(":", 1)
            return namespace, resource
        return default_namespace, value

    def _candidate_paths(self, relative: str) -> Iterable[str]:
        yield f"assets/{relative}"
        yield relative

    def read_bytes(self, relative: str) -> bytes:
        relative = self._normalize_member(relative)
        if self._zip is not None:
            for candidate in self._candidate_paths(relative):
                info = self._members.get(candidate)
                if info is not None:
                    if info.file_size > 32 * 1024 * 1024:
                        raise AppError("RESOURCE_MEMBER_SIZE", "Resource-pack member is too large.", {"entry": candidate}, 31)
                    return self._zip.read(info)
            raise FileNotFoundError(relative)
        for candidate in self._candidate_paths(relative):
            path = (self.source / PurePosixPath(candidate)).resolve()
            try:
                path.relative_to(self.source.resolve())
            except ValueError as exc:
                raise AppError("RESOURCE_PACK_PATH_TRAVERSAL", "Resource path escaped pack root.", exit_code=31) from exc
            if path.is_file():
                return path.read_bytes()
        raise FileNotFoundError(relative)

    def read_json(self, relative: str) -> dict[str, Any]:
        cached = self._json_cache.get(relative)
        if cached is not None:
            return cached
        try:
            raw = self.read_bytes(relative)
        except FileNotFoundError as exc:
            raise AppError("ASSET_NOT_FOUND", "Resource-pack JSON asset was not found.", {"path": relative}, 31) from exc
        if len(raw) > 4 * 1024 * 1024:
            raise AppError("ASSET_JSON_SIZE", "Resource-pack JSON asset exceeds size limit.", {"path": relative}, 31)
        try:
            value = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise AppError("ASSET_JSON_INVALID", "Resource-pack JSON asset is malformed.", {"path": relative}, 31) from exc
        if not isinstance(value, dict):
            raise AppError("ASSET_JSON_TYPE", "Resource-pack JSON root must be an object.", {"path": relative}, 31)
        return self._json_cache.put(relative, value)

    @staticmethod
    def _state_parts(canonical_state: str) -> tuple[str, str, dict[str, str]]:
        base, _, bracketed = canonical_state.partition("[")
        namespace, block = ResourcePackSource.split_resource(base)
        properties: dict[str, str] = {}
        if bracketed:
            for pair in bracketed[:-1].split(","):
                if "=" in pair:
                    key, value = pair.split("=", 1)
                    properties[key] = value
        return namespace, block, properties

    def _condition_matches(self, condition: Any, properties: dict[str, str], *, depth: int = 0) -> bool:
        if depth > 32:
            raise AppError("BLOCKSTATE_CONDITION_DEPTH", "Multipart condition depth exceeded.", exit_code=31)
        if condition is None:
            return True
        if not isinstance(condition, dict):
            return False
        if "OR" in condition:
            values = condition["OR"]
            return isinstance(values, list) and any(self._condition_matches(item, properties, depth=depth + 1) for item in values)
        if "AND" in condition:
            values = condition["AND"]
            return isinstance(values, list) and all(self._condition_matches(item, properties, depth=depth + 1) for item in values)
        return all(properties.get(str(key)) in str(value).split("|") for key, value in condition.items())

    @staticmethod
    def _instances(raw: Any) -> list[ModelInstance]:
        values = raw if isinstance(raw, list) else [raw]
        result: list[ModelInstance] = []
        for value in values:
            if not isinstance(value, dict) or not isinstance(value.get("model"), str):
                continue
            result.append(
                ModelInstance(
                    value["model"],
                    int(value.get("x", 0)) % 360,
                    int(value.get("y", 0)) % 360,
                    bool(value.get("uvlock", False)),
                    max(1, int(value.get("weight", 1))),
                )
            )
        return result

    @staticmethod
    def _weighted_choice(values: list[ModelInstance], seed: bytes) -> ModelInstance:
        if not values:
            raise ValueError("empty weighted selection")
        total = sum(value.weight for value in values)
        pick = int.from_bytes(hashlib.sha256(seed).digest()[:8], "big") % total
        for value in values:
            if pick < value.weight:
                return value
            pick -= value.weight
        return values[-1]

    def select_models(self, canonical_state: str, coordinate: tuple[int, int, int], seed: int = 0) -> list[ModelInstance]:
        requested_state = canonical_state
        migration = migrate_asset_state(canonical_state)
        if migration is not None:
            canonical_state = migration.target_state
            diagnostic = {
                "code": "LEGACY_ID_MAPPED",
                "source_state": migration.source_state,
                "target_state": migration.target_state,
                "migration_table": migration.table_version,
            }
            key = (diagnostic["code"], migration.source_state, migration.target_state)
            if key not in self._diagnostic_keys:
                self._diagnostic_keys.add(key)
                self.diagnostics.append(diagnostic)
        namespace, block, properties = self._state_parts(canonical_state)
        try:
            blockstate = self.read_json(f"{namespace}/blockstates/{block}.json")
        except AppError as exc:
            if migration is None:
                raise
            raise AppError(
                "UNMAPPED_LEGACY_ID",
                "The legacy block ID has a migration, but its target asset is unavailable.",
                {
                    "source_state": requested_state,
                    "target_state": canonical_state,
                    "migration_table": migration.table_version,
                },
                31,
            ) from exc
        selected: list[ModelInstance] = []
        variants = blockstate.get("variants")
        if isinstance(variants, dict):
            matches: list[tuple[int, str, Any]] = []
            for selector, raw in variants.items():
                required: dict[str, str] = {}
                valid = True
                if selector:
                    for pair in str(selector).split(","):
                        if "=" not in pair:
                            valid = False
                            break
                        key, value = pair.split("=", 1)
                        required[key] = value
                if valid and all(properties.get(key) == value for key, value in required.items()):
                    matches.append((len(required), str(selector), raw))
            if matches:
                _, selector, raw = sorted(matches, key=lambda item: (-item[0], item[1]))[0]
                values = self._instances(raw)
                if values:
                    selected.append(self._weighted_choice(values, f"{seed}|{coordinate}|{canonical_state}|{selector}".encode()))
        multipart = blockstate.get("multipart")
        if isinstance(multipart, list):
            if len(multipart) > 512:
                raise AppError("BLOCKSTATE_MULTIPART_LIMIT", "Multipart blockstate exceeds branch limit.", exit_code=31)
            for index, part in enumerate(multipart):
                if isinstance(part, dict) and self._condition_matches(part.get("when"), properties):
                    values = self._instances(part.get("apply"))
                    if values:
                        selected.append(self._weighted_choice(values, f"{seed}|{coordinate}|{canonical_state}|part{index}".encode()))
        return selected

    def resolve_model(self, resource: str, *, max_depth: int = 64) -> ResolvedModel:
        cached = self._model_cache.get(resource)
        if cached is not None:
            return cached
        namespace, path = self.split_resource(resource)
        if path.startswith("block/"):
            path = path[6:]
        chain: list[tuple[str, dict[str, Any]]] = []
        seen: set[str] = set()
        current = f"{namespace}:{path}"
        for _ in range(max_depth):
            if current in seen:
                raise AppError("MODEL_PARENT_CYCLE", "Model parent chain contains a cycle.", {"model": resource}, 31)
            seen.add(current)
            ns, model_path = self.split_resource(current, namespace)
            if model_path.startswith("block/"):
                model_path = model_path[6:]
            model = self.read_json(f"{ns}/models/block/{model_path}.json")
            chain.append((current, model))
            parent = model.get("parent")
            if not isinstance(parent, str) or parent in {"builtin/generated", "builtin/entity"}:
                break
            pns, ppath = self.split_resource(parent, ns)
            current = f"{pns}:{ppath}"
        else:
            raise AppError("MODEL_PARENT_DEPTH", "Model parent chain exceeds limit.", {"model": resource}, 31)
        textures: dict[str, str] = {}
        elements: list[dict[str, Any]] | None = None
        ambient = True
        for _, model in reversed(chain):
            if isinstance(model.get("textures"), dict):
                for raw_key, raw_value in model["textures"].items():
                    key = str(raw_key)
                    if isinstance(raw_value, str):
                        textures[key] = raw_value
                    elif isinstance(raw_value, dict) and isinstance(raw_value.get("sprite"), str):
                        # Minecraft 26+ may wrap a sprite with render metadata such
                        # as force_translucent. The block render category already
                        # controls pass selection; retain the exact sprite here.
                        textures[key] = str(raw_value["sprite"])
                        if raw_value.get("force_translucent"):
                            self.diagnostics.append({"code": "TEXTURE_FORCE_TRANSLUCENT", "model": current, "texture_key": key})
                    else:
                        self.diagnostics.append({"code": "TEXTURE_VALUE_UNSUPPORTED", "model": current, "texture_key": key})
            if isinstance(model.get("elements"), list):
                elements = [dict(item) for item in model["elements"] if isinstance(item, dict)]
            if "ambientocclusion" in model:
                ambient = bool(model["ambientocclusion"])
        if elements is None:
            elements = []
        resolved = ResolvedModel(tuple(elements), textures, ambient, tuple(item[0] for item in chain))
        return self._model_cache.put(resource, resolved)

    def resolve_texture_ref(self, textures: dict[str, str], value: str, default_namespace: str = "minecraft") -> tuple[str, str]:
        seen: set[str] = set()
        while value.startswith("#"):
            key = value[1:]
            if key in seen:
                raise AppError("TEXTURE_REFERENCE_CYCLE", "Texture variables contain a cycle.", {"key": key}, 31)
            seen.add(key)
            if key not in textures:
                raise AppError("TEXTURE_REFERENCE_MISSING", "Texture variable is undefined.", {"key": key}, 31)
            value = textures[key]
        namespace, resource = self.split_resource(value, default_namespace)
        if resource.startswith("textures/"):
            resource = resource[9:]
        return namespace, resource

    def texture(self, namespace: str, resource: str) -> Image.Image:
        key = (namespace, resource)
        cached = self._texture_cache.get(key)
        if cached is not None:
            return cached
        try:
            raw = self.read_bytes(f"{namespace}/textures/{resource}.png")
        except FileNotFoundError as exc:
            raise AppError("TEXTURE_NOT_FOUND", "Texture asset was not found.", {"texture": f"{namespace}:{resource}"}, 31) from exc
        try:
            image = Image.open(io.BytesIO(raw))
            image.load()
            image = image.convert("RGBA")
        except Exception as exc:
            raise AppError("TEXTURE_INVALID", "Texture PNG could not be decoded.", {"texture": resource}, 31) from exc
        if image.width > self.config.max_texture_dimension or image.height > self.config.max_texture_dimension:
            raise AppError("TEXTURE_DIMENSION_LIMIT", "Texture exceeds dimension limit.", {"size": image.size}, 31)
        if image.height > image.width and image.height % image.width == 0:
            self.diagnostics.append({"code": "ANIMATED_TEXTURE_FIRST_FRAME", "texture": f"{namespace}:{resource}"})
            image = image.crop((0, 0, image.width, image.width))
        return self._texture_cache.put(key, image)
