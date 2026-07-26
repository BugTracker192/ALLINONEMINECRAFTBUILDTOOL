from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict
from pathlib import Path

import numpy as np
from PIL import Image

from app.assets import ResourcePackSource
from app.render import CameraSpec, SoftwareRenderer, pixel_to_block
from app.render.semantic import load_map
from mbi.canonical import BuildDocument, BuildRegion, BuildSource, IntBoundingBox, IntVector3, PaletteEntry


def document_for_models() -> BuildDocument:
    states = [
        "minecraft:stone",
        "minecraft:oak_slab[type=bottom,waterlogged=false]",
        "minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]",
        "minecraft:glass",
        "minecraft:oak_fence[east=false,north=false,south=false,waterlogged=false,west=false]",
        "minecraft:oak_door[facing=north,half=lower,hinge=left,open=false,powered=false]",
        "minecraft:oak_trapdoor[facing=north,half=bottom,open=false,powered=false,waterlogged=false]",
        "minecraft:iron_bars[east=false,north=false,south=false,waterlogged=false,west=false]",
        "minecraft:rail[shape=north_south,waterlogged=false]",
        "minecraft:redstone_wire[east=none,north=none,power=15,south=none,west=none]",
        "minecraft:water[level=0]",
        "minecraft:white_bed[facing=north,occupied=false,part=foot]",
        "minecraft:oak_sign[rotation=0,waterlogged=false]",
    ]
    palette = [PaletteEntry.from_state(0, "minecraft:air")] + [PaletteEntry.from_state(i + 1, state) for i, state in enumerate(states)]
    positions: dict[IntVector3, int] = {}
    for index, _ in enumerate(states, start=1):
        positions[IntVector3((index - 1) % 5 * 2, (index - 1) // 10 * 2, (index - 1) // 5 * 2)] = index
    bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(8, 3, 4))
    source = BuildSource("dynamic-models", "generated", "raw_nbt", hashlib.sha256(b"dynamic-models").hexdigest(), 0, 0, 3953, 1)
    region = BuildRegion("Models", bounds.min, bounds.dimensions, bounds, tuple(item.canonical_state for item in palette))
    return BuildDocument("1.1.0", "dynamic_models", source, {"Name": "CPU model coverage"}, bounds, bounds.min, palette, [region], positions, region_blocks={"Models": dict(positions)})


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: dynamic_cpu_models.py <resource-pack.zip> <output-dir>", file=sys.stderr)
        return 2
    pack_path, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    document = document_for_models()
    with ResourcePackSource(pack_path) as pack:
        renderer = SoftwareRenderer(document, resource_pack=pack, strict_textures=True)
        results = []
        for name in ("isometric_ne", "north", "top"):
            result = renderer.render(out, camera=CameraSpec.preset(name), size=(768, 768), mode="textured", name=f"models_{name}")
            results.append(result)
    checks = []
    for result in results:
        image = np.asarray(Image.open(result.png_path).convert("RGBA"))
        coordinates = load_map(result.semantic_metadata_path, "coordinate")
        palette = load_map(result.semantic_metadata_path, "palette")
        occupied = image[..., 3] > 0
        unique_palette = sorted(int(item) for item in np.unique(palette[palette != np.iinfo(np.uint32).max]))
        ys, xs = np.where(occupied)
        if not len(xs):
            raise AssertionError(f"{result.png_path} was empty")
        hit = pixel_to_block(result.manifest_path, int(xs[len(xs)//2]), int(ys[len(ys)//2]))
        checks.append({
            "snapshot": result.snapshot_id,
            "png": str(result.png_path),
            "opaque_pixels": int(occupied.sum()),
            "unique_palette_ids": unique_palette,
            "fallback_count": result.diagnostics["fallback_count"],
            "triangles": result.diagnostics["triangles_rasterized"],
            "sample_hit": hit,
            "png_sha256": hashlib.sha256(result.png_path.read_bytes()).hexdigest(),
            "coordinate_map_populated": bool(np.any(coordinates[..., 0] != np.iinfo(np.int32).min)),
        })
        unexpected_fallbacks = [
            item for item in result.diagnostics["fallbacks"]
            if item.get("type") != "animated_texture_first_frame"
        ]
        if unexpected_fallbacks or result.diagnostics["unsupported_models"]:
            raise AssertionError(json.dumps(result.diagnostics, indent=2, default=str))
        checks[-1]["accepted_animated_texture_fallbacks"] = sum(
            1 for item in result.diagnostics["fallbacks"]
            if item.get("type") == "animated_texture_first_frame"
        )
        if not checks[-1]["coordinate_map_populated"]:
            raise AssertionError("coordinate map was empty")
    report = {
        "passed": True,
        "renderer": "pure-python-numpy-pillow",
        "gl_context_used": False,
        "resource_pack_sha256": hashlib.sha256(pack_path.read_bytes()).hexdigest(),
        "states": [entry.canonical_state for entry in document.palette[1:]],
        "checks": checks,
    }
    (out / "dynamic_cpu_models.json").write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", "utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
