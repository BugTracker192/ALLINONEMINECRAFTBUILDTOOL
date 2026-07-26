from __future__ import annotations

import stat
import zipfile
from pathlib import Path

import pytest

from mbi.assets import safe_index_resource_zip
from mbi.errors import MBIError


def _write_zip(path: Path, entries: dict[str, bytes]) -> None:
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, data in entries.items():
            archive.writestr(name, data)


def test_asset_zip_extracts_only_allowlisted_paths(tmp_path: Path) -> None:
    source = tmp_path / "assets.zip"
    _write_zip(source, {
        "minecraft/blockstates/stone.json": b"{}",
        "minecraft/textures/block/stone.png": b"png",
        "minecraft/lang/en_us.json": b"{}",
    })
    manifest = safe_index_resource_zip(source, tmp_path / "out")
    assert manifest.file_count == 2
    assert (tmp_path / "out/minecraft/blockstates/stone.json").read_bytes() == b"{}"
    assert not (tmp_path / "out/minecraft/lang/en_us.json").exists()


def test_asset_zip_rejects_path_traversal(tmp_path: Path) -> None:
    source = tmp_path / "assets.zip"
    _write_zip(source, {"../minecraft/blockstates/stone.json": b"{}"})
    with pytest.raises(MBIError) as error:
        safe_index_resource_zip(source, tmp_path / "out")
    assert error.value.code == "ASSET_ZIP_PATH_TRAVERSAL"


def test_asset_zip_rejects_symlink(tmp_path: Path) -> None:
    source = tmp_path / "assets.zip"
    with zipfile.ZipFile(source, "w") as archive:
        info = zipfile.ZipInfo("minecraft/blockstates/link.json")
        info.create_system = 3
        info.external_attr = (stat.S_IFLNK | 0o777) << 16
        archive.writestr(info, "../../outside")
    with pytest.raises(MBIError) as error:
        safe_index_resource_zip(source, tmp_path / "out")
    assert error.value.code == "ASSET_ZIP_SYMLINK"


def test_asset_zip_rejects_cumulative_size_over_limit(tmp_path: Path) -> None:
    source = tmp_path / "assets.zip"
    _write_zip(source, {
        "minecraft/models/block/a.json": b"1234",
        "minecraft/models/block/b.json": b"5678",
    })
    with pytest.raises(MBIError) as error:
        safe_index_resource_zip(source, tmp_path / "out", max_total_extracted_bytes=7)
    assert error.value.code == "ASSET_TOTAL_SIZE_LIMIT"
