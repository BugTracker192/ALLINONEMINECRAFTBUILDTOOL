#!/usr/bin/env python3
"""Autonomous, no-prompt bootstrap for the private Snowflake/CoCo release."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANDATORY = (
    ("numpy", "numpy", "numpy>=2.0,<3", (2, 0), (3, 0)),
    ("PIL", "Pillow", "Pillow>=12.3,<13", (12, 3), (13, 0)),
)


def _version_tuple(value: str) -> tuple[int, ...]:
    """Parse the release portion without requiring packaging during bootstrap."""
    release = value.split("+", 1)[0].split("-", 1)[0]
    parts: list[int] = []
    for component in release.split("."):
        digits = "".join(character for character in component if character.isdigit())
        if not digits:
            break
        parts.append(int(digits))
    return tuple(parts)


def dependency_issues() -> list[str]:
    issues: list[str] = []
    for module, distribution, requirement, minimum, maximum in MANDATORY:
        if importlib.util.find_spec(module) is None:
            issues.append(requirement)
            continue
        try:
            installed = _version_tuple(importlib.metadata.version(distribution))
        except importlib.metadata.PackageNotFoundError:
            issues.append(requirement)
            continue
        width = max(len(installed), len(minimum), len(maximum))
        padded = installed + (0,) * (width - len(installed))
        lower = minimum + (0,) * (width - len(minimum))
        upper = maximum + (0,) * (width - len(maximum))
        if not lower <= padded < upper:
            issues.append(requirement)
    return issues


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mirror_source(destination: Path) -> Path:
    destination = destination.resolve()
    if destination == ROOT or ROOT in destination.parents:
        raise SystemExit("--scratch-root must be outside the release source tree")
    target = destination / ROOT.name
    ignored = shutil.ignore_patterns(
        ".git",
        ".venv",
        ".pytest_cache",
        "__pycache__",
        "bootstrap-smoke-run",
        "*.pyc",
    )
    shutil.copytree(ROOT, target, dirs_exist_ok=True, symlinks=False, ignore=ignored)
    return target


def _cache_source(cache_root: Path) -> Path:
    target = cache_root / f"{ROOT.name}-source.tar.gz"
    cache_root.mkdir(parents=True, exist_ok=True)
    asset_manifest = json.loads(
        (ROOT / "app" / "bundled_assets" / "ASSET_MANIFEST.json").read_text(
            "utf-8"
        )
    )
    parts_root = ROOT / "app" / "bundled_assets" / str(
        asset_manifest["delivery"]["parts_directory"]
    )
    declared_parts = asset_manifest["delivery"]["parts"]
    required_part_paths: list[Path] = []
    for item in declared_parts:
        part = parts_root / str(item["name"])
        if (
            not part.is_file()
            or part.stat().st_size != int(item["size_bytes"])
            or sha256(part) != str(item["sha256"])
        ):
            raise SystemExit(
                "warm-cache source is missing or has an invalid bundled-asset "
                f"part: {part}"
            )
        required_part_paths.append(part)
    with tarfile.open(target, "w:gz", compresslevel=6) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(ROOT)
            parts = set(relative.parts)
            if parts & {".git", ".venv", ".pytest_cache", "__pycache__"}:
                continue
            archive.add(path, arcname=f"{ROOT.name}/{relative.as_posix()}", recursive=False)
    with tarfile.open(target, "r:gz") as archive:
        names = set(archive.getnames())
    required_parts = {
        f"{ROOT.name}/{path.relative_to(ROOT).as_posix()}"
        for path in required_part_paths
    }
    missing = sorted(required_parts - names)
    if missing:
        target.unlink(missing_ok=True)
        raise SystemExit(
            "warm-cache source archive omitted required bundled-asset parts: "
            + ", ".join(missing)
        )
    return target


def _cache_tree(source: Path, target: Path) -> Path:
    if not source.is_dir():
        raise SystemExit(f"cache tree does not exist: {source}")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(target, "w:gz", compresslevel=3) as archive:
        archive.add(source, arcname=source.name, recursive=True)
    return target


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Install and verify the all-in-one Snowflake/CoCo tool without prompts."
    )
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Run a strict textured reference pipeline after installation.",
    )
    parser.add_argument("--out", default=str(ROOT / "bootstrap-smoke-run"))
    parser.add_argument(
        "--scratch-root",
        help="Mirror the release to writable local scratch and continue there.",
    )
    parser.add_argument(
        "--cache-dir",
        help="Persistent cache for the reconstructed archive and warm-start tarballs.",
    )
    parser.add_argument(
        "--warm-cache",
        action="store_true",
        help="Cache the verified asset plus source and optional environment tarballs.",
    )
    parser.add_argument(
        "--cache-venv",
        help="Existing environment directory to include in the warm cache.",
    )
    parser.add_argument(
        "--index-url",
        help="Explicit authenticated or public Python package index URL.",
    )
    args = parser.parse_args()

    if sys.version_info < (3, 12):
        raise SystemExit("Python 3.12 or newer is required")

    if args.scratch_root and os.environ.get("MBI_SCRATCH_REEXEC") != "1":
        target = _mirror_source(Path(args.scratch_root))
        env = os.environ.copy()
        env["MBI_SCRATCH_REEXEC"] = "1"
        completed = subprocess.run(
            [sys.executable, str(target / Path(__file__).name), *sys.argv[1:]],
            cwd=target,
            env=env,
            check=False,
        )
        return completed.returncode

    cache_root = Path(args.cache_dir).expanduser().resolve() if args.cache_dir else None
    if cache_root is not None:
        os.environ["MBI_ASSET_CACHE_DIR"] = str(cache_root / "assets")

    missing = dependency_issues()
    if missing:
        if os.environ.get("MBI_BOOTSTRAP_REEXEC") == "1":
            raise SystemExit(
                "Mandatory dependencies remain unavailable after installation and interpreter restart: "
                + ", ".join(missing)
            )
        wheelhouse = ROOT / "vendor" / "wheelhouse"
        local_wheels = list(wheelhouse.glob("*.whl")) if wheelhouse.is_dir() else []
        if local_wheels:
            run("-m", "pip", "install", "--no-index", "--find-links", str(wheelhouse), *missing)
        else:
            install = ["-m", "pip", "install"]
            if args.index_url:
                install.extend(("--index-url", args.index_url))
            install.extend(missing)
            run(*install)
        env = os.environ.copy()
        env["MBI_BOOTSTRAP_REEXEC"] = "1"
        completed = subprocess.run(
            [sys.executable, str(Path(__file__).resolve()), *sys.argv[1:]],
            cwd=ROOT,
            env=env,
            check=False,
        )
        return completed.returncode
    from app.assets.bundled import ensure_bundled_asset, load_bundled_asset_manifest

    manifest = load_bundled_asset_manifest()
    asset_path = ensure_bundled_asset(verify=True)
    actual = sha256(asset_path)
    if actual != manifest["sha256"] or asset_path.stat().st_size != int(manifest["size_bytes"]):
        raise SystemExit(
            "Bundled asset verification failed after reconstruction: "
            f"size={asset_path.stat().st_size} sha256={actual}"
        )

    if not args.skip_install:
        run("-m", "pip", "install", "--no-deps", ".")

    result = {
        "python": sys.version.split()[0],
        "project_version": "1.2.0",
        "bundled_asset": str(asset_path),
        "bundled_asset_sha256": actual,
        "bundled_asset_bytes": asset_path.stat().st_size,
        "bundled_asset_delivery": manifest.get("delivery", {}).get("mode", "complete-file"),
        "numpy_available": importlib.util.find_spec("numpy") is not None,
        "pillow_available": importlib.util.find_spec("PIL") is not None,
        "numpy_version": importlib.metadata.version("numpy"),
        "pillow_version": importlib.metadata.version("Pillow"),
        "scratch_root": str(ROOT),
    }
    if args.warm_cache:
        if cache_root is None:
            raise SystemExit("--warm-cache requires --cache-dir")
        source_tar = _cache_source(cache_root)
        warm = {
            "asset": str(asset_path),
            "source_tar": str(source_tar),
            "source_tar_sha256": sha256(source_tar),
            "source_tar_asset_parts_included": True,
        }
        if args.cache_venv:
            venv_tar = _cache_tree(
                Path(args.cache_venv).expanduser().resolve(),
                cache_root / "python-environment.tar.gz",
            )
            warm["environment_tar"] = str(venv_tar)
            warm["environment_tar_sha256"] = sha256(venv_tar)
        cache_manifest = cache_root / "warm-cache.json"
        cache_manifest.write_text(json.dumps(warm, sort_keys=True, indent=2), "utf-8")
        result["warm_cache"] = warm
    if args.smoke:
        fixture = ROOT / "tests" / "fixtures" / "reference.schem"
        out = Path(args.out)
        if out.exists():
            import shutil
            shutil.rmtree(out)
        run("-m", "app.cli", "--quiet", "pipeline", str(fixture), "--out", str(out), "--size", "128x128")
        diagnostics = json.loads((out / "diagnostics.json").read_text("utf-8"))
        if diagnostics.get("render_mode") != "software-textured":
            raise SystemExit("Smoke pipeline did not use bundled textures")
        result["smoke_run"] = str(out)
        result["smoke_render_mode"] = diagnostics.get("render_mode")
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
