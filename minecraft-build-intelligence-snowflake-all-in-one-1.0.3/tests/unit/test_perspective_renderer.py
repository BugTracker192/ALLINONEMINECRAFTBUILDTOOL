from __future__ import annotations

import json
from pathlib import Path

import numpy as np

from app.interior import RoomCameraChoice, choose_room_camera, cutaway_mask, walkable_eye_positions
from app.assets import ResourcePackSource
from app.render import PerspectiveCameraSpec, PerspectiveRenderer, block_to_pixel, pixel_to_block
from app.render.semantic import load_map
from mbi.canonical import IntBoundingBox, IntVector3
from mbi.importer import import_build


def _center(document) -> tuple[float, float, float]:
    bounds = document.bounds
    return (
        (bounds.min.x + bounds.max.x + 1) / 2.0,
        (bounds.min.y + bounds.max.y + 1) / 2.0,
        (bounds.min.z + bounds.max.z + 1) / 2.0,
    )


def test_perspective_renderer_is_deterministic_and_grounded(reference_schem: Path, tmp_path: Path) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    target = _center(document)
    camera = PerspectiveCameraSpec(
        position=(target[0] + 8.0, target[1] + 5.0, target[2] - 10.0),
        target=target,
        vertical_fov_degrees=68.0,
    )
    first = PerspectiveRenderer(document).render(tmp_path / "a", camera=camera, size=(256, 192), mode="flat", name="perspective")
    second = PerspectiveRenderer(document).render(tmp_path / "b", camera=camera, size=(256, 192), mode="flat", name="perspective")
    assert first.png_path.read_bytes() == second.png_path.read_bytes()
    assert first.manifest["type"] == "perspective"
    assert first.manifest["projection"] == "perspective"
    assert first.manifest["render_tier"] == 0
    coordinates = load_map(first.semantic_metadata_path, "coordinate")
    occupied = np.where(coordinates[..., 0] != np.iinfo(np.int32).min)
    assert len(occupied[0]) > 0
    py, px = int(occupied[0][0]), int(occupied[1][0])
    hit = pixel_to_block(first.manifest_path, px, py)
    assert hit is not None
    assert {"px": px, "py": py} in block_to_pixel(first.manifest_path, *hit["coordinate"])


def test_perspective_depth_makes_near_block_larger(reference_schem: Path, tmp_path: Path) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    stone = document.palette_id_for_state("minecraft:stone")
    near = IntVector3(-2, 0, 4)
    far = IntVector3(2, 0, 9)
    document.blocks = {near: stone, far: stone}
    document.bounds = IntBoundingBox(IntVector3(-2, 0, 4), IntVector3(2, 0, 9))
    document.content_hash = document.compute_content_hash()
    result = PerspectiveRenderer(document).render(
        tmp_path,
        camera=PerspectiveCameraSpec(position=(0.5, 0.5, 0.0), target=(0.5, 0.5, 10.0), vertical_fov_degrees=70.0),
        size=(320, 180),
        mode="flat",
        name="depth",
    )
    coordinates = load_map(result.semantic_metadata_path, "coordinate")
    near_pixels = int(np.all(coordinates == np.asarray(near.as_tuple(), dtype=np.int32), axis=2).sum())
    far_pixels = int(np.all(coordinates == np.asarray(far.as_tuple(), dtype=np.int32), axis=2).sum())
    assert near_pixels > far_pixels > 0


def test_near_plane_clipping_does_not_explode_geometry(reference_schem: Path, tmp_path: Path) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    stone_position = next(position for position, state in document.iter_non_air() if state.canonical_state == "minecraft:stone")
    document.blocks = {stone_position: document.palette_id_for_state("minecraft:stone")}
    document.bounds = IntBoundingBox(stone_position, stone_position)
    document.content_hash = document.compute_content_hash()
    center = tuple(value + 0.5 for value in stone_position.as_tuple())
    camera = PerspectiveCameraSpec(
        position=(center[0], center[1], stone_position.z - 0.02),
        target=center,
        vertical_fov_degrees=75.0,
        near=0.01,
    )
    result = PerspectiveRenderer(document).render(tmp_path, camera=camera, size=(256, 256), mode="flat", name="near_clip")
    occupancy = load_map(result.semantic_metadata_path, "occupancy")
    assert int(occupancy.sum()) > 0
    assert int(occupancy.sum()) <= 256 * 256


def test_room_camera_uses_real_walkable_eye_position(reference_schem: Path) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    stone = document.palette_id_for_state("minecraft:stone")
    blocks = {}
    for x in range(5):
        for z in range(5):
            blocks[IntVector3(x, 0, z)] = stone
            blocks[IntVector3(x, 4, z)] = stone
    for y in range(1, 4):
        for i in range(5):
            blocks[IntVector3(0, y, i)] = stone
            blocks[IntVector3(4, y, i)] = stone
            blocks[IntVector3(i, y, 0)] = stone
            blocks[IntVector3(i, y, 4)] = stone
    document.blocks = blocks
    document.bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(4, 4, 4))
    document.content_hash = document.compute_content_hash()
    room = {
        "id": "room_0",
        "bounds": {
            "min": {"x": 1, "y": 1, "z": 1},
            "max": {"x": 3, "y": 3, "z": 3},
        },
    }
    candidates = walkable_eye_positions(document, IntBoundingBox(IntVector3(1, 1, 1), IntVector3(3, 3, 3)))
    assert len(candidates) == 9
    choice = choose_room_camera(document, room, shot="corner")
    assert choice.position in candidates
    assert choice.room_id == "room_0"
    assert choice.target != choice.position


def test_perspective_manifest_records_camera_and_visibility_mask(reference_schem: Path, tmp_path: Path) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    target = _center(document)
    hidden = frozenset(list(document.blocks)[:1])
    result = PerspectiveRenderer(document).render(
        tmp_path,
        camera=PerspectiveCameraSpec(position=(target[0] + 5, target[1] + 4, target[2] - 8), target=target),
        size=(192, 128),
        mode="flat",
        hidden_coordinates=hidden,
        name="manifest",
    )
    manifest = json.loads(result.manifest_path.read_text("utf-8"))
    assert manifest["camera"]["position"]
    assert manifest["camera"]["target"]
    assert manifest["temporary_visibility_mask"]["coordinate_count"] == 1
    assert manifest["renderer_version"] == "python-cpu-perspective-rasterizer-v1"


def test_render_room_executes_true_perspective_pipeline(reference_schem: Path, tmp_path: Path, monkeypatch) -> None:
    from app.interior import rendering as interior_rendering

    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    stone = document.palette_id_for_state("minecraft:stone")
    blocks = {}
    for x in range(5):
        for z in range(5):
            blocks[IntVector3(x, 0, z)] = stone
            blocks[IntVector3(x, 4, z)] = stone
    for y in range(1, 4):
        for i in range(5):
            blocks[IntVector3(0, y, i)] = stone
            blocks[IntVector3(4, y, i)] = stone
            blocks[IntVector3(i, y, 0)] = stone
            blocks[IntVector3(i, y, 4)] = stone
    document.blocks = blocks
    document.bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(4, 4, 4))
    document.content_hash = document.compute_content_hash()
    room = {
        "id": "room_0",
        "bounds": {
            "min": {"x": 1, "y": 1, "z": 1},
            "max": {"x": 3, "y": 3, "z": 3},
        },
    }
    monkeypatch.setattr(interior_rendering, "load_document", lambda _root: document)
    monkeypatch.setattr(interior_rendering, "get_room", lambda _root, _room_id: room)
    monkeypatch.setattr(interior_rendering, "open_resource_pack", lambda _resource_pack: None)
    result = interior_rendering.render_room(
        tmp_path, "room_0", shot="corner", size=(256, 160), occlusion="physical", out=tmp_path / "gallery"
    )
    assert result["projection"] == "perspective"
    assert result["quality_status"] in {"accepted", "degraded"}
    assert result["attempt_count"] >= 1
    assert result["quality"]["visible_coordinate_count"] > 0
    assert Path(result["png"]).is_file()
    manifest = json.loads(Path(result["manifest"]).read_text("utf-8"))
    assert manifest["type"] == "perspective"
    assert manifest["camera"]["position"]
    assert manifest["temporary_visibility_mask"]["coordinate_count"] == 0
    assert manifest["interior_intelligence"]["room_id"] == "room_0"
    assert manifest["interior_intelligence"]["quality"]["visible_coordinate_count"] > 0

    packet_root = tmp_path / "packet"
    packet = interior_rendering.render_room_packet(
        tmp_path,
        "room_0",
        shots=(),
        size=(160, 100),
        max_attempts=2,
        out=packet_root,
    )
    assert packet["schema"] == "mbi.interior-packet.v2"
    for artifact in (
        "interior_packet.json",
        "room_summary.json",
        "camera_candidates.json",
        "camera_rejections.json",
        "accepted_views.json",
        "physical_first_person.png",
        "physical_first_person.manifest.json",
        "third_person_cutaway.png",
        "third_person_cutaway.manifest.json",
        "top_plan.png",
        "top_plan.manifest.json",
        "central_slice_x.png",
        "central_slice_z.png",
        "feature_slice.png",
        "quality_metrics.json",
        "diagnostics.json",
    ):
        assert (packet_root / artifact).is_file()


def test_perspective_textures_and_yaw_pitch(reference_schem: Path, tiny_resource_pack: Path, tmp_path: Path) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    stone_position = next(position for position, state in document.iter_non_air() if state.canonical_state == "minecraft:stone")
    document.blocks = {stone_position: document.palette_id_for_state("minecraft:stone")}
    document.bounds = IntBoundingBox(stone_position, stone_position)
    document.content_hash = document.compute_content_hash()
    camera = PerspectiveCameraSpec(
        position=(stone_position.x + 0.5, stone_position.y + 0.5, stone_position.z - 4.0),
        yaw_degrees=0.0,
        pitch_degrees=0.0,
        vertical_fov_degrees=65.0,
    )
    with ResourcePackSource(tiny_resource_pack) as pack:
        result = PerspectiveRenderer(document, resource_pack=pack, strict_textures=True).render(
            tmp_path, camera=camera, size=(256, 192), mode="textured", name="perspective_textured"
        )
    assert result.manifest["render_mode"] == "software-textured"
    assert result.manifest["camera"]["yaw_degrees"] == 0.0
    assert int(load_map(result.semantic_metadata_path, "occupancy").sum()) > 0


def test_cutaway_mask_is_non_destructive(reference_schem: Path) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    stone = document.palette_id_for_state("minecraft:stone")
    blocks = {IntVector3(0, y, z): stone for y in range(4) for z in range(4)}
    document.blocks = blocks
    document.bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(3, 3, 3))
    before = dict(document.blocks)
    choice = RoomCameraChoice("room_0", "corner", (1.5, 1.62, 1.5), (2.0, 1.5, 2.0), IntBoundingBox(IntVector3(1, 1, 1), IntVector3(2, 2, 2)), 1)
    hidden = cutaway_mask(document, choice, "cutaway")
    assert hidden
    assert document.blocks == before
