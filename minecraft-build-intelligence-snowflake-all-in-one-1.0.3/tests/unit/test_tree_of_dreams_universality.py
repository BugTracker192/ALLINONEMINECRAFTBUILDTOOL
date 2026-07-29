from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path
from typing import ClassVar

import numpy as np
from mbi.analysis.structures import (
    classify_block_name,
    structure_inventory_payload,
)
from mbi.canonical import (
    BuildDocument,
    BuildSource,
    CanonicalBlockEntity,
    IntBoundingBox,
    IntVector3,
    PaletteEntry,
)
from mbi.export.sponge import export_sponge_v3
from mbi.export.verify import verify_round_trip
from mbi.formats.litematic import (
    iter_block_states,
    pack_block_states,
)
from mbi.importer import import_build
from mbi.voxel import ChunkedVoxelMap
from PIL import Image

from app.assets import ModelInstance, ResolvedModel
from app.comprehension import _asset_rows, palette_atlas
from app.config import RuntimeConfig
from app.project import initialize_layout, save_document
from app.quality_report import _scorecard
from app.render import CameraSpec, SoftwareRenderer
from app.render.semantic import load_map
from app.render.software import RenderDiagnostics
from app.workflows import export_run


def _document(
    states: list[str],
    blocks: ChunkedVoxelMap,
    bounds: IntBoundingBox,
    *,
    block_entities: list[CanonicalBlockEntity] | None = None,
) -> BuildDocument:
    source = BuildSource(
        "matrix",
        "generated",
        "none",
        hashlib.sha256(b"matrix").hexdigest(),
        0,
        0,
        4903,
        3,
    )
    return BuildDocument(
        "1.2.0",
        "build_matrix",
        source,
        {},
        bounds,
        bounds.min,
        [PaletteEntry.from_state(index, state) for index, state in enumerate(states)],
        [],
        blocks,
        block_entities=block_entities or [],
    )


def test_scale_budget_supports_at_least_five_million_blocks_per_gibibyte() -> None:
    # 4096 full chunks = 16,777,216 placed blocks, the declared 4x scale gate.
    values = ChunkedVoxelMap.from_filled_chunk_box(16, 16, 16, 1)
    assert len(values) == 16_777_216
    assert values.storage_bytes == 67_108_864
    placed_per_gib = len(values) / values.storage_bytes * (1024**3)
    assert placed_per_gib >= 5_000_000


def test_litematic_four_million_cell_stream_has_no_cell_list() -> None:
    count = 4_194_304
    words = pack_block_states(
        (index & 3 for index in range(count)),
        2,
        expected_count=count,
    )
    streamed = iter_block_states(words, count, 2)
    assert sum(1 for _ in streamed) == count
    assert len(words) == count * 2 // 64


def test_terrain_skin_is_not_a_structure_and_flowers_are_vegetation() -> None:
    states = [
        "minecraft:air",
        "minecraft:dirt",
        "minecraft:mossy_cobblestone_slab[type=bottom,waterlogged=false]",
        "minecraft:azure_bluet",
        "minecraft:blue_orchid",
        "minecraft:pink_tulip",
        "minecraft:white_tulip",
    ]
    blocks = ChunkedVoxelMap()
    for x in range(32):
        for z in range(32):
            blocks[IntVector3(x, 0, z)] = 1
            blocks[IntVector3(x, 1, z)] = 2
    for index, palette_id in enumerate(range(3, 7)):
        blocks[IntVector3(index, 2, index)] = palette_id
    document = _document(
        states,
        blocks,
        IntBoundingBox(IntVector3(0, 0, 0), IntVector3(31, 3, 31)),
    )
    report = structure_inventory_payload(
        document,
        minimum_blocks=4,
        window_edge=8,
    )
    assert report["structureCount"] == 0
    assert report["classification"]["counts"]["terrain_detail"] == 1024
    assert report["classification"]["counts"]["vegetation"] == 4
    assert classify_block_name("azure_bluet") == "vegetation"
    assert classify_block_name("pink_tulip") == "vegetation"


def _architectural_fixture(kind: str) -> BuildDocument:
    states = [
        "minecraft:air",
        "minecraft:dirt",
        (
            "minecraft:stone_bricks"
            if kind == "bridge"
            else (
                "minecraft:mossy_cobblestone"
                if kind == "dungeon"
                else "minecraft:cobblestone"
            )
        ),
    ]
    blocks = ChunkedVoxelMap()
    if kind == "castle":
        bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(11, 6, 11))
        for x in range(12):
            for z in range(12):
                blocks[IntVector3(x, 0, z)] = 1
        for y in range(1, 6):
            for x in range(2, 9):
                for z in range(2, 9):
                    if x in (2, 8) or z in (2, 8):
                        blocks[IntVector3(x, y, z)] = 2
    elif kind == "bridge":
        bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(23, 5, 6))
        for x in range(24):
            for z in range(7):
                blocks[IntVector3(x, 0, z)] = 1
        for x in range(2, 22):
            for z in range(2, 5):
                blocks[IntVector3(x, 4, z)] = 2
        for x in (2, 21):
            for y in range(1, 4):
                for z in range(2, 5):
                    blocks[IntVector3(x, y, z)] = 2
    else:
        bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(11, 9, 11))
        for x in range(12):
            for y in range(10):
                for z in range(12):
                    blocks[IntVector3(x, y, z)] = 1
        for x in range(2, 10):
            for y in range(1, 8):
                for z in range(2, 10):
                    if x in (2, 9) or y in (1, 7) or z in (2, 9):
                        blocks[IntVector3(x, y, z)] = 2
        for x in range(3, 9):
            for y in range(2, 7):
                for z in range(3, 9):
                    blocks.pop(IntVector3(x, y, z), None)
    return _document(states, blocks, bounds)


def test_material_independent_architecture_guards() -> None:
    for kind in ("castle", "bridge", "dungeon"):
        report = structure_inventory_payload(
            _architectural_fixture(kind),
            minimum_blocks=4,
            window_edge=8,
        )
        buildings = [
            item
            for item in report["structures"]
            if item["structure_kind"] == "building"
        ]
        assert buildings, kind
        evidence = buildings[0]["classification_evidence"]
        assert set(evidence) >= {
            "verticality",
            "enclosure",
            "regularity",
            "surface_embedding",
        }
        assert report["classification"]["counts"]["built"] > 0


class _RendererPack:
    pack_hash = "fake-pack"
    diagnostics: ClassVar[list[dict]] = []

    @staticmethod
    def select_models(state, coordinate, seed):
        return [
            ModelInstance(
                "minecraft:block/static"
                if "waterlogged=true" in state
                else "minecraft:block/entity"
            )
        ]

    @staticmethod
    def resolve_model(model):
        if model.endswith("/static"):
            return ResolvedModel(
                ({
                    "from": [0, 0, 0],
                    "to": [16, 8, 16],
                    "faces": {
                        face: {"texture": "#all", "cullface": face}
                        for face in (
                            "down",
                            "up",
                            "north",
                            "south",
                            "west",
                            "east",
                        )
                    },
                },),
                {"all": "minecraft:block/fake"},
                False,
                (),
            )
        return ResolvedModel((), {}, False, ())

    @staticmethod
    def resolve_texture_ref(textures, reference, namespace):
        if ":" in reference:
            return tuple(reference.split(":", 1))
        return namespace, reference.lstrip("#")

    @staticmethod
    def texture(namespace, path):
        return Image.new("RGBA", (64, 64), (80, 140, 220, 255))


def test_all_entity_rendered_families_and_general_fluids_are_accounted(
    tmp_path: Path,
) -> None:
    states = [
        "minecraft:air",
        "minecraft:red_banner[rotation=0]",
        "minecraft:skeleton_skull[rotation=0]",
        "minecraft:oak_sign[rotation=0,waterlogged=false]",
        "minecraft:red_bed[facing=north,occupied=false,part=head]",
        "minecraft:shulker_box[facing=up]",
        "minecraft:water[level=0]",
        "minecraft:water[level=7]",
        "minecraft:lava[level=3]",
        "minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=true]",
    ]
    blocks = ChunkedVoxelMap()
    for index in range(1, len(states)):
        blocks[IntVector3(index - 1, 0, 0)] = index
    document = _document(
        states,
        blocks,
        IntBoundingBox(IntVector3(0, 0, 0), IntVector3(len(states) - 2, 1, 0)),
    )
    rows = _asset_rows(document, _RendererPack())
    assert sum(item["status"] == "entity-rendered" for item in rows.values()) == 5
    assert sum(item["status"] == "fluid-rendered" for item in rows.values()) == 3
    assert rows[states[-1]]["fluid_overlay_supported"] is True

    result = SoftwareRenderer(
        document,
        resource_pack=_RendererPack(),
        strict_textures=True,
    ).render(
        tmp_path / "entities",
        camera=CameraSpec.preset("isometric_ne"),
        size=(192, 96),
        mode="textured",
        name="families",
    )
    rendered_states = {
        item["state"]
        for item in result.diagnostics["entity_rendered_models"]
    }
    assert set(states[1:6]) <= rendered_states
    assert np.asarray(Image.open(result.png_path))[..., 3].any()


def test_model_cache_is_state_shared_or_strictly_bounded() -> None:
    blocks = ChunkedVoxelMap()
    for x in range(10):
        blocks[IntVector3(x, 0, 0)] = 1
    document = _document(
        ["minecraft:air", "minecraft:stone"],
        blocks,
        IntBoundingBox(IntVector3(0, 0, 0), IntVector3(9, 0, 0)),
    )
    fallback_renderer = SoftwareRenderer(
        document,
        config=RuntimeConfig(model_cache_items=2),
    )
    for point in document.blocks:
        fallback_renderer._block_models(
            document.palette[1],
            point,
            RenderDiagnostics("test", 0),
        )
    assert len(fallback_renderer._model_cache) == 1

    positioned_renderer = SoftwareRenderer(
        document,
        resource_pack=_RendererPack(),
        config=RuntimeConfig(model_cache_items=2),
    )
    for point in document.blocks:
        positioned_renderer._block_models(
            document.palette[1],
            point,
            RenderDiagnostics("test", 0),
        )
    assert len(positioned_renderer._model_cache) == 2


def test_negative_y_roundtrip_and_fifty_thousand_rich_block_entities() -> None:
    bounds = IntBoundingBox(IntVector3(0, -64, 0), IntVector3(49, -45, 49))
    blocks = ChunkedVoxelMap.from_filled_chunk_box(
        4,
        2,
        4,
        1,
        chunk_origin=(0, -4, 0),
    )
    # Clip the chunk-aligned store to the exact 50x20x50 fixture.
    clipped = ChunkedVoxelMap()
    entities: list[CanonicalBlockEntity] = []
    index = 0
    for point, palette_id in blocks.iter_items_sorted():
        if not bounds.contains(point):
            continue
        clipped[point] = palette_id
        entities.append(
            CanonicalBlockEntity(
                point,
                "minecraft:chest",
                {
                    "id": "minecraft:chest",
                    "CustomName": f"entity-{index}",
                    "Items": [
                        {
                            "Slot": index % 27,
                            "id": "minecraft:stone",
                            "count": (index % 64) + 1,
                        }
                    ],
                    "nested": {"index": index, "flags": [True, False]},
                },
            )
        )
        index += 1
    assert len(clipped) == 50_000
    assert len(entities) == 50_000
    document = _document(
        [
            "minecraft:air",
            "minecraft:chest[facing=north,type=single,waterlogged=false]",
        ],
        clipped,
        bounds,
        block_entities=entities,
    )
    data = export_sponge_v3(document)
    report = verify_round_trip(document, data, "matrix.schem")
    assert report.valid
    assert report.coordinate_mismatches == 0
    assert report.state_mismatches == 0
    assert report.block_entity_mismatches == 0
    reparsed = import_build(data, "matrix.schem")
    assert reparsed.bounds.min.y == -64
    assert len(reparsed.block_entities) == 50_000


def test_modern_world_height_renders_semantics_and_roundtrips(
    tmp_path: Path,
) -> None:
    blocks = ChunkedVoxelMap()
    for index, y in enumerate((-64, 0, 320), start=1):
        blocks[IntVector3(index, y, index)] = 1
    document = _document(
        ["minecraft:air", "minecraft:stone"],
        blocks,
        IntBoundingBox(IntVector3(0, -64, 0), IntVector3(4, 320, 4)),
    )
    rendered = SoftwareRenderer(document).render(
        tmp_path / "modern-height",
        camera=CameraSpec.preset("isometric_ne"),
        size=(96, 384),
        mode="flat",
        name="negative-to-modern-height",
    )
    assert rendered.png_path.is_file()
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
        assert load_map(
            rendered.semantic_metadata_path,
            semantic_name,
        ).shape[:2] == (384, 96)
    exported = export_sponge_v3(document)
    assert verify_round_trip(document, exported, "modern-height.schem").valid


def test_two_million_block_exact_tiled_resume_is_byte_deterministic(
    tmp_path: Path,
) -> None:
    blocks = ChunkedVoxelMap.from_filled_chunk_box(8, 8, 8, 1)
    assert len(blocks) == 2_097_152
    document = _document(
        ["minecraft:air", "minecraft:stone"],
        blocks,
        IntBoundingBox(IntVector3(0, 0, 0), IntVector3(127, 127, 127)),
    )
    renderer = SoftwareRenderer(
        document,
        config=RuntimeConfig(max_visible_blocks=100_000),
    )
    output = tmp_path / "exact-scale"
    first = renderer.render_tiled(
        output,
        camera=CameraSpec.preset("isometric_ne"),
        size=(64, 64),
        tile_size=64,
        mode="flat",
        name="two-million",
    )
    expected_png = first.png_path.read_bytes()
    expected_maps = {
        name: load_map(first.semantic_metadata_path, name).copy()
        for name in (
            "palette",
            "coordinate",
            "depth",
            "normal",
            "region",
            "occupancy",
            "changed",
            "issue",
        )
    }
    first.png_path.unlink()
    first.manifest_path.unlink()
    first.semantic_metadata_path.unlink()
    resumed = renderer.render_tiled(
        output,
        camera=CameraSpec.preset("isometric_ne"),
        size=(64, 64),
        tile_size=64,
        resume=True,
        mode="flat",
        name="two-million",
    )
    assert resumed.png_path.read_bytes() == expected_png
    assert resumed.manifest["tiled"]["resumed_tiles"] == 1
    for name, expected in expected_maps.items():
        assert np.array_equal(
            load_map(resumed.semantic_metadata_path, name),
            expected,
        )


def test_lod_manifest_is_honestly_non_exact_and_bounded(tmp_path: Path) -> None:
    blocks = ChunkedVoxelMap.from_filled_chunk_box(2, 1, 2, 1)
    document = _document(
        ["minecraft:air", "minecraft:stone"],
        blocks,
        IntBoundingBox(IntVector3(0, 0, 0), IntVector3(31, 15, 31)),
    )
    result = SoftwareRenderer(
        document,
        config=RuntimeConfig(max_visible_blocks=1),
    ).render_lod(
        tmp_path,
        camera=CameraSpec.preset("isometric_ne"),
        size=(128, 96),
        name="lod",
    )
    assert result.manifest["lod"]["enabled"] is True
    assert result.manifest["accuracy"]["exact"] is False
    assert result.manifest["lod"]["source_block_count"] == len(blocks)


def test_lighting_unknown_and_no_verify_are_explicit(
    tmp_path: Path,
) -> None:
    blocks = ChunkedVoxelMap()
    blocks[IntVector3(0, 0, 0)] = 1
    sample_document = _document(
        ["minecraft:air", "minecraft:stone"],
        blocks,
        IntBoundingBox(IntVector3(0, 0, 0), IntVector3(0, 0, 0)),
    )
    analysis = {
        "materials": {"totalNonAir": len(sample_document.blocks), "states": {}},
        "lighting": {},
        "rooms": {"rooms": []},
        "facade": {},
        "support": {},
        "components": {},
        "navigation": {"analysisSkipped": True},
        "symmetry": {},
    }
    scorecard = _scorecard(
        sample_document,
        analysis,
        packet_coverages=[],
    )
    assert scorecard["dimensions"]["lighting"]["available"] is False
    assert scorecard["dimensions"]["lighting"]["score"] is None

    run = tmp_path / "run"
    initialize_layout(run)
    save_document(run, sample_document)
    skipped = export_run(run, format_name="schem", verify=False)
    assert skipped["passed"] == "skipped"
    assert skipped["verification"] == "skipped"


def test_two_thousand_state_atlas_is_paginated_and_bounded(
    tmp_path: Path,
) -> None:
    states = ["minecraft:air"] + [
        f"example:block_{index:04d}" for index in range(2000)
    ]
    blocks = ChunkedVoxelMap()
    for index in range(2000):
        blocks[IntVector3(index, 0, 0)] = index + 1
    document = _document(
        states,
        blocks,
        IntBoundingBox(IntVector3(0, 0, 0), IntVector3(1999, 0, 0)),
    )
    run = tmp_path / "atlas-run"
    save_document(run, document)
    pack = tmp_path / "empty-pack.zip"
    with zipfile.ZipFile(pack, "w") as archive:
        archive.writestr(
            "pack.mcmeta",
            json.dumps({"pack": {"pack_format": 46, "description": "test"}}),
        )
    report = palette_atlas(
        run,
        tmp_path / "atlas.png",
        resource_pack=pack,
        columns=5,
        swatch_size=16,
    )
    assert report["state_count"] == 2000
    assert report["paginated"] is True
    assert len(report["pages"]) == 8
    assert max(page["resolution"][1] for page in report["pages"]) <= 3200
