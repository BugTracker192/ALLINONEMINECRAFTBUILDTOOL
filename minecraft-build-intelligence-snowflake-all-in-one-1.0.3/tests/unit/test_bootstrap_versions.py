from __future__ import annotations

import importlib.metadata
import json
import tarfile
from pathlib import Path

import pytest

import BOOTSTRAP_SNOWFLAKE as bootstrap


def test_bootstrap_accepts_declared_dependency_ranges(monkeypatch) -> None:
    assert bootstrap._version_tuple("12.3.0") == (12, 3, 0)
    assert bootstrap._version_tuple("2.0.0+vendor.1") == (2, 0, 0)
    versions = {"numpy": "2.3.5", "Pillow": "12.3.0"}
    monkeypatch.setattr(bootstrap.importlib.metadata, "version", versions.__getitem__)
    assert bootstrap.dependency_issues() == []


def test_bootstrap_rejects_present_but_out_of_range_dependency(monkeypatch) -> None:
    actual = importlib.metadata.version

    def version(name: str) -> str:
        return "12.2.0" if name == "Pillow" else actual(name)

    monkeypatch.setattr(bootstrap.importlib.metadata, "version", version)
    assert "Pillow>=12.3,<13" in bootstrap.dependency_issues()


def test_warm_cache_requires_and_includes_every_declared_asset_part(
    tmp_path: Path,
    monkeypatch,
) -> None:
    release = tmp_path / "release"
    parts = release / "app" / "bundled_assets" / "parts"
    parts.mkdir(parents=True)
    part = parts / "asset.part000"
    part.write_bytes(b"complete-part")
    manifest = {
        "delivery": {
            "parts_directory": "parts",
            "parts": [
                {
                    "name": part.name,
                    "size_bytes": part.stat().st_size,
                    "sha256": bootstrap.sha256(part),
                }
            ],
        }
    }
    (parts.parent / "ASSET_MANIFEST.json").write_text(
        json.dumps(manifest),
        "utf-8",
    )
    monkeypatch.setattr(bootstrap, "ROOT", release)
    archive_path = bootstrap._cache_source(tmp_path / "cache")
    with tarfile.open(archive_path, "r:gz") as archive:
        assert f"{release.name}/app/bundled_assets/parts/{part.name}" in set(
            archive.getnames()
        )

    part.unlink()
    with pytest.raises(SystemExit, match="missing or has an invalid"):
        bootstrap._cache_source(tmp_path / "invalid-cache")
