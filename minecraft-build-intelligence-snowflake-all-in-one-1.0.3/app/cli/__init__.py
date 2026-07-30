from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from dataclasses import replace
from pathlib import Path
from typing import Any

# Source snapshots keep the canonical core under services/core/src; installed
# wheels already expose mbi normally. Make both invocation modes deterministic.
_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_CORE_SOURCE = _SOURCE_ROOT / "services" / "core" / "src"
if _CORE_SOURCE.is_dir() and str(_CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(_CORE_SOURCE))

from mbi.canonical import IntBoundingBox, IntVector3

from app.config import RuntimeConfig
from app.errors import AppError
from app.project import load_document
from app.render.perspective import PerspectiveCameraSpec, PerspectiveRenderer


def _load_legacy():
    name = "app._legacy_cli"
    cached = sys.modules.get(name)
    if cached is not None:
        return cached
    path = Path(__file__).resolve().parents[1] / "cli.py"
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load legacy CLI at {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


LEGACY = _load_legacy()


def _vec3(value: str) -> tuple[float, float, float]:
    values = [float(item) for item in value.split(",")]
    if len(values) != 3:
        raise argparse.ArgumentTypeError("coordinate must be X,Y,Z")
    return values[0], values[1], values[2]


def _subparsers(parser: argparse.ArgumentParser) -> argparse._SubParsersAction:
    action = next((item for item in parser._actions if isinstance(item, argparse._SubParsersAction)), None)
    if action is None:
        raise RuntimeError("Legacy CLI has no command subparsers")
    return action


def build_parser() -> argparse.ArgumentParser:
    parser = LEGACY.build_parser()
    sub = _subparsers(parser)
    render = sub.choices["render"]
    analyze = sub.choices["analyze"]
    analyze.add_argument(
        "--structure",
        help="Analyze one detected structure by durable id or registered name.",
    )
    render.add_argument("--projection", choices=("auto", "orthographic", "perspective"), default="auto")
    render.add_argument("--camera-position", type=_vec3)
    render.add_argument("--camera-target", type=_vec3)
    render.add_argument("--camera-yaw", type=float)
    render.add_argument("--camera-pitch", type=float)
    render.add_argument("--fov", type=float, default=70.0)
    render.add_argument("--near", type=float, default=0.05)
    render.add_argument("--far", type=float, default=4096.0)
    render.add_argument("--hide-coordinate", type=_vec3, action="append")

    quality = sub.add_parser(
        "quality-report",
        help="Emit a normalized quality scorecard and optional CI threshold gate.",
    )
    quality.add_argument("run")
    quality.add_argument("--bounds", type=LEGACY._inclusive_bounds)
    quality.add_argument("--structure")
    quality.add_argument(
        "--seal-structure-envelope",
        action="store_true",
        help="Apply automatic exterior-opening sealing to the selected bounds.",
    )
    quality.add_argument("--fail-under", type=float)
    quality.add_argument("--from", dest="from_version")
    quality.add_argument("--to", dest="to_version")

    command = sub.add_parser("export-map")
    command.add_argument("run")
    command.add_argument("--out", required=True)
    command.add_argument("--format", choices=("csv", "jsonl", "parquet"), default="csv")
    command.add_argument("--resource-pack")

    command = sub.add_parser("texture-audit")
    command.add_argument("run")
    command.add_argument("--resource-pack")
    command.add_argument("--fail-under", type=float)

    command = sub.add_parser("palette-atlas")
    command.add_argument("run")
    command.add_argument("--out", required=True)
    command.add_argument("--resource-pack")
    command.add_argument("--columns", type=int, default=5)
    command.add_argument("--swatch-size", type=int, default=48)

    command = sub.add_parser("contact-sheet")
    command.add_argument("run")
    command.add_argument(
        "--views",
        default="isometric_ne,isometric_sw,south,top",
    )
    command.add_argument("--slices", default="")
    command.add_argument("--out", required=True)
    command.add_argument("--resource-pack")
    command.add_argument("--size", type=LEGACY._size, default=(480, 320))
    command.add_argument("--accuracy", choices=("fast", "exact"), default="exact")
    command.add_argument("--resume", action="store_true")
    command.add_argument("--columns", type=int, default=3)

    command = sub.add_parser("slice-sweep")
    command.add_argument("run")
    command.add_argument("--slice", required=True, help="AXIS:MIN..MAX")
    command.add_argument("--step", type=int, default=1)
    command.add_argument("--out", required=True)
    command.add_argument("--resource-pack")
    command.add_argument("--resume", action="store_true")
    command.add_argument(
        "--montage",
        action=argparse.BooleanOptionalAction,
        default=True,
    )

    command = sub.add_parser("annotated-render")
    command.add_argument("run")
    command.add_argument("--out", required=True)
    command.add_argument("--view", default="isometric_ne")
    command.add_argument("--resource-pack")
    command.add_argument("--size", type=LEGACY._size, default=(1280, 800))
    command.add_argument("--annotate-materials", type=int, default=8)

    author = sub.add_parser(
        "author",
        help="Reference-style extraction, anchors, fixtures, and critique tooling.",
    )
    author_sub = author.add_subparsers(dest="author_command", required=True)
    command = author_sub.add_parser("anchor-set")
    command.add_argument("run")
    command.add_argument("name")
    command.add_argument("--position", type=LEGACY._int_vector, required=True)
    command = author_sub.add_parser("anchor-room")
    command.add_argument("run")
    command.add_argument("name")
    command.add_argument("--room", required=True)
    command.add_argument(
        "--face",
        choices=("north", "south", "east", "west", "floor", "ceiling"),
        required=True,
    )
    command = author_sub.add_parser("anchor-bay")
    command.add_argument("run")
    command.add_argument("name")
    command.add_argument("--structure", required=True)
    command.add_argument("--face", choices=("north", "south", "east", "west"), required=True)
    command.add_argument("--bay-index", type=int, required=True)
    command.add_argument("--bay-count", type=int, required=True)
    command = author_sub.add_parser("anchors")
    command.add_argument("run")
    command = author_sub.add_parser("style-extract")
    command.add_argument("run")
    command.add_argument("--name", default="reference")
    command = author_sub.add_parser("critique")
    command.add_argument("run")
    command.add_argument("--style-profile")
    command = author_sub.add_parser("fixture-catalog")

    structure = sub.add_parser(
        "structure",
        help="Detect, name, analyze, extract, render, and compare map structures.",
    )
    structure_sub = structure.add_subparsers(dest="structure_command", required=True)
    command = structure_sub.add_parser("inventory")
    command.add_argument("run")
    command.add_argument("--separation", type=int, default=2)
    command.add_argument("--minimum-blocks", type=int, default=24)
    command.add_argument(
        "--window-edge",
        type=int,
        default=64,
        help="Spatial aggregation window edge in blocks (default: 64).",
    )
    command.add_argument(
        "--classification-config",
        help="JSON file overriding documented geometric classification thresholds.",
    )
    command = structure_sub.add_parser("name")
    command.add_argument("run")
    command.add_argument("identifier")
    command.add_argument("name")
    command = structure_sub.add_parser("extract")
    command.add_argument("run")
    command.add_argument("identifier")
    command.add_argument("--out", required=True)
    command.add_argument("--format", choices=("schem", "litematic"), default="schem")
    command = structure_sub.add_parser("analyze-all")
    command.add_argument("run")
    command.add_argument("--resume", action="store_true")
    command.add_argument("--lighting-max-cells", type=int, default=10_000_000)
    command = structure_sub.add_parser("compare")
    command.add_argument("run")
    command.add_argument("first")
    command.add_argument("second")
    command = structure_sub.add_parser("site-plan")
    command.add_argument("run")
    command.add_argument("--out")
    command.add_argument("--pixels-per-block", type=int, default=3)
    command = structure_sub.add_parser("map-report")
    command.add_argument("run")
    command = structure_sub.add_parser("render-all")
    command.add_argument("run")
    command.add_argument("--out")
    command.add_argument("--resource-pack")
    command.add_argument("--accuracy", choices=("fast", "exact"), default="fast")
    command.add_argument("--resume", action="store_true")
    command.add_argument("--size", type=LEGACY._size, default=(640, 480))
    command = structure_sub.add_parser("interiors")
    command.add_argument("run")
    command.add_argument("--out")
    command.add_argument("--resource-pack")
    command.add_argument("--resume", action="store_true")
    command.add_argument("--max-rooms-per-structure", type=int, default=8)
    command.add_argument("--min-cumulative-coverage", type=float, default=0.0)
    command.add_argument("--size", type=LEGACY._size, default=(640, 400))

    interior = sub.add_parser("interior")
    interior_sub = interior.add_subparsers(dest="interior_command", required=True)
    command = interior_sub.add_parser("render")
    command.add_argument("run")
    command.add_argument("--room", required=True)
    command.add_argument("--shot", choices=("auto", "doorway", "corner", "center", "feature", "low", "upper", "coverage", "walkthrough"), default="auto")
    command.add_argument("--resource-pack")
    command.add_argument("--size", type=LEGACY._size, default=(1280, 800))
    command.add_argument("--fov", type=float, default=70.0)
    command.add_argument("--near", type=float, default=0.05)
    command.add_argument("--far", type=float, default=4096.0)
    command.add_argument("--eye-height", type=float, default=1.62)
    command.add_argument("--lighting", default="interior-soft")
    command.add_argument(
        "--camera-mode",
        choices=("auto", "physical-first-person", "physical-third-person", "third-person-orbit"),
        default="auto",
    )
    command.add_argument(
        "--occlusion",
        choices=("physical", "cutaway", "hybrid", "roof-off", "wall-off"),
        default="physical",
    )
    command.add_argument(
        "--cutaway-strategy",
        choices=("minimal-ray", "roof", "wall"),
        default="minimal-ray",
    )
    command.add_argument(
        "--quality-profile",
        choices=(
            "auto",
            "physical_first_person",
            "physical_third_person",
            "feature_closeup",
            "room_coverage",
            "third_person_cutaway",
            "roof_off",
            "presentation",
        ),
        default="auto",
    )
    command.add_argument("--min-room-coverage", type=float)
    command.add_argument("--max-obstruction", type=float)
    command.add_argument("--max-attempts", type=int, default=8)
    command.add_argument(
        "--fail-on-reject",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Return a non-zero exit code when the selected frame fails the quality gate (default: on).",
    )
    command.add_argument("--name")
    command.add_argument("--out")

    command = interior_sub.add_parser("gallery")
    command.add_argument("run")
    command.add_argument("--rooms", default="all")
    command.add_argument("--shots", default="doorway,corner,feature")
    command.add_argument("--resource-pack")
    command.add_argument("--size", type=LEGACY._size, default=(1280, 800))
    command.add_argument("--fov", type=float, default=70.0)
    command.add_argument("--near", type=float, default=0.05)
    command.add_argument("--far", type=float, default=4096.0)
    command.add_argument("--eye-height", type=float, default=1.62)
    command.add_argument("--lighting", default="interior-soft")
    command.add_argument(
        "--occlusion",
        choices=("physical", "cutaway", "hybrid", "roof-off", "wall-off"),
        default="physical",
    )
    command.add_argument("--include-non-rooms", action="store_true")
    command.add_argument("--out")

    for command_name in ("inspect", "diagnose"):
        command = interior_sub.add_parser(command_name)
        command.add_argument("run")
        command.add_argument("--room", required=True)

    command = interior_sub.add_parser("walkthrough")
    command.add_argument("run")
    command.add_argument("--room", required=True)
    command.add_argument("--spacing", type=int, default=6)
    command.add_argument("--render", action="store_true")
    command.add_argument("--resource-pack")
    command.add_argument("--size", type=LEGACY._size, default=(640, 400))
    command.add_argument("--resume", action="store_true")
    command.add_argument("--out")

    command = interior_sub.add_parser("sightline")
    command.add_argument("run")
    command.add_argument("--room", required=True)
    command.add_argument("--out")

    command = interior_sub.add_parser("packet")
    command.add_argument("run")
    command.add_argument("--room", required=True)
    command.add_argument("--shots", default="auto,corner,feature")
    command.add_argument("--resource-pack")
    command.add_argument("--size", type=LEGACY._size, default=(1280, 800))
    command.add_argument("--fov", type=float, default=70.0)
    command.add_argument("--near", type=float, default=0.05)
    command.add_argument("--far", type=float, default=4096.0)
    command.add_argument("--eye-height", type=float, default=1.62)
    command.add_argument("--lighting", default="interior-soft")
    command.add_argument(
        "--camera-mode",
        choices=("auto", "physical-first-person", "physical-third-person", "third-person-orbit"),
        default="auto",
    )
    command.add_argument(
        "--fallback",
        default="physical,third-person,cutaway,slices",
        help="Comma-separated evidence stages.",
    )
    command.add_argument(
        "--occlusion",
        choices=("physical", "cutaway", "hybrid", "roof-off", "wall-off"),
        default="physical",
    )
    command.add_argument(
        "--cutaway-strategy",
        choices=("minimal-ray", "roof", "wall"),
        default="minimal-ray",
    )
    command.add_argument(
        "--slice-fallback", choices=("auto", "always", "never"), default="auto"
    )
    command.add_argument(
        "--quality-profile",
        choices=("auto", "third_person_cutaway", "presentation"),
        default="auto",
    )
    command.add_argument("--min-room-coverage", type=float)
    command.add_argument("--max-obstruction", type=float)
    command.add_argument(
        "--min-cumulative-coverage",
        type=float,
        default=0.0,
        help="Require the accepted shot-set union to cover this fraction of room boundary coordinates.",
    )
    command.add_argument("--max-attempts", type=int, default=8)
    command.add_argument("--out")
    return parser


def _perspective_render(args: argparse.Namespace) -> Any:
    from app.assets import open_resource_pack

    crop = None
    if args.crop:
        values = [int(item) for item in args.crop.split(",")]
        if len(values) != 6:
            raise AppError("CROP_SPEC", "Crop must contain x,y,z,width,height,length.", exit_code=2)
        x, y, z, width, height, length = values
        crop = IntBoundingBox(IntVector3(x, y, z), IntVector3(x + width - 1, y + height - 1, z + length - 1))
    document = load_document(args.run, bounds=crop)
    if args.camera_position is None:
        raise AppError("CAMERA_POSITION_REQUIRED", "Perspective rendering requires --camera-position X,Y,Z.", exit_code=30)
    target = args.camera_target
    if target is None and (args.camera_yaw is None or args.camera_pitch is None):
        bounds = crop or document.bounds
        target = tuple((a + b + 1) / 2.0 for a, b in zip(bounds.min.as_tuple(), bounds.max.as_tuple(), strict=True))
    camera = PerspectiveCameraSpec(
        position=args.camera_position, target=target, yaw_degrees=args.camera_yaw,
        pitch_degrees=args.camera_pitch, roll_degrees=args.camera_roll,
        vertical_fov_degrees=args.fov, near=args.near, far=args.far,
    )
    hidden = frozenset(IntVector3(*(int(round(value)) for value in point)) for point in (args.hide_coordinate or ()))
    pack = open_resource_pack(args.resource_pack)
    try:
        config = RuntimeConfig.from_environment()
        if args.max_visible_blocks is not None:
            config = replace(
                config,
                max_visible_blocks=args.max_visible_blocks,
            )
        result = PerspectiveRenderer(
            document,
            resource_pack=pack,
            config=config,
            strict_textures=args.strict_textures,
            seed=args.seed,
        ).render(
            args.out or args.run, camera=camera, crop=crop, size=args.size, mode=args.mode,
            lighting_preset=args.lighting, include_regions=tuple(args.region or ()),
            include_states=tuple(args.material or ()), exclude_states=tuple(args.hide_material or ()),
            hidden_coordinates=hidden, name=args.name,
        )
    finally:
        if pack:
            pack.close()
    return {"png": str(result.png_path), "manifest": str(result.manifest_path), "snapshot_id": result.snapshot_id, "diagnostics": result.diagnostics}


def _interior(args: argparse.Namespace) -> Any:
    from app.interior import (
        diagnose_room,
        inspect_room,
        interior_walkthrough,
        render_gallery,
        render_room,
        render_room_packet,
        room_sightlines,
    )
    if args.interior_command == "inspect":
        return inspect_room(args.run, args.room)
    if args.interior_command == "diagnose":
        return diagnose_room(args.run, args.room)
    if args.interior_command == "walkthrough":
        return interior_walkthrough(
            args.run,
            args.room,
            spacing=args.spacing,
            output=args.out,
            render_frames=args.render,
            resource_pack=args.resource_pack,
            size=args.size,
            resume=args.resume,
        )
    if args.interior_command == "sightline":
        return room_sightlines(args.run, args.room, output=args.out)
    if args.interior_command == "render":
        report = render_room(
            args.run, args.room, shot=args.shot, resource_pack=args.resource_pack,
            size=args.size, fov=args.fov, near=args.near, far=args.far,
            eye_height=args.eye_height, lighting=args.lighting,
            occlusion=args.occlusion, out=args.out, name=args.name,
            max_attempts=args.max_attempts,
            camera_mode=args.camera_mode, cutaway_strategy=args.cutaway_strategy,
            quality_profile=args.quality_profile,
            min_room_coverage=args.min_room_coverage,
            max_obstruction=args.max_obstruction,
        )
        if args.fail_on_reject and report["quality_status"] != "accepted":
            reasons = report["quality"].get("rejection_reasons", [])
            raise AppError(
                "INTERIOR_RENDER_REJECTED",
                "Interior render failed its quality gate: " + ", ".join(reasons or ["unknown reason"]),
                {
                    "room_id": report["room_id"],
                    "rejection_reasons": reasons,
                    "quality": report["quality"],
                    "png": report["png"],
                    "report": str(
                        Path(args.out or args.run)
                        / f"room_{report['room_id']}_{report['shot']}_interior-report.json"
                    ),
                },
                30,
            )
        return report
    if args.interior_command == "packet":
        packet = render_room_packet(
            args.run, args.room,
            shots=tuple(item for item in args.shots.split(",") if item),
            resource_pack=args.resource_pack, size=args.size, fov=args.fov,
            near=args.near, far=args.far, eye_height=args.eye_height,
            lighting=args.lighting, occlusion=args.occlusion,
            max_attempts=args.max_attempts, out=args.out,
            camera_mode=args.camera_mode,
            fallback=tuple(item for item in args.fallback.split(",") if item),
            cutaway_strategy=args.cutaway_strategy,
            slice_fallback=args.slice_fallback,
            quality_profile=args.quality_profile,
            min_room_coverage=args.min_room_coverage,
            max_obstruction=args.max_obstruction,
            min_cumulative_coverage=args.min_cumulative_coverage,
        )
        if not packet["coverage"]["passed"]:
            coverage = packet["coverage"]
            raise AppError(
                "INTERIOR_COVERAGE_UNMET",
                "Interior packet did not meet cumulative coverage: "
                f"achieved {coverage['achieved']:.3f}, "
                f"required {coverage['minimum']:.3f}.",
                {
                    "room_id": packet["room_id"],
                    "coverage": coverage,
                    "packet": str(
                        Path(args.out or Path(args.run) / f"room-{args.room}-packet")
                        / "interior_packet.json"
                    ),
                },
                30,
            )
        return packet
    room_ids = None if args.rooms == "all" else tuple(item for item in args.rooms.split(",") if item)
    return render_gallery(
        args.run, room_ids=room_ids, shots=tuple(item for item in args.shots.split(",") if item),
        resource_pack=args.resource_pack, size=args.size, fov=args.fov, near=args.near, far=args.far,
        eye_height=args.eye_height, lighting=args.lighting, occlusion=args.occlusion, out=args.out,
        include_non_rooms=args.include_non_rooms,
    )


def dispatch(args: argparse.Namespace) -> Any:
    if args.command == "author":
        from app.authoring import (
            critique_build,
            extract_style_profile,
            load_anchors,
            set_anchor,
            set_room_face_anchor,
            set_structure_bay_anchor,
        )

        if args.author_command == "anchor-set":
            return set_anchor(args.run, args.name, args.position)
        if args.author_command == "anchor-room":
            return set_room_face_anchor(args.run, args.name, args.room, args.face)
        if args.author_command == "anchor-bay":
            return set_structure_bay_anchor(
                args.run,
                args.name,
                args.structure,
                args.face,
                args.bay_index,
                args.bay_count,
            )
        if args.author_command == "anchors":
            return load_anchors(args.run)
        if args.author_command == "style-extract":
            return extract_style_profile(args.run, name=args.name)
        if args.author_command == "critique":
            return critique_build(args.run, style_profile=args.style_profile)
        from mbi.patch.assemblies import fixture_catalog

        return fixture_catalog()
    if args.command in {
        "export-map",
        "texture-audit",
        "palette-atlas",
        "contact-sheet",
        "slice-sweep",
        "annotated-render",
    }:
        from app.comprehension import (
            annotated_render,
            contact_sheet,
            export_block_map,
            palette_atlas,
            slice_sweep,
            texture_audit,
        )

        if args.command == "export-map":
            return export_block_map(
                args.run,
                args.out,
                format_name=args.format,
                resource_pack=args.resource_pack,
            )
        if args.command == "texture-audit":
            report = texture_audit(args.run, resource_pack=args.resource_pack)
            coverage = report["texture_coverage_percent"]
            if args.fail_under is not None and coverage < args.fail_under:
                raise AppError(
                    "TEXTURE_COVERAGE_BELOW_THRESHOLD",
                    f"Static texture coverage {coverage:.6f}% is below required {args.fail_under:.6f}%.",
                    {
                        "coverage": coverage,
                        "fail_under": args.fail_under,
                        "report": str(Path(args.run) / "texture_audit.json"),
                    },
                    31,
                )
            return report
        if args.command == "palette-atlas":
            return palette_atlas(
                args.run,
                args.out,
                resource_pack=args.resource_pack,
                columns=args.columns,
                swatch_size=args.swatch_size,
            )
        if args.command == "contact-sheet":
            return contact_sheet(
                args.run,
                views=tuple(item for item in args.views.split(",") if item),
                slices=tuple(item for item in args.slices.split(",") if item),
                output=args.out,
                resource_pack=args.resource_pack,
                size=args.size,
                accuracy=args.accuracy,
                resume=args.resume,
                columns=args.columns,
            )
        if args.command == "slice-sweep":
            axis, raw_range = args.slice.split(":", 1)
            if ".." not in raw_range:
                raise AppError(
                    "SLICE_SWEEP_RANGE",
                    "Slice sweep requires AXIS:MIN..MAX.",
                    exit_code=2,
                )
            minimum, maximum = (
                int(value) for value in raw_range.split("..", 1)
            )
            return slice_sweep(
                args.run,
                axis=axis,
                minimum=minimum,
                maximum=maximum,
                step=args.step,
                output=args.out,
                resource_pack=args.resource_pack,
                resume=args.resume,
                montage=args.montage,
            )
        return annotated_render(
            args.run,
            output=args.out,
            view=args.view,
            resource_pack=args.resource_pack,
            size=args.size,
            annotate_materials=args.annotate_materials,
        )
    if args.command == "structure":
        from app.structures import (
            analyze_all_structures,
            batch_structure_interiors,
            compare_structures,
            extract_structure,
            inventory_structures,
            map_composition_report,
            name_structure,
            render_site_plan,
            render_structure_lod,
        )

        if args.structure_command == "inventory":
            classification_config = (
                json.loads(Path(args.classification_config).read_text("utf-8"))
                if args.classification_config
                else None
            )
            return inventory_structures(
                args.run,
                separation=args.separation,
                minimum_blocks=args.minimum_blocks,
                window_edge=args.window_edge,
                classification_config=classification_config,
            )
        if args.structure_command == "name":
            return name_structure(args.run, args.identifier, args.name)
        if args.structure_command == "extract":
            return extract_structure(
                args.run,
                args.identifier,
                args.out,
                format_name=args.format,
            )
        if args.structure_command == "analyze-all":
            return analyze_all_structures(
                args.run,
                resume=args.resume,
                lighting_max_cells=(
                    None
                    if args.lighting_max_cells == 0
                    else args.lighting_max_cells
                ),
            )
        if args.structure_command == "compare":
            return compare_structures(args.run, args.first, args.second)
        if args.structure_command == "site-plan":
            return render_site_plan(
                args.run,
                output=args.out,
                pixels_per_block=args.pixels_per_block,
            )
        if args.structure_command == "map-report":
            return map_composition_report(args.run)
        if args.structure_command == "render-all":
            return render_structure_lod(
                args.run,
                output=args.out,
                resource_pack=args.resource_pack,
                accuracy=args.accuracy,
                resume=args.resume,
                size=args.size,
            )
        if args.structure_command == "interiors":
            return batch_structure_interiors(
                args.run,
                output=args.out,
                resource_pack=args.resource_pack,
                resume=args.resume,
                max_rooms_per_structure=args.max_rooms_per_structure,
                min_cumulative_coverage=args.min_cumulative_coverage,
                size=args.size,
            )
    if args.command == "quality-report":
        from app.quality_report import quality_report

        if args.structure:
            from app.structures import resolve_structure_bounds

            bounds = resolve_structure_bounds(args.run, args.structure)
        else:
            bounds = args.bounds
        report = quality_report(
            args.run,
            bounds=bounds,
            from_version=args.from_version,
            to_version=args.to_version,
            seal_structure_envelope=(
                bool(args.structure)
                or args.seal_structure_envelope
            ),
        )
        score = (
            report["after"]["overall_score"]
            if report.get("schema") == "mbi.quality-diff.v1"
            else report["overall_score"]
        )
        if args.fail_under is not None and score < args.fail_under:
            raise AppError(
                "QUALITY_THRESHOLD_FAILED",
                f"Quality score {score:.3f} is below required {args.fail_under:.3f}.",
                {
                    "score": score,
                    "fail_under": args.fail_under,
                    "report": str(Path(args.run) / "quality_report.json"),
                },
                40,
            )
        return report
    if args.command == "interior":
        return _interior(args)
    if args.command == "render":
        projection = args.projection
        if projection == "auto":
            projection = "perspective" if args.camera_position is not None else "orthographic"
        if projection == "perspective" and not args.slice:
            return _perspective_render(args)
    return LEGACY.dispatch(args)


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    from app.jobs import configure_progress
    configure_progress(enabled=not args.quiet, json_mode=args.log_json)
    try:
        result = dispatch(args)
        if not args.quiet:
            LEGACY._json(result)
        return 0
    except KeyboardInterrupt:
        print(json.dumps({"error": {"code": "CANCELLED", "message": "Operation cancelled by user.", "details": {}}}, sort_keys=True), file=sys.stderr)
        return 130
    except Exception as exc:
        code = getattr(exc, "code", "UNEXPECTED_ERROR")
        message = getattr(exc, "message", str(exc))
        details = getattr(exc, "details", {})
        exit_code = LEGACY._exit_code_for(exc)
        payload = {"error": {"code": code, "message": message, "details": details}}
        if args.json_errors:
            print(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str), file=sys.stderr)
        else:
            print(f"{code}: {message}", file=sys.stderr)
            if args.verbose and details:
                print(json.dumps(details, sort_keys=True, indent=2, default=str), file=sys.stderr)
        return exit_code
