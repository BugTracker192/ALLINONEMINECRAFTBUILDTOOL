from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mbi.canonical import IntBoundingBox, IntVector3

from app.assets import open_resource_pack
from app.project import load_document
from app.render.perspective import PerspectiveCameraSpec, PerspectiveRenderer
from app.storage import atomic_write_json

from .model import choose_room_camera, cutaway_mask, get_room, load_rooms, room_bounds


def render_room(
    run: str | Path,
    room_id: str,
    *,
    shot: str = "auto",
    resource_pack: str | Path | None = None,
    size: tuple[int, int] = (1280, 800),
    fov: float = 70.0,
    near: float = 0.05,
    far: float = 4096.0,
    eye_height: float = 1.62,
    lighting: str = "interior-soft",
    occlusion: str = "physical",
    out: str | Path | None = None,
    name: str | None = None,
) -> dict[str, Any]:
    root = Path(run)
    document = load_document(root)
    room = get_room(root, room_id)
    choice = choose_room_camera(document, room, shot=shot, eye_height=eye_height, fov=fov, near=near, far=far)
    camera = PerspectiveCameraSpec(position=choice.position, target=choice.target, vertical_fov_degrees=fov, near=near, far=far)
    hidden = cutaway_mask(document, choice, occlusion)
    bounds = choice.bounds
    crop = IntBoundingBox(
        IntVector3(bounds.min.x - 2, bounds.min.y - 2, bounds.min.z - 2),
        IntVector3(bounds.max.x + 2, bounds.max.y + 2, bounds.max.z + 2),
    )
    output = Path(out) if out else root
    pack = open_resource_pack(resource_pack)
    try:
        result = PerspectiveRenderer(document, resource_pack=pack).render(
            output,
            camera=camera,
            crop=crop,
            size=size,
            mode="textured",
            lighting_preset=lighting,
            hidden_coordinates=hidden,
            name=name or f"room_{choice.room_id}_{shot}_perspective",
        )
    finally:
        if pack:
            pack.close()
    return {
        "room_id": choice.room_id,
        "shot": shot,
        "projection": "perspective",
        "camera": asdict(camera),
        "candidate_count": choice.candidate_count,
        "room_bounds": {"min": list(bounds.min.as_tuple()), "max": list(bounds.max.as_tuple())},
        "crop_bounds": {"min": list(crop.min.as_tuple()), "max": list(crop.max.as_tuple())},
        "occlusion": occlusion,
        "hidden_coordinate_count": len(hidden),
        "png": str(result.png_path),
        "manifest": str(result.manifest_path),
        "snapshot_id": result.snapshot_id,
        "diagnostics": result.diagnostics,
    }


def render_gallery(
    run: str | Path,
    *,
    room_ids: Iterable[str] | None = None,
    shots: Iterable[str] = ("doorway", "corner", "feature"),
    resource_pack: str | Path | None = None,
    size: tuple[int, int] = (1280, 800),
    fov: float = 70.0,
    near: float = 0.05,
    eye_height: float = 1.62,
    lighting: str = "interior-soft",
    occlusion: str = "physical",
    out: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(run)
    destination = Path(out) if out else root / "interior-gallery"
    destination.mkdir(parents=True, exist_ok=True)
    rooms = load_rooms(root)
    selected = {str(value) for value in room_ids} if room_ids else None
    outputs: list[dict[str, Any]] = []
    for room in rooms:
        room_id = str(room.get("id", room.get("volume_id")))
        if selected is not None and room_id not in selected:
            continue
        for shot in shots:
            outputs.append(
                render_room(
                    root,
                    room_id,
                    shot=shot,
                    resource_pack=resource_pack,
                    size=size,
                    fov=fov,
                    near=near,
                    eye_height=eye_height,
                    lighting=lighting,
                    occlusion=occlusion,
                    out=destination,
                )
            )
    report = {
        "projection": "perspective",
        "room_count": len({item["room_id"] for item in outputs}),
        "render_count": len(outputs),
        "shots": list(shots),
        "outputs": outputs,
    }
    atomic_write_json(destination / "interior-gallery.json", report)
    return report
