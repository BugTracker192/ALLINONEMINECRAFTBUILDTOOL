from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image


@pytest.fixture
def reference_schem() -> Path:
    return Path(__file__).resolve().parents[1] / "packages" / "test-fixtures" / "generated" / "asymmetric-corners.schem"


@pytest.fixture
def tiny_resource_pack(tmp_path: Path) -> Path:
    pack = tmp_path / "pack.zip"
    texture = Image.new("RGBA", (16, 16), (24, 180, 72, 255))
    for y in range(16):
        for x in range(16):
            if (x + y) % 4 == 0:
                texture.putpixel((x, y), (220, 40, 40, 255))
    texture_bytes = io.BytesIO()
    texture.save(texture_bytes, format="PNG", compress_level=9)
    with zipfile.ZipFile(pack, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("assets/minecraft/blockstates/stone.json", json.dumps({"variants": {"": {"model": "minecraft:block/stone"}}}))
        archive.writestr(
            "assets/minecraft/models/block/stone.json",
            json.dumps(
                {
                    "textures": {"all": "minecraft:block/stone"},
                    "elements": [
                        {
                            "from": [0, 0, 0],
                            "to": [16, 16, 16],
                            "faces": {name: {"texture": "#all", "cullface": name} for name in ("down", "up", "north", "south", "west", "east")},
                        }
                    ],
                }
            ),
        )
        archive.writestr("assets/minecraft/textures/block/stone.png", texture_bytes.getvalue())
    return pack
