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
        assert "app/bundled_assets/minecraft.zip" in names
        assert "app/bundled_assets/ASSET_MANIFEST.json" in names
        assert "mbi/importer.py" in names
        assert f"{build_backend.DIST_INFO}/METADATA" in names
        assert f"{build_backend.DIST_INFO}/RECORD" in names
        assert f"{build_backend.DIST_INFO}/AUTONOMOUS_LLM_AGENT_GUIDE.md" in names
        metadata = archive.read(f"{build_backend.DIST_INFO}/METADATA").decode("utf-8")
        assert "Version: 1.0.2" in metadata
