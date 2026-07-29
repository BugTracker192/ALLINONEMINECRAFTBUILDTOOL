from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from app.assets import ResourcePackSource, migrate_asset_state
from app.errors import AppError


def _alias_pack(path: Path, *, include_short_grass: bool = True) -> Path:
    with zipfile.ZipFile(path, "w") as archive:
        if include_short_grass:
            archive.writestr(
                "assets/minecraft/blockstates/short_grass.json",
                json.dumps({"variants": {"": {"model": "minecraft:block/short_grass"}}}),
            )
        archive.writestr(
            "assets/minecraft/blockstates/iron_chain.json",
            json.dumps({"variants": {"axis=y": {"model": "minecraft:block/iron_chain"}}}),
        )
    return path


def test_asset_migration_preserves_properties_and_canonical_input() -> None:
    migration = migrate_asset_state("minecraft:chain[axis=y,waterlogged=false]")
    assert migration is not None
    assert migration.source_state == "minecraft:chain[axis=y,waterlogged=false]"
    assert migration.target_state == "minecraft:iron_chain[axis=y,waterlogged=false]"


def test_resource_pack_resolves_versioned_legacy_aliases(tmp_path: Path) -> None:
    with ResourcePackSource(_alias_pack(tmp_path / "pack.zip")) as source:
        grass = source.select_models("minecraft:grass", (1, 2, 3))
        chain = source.select_models("minecraft:chain[axis=y]", (4, 5, 6))
        assert grass[0].model == "minecraft:block/short_grass"
        assert chain[0].model == "minecraft:block/iron_chain"
        assert [item["code"] for item in source.diagnostics] == ["LEGACY_ID_MAPPED", "LEGACY_ID_MAPPED"]
        assert source.diagnostics[0]["migration_table"].startswith("java-1.20")


def test_missing_migration_target_has_specific_diagnostic(tmp_path: Path) -> None:
    with (
        ResourcePackSource(_alias_pack(tmp_path / "pack.zip", include_short_grass=False)) as source,
        pytest.raises(AppError) as error,
    ):
        source.select_models("minecraft:grass", (0, 0, 0))
    assert error.value.code == "UNMAPPED_LEGACY_ID"
