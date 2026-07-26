from __future__ import annotations

import argparse
import hashlib
import json
import random
import time
import resource
import tracemalloc
from dataclasses import asdict
from pathlib import Path

from mbi.analysis import analyze_document
from mbi.canonical import BuildDocument, BuildRegion, BuildSource, IntBoundingBox, IntVector3, PaletteEntry
from mbi.chunking import build_chunks
from mbi.export import export_litematic, export_sponge_v3, verify_round_trip
from mbi.importer import import_build
from mbi.patch import PatchEngine
from mbi.snapshot import render_global_snapshot


def make_document(size: int, density: float, seed: int) -> BuildDocument:
    randomizer = random.Random(seed)
    bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(size - 1, size - 1, size - 1))
    palette = [
        PaletteEntry.from_state(0, "minecraft:air"), PaletteEntry.from_state(1, "minecraft:stone"),
        PaletteEntry.from_state(2, "minecraft:glass"), PaletteEntry.from_state(3, "minecraft:oak_stairs[facing=north,half=bottom,shape=straight,waterlogged=false]"),
    ]
    blocks = {point: randomizer.choice((1, 2, 3)) for point in bounds.iter_points() if randomizer.random() < density}
    source_hash = hashlib.sha256(f"{size}:{density}:{seed}".encode()).hexdigest()
    source = BuildSource("benchmark", "generated", "raw_nbt", source_hash, 0, 0, 3953, 1)
    region = BuildRegion("Main", bounds.min, bounds.dimensions, bounds, tuple(p.canonical_state for p in palette))
    return BuildDocument("1.1.0", "bench_" + source_hash[:12], source, {}, bounds, bounds.min, palette, [region], blocks, region_blocks={"Main": dict(blocks)})


def timed(label, function):
    start = time.perf_counter()
    value = function()
    return value, {"name": label, "seconds": time.perf_counter() - start}


def run_case(size: int, density: float, *, trace_allocations: bool = False) -> dict[str, object]:
    document = make_document(size, density, 42)
    if trace_allocations:
        tracemalloc.start()
    rss_before = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    timings = []
    chunks, measurement = timed("chunking", lambda: build_chunks(document)); timings.append(measurement)
    analysis, measurement = timed("analysis", lambda: analyze_document(document)); timings.append(measurement)
    snapshot, measurement = timed("snapshot_north", lambda: render_global_snapshot(document, "north", pixels_per_block=1)); timings.append(measurement)
    schem, measurement = timed("export_schem", lambda: export_sponge_v3(document)); timings.append(measurement)
    _, measurement = timed("import_schem", lambda: import_build(schem, "benchmark.schem")); timings.append(measurement)
    litematic, measurement = timed("export_litematic", lambda: export_litematic(document)); timings.append(measurement)
    report, measurement = timed("verify_litematic", lambda: verify_round_trip(document, litematic, "benchmark.litematic")); timings.append(measurement)
    engine = PatchEngine(document)
    point = bounds_center(document.bounds)
    def patch():
        operation = engine.create_patch("benchmark", "benchmark", IntBoundingBox(point, point), 1, [{"type": "set_block", "position": list(point.as_tuple()), "state": "minecraft:diamond_block"}])
        engine.validate(operation); engine.preview(operation); engine.commit(operation); engine.undo()
    _, measurement = timed("patch_commit_undo", patch); timings.append(measurement)
    if trace_allocations:
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
    else:
        current = peak = 0
    rss_after = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return {
        "size": size, "volume": document.bounds.volume, "density": density, "nonAir": len(document.blocks),
        "chunkCount": len(chunks), "snapshotBytes": len(snapshot.color_png), "schemBytes": len(schem), "litematicBytes": len(litematic),
        "roundTripValid": report.valid, "analysisSkipped": {key: value.get("analysisSkipped", False) for key, value in analysis.items() if isinstance(value, dict)},
        "timings": timings, "peakPythonBytes": peak, "currentPythonBytes": current,
        "maxRssKiBBefore": rss_before, "maxRssKiBAfter": rss_after,
        "allocationTracingEnabled": trace_allocations,
    }


def bounds_center(bounds: IntBoundingBox) -> IntVector3:
    return IntVector3((bounds.min.x + bounds.max.x) // 2, (bounds.min.y + bounds.max.y) // 2, (bounds.min.z + bounds.max.z) // 2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--tracemalloc", action="store_true", help="Enable expensive Python allocation tracing.")
    args = parser.parse_args()
    cases = [(16, 0.35), (32, 0.08)] if args.quick else [(16, 0.35), (32, 0.10), (64, 0.02), (96, 0.005)]
    results = [run_case(size, density, trace_allocations=args.tracemalloc) for size, density in cases]
    output = {"schemaVersion": 1, "cases": results, "totalSeconds": sum(item["seconds"] for result in results for item in result["timings"])}
    text = json.dumps(output, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text, "utf-8")
    print(text)


if __name__ == "__main__":
    main()
