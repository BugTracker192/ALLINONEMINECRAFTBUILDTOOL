#!/usr/bin/env python3
"""Autonomous, no-prompt bootstrap for the private Snowflake/CoCo release."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
MANDATORY = (("numpy", "numpy>=2.0,<3"), ("PIL", "Pillow>=12.3,<13"))


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], cwd=ROOT, check=True)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Install and verify the all-in-one Snowflake/CoCo tool without prompts.")
    parser.add_argument("--skip-install", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Run a strict textured reference pipeline after installation.")
    parser.add_argument("--out", default=str(ROOT / "bootstrap-smoke-run"))
    args = parser.parse_args()

    if sys.version_info < (3, 12):
        raise SystemExit("Python 3.12 or newer is required")

    missing = [requirement for module, requirement in MANDATORY if importlib.util.find_spec(module) is None]
    if missing:
        wheelhouse = ROOT / "vendor" / "wheelhouse"
        local_wheels = list(wheelhouse.glob("*.whl")) if wheelhouse.is_dir() else []
        if local_wheels:
            run("-m", "pip", "install", "--no-index", "--find-links", str(wheelhouse), *missing)
        else:
            run("-m", "pip", "install", *missing)
    if not args.skip_install:
        run("-m", "pip", "install", "--no-deps", ".")

    manifest_path = ROOT / "app" / "bundled_assets" / "ASSET_MANIFEST.json"
    manifest = json.loads(manifest_path.read_text("utf-8"))
    asset_path = ROOT / manifest["path"]
    actual = sha256(asset_path)
    if actual != manifest["sha256"]:
        raise SystemExit(f"Bundled asset hash mismatch: {actual}")

    result = {
        "python": sys.version.split()[0],
        "project_version": "1.0.2",
        "bundled_asset": str(asset_path),
        "bundled_asset_sha256": actual,
        "bundled_asset_bytes": asset_path.stat().st_size,
        "numpy_available": importlib.util.find_spec("numpy") is not None,
        "pillow_available": importlib.util.find_spec("PIL") is not None,
    }
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
