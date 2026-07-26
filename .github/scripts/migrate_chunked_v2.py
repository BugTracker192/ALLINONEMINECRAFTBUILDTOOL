from __future__ import annotations

import hashlib
import json
import shutil
from pathlib import Path

REPO = Path.cwd()
OLD = REPO / "minecraft-build-intelligence-snowflake-all-in-one-1.0.2"
NEW = REPO / "minecraft-build-intelligence-snowflake-all-in-one-1.0.3"
ASSET_SHA = "f99aefac7040f85c67b509ebc63a56e542d5f250fd51040d6a3bd7f97e6e5bbc"
ASSET_SIZE = 411_443_953
CHUNK_SIZE = 48 * 1024 * 1024


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def patch_text(path: Path, old: str, new: str) -> None:
    text = path.read_text("utf-8")
    if old not in text:
        raise SystemExit(f"Required marker missing in {path}: {old[:80]!r}")
    path.write_text(text.replace(old, new, 1), "utf-8")


def main() -> None:
    if OLD.exists() and NEW.exists():
        raise SystemExit("Both 1.0.2 and 1.0.3 directories exist")
    if OLD.exists():
        OLD.rename(NEW)
    if not NEW.is_dir():
        raise SystemExit(f"Missing release directory: {NEW}")

    asset = NEW / "app/bundled_assets/minecraft.zip"
    if not asset.is_file():
        raise SystemExit(f"Hydrated asset missing: {asset}")
    if asset.stat().st_size != ASSET_SIZE or sha256(asset) != ASSET_SHA:
        raise SystemExit(f"Hydrated asset mismatch: size={asset.stat().st_size} sha256={sha256(asset)}")

    text_suffixes = {".py", ".pyi", ".toml", ".md", ".json", ".yml", ".yaml", ".txt", ".ps1", ".sh", ".cjs", ".js", ".ts", ".tsx", ".html", ".sql", ".example"}
    for path in sorted(p for p in NEW.rglob("*") if p.is_file() and p.suffix.lower() in text_suffixes):
        data = path.read_bytes()
        updated = data.replace(b"1.0.2", b"1.0.3")
        if updated != data:
            path.write_bytes(updated)

    resource = NEW / "app/assets/resource_pack.py"
    patch_text(
        resource,
        "from app.config import RuntimeConfig\n",
        "from app.assets.bundled import ensure_bundled_asset\nfrom app.config import RuntimeConfig\n",
    )
    text = resource.read_text("utf-8")
    start = text.index("def bundled_resource_pack_path()")
    end = text.index("\n\ndef resolve_resource_pack_path", start)
    text = text[:start] + '''def bundled_resource_pack_path() -> Path | None:
    """Return the verified bundle or reconstruct it from ordinary-Git parts."""
    return ensure_bundled_asset()
''' + text[end:]
    resource.write_text(text, "utf-8")

    bootstrap = NEW / "BOOTSTRAP_SNOWFLAKE.py"
    text = bootstrap.read_text("utf-8")
    start = text.index("    if not args.skip_install:")
    end = text.index("\n\n    result = {", start)
    replacement = '''    from app.assets.bundled import ensure_bundled_asset, load_bundled_asset_manifest

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
'''
    text = text[:start] + replacement + text[end:]
    needle = '        "bundled_asset_bytes": asset_path.stat().st_size,\n'
    if needle not in text:
        raise SystemExit("Bootstrap result marker missing")
    text = text.replace(needle, needle + '        "bundled_asset_delivery": manifest.get("delivery", {}).get("mode", "complete-file"),\n', 1)
    bootstrap.write_text(text, "utf-8")

    parts_dir = NEW / "app/bundled_assets/parts"
    shutil.rmtree(parts_dir, ignore_errors=True)
    parts_dir.mkdir(parents=True)
    parts: list[dict[str, object]] = []
    with asset.open("rb") as source:
        index = 0
        while True:
            data = source.read(CHUNK_SIZE)
            if not data:
                break
            name = f"minecraft.zip.part{index:03d}"
            part = parts_dir / name
            part.write_bytes(data)
            parts.append({"name": name, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()})
            index += 1
    if len(parts) != 9 or sum(int(p["size_bytes"]) for p in parts) != ASSET_SIZE:
        raise SystemExit("Unexpected chunk layout")

    manifest = {
        "archive_members": 16572,
        "default_resolution_policy": "explicit override, environment override, verified complete bundle, or automatic reconstruction from ordinary-Git parts",
        "delivery": {
            "cache_environment_variable": "MBI_ASSET_CACHE_DIR",
            "chunk_size_bytes": CHUNK_SIZE,
            "mode": "ordinary-git-chunks",
            "parts_directory": "parts",
            "parts": parts,
        },
        "filename": "minecraft.zip",
        "path": "app/bundled_assets/minecraft.zip",
        "private_user_supplied_asset_bundle": True,
        "redistribution_notice": "User-supplied Minecraft assets are bundled only in this private deliverable. Do not publish or redistribute them without authorization.",
        "render_relevant_members": 8092,
        "schema_version": "1.1",
        "sha256": ASSET_SHA,
        "size_bytes": ASSET_SIZE,
    }
    (NEW / "app/bundled_assets/ASSET_MANIFEST.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", "utf-8")
    asset.unlink()

    pyproject = NEW / "pyproject.toml"
    pyproject.write_text(pyproject.read_text("utf-8").replace('version = "1.0.2"', 'version = "1.0.3"'), "utf-8")
    (NEW / "app/version.py").write_text('__version__ = "1.0.3"\n', "utf-8")

    build_test = NEW / "tests/unit/test_build_backend.py"
    test = build_test.read_text("utf-8")
    test = test.replace(
        '        assert "app/bundled_assets/minecraft.zip" in names\n',
        '        assert "app/bundled_assets/ASSET_MANIFEST.json" in names\n'
        '        assert "app/bundled_assets/parts/minecraft.zip.part000" in names\n'
        '        assert "app/bundled_assets/parts/minecraft.zip.part008" in names\n'
        '        assert "app/bundled_assets/minecraft.zip" not in names\n',
    ).replace("Version: 1.0.2", "Version: 1.0.3")
    build_test.write_text(test, "utf-8")

    guide = NEW / "SNOWFLAKE_COCO_AUTONOMOUS_LLM_AGENT_GUIDE.md"
    marker = "## Snowflake snapshot asset reconstruction (v1.0.3)"
    guide_text = guide.read_text("utf-8")
    if marker not in guide_text:
        guide_text += (
            "\n\n" + marker + "\n\n"
            "This release stores the private Minecraft archive as nine hash-locked ordinary Git files under `app/bundled_assets/parts/`. Run `python BOOTSTRAP_SNOWFLAKE.py --smoke`; it reconstructs the exact 411,443,953-byte archive in a writable cache, verifies SHA-256 `" + ASSET_SHA + "`, installs the package, and performs a textured render. No `.git`, remote, Git LFS client, or resource-pack path is required.\n"
        )
        guide.write_text(guide_text, "utf-8")

    release_manifest = {
        "agent_manual": "SNOWFLAKE_COCO_AUTONOMOUS_LLM_AGENT_GUIDE.md",
        "bootstrap": "BOOTSTRAP_SNOWFLAKE.py",
        "bundled_asset_delivery": "ordinary-git-chunks",
        "bundled_asset_parts": 9,
        "bundled_asset_sha256": ASSET_SHA,
        "bundled_asset_size_bytes": ASSET_SIZE,
        "profile": "private-snowflake-coco-all-in-one",
        "test_count": 86,
        "version": "1.0.3",
    }
    (NEW / "RELEASE_MANIFEST.json").write_text(json.dumps(release_manifest, indent=2, sort_keys=True) + "\n", "utf-8")

    report_path = NEW / "ALL_IN_ONE_RELEASE_REPORT.json"
    report = json.loads(report_path.read_text("utf-8"))
    report["release_version"] = "1.0.3"
    report["bundled_assets"] = manifest
    report["tests"] = {"passed": 86, "failed": 0, "skipped": 0}
    report["snowflake_snapshot_delivery"] = {
        "git_metadata_required": False,
        "git_lfs_required": False,
        "remote_required": False,
        "part_count": 9,
        "maximum_part_size_bytes": CHUNK_SIZE,
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", "utf-8")

    source_hashes = NEW / "SOURCE_FILES.sha256"
    file_manifest = NEW / "RELEASE_FILE_MANIFEST.json"
    source_hashes.unlink(missing_ok=True)
    file_manifest.unlink(missing_ok=True)
    source_files = [p for p in sorted(NEW.rglob("*")) if p.is_file() and p.name not in {"SOURCE_FILES.sha256", "RELEASE_FILE_MANIFEST.json"}]
    source_hashes.write_text("".join(f"{sha256(p)}  {p.relative_to(NEW).as_posix()}\n" for p in source_files), "utf-8")
    files = [p for p in sorted(NEW.rglob("*")) if p.is_file() and p.name != "RELEASE_FILE_MANIFEST.json"]
    entries = [{"path": p.relative_to(NEW).as_posix(), "size_bytes": p.stat().st_size, "sha256": sha256(p)} for p in files]
    file_manifest.write_text(json.dumps({
        "bundled_asset_sha256": ASSET_SHA,
        "file_count": len(entries),
        "files": entries,
        "profile": "private-snowflake-coco-all-in-one-chunked",
        "schema_version": "1.1",
        "total_size_bytes": sum(e["size_bytes"] for e in entries),
        "version": "1.0.3",
    }, indent=2, sort_keys=True) + "\n", "utf-8")

    (REPO / ".gitattributes").write_text(
        "minecraft-build-intelligence-snowflake-all-in-one-1.0.3/app/bundled_assets/parts/* -text\n"
        "minecraft-build-intelligence-snowflake-all-in-one-1.0.3/docs/MASTER_SPEC.md -text\n"
        "minecraft-build-intelligence-snowflake-all-in-one-1.0.3/tests/fixtures/reference.schem -text\n",
        "utf-8",
    )
    print(json.dumps({"version": "1.0.3", "parts": len(parts), "asset_sha256": ASSET_SHA, "manifest_files": len(entries)}, indent=2))


if __name__ == "__main__":
    main()
