from __future__ import annotations

import argparse
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

# Source snapshots keep the canonical core under services/core/src; installed
# wheels already expose mbi normally. Make both invocation modes deterministic.
_SOURCE_ROOT = Path(__file__).resolve().parents[2]
_CORE_SOURCE = _SOURCE_ROOT / "services" / "core" / "src"
if _CORE_SOURCE.is_dir() and str(_CORE_SOURCE) not in sys.path:
    sys.path.insert(0, str(_CORE_SOURCE))

from mbi.canonical import IntBoundingBox, IntVector3
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
    render.add_argument("--projection", choices=("auto", "orthographic", "perspective"), default="auto")
    render.add_argument("--camera-position", type=_vec3)
    render.add_argument("--camera-target", type=_vec3)
    render.add_argument("--camera-yaw", type=float)
    render.add_argument("--camera-pitch", type=float)
    render.add_argument("--fov", type=float, default=70.0)
    render.add_argument("--near", type=float, default=0.05)
    render.add_argument("--far", type=float, default=4096.0)
    render.add_argument("--hide-coordinate", type=_vec3, action="append")

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
    command.add_argument("--max-attempts", type=int, default=8)
    command.add_argument("--out")
    return parser


def _perspective_render(args: argparse.Namespace) -> Any:
    from app.assets import open_resource_pack

    document = load_document(args.run)
    crop = None
    if args.crop:
        values = [int(item) for item in args.crop.split(",")]
        if len(values) != 6:
            raise AppError("CROP_SPEC", "Crop must contain x,y,z,width,height,length.", exit_code=2)
        x, y, z, width, height, length = values
        crop = IntBoundingBox(IntVector3(x, y, z), IntVector3(x + width - 1, y + height - 1, z + length - 1))
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
        result = PerspectiveRenderer(document, resource_pack=pack, strict_textures=args.strict_textures, seed=args.seed).render(
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
    from app.interior import diagnose_room, inspect_room, render_gallery, render_room, render_room_packet
    if args.interior_command == "inspect":
        return inspect_room(args.run, args.room)
    if args.interior_command == "diagnose":
        return diagnose_room(args.run, args.room)
    if args.interior_command == "render":
        return render_room(
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
    if args.interior_command == "packet":
        return render_room_packet(
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
        )
    room_ids = None if args.rooms == "all" else tuple(item for item in args.rooms.split(",") if item)
    return render_gallery(
        args.run, room_ids=room_ids, shots=tuple(item for item in args.shots.split(",") if item),
        resource_pack=args.resource_pack, size=args.size, fov=args.fov, near=args.near, far=args.far,
        eye_height=args.eye_height, lighting=args.lighting, occlusion=args.occlusion, out=args.out,
        include_non_rooms=args.include_non_rooms,
    )


def dispatch(args: argparse.Namespace) -> Any:
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
