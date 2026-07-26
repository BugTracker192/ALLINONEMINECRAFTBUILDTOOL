from __future__ import annotations

import hashlib
import json
import posixpath
import stat
import zipfile
from dataclasses import asdict, dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from .errors import MBIError

_ALLOWED_RESOURCE_ROOTS = ("blockstates", "models/block", "textures", "atlases")


def _normalized_asset_target(name: str) -> tuple[str, str] | None:
    """Return ``(namespace, relative-resource-path)`` for supported pack layouts.

    Both standard resource packs (``assets/<namespace>/...``) and Mojang client
    asset trees (``<namespace>/...``) are accepted. All texture subtrees are
    retained because block-entity renderers use chest, sign, banner, bed, shulker,
    decorated-pot, and entity textures outside ``textures/block``.
    """
    parts = PurePosixPath(name).parts
    if len(parts) >= 3 and parts[0] == "assets":
        namespace = parts[1]
        resource_parts = parts[2:]
    elif len(parts) >= 2:
        namespace = parts[0]
        resource_parts = parts[1:]
    else:
        return None
    if not namespace or any(char not in "abcdefghijklmnopqrstuvwxyz0123456789_.-" for char in namespace):
        return None
    relative = "/".join(resource_parts)
    if not any(relative == root or relative.startswith(root + "/") for root in _ALLOWED_RESOURCE_ROOTS):
        return None
    return namespace, relative



@dataclass(frozen=True, slots=True)
class AssetManifest:
    pack_hash: str
    source_name: str
    file_count: int
    files: dict[str, str]


class ResourcePack:
    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def _path(self, namespace: str, kind: str, resource: str, suffix: str) -> Path:
        normalized = PurePosixPath(resource)
        if normalized.is_absolute() or ".." in normalized.parts:
            raise MBIError("ASSET_PATH_TRAVERSAL", "Asset resource path is unsafe.")
        return self.root / namespace / kind / f"{normalized.as_posix()}{suffix}"

    def json(self, namespace: str, kind: str, resource: str) -> dict[str, Any]:
        path = self._path(namespace, kind, resource, ".json")
        try:
            return json.loads(path.read_text("utf-8"))
        except FileNotFoundError as exc:
            raise MBIError("ASSET_NOT_FOUND", "Resource-pack JSON asset was not found.", {"path": str(path)}) from exc
        except json.JSONDecodeError as exc:
            raise MBIError("ASSET_JSON_INVALID", "Resource-pack JSON asset is invalid.", {"path": str(path), "line": exc.lineno}) from exc

    def texture_path(self, namespace: str, resource: str) -> Path:
        path = self._path(namespace, "textures", resource, ".png")
        if not path.is_file():
            raise MBIError("TEXTURE_NOT_FOUND", "Resource-pack texture was not found.", {"path": str(path)})
        return path

    @staticmethod
    def split_resource(value: str, default_namespace: str = "minecraft") -> tuple[str, str]:
        return tuple(value.split(":", 1)) if ":" in value else (default_namespace, value)  # type: ignore[return-value]

    def resolve_model(self, resource: str, *, max_depth: int = 64) -> dict[str, Any]:
        namespace, path = self.split_resource(resource)
        if path.startswith("block/"):
            path = path[len("block/") :]
        chain: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for _ in range(max_depth):
            key = (namespace, path)
            if key in seen:
                raise MBIError("MODEL_PARENT_CYCLE", "Resource-pack model parent chain contains a cycle.", {"model": resource})
            seen.add(key)
            model = self.json(namespace, "models/block", path)
            chain.append(model)
            parent = model.get("parent")
            if not isinstance(parent, str):
                break
            namespace, path = self.split_resource(parent, namespace)
            if path.startswith("block/"):
                path = path[len("block/") :]
        else:
            raise MBIError("MODEL_PARENT_DEPTH", "Resource-pack model parent chain exceeds the configured limit.")
        resolved: dict[str, Any] = {}
        textures: dict[str, str] = {}
        for model in reversed(chain):
            if "ambientocclusion" in model:
                resolved["ambientocclusion"] = model["ambientocclusion"]
            if "gui_light" in model:
                resolved["gui_light"] = model["gui_light"]
            if isinstance(model.get("textures"), dict):
                textures.update({str(k): str(v) for k, v in model["textures"].items()})
            if "elements" in model:
                resolved["elements"] = model["elements"]
        resolved["textures"] = textures
        return resolved

    def resolve_texture_variable(self, textures: dict[str, str], value: str) -> str:
        seen: set[str] = set()
        while value.startswith("#"):
            key = value[1:]
            if key in seen:
                raise MBIError("TEXTURE_REFERENCE_CYCLE", "Model texture variables contain a cycle.", {"key": key})
            seen.add(key)
            replacement = textures.get(key)
            if replacement is None:
                raise MBIError("TEXTURE_REFERENCE_MISSING", "Model texture variable is missing.", {"key": key})
            value = replacement
        return value

    def select_blockstate_models(self, canonical_state: str) -> list[dict[str, Any]]:
        base, _, bracketed = canonical_state.partition("[")
        namespace, block = self.split_resource(base)
        properties: dict[str, str] = {}
        if bracketed:
            for pair in bracketed[:-1].split(","):
                key, value = pair.split("=", 1)
                properties[key] = value
        blockstate = self.json(namespace, "blockstates", block)
        selected: list[dict[str, Any]] = []
        variants = blockstate.get("variants")
        if isinstance(variants, dict):
            for selector, model in variants.items():
                required = {}
                if selector:
                    for pair in selector.split(","):
                        key, value = pair.split("=", 1)
                        required[key] = value
                if all(properties.get(key) == value for key, value in required.items()):
                    selected.extend(model if isinstance(model, list) else [model])
                    break
        multipart = blockstate.get("multipart")
        if isinstance(multipart, list):
            for part in multipart:
                if not isinstance(part, dict):
                    continue
                condition = part.get("when")
                if self._condition_matches(condition, properties):
                    apply = part.get("apply")
                    selected.extend(apply if isinstance(apply, list) else [apply])
        return [item for item in selected if isinstance(item, dict) and isinstance(item.get("model"), str)]

    def _condition_matches(self, condition: Any, properties: dict[str, str]) -> bool:
        if condition is None:
            return True
        if not isinstance(condition, dict):
            return False
        if "OR" in condition:
            values = condition["OR"]
            return isinstance(values, list) and any(self._condition_matches(item, properties) for item in values)
        if "AND" in condition:
            values = condition["AND"]
            return isinstance(values, list) and all(self._condition_matches(item, properties) for item in values)
        return all(properties.get(key) in str(value).split("|") for key, value in condition.items())


def safe_index_resource_zip(
    source: Path,
    destination: Path,
    *,
    max_file_size_bytes: int = 16 * 1024 * 1024,
    max_total_extracted_bytes: int = 512 * 1024 * 1024,
    max_compression_ratio: float = 1_000.0,
) -> AssetManifest:
    """Safely extract and index render-relevant assets from a Minecraft asset ZIP.

    The source archive is untrusted. Only explicitly allowlisted paths are extracted,
    and extraction is bounded by per-file size, cumulative size, compression ratio,
    duplicate-path, encryption, symlink, and path-containment checks.
    """
    destination.mkdir(parents=True, exist_ok=True)
    destination_root = destination.resolve()
    files: dict[str, str] = {}
    seen: set[str] = set()
    extracted_bytes = 0
    hasher = hashlib.sha256()
    with source.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(chunk)
    pack_hash = hasher.hexdigest()

    with zipfile.ZipFile(source) as archive:
        for info in archive.infolist():
            name = posixpath.normpath(info.filename.replace("\\", "/"))
            if name in ("", "."):
                continue
            if name.startswith("../") or name.startswith("/") or "/../" in f"/{name}/":
                raise MBIError("ASSET_ZIP_PATH_TRAVERSAL", "Resource-pack ZIP contains an unsafe path.", {"entry": info.filename})
            if name in seen:
                raise MBIError("ASSET_ZIP_DUPLICATE_ENTRY", "Resource-pack ZIP contains duplicate entries.", {"entry": name})
            seen.add(name)

            unix_mode = info.external_attr >> 16
            if stat.S_ISLNK(unix_mode):
                raise MBIError("ASSET_ZIP_SYMLINK", "Resource-pack ZIP contains a symbolic link.", {"entry": name})
            if info.flag_bits & 0x1:
                raise MBIError("ASSET_ZIP_ENCRYPTED", "Encrypted resource-pack entries are not supported.", {"entry": name})
            normalized_target = _normalized_asset_target(name)
            if info.is_dir() or normalized_target is None:
                continue
            if info.file_size < 0 or info.file_size > max_file_size_bytes:
                raise MBIError("ASSET_FILE_SIZE_LIMIT", "Individual resource-pack file exceeds the configured limit.", {"entry": name, "sizeBytes": info.file_size})
            if info.file_size and info.compress_size == 0:
                raise MBIError("ASSET_ZIP_INVALID_SIZE", "Resource-pack ZIP entry has an invalid compressed size.", {"entry": name})
            ratio = info.file_size / max(1, info.compress_size)
            if ratio > max_compression_ratio:
                raise MBIError("ASSET_ZIP_COMPRESSION_RATIO", "Resource-pack ZIP entry exceeds the compression-ratio limit.", {"entry": name, "ratio": ratio})
            if extracted_bytes + info.file_size > max_total_extracted_bytes:
                raise MBIError("ASSET_TOTAL_SIZE_LIMIT", "Resource-pack files exceed the cumulative extraction limit.", {"entry": name, "limitBytes": max_total_extracted_bytes})

            namespace, relative = normalized_target
            target = destination / namespace / relative
            resolved_target = target.resolve(strict=False)
            if destination_root not in resolved_target.parents:
                raise MBIError("ASSET_ZIP_PATH_TRAVERSAL", "Resource-pack target escapes the destination.", {"entry": name})
            target.parent.mkdir(parents=True, exist_ok=True)

            digest = hashlib.sha256()
            written = 0
            temporary = target.with_name(f".{target.name}.extracting")
            try:
                with archive.open(info, "r") as source_stream, temporary.open("wb") as target_stream:
                    while chunk := source_stream.read(1024 * 1024):
                        written += len(chunk)
                        if written > info.file_size or extracted_bytes + written > max_total_extracted_bytes:
                            raise MBIError("ASSET_TOTAL_SIZE_LIMIT", "Resource-pack extraction exceeded declared or configured limits.", {"entry": name})
                        digest.update(chunk)
                        target_stream.write(chunk)
                if written != info.file_size:
                    raise MBIError("ASSET_ZIP_SIZE_MISMATCH", "Resource-pack entry size does not match ZIP metadata.", {"entry": name, "declared": info.file_size, "actual": written})
                temporary.replace(target)
            finally:
                temporary.unlink(missing_ok=True)

            extracted_bytes += written
            files[f"{namespace}/{relative}"] = digest.hexdigest()

    manifest = AssetManifest(pack_hash, source.name, len(files), dict(sorted(files.items())))
    (destination / "manifest.json").write_text(json.dumps(asdict(manifest), indent=2, sort_keys=True), "utf-8")
    return manifest
