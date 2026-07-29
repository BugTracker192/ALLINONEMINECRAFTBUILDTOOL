from __future__ import annotations

import csv
from pathlib import Path

from mbi.importer import import_build

from app.comprehension import (
    annotated_render,
    contact_sheet,
    export_block_map,
    palette_atlas,
    slice_sweep,
    texture_audit,
)
from app.project import initialize_layout, save_document


def _single_stone_run(reference_schem: Path, root: Path) -> Path:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    point = next(
        point
        for point, state in document.iter_non_air()
        if state.canonical_state == "minecraft:stone"
    )
    document.blocks = {
        point: document.palette_id_for_state("minecraft:stone")
    }
    document.bounds = type(document.bounds)(point, point)
    document.regions = []
    document.region_blocks = {}
    document.block_entities = []
    document.content_hash = document.compute_content_hash()
    initialize_layout(root)
    save_document(root, document)
    return root


def test_comprehension_artifacts_are_grounded_and_labelled(
    reference_schem: Path,
    tiny_resource_pack: Path,
    tmp_path: Path,
) -> None:
    run = _single_stone_run(reference_schem, tmp_path / "run")
    csv_path = tmp_path / "block-map.csv"
    block_map = export_block_map(
        run,
        csv_path,
        resource_pack=tiny_resource_pack,
    )
    with csv_path.open(newline="", encoding="utf-8") as stream:
        rows = list(csv.DictReader(stream))

    assert block_map["row_count"] == 1
    assert rows[0]["canonical_state"] == "minecraft:stone"
    assert rows[0]["textures"] == "minecraft:block/stone"
    assert rows[0]["classification"] == "terrain"

    audit = texture_audit(run, resource_pack=tiny_resource_pack)
    assert audit["texture_coverage_percent"] == 100.0
    assert audit["failed_block_count"] == 0

    atlas = palette_atlas(
        run,
        tmp_path / "atlas.png",
        resource_pack=tiny_resource_pack,
        columns=2,
        swatch_size=16,
    )
    assert atlas["state_count"] >= 1
    assert Path(atlas["png"]).is_file()

    sheet = contact_sheet(
        run,
        views=("top",),
        output=tmp_path / "sheet.png",
        size=(64, 64),
        accuracy="fast",
    )
    assert sheet["item_count"] == 1
    assert sheet["accuracy"]["texture_exact"] is False

    sweep = slice_sweep(
        run,
        axis="y",
        minimum=int(rows[0]["y"]),
        maximum=int(rows[0]["y"]),
        step=1,
        output=tmp_path / "sweep.png",
        resource_pack=tiny_resource_pack,
    )
    assert len(sweep["slices"]) == 1

    annotated = annotated_render(
        run,
        output=tmp_path / "annotated.png",
        view="top",
        resource_pack=tiny_resource_pack,
        size=(128, 96),
        annotate_materials=1,
    )
    assert annotated["compass"] is True
    assert annotated["material_labels"]
