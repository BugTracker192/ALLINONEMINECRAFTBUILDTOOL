from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from typing import Any

from app.errors import AppError

_RESOLVED: dict[tuple[str, str], Path] = {}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _asset_directory() -> Path:
    return Path(__file__).resolve().parent.parent / "bundled_assets"


def load_bundled_asset_manifest(asset_dir: Path | None = None) -> dict[str, Any]:
    directory = asset_dir or _asset_directory()
    path = directory / "ASSET_MANIFEST.json"
    try:
        value = json.loads(path.read_text("utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise AppError(
            "BUNDLED_ASSET_MANIFEST_INVALID",
            "Bundled asset manifest is missing or invalid.",
            {"path": str(path)},
            31,
        ) from exc
    if not isinstance(value, dict):
        raise AppError("BUNDLED_ASSET_MANIFEST_INVALID", "Bundled asset manifest must be an object.", exit_code=31)
    for key in ("sha256", "size_bytes"):
        if key not in value:
            raise AppError(
                "BUNDLED_ASSET_MANIFEST_INVALID",
                "Bundled asset manifest is incomplete.",
                {"missing": key, "path": str(path)},
                31,
            )
    return value


def _is_lfs_pointer(path: Path) -> bool:
    if not path.is_file() or path.stat().st_size > 1024:
        return False
    try:
        head = path.read_bytes()
    except OSError:
        return False
    return head.startswith(b"version https://git-lfs.github.com/spec/v1\n")


def _cache_directory() -> Path:
    configured = os.environ.get("MBI_ASSET_CACHE_DIR", "").strip()
    if configured:
        return Path(configured).expanduser()
    xdg = os.environ.get("XDG_CACHE_HOME", "").strip()
    if xdg:
        return Path(xdg).expanduser() / "minecraft-build-intelligence" / "assets"
    try:
        return Path.home() / ".cache" / "minecraft-build-intelligence" / "assets"
    except RuntimeError:
        return Path(tempfile.gettempdir()) / "minecraft-build-intelligence" / "assets"


def _validate(path: Path, manifest: dict[str, Any], *, hash_required: bool = True) -> bool:
    if not path.is_file() or path.stat().st_size != int(manifest["size_bytes"]):
        return False
    return not hash_required or _sha256(path) == str(manifest["sha256"])


def _publish_cache_manifest(source_directory: Path, cache_root: Path) -> None:
    source = source_directory / "ASSET_MANIFEST.json"
    target = cache_root / "ASSET_MANIFEST.json"
    if not target.is_file() or target.read_bytes() != source.read_bytes():
        cache_root.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
        try:
            shutil.copyfile(source, temporary)
            os.replace(temporary, target)
        finally:
            temporary.unlink(missing_ok=True)


def _part_entries(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    delivery = manifest.get("delivery")
    if not isinstance(delivery, dict):
        return []
    raw = delivery.get("parts")
    if not isinstance(raw, list):
        return []
    result: list[dict[str, Any]] = []
    for entry in raw:
        if not isinstance(entry, dict) or not all(key in entry for key in ("name", "size_bytes", "sha256")):
            raise AppError(
                "BUNDLED_ASSET_MANIFEST_INVALID",
                "Bundled asset part manifest contains an invalid entry.",
                exit_code=31,
            )
        result.append(entry)
    return result


def _acquire_lock(lock: Path, target: Path, manifest: dict[str, Any], timeout: float = 180.0) -> int | None:
    deadline = time.monotonic() + timeout
    while True:
        try:
            return os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        except FileExistsError:
            if _validate(target, manifest):
                return None
            try:
                if time.time() - lock.stat().st_mtime > 600:
                    lock.unlink()
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() >= deadline:
                raise AppError(
                    "BUNDLED_ASSET_LOCK_TIMEOUT",
                    "Timed out waiting for another process to reconstruct the bundled asset.",
                    {"lock": str(lock)},
                    31,
                )
            time.sleep(0.25)


def ensure_bundled_asset(
    *,
    asset_dir: Path | None = None,
    cache_dir: Path | None = None,
    verify: bool = True,
) -> Path:
    """Return the full bundled archive, reconstructing ordinary-Git parts when needed.

    Snowflake snapshots may contain no Git metadata, remote, or Git LFS client.
    Hash-locked ordinary Git files are therefore concatenated into a writable
    cache, verified against the final archive SHA-256, and atomically published.
    """
    directory = (asset_dir or _asset_directory()).resolve()
    manifest = load_bundled_asset_manifest(directory)
    expected_sha = str(manifest["sha256"])
    cache_root = (cache_dir or _cache_directory()).expanduser().resolve()
    key = (str(directory), str(cache_root))
    resolved = _RESOLVED.get(key)
    if resolved is not None and _validate(resolved, manifest, hash_required=False):
        if resolved.parent == cache_root:
            _publish_cache_manifest(directory, cache_root)
        return resolved

    filename = str(manifest.get("filename") or Path(str(manifest.get("path", "minecraft.zip"))).name)
    direct = directory / filename
    if _validate(direct, manifest, hash_required=verify):
        _RESOLVED[key] = direct
        return direct

    entries = _part_entries(manifest)
    delivery = manifest.get("delivery") if isinstance(manifest.get("delivery"), dict) else {}
    parts_directory = directory / str(delivery.get("parts_directory", "parts"))
    if not entries:
        raise AppError(
            "BUNDLED_ASSET_UNAVAILABLE",
            "The real bundled Minecraft asset is unavailable and no ordinary-Git parts were found.",
            {
                "asset": str(direct),
                "actual_size": direct.stat().st_size if direct.exists() else None,
                "expected_size": int(manifest["size_bytes"]),
                "lfs_pointer": _is_lfs_pointer(direct),
            },
            31,
        )

    cache_root.mkdir(parents=True, exist_ok=True)
    target = cache_root / f"minecraft-{expected_sha}.zip"
    if _validate(target, manifest):
        _publish_cache_manifest(directory, cache_root)
        _RESOLVED[key] = target
        return target

    lock = target.with_suffix(target.suffix + ".lock")
    fd = _acquire_lock(lock, target, manifest)
    if fd is None:
        _publish_cache_manifest(directory, cache_root)
        _RESOLVED[key] = target
        return target
    os.write(fd, f"pid={os.getpid()}\n".encode("ascii"))
    os.close(fd)

    temporary = target.with_name(f".{target.name}.{os.getpid()}.tmp")
    try:
        full_hash = hashlib.sha256()
        total = 0
        with temporary.open("wb") as output:
            for index, entry in enumerate(entries):
                part = parts_directory / str(entry["name"])
                if not part.is_file():
                    raise AppError(
                        "BUNDLED_ASSET_PART_MISSING",
                        "A bundled asset part is missing.",
                        {"index": index, "path": str(part)},
                        31,
                    )
                expected_size = int(entry["size_bytes"])
                actual_size = part.stat().st_size
                if actual_size != expected_size:
                    raise AppError(
                        "BUNDLED_ASSET_PART_SIZE",
                        "A bundled asset part has the wrong size.",
                        {"index": index, "path": str(part), "expected": expected_size, "actual": actual_size},
                        31,
                    )
                part_hash = hashlib.sha256()
                with part.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
                        part_hash.update(chunk)
                        full_hash.update(chunk)
                        output.write(chunk)
                        total += len(chunk)
                actual_part_hash = part_hash.hexdigest()
                if actual_part_hash != str(entry["sha256"]):
                    raise AppError(
                        "BUNDLED_ASSET_PART_HASH",
                        "A bundled asset part failed SHA-256 verification.",
                        {
                            "index": index,
                            "path": str(part),
                            "expected": str(entry["sha256"]),
                            "actual": actual_part_hash,
                        },
                        31,
                    )
            output.flush()
            os.fsync(output.fileno())

        actual_sha = full_hash.hexdigest()
        if total != int(manifest["size_bytes"]) or actual_sha != expected_sha:
            raise AppError(
                "BUNDLED_ASSET_RECONSTRUCTION_MISMATCH",
                "Reconstructed bundled asset failed final verification.",
                {
                    "expected_size": int(manifest["size_bytes"]),
                    "actual_size": total,
                    "expected_sha256": expected_sha,
                    "actual_sha256": actual_sha,
                },
                31,
            )
        os.replace(temporary, target)
        _publish_cache_manifest(directory, cache_root)
        _RESOLVED[key] = target
        return target
    finally:
        temporary.unlink(missing_ok=True)
        lock.unlink(missing_ok=True)
