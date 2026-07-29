from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mbi.canonical import IntBoundingBox, IntVector3
from mbi.chunking import CHUNK_SIZE, build_chunks

from app.errors import AppError
from app.project import clone_run_base, load_document, parse_box, parse_vec
from app.render import CameraSpec, SoftwareRenderer, block_to_pixel, pixel_to_block
from app.storage import atomic_write_json
from app.workflows import (
    analyze_run,
    apply_build_plan,
    create_build_plan,
    export_run,
    import_file,
    patch_action,
    pipeline,
    rollback_patch,
    snapshot_run,
)


def _size(value: str) -> tuple[int, int]:
    separator = "x" if "x" in value.lower() else ","
    values = [int(item) for item in value.lower().split(separator)]
    if len(values) != 2:
        raise argparse.ArgumentTypeError("size must be WIDTHxHEIGHT")
    return values[0], values[1]


def _inclusive_bounds(value: str) -> IntBoundingBox:
    values = [int(item.strip()) for item in value.split(",")]
    if len(values) != 6:
        raise argparse.ArgumentTypeError(
            "bounds must be X1,Y1,Z1,X2,Y2,Z2 (inclusive)"
        )
    return IntBoundingBox(IntVector3(*values[:3]), IntVector3(*values[3:]))


def _int_vector(value: str) -> IntVector3:
    values = [int(item.strip()) for item in value.split(",")]
    if len(values) != 3:
        raise argparse.ArgumentTypeError("coordinate must be X,Y,Z")
    return IntVector3(*values)


def _json(value: Any) -> None:
    print(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str))


def _query(args: argparse.Namespace) -> Any:
    document = load_document(args.run)
    if args.query_command == "block":
        position = IntVector3(args.x, args.y, args.z)
        entry = document.state_at(position)
        block_entity = next((item for item in document.block_entities if item.position == position), None)
        return {
            "coordinate_space": "document",
            "position": list(position.as_tuple()),
            "palette_id": document.blocks.get(position),
            "state": asdict(entry),
            "block_entity": asdict(block_entity) if block_entity else None,
        }
    if args.query_command == "box":
        bounds = parse_box(args.minimum, args.maximum)
        palette = document.palette_by_id()
        items = [
            {"position": list(position.as_tuple()), "palette_id": pid, "state": palette[pid].canonical_state}
            for position, pid in sorted(document.blocks.items())
            if bounds.contains(position)
        ]
        return {"coordinate_space": "document", "bounds": asdict(bounds), "items": items}
    if args.query_command == "palette":
        return {"palette": [asdict(item) for item in document.palette]}
    if args.query_command == "chunk":
        chunk = IntVector3(args.cx, args.cy, args.cz)
        blob = next((item for item in build_chunks(document) if item.coordinate == chunk), None)
        minimum = IntVector3(chunk.x * CHUNK_SIZE, chunk.y * CHUNK_SIZE, chunk.z * CHUNK_SIZE)
        maximum = IntVector3(minimum.x + CHUNK_SIZE - 1, minimum.y + CHUNK_SIZE - 1, minimum.z + CHUNK_SIZE - 1)
        palette = document.palette_by_id()
        blocks = [
            {"position": list(position.as_tuple()), "palette_id": palette_id, "state": palette[palette_id].canonical_state}
            for position, palette_id in sorted(document.blocks.items())
            if minimum.x <= position.x <= maximum.x and minimum.y <= position.y <= maximum.y and minimum.z <= position.z <= maximum.z
        ]
        metadata = (
            {
                "encoding": blob.encoding.value,
                "content_hash": blob.content_hash,
                "non_air_count": blob.non_air_count,
                "material_histogram": blob.material_histogram,
                "byte_length": len(blob.data),
            }
            if blob
            else {
                "encoding": "single-air",
                "content_hash": None,
                "non_air_count": 0,
                "material_histogram": {},
                "byte_length": 0,
            }
        )
        return {
            "coordinate_space": "document",
            "chunk": list(chunk.as_tuple()),
            "bounds": {"min": list(minimum.as_tuple()), "max": list(maximum.as_tuple())},
            "metadata": metadata,
            "blocks": blocks,
        }
    if args.query_command == "block-entity":
        position = IntVector3(args.x, args.y, args.z)
        block_entity = next((item for item in document.block_entities if item.position == position), None)
        return {
            "coordinate_space": "document",
            "position": list(position.as_tuple()),
            "block_entity": asdict(block_entity) if block_entity else None,
        }
    if args.query_command == "region":
        region = next((item for item in document.regions if item.name == args.name), None)
        if region is None:
            raise AppError("REGION_NOT_FOUND", "Region was not found.", {"name": args.name}, 20)
        values = document.region_blocks.get(region.name, {})
        return {"region": asdict(region), "voxel_count": len(values)}
    analysis_path = Path(args.run) / "analysis.json"
    if not analysis_path.exists():
        analyze_run(args.run)
    analysis = json.loads(analysis_path.read_text("utf-8"))["results"]
    if args.query_command == "room":
        rooms = analysis["rooms"].get("rooms", analysis["rooms"].get("interiorVolumes", []))
        room = next((item for item in rooms if str(item.get("id")) == args.id), None)
        if room is None:
            raise AppError("ROOM_NOT_FOUND", "Room was not found.", {"id": args.id}, 20)
        return room
    if args.query_command == "issues":
        key_map = {
            "unsupported": "support",
            "support": "support",
            "navigation": "navigation",
            "facade": "facade",
            "consistency": "interiorExterior",
            "lighting": "lighting",
        }
        key = key_map.get(args.type, args.type)
        return {"type": args.type, "result": analysis.get(key)}
    raise AppError("QUERY_COMMAND", "Unknown query command.", exit_code=2)


def _render(args: argparse.Namespace) -> Any:
    from app.assets import open_resource_pack

    document = load_document(args.run)
    pack = (
        open_resource_pack(args.resource_pack)
        if args.accuracy == "exact"
        else None
    )
    effective_mode = "flat" if args.accuracy == "fast" else args.mode
    try:
        renderer = SoftwareRenderer(document, resource_pack=pack, strict_textures=args.strict_textures, seed=args.seed)
        if args.slice:
            axis, spec = args.slice.split(":", 1)
            if ".." in spec:
                minimum, maximum = [int(value) for value in spec.split("..", 1)]
            else:
                minimum = maximum = int(spec)
            result = renderer.render_slice(
                args.out or args.run,
                axis=axis,
                minimum=minimum,
                maximum=maximum,
                pixels_per_block=args.pixels_per_block,
                mode=effective_mode,
                include_regions=tuple(args.region or ()),
                include_states=tuple(args.material or ()),
                exclude_states=tuple(args.hide_material or ()),
                name=args.name,
            )
        else:
            crop = None
            if args.crop:
                values = [int(item) for item in args.crop.split(",")]
                if len(values) != 6:
                    raise AppError("CROP_SPEC", "Crop must contain x,y,z,width,height,length.", exit_code=2)
                x, y, z, width, height, length = values
                crop = IntBoundingBox(IntVector3(x, y, z), IntVector3(x + width - 1, y + height - 1, z + length - 1))
            if args.view:
                camera = CameraSpec.preset(args.view)
                camera = CameraSpec(
                    camera.azimuth_degrees,
                    camera.elevation_degrees,
                    args.camera_roll,
                    args.zoom,
                    None,
                    args.fit,
                    args.margin,
                )
            else:
                camera = CameraSpec(
                    args.camera_azimuth,
                    args.camera_elevation,
                    args.camera_roll,
                    args.zoom,
                    None,
                    args.fit,
                    args.margin,
                )
            render_method = (
                renderer.render_tiled
                if args.tile_size
                else renderer.render
            )
            render_options = {
                "camera": camera,
                "crop": crop,
                "size": args.size,
                "mode": effective_mode,
                "lighting_preset": args.lighting,
                "include_regions": tuple(args.region or ()),
                "include_states": tuple(args.material or ()),
                "exclude_states": tuple(args.hide_material or ()),
                "name": args.name,
            }
            if args.tile_size:
                render_options["tile_size"] = args.tile_size
                render_options["resume"] = args.resume
            result = render_method(args.out or args.run, **render_options)
        result.manifest["accuracy"] = {
            "profile": args.accuracy,
            "texture_exact": (
                args.accuracy == "exact"
                and effective_mode == "textured"
                and pack is not None
            ),
            "contract": (
                "full blockstate/model/resource-pack texture resolution"
                if args.accuracy == "exact" and effective_mode == "textured"
                else (
                    "palette-color occupancy preview; not texture-exact "
                    "and not model-shape-exact"
                    if args.accuracy == "fast"
                    else "flat semantic geometry; not texture-exact"
                )
            ),
        }
        atomic_write_json(result.manifest_path, result.manifest)
        return {
            "png": str(result.png_path),
            "manifest": str(result.manifest_path),
            "snapshot_id": result.snapshot_id,
            "accuracy": result.manifest["accuracy"],
            "diagnostics": result.diagnostics,
        }
    finally:
        if pack:
            pack.close()


def _version(args: argparse.Namespace) -> Any:
    root = Path(args.run)
    manifest = json.loads((root / "versions" / "manifest.json").read_text("utf-8"))
    if args.version_command == "list":
        return manifest
    if args.version_command == "compare":
        a = load_document(root, version_id=args.from_version)
        b = load_document(root, version_id=args.to_version)
        a_palette, b_palette = a.palette_by_id(), b.palette_by_id()
        changes = []
        for position in sorted(set(a.blocks) | set(b.blocks)):
            before = a_palette[a.blocks[position]].canonical_state if position in a.blocks else "minecraft:air"
            after = b_palette[b.blocks[position]].canonical_state if position in b.blocks else "minecraft:air"
            if before != after:
                changes.append({"position": list(position.as_tuple()), "before": before, "after": after})
        return {"from": args.from_version, "to": args.to_version, "change_count": len(changes), "changes": changes}
    raise AppError("VERSION_COMMAND", "Unknown version command.", exit_code=2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="python -m app.cli", description="Offline Minecraft Build Intelligence CLI")
    parser.add_argument("--json-errors", action="store_true")
    parser.add_argument("--quiet", action="store_true")
    parser.add_argument("--verbose", action="store_true")
    parser.add_argument("--log-json", action="store_true")
    sub = parser.add_subparsers(dest="command", required=True)

    command = sub.add_parser("import")
    command.add_argument("file")
    command.add_argument("--out", required=True)

    command = sub.add_parser("analyze")
    command.add_argument("run")
    command.add_argument(
        "--bounds",
        type=_inclusive_bounds,
        help="Analyze inclusive world bounds X1,Y1,Z1,X2,Y2,Z2 independently.",
    )
    command.add_argument(
        "--lighting-max-cells",
        type=int,
        default=10_000_000,
        help="Maximum lighting scope volume; pass 0 to remove the cap.",
    )
    command.add_argument("--dark-threshold", type=int, default=7)
    command.add_argument("--room-max-cells", type=int, default=20_000_000)
    command.add_argument(
        "--seal-structure-envelope",
        action="store_true",
        help=(
            "Recover plausible rooms behind exterior openings inside the "
            "selected bounds."
        ),
    )
    command.add_argument(
        "--room-bounds",
        type=_inclusive_bounds,
        action="append",
        help="Seed-and-clip a manual room; repeatable. Openings at the bound are sealed and reported.",
    )
    command.add_argument(
        "--room-seed",
        type=_int_vector,
        action="append",
        help="Air-cell seed corresponding to each --room-bounds, in the same order.",
    )
    command.add_argument("--out")

    command = sub.add_parser("snapshot")
    command.add_argument("run")
    command.add_argument("--views", default="global,layers,slices")
    command.add_argument("--resource-pack")
    command.add_argument("--strict-textures", action="store_true")
    command.add_argument("--size", type=_size, default=(768, 768))
    command.add_argument("--pixels-per-block", type=int, default=8)
    command.add_argument("--out")

    command = sub.add_parser("export")
    command.add_argument("run")
    command.add_argument("--format", choices=("schem", "litematic"), required=True)
    command.add_argument("--verify", action="store_true")
    command.add_argument("--out")

    command = sub.add_parser("pipeline")
    command.add_argument("file")
    command.add_argument("--out", required=True)
    command.add_argument("--resource-pack")
    command.add_argument("--format", choices=("schem", "litematic"), default="schem")
    command.add_argument("--size", type=_size, default=(512, 512))

    command = sub.add_parser("render")
    command.add_argument("run")
    command.add_argument("--camera-azimuth", type=float, default=45)
    command.add_argument("--camera-elevation", type=float, default=30)
    command.add_argument("--camera-roll", type=float, default=0)
    command.add_argument(
        "--zoom",
        type=float,
        default=1.0,
        help=(
            "Scale after automatic fit-to-subject framing; with --no-fit, "
            "absolute pixels per block."
        ),
    )
    command.add_argument(
        "--fit",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Automatically fit canonical or cropped bounds to the frame (default: enabled).",
    )
    command.add_argument(
        "--margin",
        type=float,
        default=0.5,
        help="World-space margin in blocks around the automatically fitted subject.",
    )
    command.add_argument("--size", type=_size, default=(1536, 1536))
    command.add_argument("--mode", choices=("flat", "textured"), default="textured")
    command.add_argument(
        "--accuracy",
        choices=("exact", "fast"),
        default="exact",
        help=(
            "Exact uses resource-pack models/textures; fast emits a cheap "
            "palette-color occupancy preview with an explicit non-exact contract."
        ),
    )
    command.add_argument("--lighting", default="analysis-neutral")
    command.add_argument("--resource-pack")
    command.add_argument("--strict-textures", action="store_true")
    command.add_argument("--slice")
    command.add_argument("--pixels-per-block", type=int, default=8)
    command.add_argument("--crop")
    command.add_argument("--view", choices=("north", "south", "east", "west", "top", "bottom", "isometric_ne", "isometric_nw", "isometric_se", "isometric_sw"))
    command.add_argument("--seed", type=int, default=0)
    command.add_argument("--region", action="append", help="Render only the named region; repeatable.")
    command.add_argument("--material", action="append", help="Render only this exact state or base block ID; repeatable.")
    command.add_argument("--hide-material", action="append", help="Hide this exact state or base block ID; repeatable.")
    command.add_argument(
        "--tile-size",
        type=int,
        default=0,
        help=(
            "Enable exact checkpointed screen-tiled rendering with TILE_SIZE "
            "pixels per tile (recommended: 256-1024)."
        ),
    )
    command.add_argument(
        "--resume",
        action="store_true",
        help="Resume completed tiles from durable render checkpoints.",
    )
    command.add_argument("--name")
    command.add_argument("--out")

    query = sub.add_parser("query")
    query_sub = query.add_subparsers(dest="query_command", required=True)
    command = query_sub.add_parser("block")
    command.add_argument("run")
    command.add_argument("--x", type=int, required=True)
    command.add_argument("--y", type=int, required=True)
    command.add_argument("--z", type=int, required=True)
    command = query_sub.add_parser("box")
    command.add_argument("run")
    command.add_argument("--min", dest="minimum", required=True)
    command.add_argument("--max", dest="maximum", required=True)
    command = query_sub.add_parser("palette")
    command.add_argument("run")
    command = query_sub.add_parser("chunk")
    command.add_argument("run")
    command.add_argument("--cx", type=int, required=True)
    command.add_argument("--cy", type=int, required=True)
    command.add_argument("--cz", type=int, required=True)
    command = query_sub.add_parser("block-entity")
    command.add_argument("run")
    command.add_argument("--x", type=int, required=True)
    command.add_argument("--y", type=int, required=True)
    command.add_argument("--z", type=int, required=True)
    command = query_sub.add_parser("region")
    command.add_argument("run")
    command.add_argument("--name", required=True)
    command = query_sub.add_parser("room")
    command.add_argument("run")
    command.add_argument("--id", required=True)
    command = query_sub.add_parser("issues")
    command.add_argument("run")
    command.add_argument("--type", required=True)
    for child in query_sub.choices.values():
        child.add_argument("--json", action="store_true")

    patch = sub.add_parser("patch")
    patch_sub = patch.add_subparsers(dest="patch_command", required=True)
    for name in ("validate", "preview", "commit", "reject"):
        command = patch_sub.add_parser(name)
        command.add_argument("run")
        command.add_argument("patch_file")
        command.add_argument("--resource-pack")
        command.add_argument("--out")
    command = patch_sub.add_parser("rollback")
    command.add_argument("run")
    command.add_argument("--patch-id", required=True)
    command.add_argument("--out")

    version = sub.add_parser("version")
    version_sub = version.add_subparsers(dest="version_command", required=True)
    command = version_sub.add_parser("list")
    command.add_argument("run")
    command = version_sub.add_parser("compare")
    command.add_argument("run")
    command.add_argument("--from", dest="from_version", required=True)
    command.add_argument("--to", dest="to_version", required=True)

    command = sub.add_parser("build-plan")
    command.add_argument("run")
    command.add_argument("design_brief")
    command.add_argument("--out", required=True)

    command = sub.add_parser("apply-plan")
    command.add_argument("run")
    command.add_argument("build_plan")
    command.add_argument("--resource-pack")
    command.add_argument("--out", required=True)

    command = sub.add_parser("pixel-to-block")
    command.add_argument("manifest")
    command.add_argument("--px", type=int, required=True)
    command.add_argument("--py", type=int, required=True)

    command = sub.add_parser("block-to-pixel")
    command.add_argument("manifest")
    command.add_argument("--x", type=int, required=True)
    command.add_argument("--y", type=int, required=True)
    command.add_argument("--z", type=int, required=True)


    command = sub.add_parser("tool")
    command.add_argument("run")
    command.add_argument("request_file")
    command.add_argument("--resource-pack")
    command.add_argument("--allow-commit", action="store_true")
    command.add_argument("--result")

    command = sub.add_parser("agent")
    command.add_argument("run")
    command.add_argument("--task", required=True)
    command.add_argument("--provider", choices=("openai", "anthropic", "openai-compatible"), required=True)
    command.add_argument("--model", required=True)
    command.add_argument("--base-url")
    command.add_argument("--api-key-env", default="MBI_AI_API_KEY")
    command.add_argument("--resource-pack")
    command.add_argument("--auto-commit", action="store_true")
    command.add_argument("--max-iterations", type=int, default=8)
    command.add_argument("--max-context-tokens", type=int, default=512000)
    command.add_argument("--max-images", type=int, default=16)
    command.add_argument("--max-image-bytes", type=int, default=24 * 1024 * 1024)
    command.add_argument("--max-output-tokens", type=int, default=4096)
    command.add_argument("--out")
    return parser


def dispatch(args: argparse.Namespace) -> Any:
    if args.command == "import":
        return import_file(args.file, args.out).to_summary()
    if args.command == "analyze":
        analysis_bounds = args.bounds
        structure_identifier = getattr(args, "structure", None)
        if structure_identifier:
            if analysis_bounds is not None:
                raise AppError(
                    "ANALYSIS_SCOPE_CONFLICT",
                    "--bounds and --structure cannot be supplied together.",
                    exit_code=2,
                )
            from app.structures import resolve_structure_bounds

            analysis_bounds = resolve_structure_bounds(
                args.run,
                structure_identifier,
            )
        target = clone_run_base(args.run, args.out) if args.out else Path(args.run)
        room_bounds = tuple(args.room_bounds or ())
        room_seeds = tuple(args.room_seed or ())
        if len(room_seeds) > len(room_bounds):
            raise AppError(
                "ROOM_SEED_WITHOUT_BOUNDS",
                "Each --room-seed requires a corresponding --room-bounds.",
                exit_code=2,
            )
        manual_rooms = tuple(
            (
                requested,
                room_seeds[index] if index < len(room_seeds) else None,
            )
            for index, requested in enumerate(room_bounds)
        )
        return analyze_run(
            target,
            bounds=analysis_bounds,
            lighting_max_cells=(
                None if args.lighting_max_cells == 0 else args.lighting_max_cells
            ),
            dark_threshold=args.dark_threshold,
            room_max_cells=args.room_max_cells,
            manual_rooms=manual_rooms,
            seal_structure_envelope=(
                bool(structure_identifier)
                or args.seal_structure_envelope
            ),
        )
    if args.command == "snapshot":
        target = clone_run_base(args.run, args.out) if args.out else Path(args.run)
        return {"snapshots": snapshot_run(target, resource_pack=args.resource_pack, views=tuple(item for item in args.views.split(",") if item), size=args.size, pixels_per_block=args.pixels_per_block, strict_textures=args.strict_textures)}
    if args.command == "export":
        target = clone_run_base(args.run, args.out) if args.out else Path(args.run)
        return export_run(target, format_name=args.format, verify=args.verify)
    if args.command == "pipeline":
        return pipeline(args.file, args.out, resource_pack=args.resource_pack, export_format=args.format, size=args.size)
    if args.command == "render":
        return _render(args)
    if args.command == "query":
        return _query(args)
    if args.command == "patch":
        target = clone_run_base(args.run, args.out) if args.out else Path(args.run)
        if args.patch_command == "rollback":
            return rollback_patch(target, args.patch_id)
        return patch_action(target, args.patch_file, action=args.patch_command, resource_pack=args.resource_pack)
    if args.command == "version":
        return _version(args)
    if args.command == "build-plan":
        return create_build_plan(args.design_brief, args.out, source_run=args.run)
    if args.command == "apply-plan":
        return apply_build_plan(args.build_plan, args.out, resource_pack=args.resource_pack, source_run=args.run)
    if args.command == "pixel-to-block":
        return pixel_to_block(args.manifest, args.px, args.py)
    if args.command == "block-to-pixel":
        return block_to_pixel(args.manifest, args.x, args.y, args.z)
    if args.command == "tool":
        from app.ai.multimodal import run_tool_request_file
        return run_tool_request_file(
            args.run, args.request_file, resource_pack=args.resource_pack,
            allow_commit=args.allow_commit, result_path=args.result,
        )
    if args.command == "agent":
        from app.ai.multimodal import run_agent_cli
        return asyncio.run(run_agent_cli(args))
    raise AppError("COMMAND", "Unknown command.", exit_code=2)


def _exit_code_for(exc: Exception) -> int:
    explicit = getattr(exc, "exit_code", None)
    if explicit is not None:
        return int(explicit)
    code = str(getattr(exc, "code", ""))
    if "ROUNDTRIP" in code or "VERIFY" in code:
        return 51
    if code.startswith(("EXPORT", "LITEMATIC_EXPORT", "SPONGE_EXPORT")):
        return 50
    if code.startswith(("PATCH", "VERSION", "MERGE", "BRANCH", "CHECKPOINT")):
        return 41 if "STALE" in code or "PRECONDITION" in code else 40
    if code.startswith(("RENDER", "CAMERA", "SLICE", "CROP")):
        return 30
    if code.startswith(("ASSET", "TEXTURE", "MODEL", "RESOURCE_PACK", "BLOCKSTATE")):
        return 31
    if code.startswith(("AI", "PROVIDER", "AGENT")):
        return 60
    if code.startswith(("NBT", "GZIP", "ZLIB", "COMPRESSION")):
        return 11
    if "LIMIT" in code or "BOMB" in code or "OVERFLOW" in code:
        return 12
    if code.startswith(("UNKNOWN_STRUCTURE", "UNSUPPORTED_FORMAT", "LITEMATIC_STRUCTURE")):
        return 10
    if code.startswith(("DOCUMENT", "CANONICAL", "PALETTE")):
        return 20
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    from app.jobs import configure_progress
    configure_progress(enabled=not args.quiet, json_mode=args.log_json)
    try:
        result = dispatch(args)
        if not args.quiet:
            _json(result)
        return 0
    except KeyboardInterrupt:
        error = {"error": {"code": "CANCELLED", "message": "Operation cancelled by user.", "details": {}}}
        print(json.dumps(error, sort_keys=True), file=sys.stderr)
        return 130
    except Exception as exc:
        code = getattr(exc, "code", "UNEXPECTED_ERROR")
        message = getattr(exc, "message", str(exc))
        details = getattr(exc, "details", {})
        exit_code = _exit_code_for(exc)
        payload = {"error": {"code": code, "message": message, "details": details}}
        if args.json_errors:
            print(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str), file=sys.stderr)
        else:
            print(f"{code}: {message}", file=sys.stderr)
            if args.verbose and details:
                print(json.dumps(details, sort_keys=True, indent=2, default=str), file=sys.stderr)
        return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
