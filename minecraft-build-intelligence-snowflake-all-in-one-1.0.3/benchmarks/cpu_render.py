from __future__ import annotations

import argparse
import hashlib
import json
import time
from pathlib import Path

from mbi.canonical import BuildDocument, BuildRegion, BuildSource, IntBoundingBox, IntVector3, PaletteEntry

from app.assets import ResourcePackSource
from app.render import CameraSpec, SoftwareRenderer
from app.storage import atomic_write_json

try:
    import resource
except ModuleNotFoundError:  # Windows has no stdlib resource module.
    resource = None  # type: ignore[assignment]


def make_fixture(width: int = 24, height: int = 12, length: int = 24) -> BuildDocument:
    bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(width - 1, height - 1, length - 1))
    states = [
        "minecraft:air",
        "minecraft:stone_bricks",
        "minecraft:oak_planks",
        "minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]",
        "minecraft:glass",
        "minecraft:water[level=0]",
        "minecraft:oak_fence[east=false,north=false,south=false,waterlogged=false,west=false]",
        "minecraft:lantern[hanging=false,waterlogged=false]",
    ]
    palette = [PaletteEntry.from_state(index, state) for index, state in enumerate(states)]
    blocks: dict[IntVector3, int] = {}
    # Floor and bounded shell with windows.
    for x in range(width):
        for z in range(length):
            blocks[IntVector3(x, 0, z)] = 1
    for y in range(1, height - 2):
        for x in range(width):
            for z in (0, length - 1):
                blocks[IntVector3(x, y, z)] = 4 if y in {3, 4} and x % 4 in {1, 2} else 1
        for z in range(1, length - 1):
            for x in (0, width - 1):
                blocks[IntVector3(x, y, z)] = 4 if y in {3, 4} and z % 4 in {1, 2} else 1
    # Roof ridgeline and stair eaves.
    for x in range(width):
        for z in range(length):
            rise = min(z, length - 1 - z, 4)
            y = height - 3 + rise // 2
            if y < height:
                blocks[IntVector3(x, y, z)] = 3 if z in {0, length - 1} else 2
    # Interior supports, lights, water feature, and fences.
    for x in range(3, width - 3, 6):
        for z in range(3, length - 3, 6):
            for y in range(1, min(height - 2, 7)):
                blocks[IntVector3(x, y, z)] = 1
            blocks[IntVector3(x, min(height - 2, 7), z)] = 7
    for x in range(width // 2 - 2, width // 2 + 3):
        for z in range(length // 2 - 2, length // 2 + 3):
            blocks[IntVector3(x, 1, z)] = 5
    for x in range(2, width - 2):
        blocks[IntVector3(x, 1, 2)] = 6
    source_hash = hashlib.sha256(f"cpu-render:{width}:{height}:{length}".encode()).hexdigest()
    source = BuildSource("cpu-render-benchmark", "generated", "raw_nbt", source_hash, 0, 0, 3953, 1)
    region = BuildRegion(
        "Main", bounds.min, bounds.dimensions, bounds, tuple(item.canonical_state for item in palette)
    )
    return BuildDocument(
        "1.1.0",
        "bench_" + source_hash[:20],
        source,
        {},
        bounds,
        bounds.min,
        palette,
        [region],
        blocks,
        region_blocks={"Main": dict(blocks)},
    )


def timed(function):
    started = time.perf_counter()
    result = function()
    return result, time.perf_counter() - started


def max_rss_kib() -> int | None:
    if resource is None:
        return None
    return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource-pack", type=Path)
    parser.add_argument("--output-root", type=Path, default=Path("var/cpu-render-benchmark"))
    parser.add_argument(
        "--report", type=Path, default=Path("var/reports/snowflake-cpu-render-benchmark.json")
    )
    parser.add_argument("--size", default="512x512")
    args = parser.parse_args()
    size = tuple(int(value) for value in args.size.lower().split("x"))
    document = make_fixture()
    args.output_root.mkdir(parents=True, exist_ok=True)
    pack = ResourcePackSource(args.resource_pack) if args.resource_pack else None
    rss_before = max_rss_kib()
    try:
        renderer = SoftwareRenderer(document, resource_pack=pack)
        iso, iso_seconds = timed(
            lambda: renderer.render(
                args.output_root,
                camera=CameraSpec.preset("isometric_ne"),
                size=size,
                mode="textured" if pack else "flat",
                name="benchmark_iso",
            )
        )
        north, north_seconds = timed(
            lambda: renderer.render(
                args.output_root,
                camera=CameraSpec.preset("north"),
                size=size,
                mode="textured" if pack else "flat",
                name="benchmark_north",
            )
        )
        layer, layer_seconds = timed(
            lambda: renderer.render_slice(
                args.output_root,
                axis="y",
                minimum=1,
                pixels_per_block=8,
                mode="textured" if pack else "flat",
                name="benchmark_layer",
            )
        )
    finally:
        if pack:
            pack.close()
    rss_after = max_rss_kib()
    report = {
        "schema": "mbi.cpu-render-benchmark.v1",
        "passed": True,
        "gl_context_used": False,
        "renderer": "pure-python-numpy-pillow",
        "python_blocks": len(document.blocks),
        "resource_pack_hash": iso.manifest.get("resource_pack_hash"),
        "size": list(size),
        "max_rss_kib_before": rss_before,
        "max_rss_kib_after": rss_after,
        "max_rss_available": resource is not None,
        "renders": [
            {
                "name": "isometric",
                "seconds": iso_seconds,
                "png": str(iso.png_path),
                "diagnostics": iso.diagnostics,
            },
            {
                "name": "north",
                "seconds": north_seconds,
                "png": str(north.png_path),
                "diagnostics": north.diagnostics,
            },
            {
                "name": "layer_y_1",
                "seconds": layer_seconds,
                "png": str(layer.png_path),
                "diagnostics": layer.diagnostics,
            },
        ],
    }
    atomic_write_json(args.report, report)
    print(json.dumps(report, indent=2, default=str))


if __name__ == "__main__":
    main()
