from __future__ import annotations

import hashlib
import json
from pathlib import Path

from app.assets import bundled_resource_pack_path, open_resource_pack, resolve_resource_pack_path


def test_private_bundled_assets_are_auto_discovered(monkeypatch) -> None:
    monkeypatch.delenv("MBI_RESOURCE_PACK", raising=False)
    monkeypatch.delenv("MBI_DISABLE_BUNDLED_ASSETS", raising=False)
    path = bundled_resource_pack_path()
    assert path is not None and path.is_file()
    assert resolve_resource_pack_path() == path
    manifest = json.loads((path.parent / "ASSET_MANIFEST.json").read_text("utf-8"))
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    assert digest == manifest["sha256"]
    with open_resource_pack() as pack:
        assert pack is not None
        assert pack.pack_hash == manifest["sha256"]
        models = pack.select_models("minecraft:stone", (0, 0, 0))
        assert models


def test_bundled_assets_can_be_explicitly_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MBI_DISABLE_BUNDLED_ASSETS", "1")
    monkeypatch.delenv("MBI_RESOURCE_PACK", raising=False)
    assert resolve_resource_pack_path() is None
    assert resolve_resource_pack_path("none") is None
