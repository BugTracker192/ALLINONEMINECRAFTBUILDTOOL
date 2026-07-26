from __future__ import annotations

import json
import zipfile
from pathlib import Path

from mbi.assets import safe_index_resource_zip


def test_indexes_standard_resource_pack_namespaces_and_entity_textures(tmp_path: Path) -> None:
    source = tmp_path / "pack.zip"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("assets/example/blockstates/custom.json", json.dumps({"variants": {"": {"model": "example:block/custom"}}}))
        archive.writestr("assets/example/models/block/custom.json", json.dumps({"textures": {"all": "example:block/custom"}}))
        archive.writestr("assets/example/textures/block/custom.png", b"png")
        archive.writestr("assets/example/textures/entity/chest/custom.png", b"entity")
        archive.writestr("assets/example/lang/en_us.json", b"{}")
    destination = tmp_path / "indexed"
    manifest = safe_index_resource_zip(source, destination)
    assert manifest.file_count == 4
    assert (destination / "example" / "textures" / "entity" / "chest" / "custom.png").read_bytes() == b"entity"
    assert not (destination / "example" / "lang" / "en_us.json").exists()
