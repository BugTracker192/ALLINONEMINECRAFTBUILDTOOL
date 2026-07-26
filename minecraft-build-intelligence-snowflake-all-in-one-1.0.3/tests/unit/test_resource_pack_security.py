from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from app.assets import ResourcePackSource
from app.errors import AppError


def test_resource_pack_rejects_path_traversal(tmp_path: Path) -> None:
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("../escape.txt", b"bad")
    with pytest.raises(AppError, match="unsafe path"):
        ResourcePackSource(path)


def test_resource_pack_rejects_duplicate_entries(tmp_path: Path) -> None:
    path = tmp_path / "duplicate.zip"
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(path, "w") as archive:
            archive.writestr("assets/minecraft/models/block/a.json", "{}")
            archive.writestr("assets/minecraft/models/block/a.json", "{}")
    with pytest.raises(AppError, match="duplicate"):
        ResourcePackSource(path)


def test_resource_pack_accepts_modern_texture_sprite_object(tmp_path: Path) -> None:
    import io
    import json
    from PIL import Image
    from app.assets import ResourcePackSource

    pack = tmp_path / "modern.zip"
    image = Image.new("RGBA", (16, 16), (100, 150, 200, 90))
    payload = io.BytesIO()
    image.save(payload, "PNG")
    with zipfile.ZipFile(pack, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("minecraft/blockstates/glass.json", json.dumps({"variants": {"": {"model": "minecraft:block/glass"}}}))
        archive.writestr("minecraft/models/block/glass.json", json.dumps({
            "parent": "minecraft:block/cube_all",
            "textures": {"all": {"force_translucent": True, "sprite": "minecraft:block/glass"}},
        }))
        archive.writestr("minecraft/models/block/cube_all.json", json.dumps({
            "textures": {name: "#all" for name in ("particle", "down", "up", "north", "south", "west", "east")},
            "elements": [{"from": [0, 0, 0], "to": [16, 16, 16], "faces": {name: {"texture": f"#{name}"} for name in ("down", "up", "north", "south", "west", "east")}}],
        }))
        archive.writestr("minecraft/textures/block/glass.png", payload.getvalue())
    with ResourcePackSource(pack) as source:
        model = source.resolve_model("minecraft:block/glass")
        assert model.textures["all"] == "minecraft:block/glass"
        assert source.texture(*source.resolve_texture_ref(model.textures, "#all")).getpixel((0, 0))[3] == 90
