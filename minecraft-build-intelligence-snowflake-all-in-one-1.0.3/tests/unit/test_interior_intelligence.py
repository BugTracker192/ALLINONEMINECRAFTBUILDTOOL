from __future__ import annotations

import json
from pathlib import Path

from mbi.analysis.rooms import classify_air_volumes, room_report
from mbi.canonical import CanonicalBlockEntity, IntBoundingBox, IntVector3
from mbi.importer import import_build

from app.cli import build_parser
from app.interior import (
    camera_candidates,
    feature_candidates,
    room_geometry,
    voxel_ray,
)
from app.render.software import SoftwareRenderer


def _boxed_room(reference_schem: Path, *, size: int = 7):
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    stone = document.palette_id_for_state("minecraft:stone")
    blocks = {}
    for x in range(size):
        for z in range(size):
            blocks[IntVector3(x, 0, z)] = stone
            blocks[IntVector3(x, 4, z)] = stone
    for y in range(1, 4):
        for value in range(size):
            blocks[IntVector3(0, y, value)] = stone
            blocks[IntVector3(size - 1, y, value)] = stone
            blocks[IntVector3(value, y, 0)] = stone
            blocks[IntVector3(value, y, size - 1)] = stone
    document.blocks = blocks
    document.block_entities = []
    document.bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(size - 1, 4, size - 1))
    document.content_hash = document.compute_content_hash()
    room = {
        "id": "room_0",
        "seed": {"x": 1, "y": 1, "z": 1},
        "bounds": {
            "min": {"x": 1, "y": 1, "z": 1},
            "max": {"x": size - 2, "y": 3, "z": size - 2},
        },
    }
    return document, room


def test_room_geometry_uses_exact_seed_component(reference_schem: Path) -> None:
    document, room = _boxed_room(reference_schem)
    stone = document.palette_id_for_state("minecraft:stone")
    chest = document.palette_id_for_state("minecraft:chest[facing=north,type=single,waterlogged=false]")
    for y in range(1, 4):
        for z in range(1, 6):
            document.blocks[IntVector3(3, y, z)] = stone
    disconnected_feature = IntVector3(5, 1, 4)
    document.blocks[disconnected_feature] = chest
    document.block_entities = [CanonicalBlockEntity(disconnected_feature, "minecraft:chest", {})]

    geometry = room_geometry(document, room)
    features = feature_candidates(document, geometry)

    assert IntVector3(1, 1, 1) in geometry.cells
    assert IntVector3(4, 1, 1) not in geometry.cells
    assert all(item.coordinate != disconnected_feature for item in features)


def test_voxel_ray_reports_first_opaque_blocker(reference_schem: Path) -> None:
    document, _ = _boxed_room(reference_schem)
    blocker = IntVector3(3, 2, 3)
    document.blocks[blocker] = document.palette_id_for_state("minecraft:stone")
    hit = voxel_ray(document, (1.5, 2.5, 3.5), (5.5, 2.5, 3.5))
    accepted_hit = voxel_ray(
        document,
        (1.5, 2.5, 3.5),
        (3.5, 2.5, 3.5),
        acceptable_hit=blocker,
    )
    assert not hit.visible
    assert hit.first_blocker == blocker
    assert accepted_hit.visible


def test_camera_candidates_are_ranked_and_diagnostic(reference_schem: Path) -> None:
    document, room = _boxed_room(reference_schem)
    candidates, geometry, features = camera_candidates(document, room, shot="corner")
    assert geometry.cells
    assert candidates
    assert candidates[0].accepted
    assert candidates[0].mode.startswith("physical")
    assert candidates[0].visible_sample_ratio >= 0.5
    assert any(item.mode == "visibility-aware-orbit" for item in candidates)
    assert features == []


def test_room_classifier_separates_room_from_exterior(reference_schem: Path) -> None:
    document, _ = _boxed_room(reference_schem)
    volumes = classify_air_volumes(document)
    enclosed = [item for item in volumes if not item.exterior]
    report = room_report(document, volumes=volumes)
    assert len(enclosed) == 1
    assert enclosed[0].classification == "architectural_room"
    assert enclosed[0].room_like
    assert report["roomLikeCount"] == 1
    assert report["classificationCounts"]["architectural_room"] == 1


def test_slice_crop_is_hashed_and_recorded(reference_schem: Path, tmp_path: Path) -> None:
    document, _room = _boxed_room(reference_schem, size=9)
    crop = IntBoundingBox(IntVector3(2, 0, 2), IntVector3(6, 4, 6))
    result = SoftwareRenderer(document).render_slice(
        tmp_path,
        axis="y",
        minimum=0,
        crop=crop,
        pixels_per_block=4,
        mode="flat",
    )
    manifest = json.loads(result.manifest_path.read_text("utf-8"))
    assert manifest["resolution"] == [20, 20]
    assert manifest["visible_bounds"] == {"min": [2, 0, 2], "max": [6, 4, 6]}


def test_packet_cli_contract_parses_production_options() -> None:
    args = build_parser().parse_args(
        [
            "interior",
            "packet",
            "run-root",
            "--room",
            "157",
            "--camera-mode",
            "auto",
            "--fallback",
            "physical,third-person,cutaway,slices",
            "--shots",
            "doorway,corner,feature,coverage",
            "--quality-profile",
            "presentation",
            "--cutaway-strategy",
            "minimal-ray",
            "--slice-fallback",
            "always",
        ]
    )
    assert args.interior_command == "packet"
    assert args.camera_mode == "auto"
    assert args.fallback.endswith("slices")
