from __future__ import annotations

import zipfile
from pathlib import Path

import build_backend


def test_stdlib_backend_has_no_build_requirements_and_builds_complete_wheel(tmp_path: Path) -> None:
    assert build_backend.get_requires_for_build_wheel() == []
    filename = build_backend.build_wheel(tmp_path)
    wheel = tmp_path / filename
    assert wheel.is_file()
    with zipfile.ZipFile(wheel) as archive:
        names = set(archive.namelist())
        assert "app/cli.py" in names
        assert "app/bundled_assets/ASSET_MANIFEST.json" in names
        assert "app/bundled_assets/parts/minecraft.zip.part000" in names
        assert "app/bundled_assets/parts/minecraft.zip.part008" in names
        assert "app/bundled_assets/minecraft.zip" not in names
        assert "app/bundled_assets/ASSET_MANIFEST.json" in names
        assert "mbi/importer.py" in names
        assert f"{build_backend.DIST_INFO}/METADATA" in names
        assert f"{build_backend.DIST_INFO}/RECORD" in names
        assert f"{build_backend.DIST_INFO}/AUTONOMOUS_LLM_AGENT_GUIDE.md" in names
        metadata = archive.read(f"{build_backend.DIST_INFO}/METADATA").decode("utf-8")
        assert "Version: 1.1.0" in metadata
        assert "pytest-asyncio<2,>=1" in metadata


def test_stdlib_backend_builds_pep660_editable_wheel(tmp_path: Path) -> None:
    assert build_backend.get_requires_for_build_editable() == []
    filename = build_backend.build_editable(tmp_path)
    assert "editable" in filename
    with zipfile.ZipFile(tmp_path / filename) as archive:
        names = set(archive.namelist())
        pth_name = "_minecraft_build_intelligence_editable.pth"
        assert pth_name in names
        paths = archive.read(pth_name).decode("utf-8").splitlines()
        assert str(build_backend.ROOT.resolve()) in paths
        assert str((build_backend.ROOT / "services" / "core" / "src").resolve()) in paths
        assert f"{build_backend.DIST_INFO}/RECORD" in names
