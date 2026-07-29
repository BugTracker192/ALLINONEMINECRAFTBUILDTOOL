from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

from app.assets import ResourcePackSource
from app.render import CameraSpec, SoftwareRenderer, block_to_pixel, pixel_to_block
from app.render.camera import camera_transform
from app.render.semantic import load_map
from mbi.canonical import CanonicalBlockEntity, IntBoundingBox, IntVector3, PaletteEntry
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


def test_entity_rendered_banner_and_skull_use_real_entity_textures(
    reference_schem: Path,
    tmp_path: Path,
) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    banner = IntVector3(0, 0, 0)
    skull = IntVector3(1, 0, 0)
    document.palette = [
        PaletteEntry.from_state(0, "minecraft:red_wall_banner[facing=north]"),
        PaletteEntry.from_state(1, "minecraft:skeleton_wall_skull[facing=north]"),
    ]
    document.blocks = {banner: 0, skull: 1}
    document.bounds = IntBoundingBox(banner, skull)
    document.region_blocks = {}
    document.regions = []
    document.block_entities = [
        CanonicalBlockEntity(banner, "minecraft:banner", {"Patterns": []}),
        CanonicalBlockEntity(skull, "minecraft:skull", {}),
    ]
    document.content_hash = document.compute_content_hash()

    pack_path = tmp_path / "entity-pack.zip"
    banner_texture = Image.new("RGBA", (64, 64), (220, 220, 220, 255))
    skeleton_texture = Image.new("RGBA", (64, 32), (176, 176, 176, 255))
    wood_texture = Image.new("RGBA", (16, 16), (115, 75, 35, 255))

    def png_bytes(image: Image.Image) -> bytes:
        stream = io.BytesIO()
        image.save(stream, "PNG")
        return stream.getvalue()

    with zipfile.ZipFile(pack_path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(
            "assets/minecraft/blockstates/red_wall_banner.json",
            json.dumps({"variants": {"facing=north": {"model": "minecraft:block/banner"}}}),
        )
        archive.writestr(
            "assets/minecraft/blockstates/skeleton_wall_skull.json",
            json.dumps({"variants": {"facing=north": {"model": "minecraft:block/skull"}}}),
        )
        archive.writestr(
            "assets/minecraft/models/block/banner.json",
            json.dumps({"parent": "builtin/entity"}),
        )
        archive.writestr(
            "assets/minecraft/models/block/skull.json",
            json.dumps({"parent": "builtin/entity"}),
        )
        archive.writestr(
            "assets/minecraft/textures/entity/banner/base.png",
            png_bytes(banner_texture),
        )
        archive.writestr(
            "assets/minecraft/textures/entity/skeleton/skeleton.png",
            png_bytes(skeleton_texture),
        )
        archive.writestr(
            "assets/minecraft/textures/block/oak_planks.png",
            png_bytes(wood_texture),
        )

    with ResourcePackSource(pack_path) as pack:
        result = SoftwareRenderer(
            document,
            resource_pack=pack,
            strict_textures=True,
        ).render(
            tmp_path / "entity-render",
            camera=CameraSpec.preset("north"),
            size=(256, 160),
            mode="textured",
            name="entities",
        )

    assert result.diagnostics["fallback_count"] == 0
    assert len(result.diagnostics["entity_rendered_models"]) == 2
    assert {
        item["representation"]
        for item in result.diagnostics["entity_rendered_models"]
    } == {"entity_texture_proxy"}
    rendered = np.asarray(Image.open(result.png_path).convert("RGBA"))
    opaque_colors = rendered[rendered[..., 3] > 0, :3]
    assert opaque_colors.size
    assert np.any(
        opaque_colors[:, 0].astype(np.int16)
        > opaque_colors[:, 1].astype(np.int16) + 30
    )


def test_camera_fit_is_default_and_manual_mode_uses_pixels_per_block() -> None:
    bounds = IntBoundingBox(IntVector3(10, 20, 30), IntVector3(11, 21, 31))
    fitted = camera_transform(bounds, (200, 100), CameraSpec())
    manual_spec = CameraSpec(
        zoom=3.5,
        target=(10.5, 20.5, 30.5),
        fit_bounds=False,
    )
    manual = camera_transform(bounds, (200, 100), manual_spec)
    projected, _ = manual.project(
        np.asarray([[10.5, 20.5, 30.5]], dtype=np.float64)
    )

    assert fitted.scale > 3.5
    assert manual.scale == 3.5
    assert np.allclose(projected[0], (99.5, 49.5))


def test_tiled_render_is_pixel_exact_and_resumable(
    reference_schem: Path,
    tmp_path: Path,
) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    camera = CameraSpec.preset("isometric_ne")
    monolithic = SoftwareRenderer(document).render(
        tmp_path / "monolithic",
        camera=camera,
        size=(256, 192),
        mode="flat",
        name="reference",
    )
    tiled_renderer = SoftwareRenderer(document)
    tiled = tiled_renderer.render_tiled(
        tmp_path / "tiled",
        camera=camera,
        size=(256, 192),
        tile_size=64,
        mode="flat",
        name="checkpointed",
    )

    assert (
        np.asarray(Image.open(monolithic.png_path))
        == np.asarray(Image.open(tiled.png_path))
    ).all()
    for semantic_name in (
        "palette",
        "coordinate",
        "depth",
        "normal",
        "region",
        "occupancy",
        "changed",
        "issue",
    ):
        expected = load_map(
            monolithic.semantic_metadata_path,
            semantic_name,
        )
        actual = load_map(tiled.semantic_metadata_path, semantic_name)
        assert np.array_equal(expected, actual)

    tiled.png_path.unlink()
    tiled.manifest_path.unlink()
    tiled.semantic_metadata_path.unlink()
    resumed = tiled_renderer.render_tiled(
        tmp_path / "tiled",
        camera=camera,
        size=(256, 192),
        tile_size=64,
        resume=True,
        mode="flat",
        name="checkpointed",
    )
    assert resumed.manifest["tiled"]["resumed_tiles"] == 12
    assert resumed.manifest["tiled"]["completed_tiles"] == 12

    finalized = tiled_renderer.render_tiled(
        tmp_path / "tiled",
        camera=camera,
        size=(256, 192),
        tile_size=64,
        resume=True,
        mode="flat",
        name="checkpointed",
    )
    assert finalized.manifest["tiled"]["resumed_tiles"] == 12
    assert finalized.manifest["tiled"]["resume_source"] == "finalized-output"
