from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image

from app.assets import ResourcePackSource
from app.render import CameraSpec, SoftwareRenderer, block_to_pixel, pixel_to_block
from app.render.semantic import load_map
from mbi.importer import import_build


def test_flat_renderer_is_deterministic_and_grounded(reference_schem: Path, tmp_path: Path) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    first = SoftwareRenderer(document).render(tmp_path / "a", camera=CameraSpec.preset("isometric_ne"), size=(256, 256), mode="flat", name="iso")
    second = SoftwareRenderer(document).render(tmp_path / "b", camera=CameraSpec.preset("isometric_ne"), size=(256, 256), mode="flat", name="iso")
    assert first.png_path.read_bytes() == second.png_path.read_bytes()
    assert first.manifest["render_mode"] == "software-flat"
    metadata = json.loads(first.semantic_metadata_path.read_text("utf-8"))
    coordinates = load_map(first.semantic_metadata_path, "coordinate")
    occupied = np.where(coordinates[..., 0] != np.iinfo(np.int32).min)
    assert len(occupied[0]) > 0
    py, px = int(occupied[0][0]), int(occupied[1][0])
    hit = pixel_to_block(first.manifest_path, px, py)
    assert hit is not None
    projections = block_to_pixel(first.manifest_path, *hit["coordinate"])
    assert {"px": px, "py": py} in projections
    assert metadata["arrays"]["coordinate"]["dtype"] == "<i4"


def test_textured_renderer_samples_pack(reference_schem: Path, tiny_resource_pack: Path, tmp_path: Path) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    # Isolate the known stone corner so unknown/modded fixture blocks cannot affect strict mode.
    stone_position = next(position for position, state in document.iter_non_air() if state.canonical_state == "minecraft:stone")
    document.blocks = {stone_position: document.palette_id_for_state("minecraft:stone")}
    document.bounds = type(document.bounds)(stone_position, stone_position)
    document.content_hash = document.compute_content_hash()
    with ResourcePackSource(tiny_resource_pack) as pack:
        result = SoftwareRenderer(document, resource_pack=pack, strict_textures=True).render(
            tmp_path, camera=CameraSpec.preset("isometric_ne"), size=(256, 256), mode="textured", name="textured"
        )
    image = np.asarray(Image.open(result.png_path).convert("RGBA"))
    opaque = image[..., 3] > 0
    assert opaque.any()
    assert result.manifest["render_mode"] == "software-textured"
    # Real texture red/green pattern survives lighting; it is not a single palette color.
    assert np.unique(image[opaque][:, :3], axis=0).shape[0] >= 2


def test_exact_axis_slice_mapping(reference_schem: Path, tmp_path: Path) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    result = SoftwareRenderer(document).render_slice(tmp_path, axis="y", minimum=3, pixels_per_block=10, mode="flat")
    assert result.manifest["pixels_per_block"] == 10
    hit = pixel_to_block(result.manifest_path, 5, 5)
    assert hit is not None
    assert hit["coordinate"][1] == 3


def test_renderer_material_filters_and_issue_map(reference_schem: Path, tmp_path: Path) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    stone_position = next(position for position, state in document.iter_non_air() if state.canonical_state == "minecraft:stone")
    result = SoftwareRenderer(document).render(
        tmp_path,
        camera=CameraSpec.preset("isometric_ne"),
        size=(256, 256),
        mode="flat",
        include_states=("minecraft:stone",),
        issue_coordinates={stone_position: 3},
        name="filtered_issue",
    )
    palette = load_map(result.semantic_metadata_path, "palette")
    visible = set(int(value) for value in np.unique(palette) if int(value) != np.iinfo(palette.dtype).max)
    assert visible == {document.palette_id_for_state("minecraft:stone")}
    issue = load_map(result.semantic_metadata_path, "issue")
    assert int(issue.max()) == 3
    assert result.manifest["filters"]["include_states"] == ["minecraft:stone"]
