from __future__ import annotations

import contextlib
import csv
import io
import json
import math
from collections import Counter, deque
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
from mbi.analysis.structures import classify_block_name
from mbi.canonical import BuildDocument, IntVector3
from mbi.snapshot.raster import palette_color
from PIL import Image, ImageDraw, ImageFont

from app.assets import ResourcePackSource, open_resource_pack
from app.errors import AppError
from app.project import load_document
from app.render import CameraSpec, SoftwareRenderer
from app.render.semantic import NO_PALETTE, load_map
from app.storage import atomic_write_bytes, atomic_write_json

_ENTITY_SUFFIXES = (
    "_banner",
    "_bed",
    "_head",
    "_shulker_box",
    "_sign",
    "_skull",
    "_wall_banner",
    "_wall_head",
    "_wall_sign",
    "_wall_skull",
)
_NEIGHBORS = (
    IntVector3(1, 0, 0),
    IntVector3(-1, 0, 0),
    IntVector3(0, 1, 0),
    IntVector3(0, -1, 0),
    IntVector3(0, 0, 1),
    IntVector3(0, 0, -1),
)


def _entity_rendered(block_name: str) -> bool:
    return (
        block_name == "shulker_box"
        or block_name.endswith(_ENTITY_SUFFIXES)
    )


def _entity_texture_paths(block_name: str) -> list[str]:
    if block_name.endswith("_banner"):
        return ["minecraft:entity/banner/base"]
    if block_name.endswith(("_skull", "_head")):
        kind = block_name
        for suffix in ("_wall_skull", "_wall_head", "_skull", "_head"):
            if kind.endswith(suffix):
                kind = kind[: -len(suffix)]
                break
        return [
            "minecraft:"
            + {
                "skeleton": "entity/skeleton/skeleton",
                "wither_skeleton": "entity/skeleton/wither_skeleton",
                "zombie": "entity/zombie/zombie",
                "creeper": "entity/creeper/creeper",
                "piglin": "entity/piglin/piglin",
                "dragon": "entity/enderdragon/dragon",
                "player": "entity/player/wide/steve",
            }.get(kind, "entity/skeleton/skeleton")
        ]
    if block_name == "shulker_box" or block_name.endswith("_shulker_box"):
        color = (
            ""
            if block_name == "shulker_box"
            else block_name.removesuffix("_shulker_box")
        )
        suffix = f"_{color}" if color else ""
        return [f"minecraft:entity/shulker/shulker{suffix}"]
    if block_name.endswith("_bed"):
        return [
            "minecraft:entity/bed/"
            + block_name.removesuffix("_bed")
        ]
    if block_name.endswith("_sign"):
        wood = block_name
        for suffix in (
            "_wall_hanging_sign",
            "_hanging_sign",
            "_wall_sign",
            "_sign",
        ):
            if wood.endswith(suffix):
                wood = wood[: -len(suffix)]
                break
        return [f"minecraft:entity/signs/{wood}"]
    return []


def _asset_rows(
    document: BuildDocument,
    pack: ResourcePackSource | None,
) -> dict[str, dict[str, Any]]:
    rows: dict[str, dict[str, Any]] = {}
    for entry in document.palette:
        if entry.is_air_like:
            continue
        item: dict[str, Any] = {
            "canonical_state": entry.canonical_state,
            "models": [],
            "textures": [],
            "status": "flat-no-resource-pack" if pack is None else "resolved",
            "reason": None,
        }
        if pack is not None:
            try:
                instances = pack.select_models(entry.canonical_state, (0, 0, 0), 0)
                item["models"] = [instance.model for instance in instances]
                texture_refs = set()
                static = False
                for instance in instances:
                    model = pack.resolve_model(instance.model)
                    static |= bool(model.elements)
                    for value in model.textures.values():
                        try:
                            namespace, path = pack.resolve_texture_ref(
                                model.textures, value, entry.namespace
                            )
                            texture_refs.add(f"{namespace}:{path}")
                        except AppError:
                            continue
                item["textures"] = sorted(texture_refs)
                if not static and _entity_rendered(entry.block_name):
                    entity_textures = _entity_texture_paths(
                        entry.block_name
                    )
                    for texture in entity_textures:
                        namespace, resource = texture.split(":", 1)
                        pack.texture(namespace, resource)
                    if entity_textures:
                        item["textures"] = entity_textures
                        item["status"] = "entity-rendered"
                        item["reason"] = "ENTITY_TEXTURE_RENDERED"
                        item["entity_texture_supported"] = True
                    else:
                        item["status"] = "unresolved"
                        item["reason"] = "ENTITY_TEXTURE_MAPPING_MISSING"
                elif not static:
                    item["status"] = "unresolved"
                    item["reason"] = "MODEL_NO_ELEMENTS"
            except Exception as exc:
                item["status"] = "unresolved"
                item["reason"] = str(exc)
        rows[entry.canonical_state] = item
    return rows


def texture_audit(
    run: str | Path,
    *,
    resource_pack: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(run)
    document = load_document(root)
    counts = Counter(entry.canonical_state for _, entry in document.iter_non_air())
    pack = open_resource_pack(resource_pack)
    try:
        states = _asset_rows(document, pack)
        rows = []
        resolved_blocks = entity_blocks = failed_blocks = 0
        for state, count in counts.most_common():
            item = {**states[state], "placed_count": count}
            rows.append(item)
            if item["status"] == "resolved":
                resolved_blocks += count
            elif item["status"] == "entity-rendered":
                entity_blocks += count
            else:
                failed_blocks += count
        total = sum(counts.values())
        report = {
            "schema": "mbi.texture-audit.v1",
            "content_hash": document.content_hash,
            "resource_pack_hash": pack.pack_hash if pack else None,
            "state_count": len(counts),
            "resolved_state_count": sum(item["status"] == "resolved" for item in rows),
            "entity_rendered_state_count": sum(
                item["status"] == "entity-rendered" for item in rows
            ),
            "failed_state_count": sum(item["status"] == "unresolved" for item in rows),
            "placed_block_count": total,
            "static_textured_block_count": resolved_blocks,
            "entity_rendered_block_count": entity_blocks,
            "entity_textured_block_count": entity_blocks,
            "failed_block_count": failed_blocks,
            "static_texture_coverage_percent": round(
                resolved_blocks / max(1, total) * 100.0, 6
            ),
            "accounted_coverage_percent": round(
                (resolved_blocks + entity_blocks) / max(1, total) * 100.0, 6
            ),
            "texture_coverage_percent": round(
                (resolved_blocks + entity_blocks) / max(1, total) * 100.0,
                6,
            ),
            "states": rows,
            "asset_diagnostics": list(pack.diagnostics) if pack else [],
        }
    finally:
        if pack:
            pack.close()
    atomic_write_json(root / "texture_audit.json", report)
    return report


def _component_labels(document: BuildDocument) -> dict[IntVector3, int]:
    solid = {point for point, _ in document.iter_non_air()}
    unseen = set(solid)
    labels: dict[IntVector3, int] = {}
    component = 0
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        queue = deque([start])
        while queue:
            point = queue.popleft()
            labels[point] = component
            for offset in _NEIGHBORS:
                neighbor = point + offset
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
        component += 1
    return labels


def export_block_map(
    run: str | Path,
    output: str | Path,
    *,
    format_name: str = "csv",
    resource_pack: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(run)
    destination = Path(output)
    document = load_document(root)
    palette = document.palette_by_id()
    pack = open_resource_pack(resource_pack)
    try:
        assets = _asset_rows(document, pack)
    finally:
        if pack:
            pack.close()
    components = _component_labels(document)
    region_by_point: dict[IntVector3, list[str]] = {}
    for name, blocks in document.region_blocks.items():
        for point in blocks:
            region_by_point.setdefault(point, []).append(name)
    analysis_path = root / "analysis.json"
    rooms = []
    if analysis_path.is_file():
        analysis = json.loads(analysis_path.read_text("utf-8"))
        rooms = analysis.get("results", {}).get("rooms", {}).get("rooms", [])
    fields = (
        "x",
        "y",
        "z",
        "palette_id",
        "canonical_state",
        "textures",
        "models",
        "status",
        "region",
        "component",
        "room",
        "classification",
    )
    records = []
    for point, palette_id in sorted(document.blocks.items()):
        entry = palette[palette_id]
        if entry.is_air_like:
            continue
        room_ids = [
            str(item.get("volume_id", item.get("id")))
            for item in rooms
            if (
                item["bounds"]["min"]["x"] - 1
                <= point.x
                <= item["bounds"]["max"]["x"] + 1
                and item["bounds"]["min"]["y"] - 1
                <= point.y
                <= item["bounds"]["max"]["y"] + 1
                and item["bounds"]["min"]["z"] - 1
                <= point.z
                <= item["bounds"]["max"]["z"] + 1
            )
        ]
        asset = assets[entry.canonical_state]
        records.append(
            {
                "x": point.x,
                "y": point.y,
                "z": point.z,
                "palette_id": palette_id,
                "canonical_state": entry.canonical_state,
                "textures": "|".join(asset["textures"]),
                "models": "|".join(asset["models"]),
                "status": asset["status"],
                "region": "|".join(sorted(region_by_point.get(point, ()))),
                "component": components.get(point),
                "room": "|".join(room_ids),
                "classification": classify_block_name(entry.block_name),
            }
        )
    if format_name == "csv":
        buffer = io.StringIO(newline="")
        writer = csv.DictWriter(buffer, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows(records)
        atomic_write_bytes(destination, buffer.getvalue().encode("utf-8"))
    elif format_name in {"json", "jsonl"}:
        payload = "".join(
            json.dumps(record, sort_keys=True, separators=(",", ":")) + "\n"
            for record in records
        )
        atomic_write_bytes(destination, payload.encode("utf-8"))
    elif format_name == "parquet":
        raise AppError(
            "PARQUET_ENGINE_UNAVAILABLE",
            "Parquet export requires an optional pyarrow installation; CSV and JSONL are dependency-free.",
            {"suggestion": "Use --format csv or install pyarrow in a connected environment."},
            2,
        )
    else:
        raise AppError("EXPORT_MAP_FORMAT", "Unsupported export-map format.", exit_code=2)
    manifest = {
        "schema": "mbi.block-map.v1",
        "content_hash": document.content_hash,
        "format": format_name,
        "path": str(destination),
        "row_count": len(records),
        "columns": fields,
        "coordinate_space": "document",
    }
    atomic_write_json(destination.with_suffix(destination.suffix + ".manifest.json"), manifest)
    return manifest


def _montage(
    items: list[tuple[str, Path]],
    output: Path,
    *,
    columns: int = 3,
) -> dict[str, Any]:
    if not items:
        raise AppError("MONTAGE_EMPTY", "No images were available for the montage.", exit_code=30)
    images = [(label, Image.open(path).convert("RGBA")) for label, path in items]
    tile_width = max(image.width for _, image in images)
    tile_height = max(image.height for _, image in images)
    label_height = 22
    columns = max(1, min(columns, len(images)))
    rows = math.ceil(len(images) / columns)
    canvas = Image.new(
        "RGBA",
        (columns * tile_width, rows * (tile_height + label_height)),
        (20, 22, 25, 255),
    )
    draw = ImageDraw.Draw(canvas)
    font = ImageFont.load_default()
    for index, (label, image) in enumerate(images):
        column = index % columns
        row = index // columns
        x = column * tile_width + (tile_width - image.width) // 2
        y = row * (tile_height + label_height) + label_height
        canvas.alpha_composite(image, (x, y))
        draw.text(
            (column * tile_width + 6, row * (tile_height + label_height) + 5),
            label,
            fill=(255, 255, 255, 255),
            font=font,
        )
    output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output, "PNG", compress_level=9)
    return {
        "png": str(output),
        "resolution": list(canvas.size),
        "item_count": len(items),
        "items": [{"label": label, "path": str(path)} for label, path in items],
    }


def contact_sheet(
    run: str | Path,
    *,
    views: Iterable[str],
    slices: Iterable[str] = (),
    output: str | Path,
    resource_pack: str | Path | None = None,
    size: tuple[int, int] = (480, 320),
    accuracy: str = "exact",
    resume: bool = False,
    columns: int = 3,
) -> dict[str, Any]:
    root = Path(run)
    batch = root / "visual_batches" / Path(output).stem
    document = load_document(root)
    pack = open_resource_pack(resource_pack) if accuracy == "exact" else None
    items: list[tuple[str, Path]] = []
    try:
        renderer = SoftwareRenderer(document, resource_pack=pack)
        for view in views:
            name = f"view_{view}"
            expected = batch / "snapshots" / f"{name}.png"
            if not (resume and expected.is_file()):
                renderer.render(
                    batch,
                    camera=CameraSpec.preset(view),
                    size=size,
                    mode="textured" if pack else "flat",
                    name=name,
                )
            items.append((view, expected))
        for spec in slices:
            axis, value = spec.split(":", 1)
            minimum, maximum = (
                (int(item) for item in value.split("..", 1))
                if ".." in value
                else (int(value), int(value))
            )
            name = f"slice_{axis}_{minimum}_{maximum}"
            expected = batch / "snapshots" / f"{name}.png"
            if not (resume and expected.is_file()):
                renderer.render_slice(
                    batch,
                    axis=axis,
                    minimum=minimum,
                    maximum=maximum,
                    pixels_per_block=4,
                    mode="textured" if pack else "flat",
                    name=name,
                )
            items.append((spec, expected))
    finally:
        if pack:
            pack.close()
    report = _montage(items, Path(output), columns=columns)
    report.update(
        {
            "schema": "mbi.contact-sheet.v1",
            "accuracy": {
                "profile": accuracy,
                "texture_exact": accuracy == "exact",
                "contract": (
                    "full resource-pack blockstate/model/texture resolution"
                    if accuracy == "exact"
                    else "palette-color geometry preview; not texture-exact"
                ),
            },
            "resume": resume,
        }
    )
    atomic_write_json(Path(output).with_suffix(".manifest.json"), report)
    return report


def slice_sweep(
    run: str | Path,
    *,
    axis: str,
    minimum: int,
    maximum: int,
    step: int,
    output: str | Path,
    resource_pack: str | Path | None = None,
    resume: bool = False,
    montage: bool = True,
) -> dict[str, Any]:
    if step <= 0:
        raise AppError("SLICE_STEP", "Slice sweep step must be positive.", exit_code=2)
    root = Path(run)
    batch = root / "visual_batches" / Path(output).stem
    document = load_document(root)
    pack = open_resource_pack(resource_pack)
    items = []
    try:
        renderer = SoftwareRenderer(document, resource_pack=pack)
        for coordinate in range(minimum, maximum + 1, step):
            name = f"slice_{axis}_{coordinate}"
            expected = batch / "snapshots" / f"{name}.png"
            if not (resume and expected.is_file()):
                renderer.render_slice(
                    batch,
                    axis=axis,
                    minimum=coordinate,
                    pixels_per_block=4,
                    mode="textured" if pack else "flat",
                    name=name,
                )
            items.append((f"{axis}={coordinate}", expected))
    finally:
        if pack:
            pack.close()
    report: dict[str, Any] = {
        "schema": "mbi.slice-sweep.v1",
        "axis": axis,
        "range": [minimum, maximum],
        "step": step,
        "slices": [{"label": label, "png": str(path)} for label, path in items],
        "resume": resume,
    }
    if montage:
        report["montage"] = _montage(items, Path(output), columns=3)
    atomic_write_json(Path(output).with_suffix(".manifest.json"), report)
    return report


def palette_atlas(
    run: str | Path,
    output: str | Path,
    *,
    resource_pack: str | Path | None = None,
    columns: int = 5,
    swatch_size: int = 48,
) -> dict[str, Any]:
    document = load_document(run)
    pack = open_resource_pack(resource_pack)
    entries = [entry for entry in document.palette if not entry.is_air_like]
    rows = math.ceil(len(entries) / columns)
    cell_width = 260
    cell_height = max(64, swatch_size + 12)
    image = Image.new(
        "RGBA",
        (cell_width * columns, cell_height * rows),
        (24, 26, 30, 255),
    )
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    assets = _asset_rows(document, pack)
    cells = []
    try:
        for index, entry in enumerate(entries):
            column, row = index % columns, index // columns
            x, y = column * cell_width, row * cell_height
            swatch = Image.new("RGBA", (swatch_size, swatch_size), palette_color(entry.palette_id))
            asset = assets[entry.canonical_state]
            if pack and asset["textures"]:
                namespace, path = asset["textures"][0].split(":", 1)
                with contextlib.suppress(Exception):
                    swatch = pack.texture(namespace, path).resize(
                        (swatch_size, swatch_size), Image.Resampling.NEAREST
                    )
            image.alpha_composite(swatch, (x + 6, y + 6))
            label = entry.canonical_state
            shortened = label if len(label) <= 31 else label[:28] + "..."
            draw.text((x + swatch_size + 12, y + 8), shortened, fill="white", font=font)
            draw.text(
                (x + swatch_size + 12, y + 25),
                asset["status"],
                fill=(150, 220, 160, 255)
                if asset["status"] == "resolved"
                else (255, 190, 90, 255),
                font=font,
            )
            cells.append(
                {
                    "state": entry.canonical_state,
                    "status": asset["status"],
                    "cell": [x, y, cell_width, cell_height],
                    "textures": asset["textures"],
                }
            )
    finally:
        if pack:
            pack.close()
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "PNG", compress_level=9)
    report = {
        "schema": "mbi.palette-atlas.v1",
        "png": str(destination),
        "state_count": len(entries),
        "resolution": list(image.size),
        "cells": cells,
    }
    atomic_write_json(destination.with_suffix(".manifest.json"), report)
    return report


def annotated_render(
    run: str | Path,
    *,
    output: str | Path,
    view: str = "isometric_ne",
    resource_pack: str | Path | None = None,
    size: tuple[int, int] = (1280, 800),
    annotate_materials: int = 8,
) -> dict[str, Any]:
    root = Path(run)
    working = root / "visual_batches" / Path(output).stem
    document = load_document(root)
    pack = open_resource_pack(resource_pack)
    try:
        result = SoftwareRenderer(document, resource_pack=pack).render(
            working,
            camera=CameraSpec.preset(view),
            size=size,
            mode="textured" if pack else "flat",
            name="annotated_source",
        )
    finally:
        if pack:
            pack.close()
    image = Image.open(result.png_path).convert("RGBA")
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()
    draw.rectangle((8, 8, 150, 54), fill=(0, 0, 0, 180))
    draw.text((16, 15), f"VIEW {view}", fill="white", font=font)
    draw.text((16, 33), "N ↑   +X →   +Z ↓", fill=(255, 220, 80, 255), font=font)
    palette_map = load_map(result.semantic_metadata_path, "palette")
    visible_counts = Counter(
        int(value) for value in palette_map.ravel() if int(value) != int(NO_PALETTE)
    )
    palette = document.palette_by_id()
    labels = []
    for index, (palette_id, _) in enumerate(
        visible_counts.most_common(max(0, annotate_materials))
    ):
        locations = np.argwhere(palette_map == palette_id)
        if locations.size == 0:
            continue
        py, px = (int(value) for value in locations[len(locations) // 2])
        label = palette[palette_id].canonical_state.split("[", 1)[0]
        text_x, text_y = 12, 72 + index * 18
        draw.line((text_x + 165, text_y + 5, px, py), fill=(255, 220, 80, 220), width=1)
        draw.rectangle((text_x, text_y - 2, text_x + 165, text_y + 14), fill=(0, 0, 0, 170))
        draw.text((text_x + 4, text_y), label[:25], fill="white", font=font)
        labels.append({"state": label, "pixel": [px, py]})
    destination = Path(output)
    destination.parent.mkdir(parents=True, exist_ok=True)
    image.save(destination, "PNG", compress_level=9)
    report = {
        "schema": "mbi.annotated-render.v1",
        "png": str(destination),
        "source_manifest": str(result.manifest_path),
        "view": view,
        "compass": True,
        "axis_ticks": True,
        "material_labels": labels,
    }
    atomic_write_json(destination.with_suffix(".manifest.json"), report)
    return report
