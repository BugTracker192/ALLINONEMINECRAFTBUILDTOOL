from __future__ import annotations

import base64
import copy
import json
import os
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from mbi.ai.protocol import ModelRequest, MultimodalProvider
from mbi.ai.tools import BuildToolExecutor
from mbi.analysis import analyze_document
from mbi.export import export_litematic, export_sponge_v3, verify_round_trip
from mbi.canonical import IntBoundingBox, IntVector3
from mbi.patch import PatchEngine

from app.assets import open_resource_pack
from app.errors import AppError
from app.project import load_document, load_patch_engine, persist_patch_engine, save_document
from app.render import CameraSpec, SoftwareRenderer, pixel_to_block
from app.storage import atomic_write_json
from app.workflows import export_run, snapshot_run


@dataclass(slots=True)
class AgentRun:
    run_id: str
    task: str
    model: str
    provider: str
    status: str = "queued"
    iteration: int = 0
    evidence_ids: list[str] = field(default_factory=list)
    images_sent: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    pending_patch_ids: list[str] = field(default_factory=list)
    text: str = ""
    usage: dict[str, int] = field(default_factory=dict)
    context_estimates: list[dict[str, int]] = field(default_factory=list)
    error: dict[str, Any] | None = None


class AgentToolExecutor:
    def __init__(
        self,
        run_root: Path,
        engine: PatchEngine,
        *,
        resource_pack: str | Path | None,
        allow_commit: bool,
    ) -> None:
        self.run_root = run_root
        self.engine = engine
        self.resource_pack_path = resource_pack
        self.allow_commit = allow_commit
        self.core = BuildToolExecutor(lambda: self.engine.active.document, engine)
        self.new_images: list[Path] = []

    @staticmethod
    def definitions() -> tuple[dict[str, Any], ...]:
        definitions = list(BuildToolExecutor.definitions())
        vector = {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3}
        bounds = {"type": "object", "properties": {"min": vector, "max": vector}, "required": ["min", "max"], "additionalProperties": False}
        definitions.extend(
            [
                {
                    "type": "function",
                    "name": "render_view",
                    "description": "Render a new textured or flat orthographic/isometric view and return its evidence manifest.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "view": {"type": "string", "enum": ["north", "south", "east", "west", "top", "bottom", "isometric_ne", "isometric_nw", "isometric_se", "isometric_sw"]},
                            "size": {"type": "integer", "minimum": 128, "maximum": 2048},
                            "regions": {"type": "array", "items": {"type": "string"}},
                            "materials": {"type": "array", "items": {"type": "string"}},
                            "hideMaterials": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["view"],
                        "additionalProperties": False,
                    },
                },
                {
                    "type": "function",
                    "name": "render_crop",
                    "description": "Render a coordinate-bounded crop and return a grounded visual evidence manifest.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "bounds": bounds,
                            "view": {"type": "string"},
                            "size": {"type": "integer", "minimum": 128, "maximum": 2048},
                            "regions": {"type": "array", "items": {"type": "string"}},
                            "materials": {"type": "array", "items": {"type": "string"}},
                            "hideMaterials": {"type": "array", "items": {"type": "string"}},
                        },
                        "required": ["bounds"],
                        "additionalProperties": False,
                    },
                },
                {
                    "type": "function",
                    "name": "pixel_to_block",
                    "description": "Resolve an exact visible pixel from a snapshot manifest to its canonical coordinate and palette ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {"manifest": {"type": "string"}, "px": {"type": "integer"}, "py": {"type": "integer"}},
                        "required": ["manifest", "px", "py"],
                        "additionalProperties": False,
                    },
                },
                *[
                    {
                        "type": "function",
                        "name": name,
                        "description": description,
                        "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
                    }
                    for name, description in (
                        ("get_rooms", "Return grounded room and air-volume analysis."),
                        ("get_navigation_graph", "Return approximate player navigation analysis."),
                        ("get_components", "Return connected-component and floating-cluster analysis."),
                        ("get_facade_report", "Return facade flatness and depth analysis."),
                        ("get_lighting_report", "Return heuristic lighting coverage analysis."),
                        ("get_interior_report", "Return interior/exterior consistency findings."),
                    )
                ],
            ]
        )
        simple_read_tools = {
            "get_import_diagnostics": "Return structured import diagnostics.",
            "get_regions": "Return all source regions and exact bounds.",
            "get_floors": "Return detected floor-level summaries.",
            "get_symmetry_report": "Return grounded reflection symmetry metrics.",
            "find_block_entities": "Find block entities, optionally bounded.",
            "get_patch": "Return a pending transactional patch record.",
        }
        for name, description in simple_read_tools.items():
            definitions.append({"type": "function", "name": name, "description": description, "parameters": {"type": "object", "properties": {"patchId": {"type": "string"}}, "additionalProperties": True}})
        definitions.extend([
            {"type": "function", "name": "get_region", "description": "Return one named region.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}}, "required": ["name"], "additionalProperties": False}},
            {"type": "function", "name": "get_room", "description": "Return one room by ID.", "parameters": {"type": "object", "properties": {"id": {"type": "string"}}, "required": ["id"], "additionalProperties": False}},
            {"type": "function", "name": "get_component", "description": "Return one component by ID/index.", "parameters": {"type": "object", "properties": {"id": {"type": ["string", "integer"]}}, "required": ["id"], "additionalProperties": False}},
            {"type": "function", "name": "measure_distance", "description": "Measure Euclidean and Manhattan distance between exact coordinates.", "parameters": {"type": "object", "properties": {"a": vector, "b": vector}, "required": ["a", "b"], "additionalProperties": False}},
            {"type": "function", "name": "measure_bounds", "description": "Measure dimensions, area, and volume of bounds.", "parameters": {"type": "object", "properties": {"bounds": bounds}, "required": ["bounds"], "additionalProperties": False}},
            {"type": "function", "name": "find_material", "description": "Find exact coordinates using a canonical state or base block.", "parameters": {"type": "object", "properties": {"state": {"type": "string"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100000}}, "required": ["state"], "additionalProperties": False}},
            {"type": "function", "name": "find_nearest", "description": "Find nearest block matching a state from a coordinate.", "parameters": {"type": "object", "properties": {"position": vector, "state": {"type": "string"}}, "required": ["position", "state"], "additionalProperties": False}},
            {"type": "function", "name": "get_block_entity", "description": "Return exact block-entity NBT at a coordinate.", "parameters": {"type": "object", "properties": {"position": vector}, "required": ["position"], "additionalProperties": False}},
        ])
        for name in ("create_design_brief", "define_build_bounds", "define_palette_constraints", "create_floor_plan", "create_room_program", "create_build_phase", "estimate_materials", "validate_plan"):
            definitions.append({"type": "function", "name": name, "description": f"Structured planning operation: {name}.", "parameters": {"type": "object", "properties": {"artifact": {"type": "object"}}, "additionalProperties": True}})
        edit_names = (
            "set_block", "set_blocks", "fill_cuboid", "hollow_cuboid", "replace_blocks", "draw_line", "draw_polyline",
            "draw_wall", "draw_floor", "draw_roof", "draw_circle", "draw_ellipse", "draw_cylinder", "draw_sphere",
            "draw_dome", "draw_arch", "draw_bezier", "extrude_profile", "loft_profiles", "copy_region", "move_region",
            "rotate_region", "mirror_region", "scale_pattern_integer", "apply_noise_mask", "apply_gradient_palette",
            "paste_template", "clear_region", "set_block_entity", "remove_block_entity",
        )
        common_edit_properties = {
            "bounds": bounds, "maxAffectedBlocks": {"type": "integer", "minimum": 1, "maximum": 10000000},
            "reason": {"type": "string"}, "operation": {"type": "object"}, "preconditions": {"type": "array", "items": {"type": "object"}},
            "evidenceRefs": {"type": "array", "items": {"type": "string"}},
        }
        for name in edit_names:
            definitions.append({"type": "function", "name": name, "description": f"Create a bounded transactional {name} patch; does not commit automatically.", "parameters": {"type": "object", "properties": common_edit_properties, "required": ["bounds", "maxAffectedBlocks", "reason", "operation"], "additionalProperties": False}})
        for name in ("validate_patch", "create_checkpoint", "restore_checkpoint", "branch_version", "merge_versions"):
            definitions.append({"type": "function", "name": name, "description": f"Version/transaction operation: {name}.", "parameters": {"type": "object", "properties": {"patchId": {"type": "string"}, "name": {"type": "string"}, "versionId": {"type": "string"}, "sourceVersionId": {"type": "string"}, "reason": {"type": "string"}}, "additionalProperties": True}})
        for name in ("validate_export", "export_schem", "export_litematic", "get_export_artifact"):
            definitions.append({"type": "function", "name": name, "description": f"Export operation: {name}.", "parameters": {"type": "object", "properties": {"format": {"type": "string"}}, "additionalProperties": True}})
        return tuple(definitions)

    @staticmethod
    def _bounds(raw: Any) -> IntBoundingBox:
        if not isinstance(raw, dict):
            raise ValueError("bounds must be an object")
        return IntBoundingBox(IntVector3(*raw["min"]), IntVector3(*raw["max"]))

    def _render(
        self,
        *,
        view: str,
        crop: IntBoundingBox | None = None,
        size: int = 640,
        changed: frozenset[IntVector3] = frozenset(),
        regions: tuple[str, ...] = (),
        materials: tuple[str, ...] = (),
        hide_materials: tuple[str, ...] = (),
    ) -> dict[str, Any]:
        pack = open_resource_pack(self.resource_pack_path)
        try:
            result = SoftwareRenderer(self.engine.active.document, resource_pack=pack).render(
                self.run_root,
                camera=CameraSpec.preset(view),
                crop=crop,
                size=(size, size),
                mode="textured" if pack else "flat",
                changed_coordinates=changed,
                include_regions=regions,
                include_states=materials,
                exclude_states=hide_materials,
                name=f"agent_{view}_{uuid.uuid4().hex[:10]}",
            )
        finally:
            if pack:
                pack.close()
        self.new_images.append(result.png_path)
        return {
            "evidence_id": f"view:{view}:{result.snapshot_id}",
            "png": str(result.png_path.relative_to(self.run_root)),
            "manifest": str(result.manifest_path.relative_to(self.run_root)),
            "visible_bounds": result.manifest["visible_bounds"],
            "diagnostics": result.diagnostics,
        }

    def execute(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        analysis = None
        document = self.engine.active.document
        if name == "get_import_diagnostics":
            return {"evidence_id": f"diagnostics:{document.content_hash[:12]}", "diagnostics": [asdict(item) for item in document.diagnostics]}
        if name == "get_regions":
            return {"evidence_id": f"regions:{document.content_hash[:12]}", "regions": [asdict(item) for item in document.regions]}
        if name == "get_region":
            region = next((item for item in document.regions if item.name == str(arguments["name"])), None)
            return {"region": asdict(region) if region else None, "evidence_id": f"region:{arguments['name']}:{document.content_hash[:12]}"}
        if name in {"get_floors", "get_symmetry_report", "get_room", "get_component"}:
            analysis = analyze_document(document)
            if name == "get_floors":
                layers = analysis["materials"].get("byLayer", analysis["materials"].get("layerCounts", {}))
                return {"evidence_id": f"floors:{document.content_hash[:12]}", "layers": layers, "rooms": analysis["rooms"]}
            if name == "get_symmetry_report":
                return {"evidence_id": f"symmetry:{document.content_hash[:12]}", "result": analysis["symmetry"]}
            collection = analysis["rooms"].get("rooms", analysis["rooms"].get("interiorVolumes", [])) if name == "get_room" else analysis["components"].get("components", [])
            target = str(arguments["id"])
            item = next((value for value in collection if str(value.get("id", value.get("componentId", value.get("index")))) == target), None)
            return {"evidence_id": f"{name[4:]}:{target}:{document.content_hash[:12]}", "result": item}
        if name == "measure_distance":
            a, b = IntVector3(*arguments["a"]), IntVector3(*arguments["b"])
            dx, dy, dz = b.x-a.x, b.y-a.y, b.z-a.z
            return {"euclidean": (dx*dx+dy*dy+dz*dz) ** 0.5, "manhattan": abs(dx)+abs(dy)+abs(dz), "delta": [dx,dy,dz]}
        if name == "measure_bounds":
            box = self._bounds(arguments["bounds"]); d = box.dimensions
            return {"bounds": asdict(box), "dimensions": list(d.as_tuple()), "volume": box.volume, "surface_area": 2*(d.x*d.y+d.y*d.z+d.x*d.z)}
        if name in {"find_material", "find_nearest"}:
            state = str(arguments["state"]); palette = document.palette_by_id()
            matches = [(position, palette[pid].canonical_state) for position,pid in document.blocks.items() if palette[pid].canonical_state == state or palette[pid].canonical_state.split("[",1)[0] == state]
            if name == "find_nearest":
                origin = IntVector3(*arguments["position"]); matches.sort(key=lambda item: (abs(item[0].x-origin.x)+abs(item[0].y-origin.y)+abs(item[0].z-origin.z), item[0]))
                return {"result": {"position": list(matches[0][0].as_tuple()), "state": matches[0][1]} if matches else None}
            limit = int(arguments.get("limit", 10000)); matches.sort()
            return {"items": [{"position": list(point.as_tuple()), "state": value} for point,value in matches[:limit]], "truncated": len(matches)>limit}
        if name == "find_block_entities":
            return {"items": [asdict(item) for item in document.block_entities]}
        if name == "get_block_entity":
            point = IntVector3(*arguments["position"]); item = next((value for value in document.block_entities if value.position == point), None)
            return {"position": list(point.as_tuple()), "block_entity": asdict(item) if item else None}
        if name == "get_patch":
            patch = self.core.pending_patches.get(str(arguments.get("patchId", "")))
            return {"patch": asdict(patch) if patch else None}
        if name in {"create_design_brief", "define_build_bounds", "define_palette_constraints", "create_floor_plan", "create_room_program", "create_build_phase", "estimate_materials", "validate_plan"}:
            artifact = arguments.get("artifact", arguments)
            valid = isinstance(artifact, dict)
            digest = __import__("hashlib").sha256(json.dumps(artifact, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()[:16]
            relative = Path("ai") / "evidence" / f"{name}_{digest}.json"
            atomic_write_json(self.run_root / relative, {"artifact_type": name, "artifact": artifact, "valid": valid, "build_hash": document.content_hash})
            return {"artifact_type": name, "artifact": artifact, "valid": valid, "path": str(relative), "evidence_id": f"plan:{name}:{digest}"}
        edit_names = {"set_block", "set_blocks", "fill_cuboid", "hollow_cuboid", "replace_blocks", "draw_line", "draw_polyline", "draw_wall", "draw_floor", "draw_roof", "draw_circle", "draw_ellipse", "draw_cylinder", "draw_sphere", "draw_dome", "draw_arch", "draw_bezier", "extrude_profile", "loft_profiles", "copy_region", "move_region", "rotate_region", "mirror_region", "scale_pattern_integer", "apply_noise_mask", "apply_gradient_palette", "paste_template", "clear_region", "set_block_entity", "remove_block_entity"}
        if name in edit_names:
            operation = dict(arguments["operation"]); operation["type"] = name
            begin = {"reason": str(arguments["reason"]), "author": "ai", "bounds": arguments["bounds"], "maxAffectedBlocks": int(arguments["maxAffectedBlocks"]), "operations": [operation], "preconditions": list(arguments.get("preconditions", [])), "evidenceRefs": list(arguments.get("evidenceRefs", [])), "expectedParentHash": document.content_hash}
            return self.core.execute("begin_patch", begin, allow_commit=False)
        if name == "validate_patch":
            patch = self.core.pending_patches[str(arguments["patchId"])]; self.engine.validate(patch)
            return {"patchId": patch.patch_id, "status": patch.status.value, "validation": patch.validation_report}
        if name == "create_checkpoint":
            version_id = self.engine.create_checkpoint(str(arguments["name"]))
            persist_patch_engine(self.run_root, self.engine)
            return {"name": arguments["name"], "versionId": version_id}
        if name == "restore_checkpoint":
            version = self.engine.restore_checkpoint(str(arguments["name"])); persist_patch_engine(self.run_root, self.engine)
            return {"versionId": version.version_id, "contentHash": version.document.content_hash}
        if name == "branch_version":
            version = self.engine.branch_version(str(arguments["name"]), arguments.get("versionId"))
            persist_patch_engine(self.run_root, self.engine)
            return {"branch": arguments["name"], "versionId": version.version_id}
        if name == "merge_versions":
            version = self.engine.merge_versions(str(arguments["sourceVersionId"]), author="ai", reason=str(arguments.get("reason", "AI merge"))); persist_patch_engine(self.run_root, self.engine)
            return {"versionId": version.version_id, "contentHash": version.document.content_hash}
        if name in {"validate_export", "export_schem", "export_litematic"}:
            fmt = "litematic" if name == "export_litematic" or arguments.get("format") == "litematic" else "schem"
            return export_run(self.run_root, format_name=fmt, verify=True)
        if name == "get_export_artifact":
            candidates = sorted((self.run_root / "export").glob("out.*"))
            return {"artifacts": [str(path.relative_to(self.run_root)) for path in candidates]}
        if name in {"get_rooms", "get_navigation_graph", "get_components", "get_facade_report", "get_lighting_report", "get_interior_report"}:
            analysis = analyze_document(self.engine.active.document)
            keys = {
                "get_rooms": "rooms",
                "get_navigation_graph": "navigation",
                "get_components": "components",
                "get_facade_report": "facade",
                "get_lighting_report": "lighting",
                "get_interior_report": "interiorExterior",
            }
            return {"evidence_id": f"analysis:{keys[name]}:{self.engine.active.document.content_hash[:12]}", "result": analysis[keys[name]]}
        if name == "render_view":
            return self._render(
                view=str(arguments.get("view", "isometric_ne")),
                size=int(arguments.get("size", 640)),
                regions=tuple(str(item) for item in arguments.get("regions", [])),
                materials=tuple(str(item) for item in arguments.get("materials", [])),
                hide_materials=tuple(str(item) for item in arguments.get("hideMaterials", [])),
            )
        if name == "render_crop":
            return self._render(
                view=str(arguments.get("view", "isometric_ne")),
                crop=self._bounds(arguments["bounds"]),
                size=int(arguments.get("size", 640)),
                regions=tuple(str(item) for item in arguments.get("regions", [])),
                materials=tuple(str(item) for item in arguments.get("materials", [])),
                hide_materials=tuple(str(item) for item in arguments.get("hideMaterials", [])),
            )
        if name == "pixel_to_block":
            manifest = (self.run_root / str(arguments["manifest"])).resolve()
            try:
                manifest.relative_to(self.run_root.resolve())
            except ValueError as exc:
                raise AppError("AGENT_PATH_ESCAPE", "Snapshot manifest path escapes run root.", exit_code=60) from exc
            return {"evidence_id": f"pixel:{manifest.name}:{arguments['px']}:{arguments['py']}", "hit": pixel_to_block(manifest, int(arguments["px"]), int(arguments["py"]))}

        output = self.core.execute(name, arguments, allow_commit=self.allow_commit)
        if name == "preview_patch" and output.get("patchId"):
            patch = self.core.pending_patches[str(output["patchId"])]
            preview = self.engine.preview(patch)
            before = self.engine.active.document
            pack = open_resource_pack(self.resource_pack_path)
            try:
                before_result = SoftwareRenderer(before, resource_pack=pack).render(
                    self.run_root,
                    camera=CameraSpec.preset("isometric_ne"), crop=patch.intended_bounds, size=(640, 640),
                    mode="textured" if pack else "flat", name=f"agent_before_{patch.patch_id}",
                )
                after_result = SoftwareRenderer(preview, resource_pack=pack).render(
                    self.run_root,
                    camera=CameraSpec.preset("isometric_ne"), crop=patch.intended_bounds, size=(640, 640),
                    mode="textured" if pack else "flat", name=f"agent_after_{patch.patch_id}",
                    changed_coordinates=frozenset(change.position for change in patch.changes),
                )
            finally:
                if pack:
                    pack.close()
            self.new_images.extend([before_result.png_path, after_result.png_path])
            output["visual_evidence"] = [
                {"evidence_id": f"patch:{patch.patch_id}:before", "png": str(before_result.png_path.relative_to(self.run_root)), "manifest": str(before_result.manifest_path.relative_to(self.run_root))},
                {"evidence_id": f"patch:{patch.patch_id}:after", "png": str(after_result.png_path.relative_to(self.run_root)), "manifest": str(after_result.manifest_path.relative_to(self.run_root))},
            ]
        elif name == "commit_patch" and self.allow_commit and output.get("versionId"):
            persist_patch_engine(self.run_root, self.engine)
            patch = self.core.pending_patches[str(output["patchId"])]
            visual = self._render(
                view="isometric_ne",
                crop=patch.intended_bounds,
                size=640,
                changed=frozenset(change.position for change in patch.changes),
            )
            output["post_commit_visual_evidence"] = visual
        elif name == "rollback_patch" and self.allow_commit and output.get("activeVersionId"):
            patch_id = str(arguments["patchId"])
            output["patchId"] = patch_id
            persist_patch_engine(self.run_root, self.engine)
            patch = self.core.pending_patches[patch_id]
            visual = self._render(
                view="isometric_ne",
                crop=patch.intended_bounds,
                size=640,
                changed=frozenset(change.position for change in patch.changes),
            )
            output["post_rollback_visual_evidence"] = visual
        return output


class MultimodalAgent:
    def __init__(
        self,
        run_root: str | Path,
        provider: MultimodalProvider,
        model: str,
        *,
        provider_name: str,
        resource_pack: str | Path | None = None,
        allow_auto_commit: bool = False,
        max_context_tokens: int = 512_000,
        max_images: int = 16,
        max_image_bytes: int = 24 * 1024 * 1024,
        max_output_tokens: int = 4096,
    ) -> None:
        self.root = Path(run_root)
        self.provider = provider
        self.model = model
        self.provider_name = provider_name
        self.resource_pack = resource_pack
        self.allow_auto_commit = allow_auto_commit
        self.max_context_tokens = max(1, int(max_context_tokens))
        self.max_images = max(1, int(max_images))
        self.max_image_bytes = max(1, int(max_image_bytes))
        self.max_output_tokens = max(1, int(max_output_tokens))
        self.engine = load_patch_engine(self.root)
        self.document = self.engine.active.document
        self.tools = AgentToolExecutor(self.root, self.engine, resource_pack=resource_pack, allow_commit=allow_auto_commit)

    @staticmethod
    def _data_uri(path: Path) -> str:
        return "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode("ascii")

    @staticmethod
    def _image_payload_bytes(item: dict[str, Any]) -> int:
        value = str(item.get("image_url", ""))
        if not value.startswith("data:image/") or "," not in value:
            return 0
        encoded = value.split(",", 1)[1]
        return max(0, (len(encoded) * 3) // 4 - encoded.count("="))

    @classmethod
    def _trim_visual_context(
        cls,
        messages: list[dict[str, Any]],
        *,
        max_images: int,
        max_image_bytes: int,
    ) -> tuple[int, int]:
        """Keep the newest literal images while preserving all textual evidence IDs.

        Provider context limits are per request, not per agent lifetime. Old image
        pixels are therefore removed from message content once the bound is
        exceeded; their manifest references and tool outputs remain in context.
        """
        refs: list[tuple[list[dict[str, Any]], dict[str, Any]]] = []
        for message in messages:
            content = message.get("content")
            if not isinstance(content, list):
                continue
            for item in content:
                if isinstance(item, dict) and item.get("type") == "input_image":
                    refs.append((content, item))
        total_bytes = sum(cls._image_payload_bytes(item) for _, item in refs)
        while refs and (len(refs) > max_images or total_bytes > max_image_bytes):
            content, item = refs.pop(0)
            total_bytes -= cls._image_payload_bytes(item)
            content.remove(item)
        return len(refs), max(0, total_bytes)

    def _persist(self, run: AgentRun) -> None:
        atomic_write_json(self.root / "ai" / "runs" / f"{run.run_id}.json", asdict(run))

    def _initial_images(self, task: str) -> list[Path]:
        manifest_path = self.root / "snapshots" / "manifest.json"
        if not manifest_path.exists():
            snapshot_run(self.root, resource_pack=self.resource_pack, views=("global",), size=(640, 640))
        manifest = json.loads(manifest_path.read_text("utf-8"))
        snapshots = manifest.get("snapshots", [])
        names: list[str]
        lower = task.lower()
        if any(word in lower for word in ("interior", "room", "stair", "corridor", "floor")):
            names = ["global_isometric_ne", "global_top", "global_north", "global_south"]
        elif "rear" in lower or "back" in lower:
            names = ["global_south", "global_isometric_se", "global_east", "global_west"]
        else:
            names = ["global_isometric_ne", "global_north", "global_south", "global_top"]
        by_direction = {str(item.get("direction")): item for item in snapshots}
        result = []
        for name in names:
            candidate = self.root / "snapshots" / f"{name}.png"
            if candidate.exists():
                result.append(candidate)
        if not result:
            result = sorted((self.root / "snapshots").glob("global_*.png"))[:4]
        return result

    async def run(self, task: str, *, max_iterations: int = 8) -> AgentRun:
        run = AgentRun("airun_" + uuid.uuid4().hex[:20], task, self.model, self.provider_name)
        self._persist(run)
        try:
            capabilities = await self.provider.get_capabilities()
            if not capabilities.image_input:
                raise AppError("PROVIDER_NO_IMAGE_INPUT", "Selected provider cannot receive rendered build images.", exit_code=60)
            image_limit = max(1, min(capabilities.max_images or self.max_images, self.max_images))
            images: list[Path] = []
            selected_bytes = 0
            for candidate in self._initial_images(task):
                size_bytes = candidate.stat().st_size
                if len(images) >= image_limit:
                    break
                if images and selected_bytes + size_bytes > self.max_image_bytes:
                    continue
                images.append(candidate)
                selected_bytes += size_bytes
            if not images:
                raise AppError(
                    "AGENT_NO_VISUAL_EVIDENCE",
                    "No rendered image fit the configured multimodal evidence budget.",
                    {"max_images": image_limit, "max_image_bytes": self.max_image_bytes},
                    60,
                )
            summary = self.document.to_summary()
            analysis = analyze_document(self.document)
            evidence = []
            for path in images:
                manifest = path.with_suffix(".manifest.json")
                evidence_id = f"view:{path.stem}:{self.document.content_hash[:12]}"
                evidence.append({"evidence_id": evidence_id, "png": str(path.relative_to(self.root)), "manifest": str(manifest.relative_to(self.root)) if manifest.exists() else None})
                run.evidence_ids.append(evidence_id)
                run.images_sent.append(str(path.relative_to(self.root)))
            image_bytes = sum(path.stat().st_size for path in images)
            synopsis_text = json.dumps(summary, sort_keys=True, separators=(",", ":"), default=str)
            context_manifest = {
                "schema": "mbi.ai-context.v1",
                "task": task,
                "build_hash": self.document.content_hash,
                "summary": summary,
                "selected_images": evidence,
                "selected_analyses": ["materials", "components", "rooms", "navigation", "facade", "interiorExterior"],
                "estimated_text_tokens_before_tools": max(1, len(synopsis_text) // 4),
                "selected_image_bytes": image_bytes,
                "selected_image_count": len(images),
                "configured_limits": {
                    "max_context_tokens": self.max_context_tokens,
                    "max_images": self.max_images,
                    "max_image_bytes": self.max_image_bytes,
                    "max_output_tokens": self.max_output_tokens,
                },
                "provider_capability_assumptions": asdict(capabilities),
                "coordinate_space": "document",
                "excluded_data": ["full raw voxel field; available through exact paginated query tools"],
            }
            atomic_write_json(self.root / "ai" / "context_manifests" / f"{run.run_id}.json", context_manifest)
            content: list[dict[str, Any]] = [
                {
                    "type": "input_text",
                    "text": (
                        f"Task: {task}\n\nBuild summary:\n{json.dumps(summary, sort_keys=True, separators=(',', ':'))}\n\n"
                        f"Analysis overview:\n{json.dumps({key: analysis[key] for key in ('materials','components','rooms','navigation','facade','interiorExterior')}, sort_keys=True, separators=(',', ':'), default=str)}\n\n"
                        "The images below are deterministic CPU renders. Each has a semantic coordinate/depth/palette map. "
                        "Use tool calls for exact blocks and cite evidence IDs or coordinates in every finding."
                    ),
                }
            ]
            for item, path in zip(evidence, images, strict=True):
                content.append({"type": "input_text", "text": f"Evidence {item['evidence_id']} ({item['png']})"})
                content.append({"type": "input_image", "image_url": self._data_uri(path)})
            messages: list[dict[str, Any]] = [
                {
                    "role": "developer",
                    "content": (
                        "You are a Minecraft build architect operating a grounded voxel tool. You literally receive rendered images and exact symbolic tools. "
                        "Never infer an exact block ID from color alone. Cite view/slice/room/component/issue evidence IDs and exact coordinates. "
                        "Inspect macro form before micro detail. All edits must use bounded transactions, be previewed, and be visually re-inspected after change."
                    ),
                },
                {"role": "user", "content": content},
            ]
            run.status = "running"
            for iteration in range(max_iterations):
                run.iteration = iteration + 1
                self._persist(run)
                current_image_count, current_image_bytes = self._trim_visual_context(
                    messages,
                    max_images=image_limit,
                    max_image_bytes=self.max_image_bytes,
                )
                request = ModelRequest(
                    self.model,
                    tuple(copy.deepcopy(messages)),
                    AgentToolExecutor.definitions(),
                    min(self.max_output_tokens, capabilities.max_output_tokens or self.max_output_tokens),
                    {
                        "run_id": run.run_id,
                        "iteration": iteration + 1,
                        "image_count": current_image_count,
                        "image_bytes": current_image_bytes,
                    },
                )
                estimated_tokens = await self.provider.count_or_estimate_tokens(request)
                effective_context_limit = self.max_context_tokens
                if capabilities.max_context_tokens:
                    effective_context_limit = min(effective_context_limit, capabilities.max_context_tokens)
                run.context_estimates.append(
                    {
                        "iteration": iteration + 1,
                        "estimated_tokens": int(estimated_tokens),
                        "limit": int(effective_context_limit),
                        "image_count": current_image_count,
                    }
                )
                if estimated_tokens + (request.max_output_tokens or 0) > effective_context_limit:
                    raise AppError(
                        "AI_CONTEXT_BUDGET",
                        "Multimodal request exceeds the configured context budget.",
                        {
                            "estimated_tokens": estimated_tokens,
                            "reserved_output_tokens": request.max_output_tokens or 0,
                            "limit": effective_context_limit,
                            "image_count": current_image_count,
                        },
                        60,
                    )
                response = await self.provider.create_response(request)
                run.text += response.text
                for key, value in response.usage.items():
                    run.usage[key] = run.usage.get(key, 0) + int(value)
                if not response.tool_calls:
                    run.status = "completed"
                    self._persist(run)
                    return run
                messages.append({"role": "assistant", "content": response.text, "tool_calls": list(response.tool_calls)})
                self.tools.new_images.clear()
                waiting = False
                for call in response.tool_calls:
                    call_id = str(call.get("id") or "call_" + uuid.uuid4().hex[:12])
                    name = str(call.get("name"))
                    arguments = call.get("arguments") if isinstance(call.get("arguments"), dict) else {}
                    try:
                        output = self.tools.execute(name, arguments)
                    except Exception as exc:
                        output = {"error": {"code": getattr(exc, "code", "TOOL_FAILED"), "message": str(exc), "details": getattr(exc, "details", {})}}
                    run.tool_calls.append({"id": call_id, "name": name, "arguments": arguments, "output": output})
                    if output.get("patchId"):
                        run.pending_patch_ids.append(str(output["patchId"]))
                    if output.get("requiresApproval"):
                        waiting = True
                    messages.append(BuildToolExecutor.tool_output_message(call_id, output))
                if self.tools.new_images:
                    feedback: list[dict[str, Any]] = [{"type": "input_text", "text": "New deterministic visual feedback after your tool calls. Inspect it before further edits."}]
                    for path in self.tools.new_images:
                        relative = str(path.relative_to(self.root))
                        evidence_id = f"view:feedback:{path.stem}:{self.engine.active.document.content_hash[:12]}"
                        feedback.append({"type": "input_text", "text": f"Evidence {evidence_id} ({relative})"})
                        run.evidence_ids.append(evidence_id)
                        if path.stat().st_size <= self.max_image_bytes:
                            feedback.append({"type": "input_image", "image_url": self._data_uri(path)})
                            run.images_sent.append(relative)
                        else:
                            feedback.append(
                                {
                                    "type": "input_text",
                                    "text": "Image attachment omitted because this single PNG exceeds the configured byte budget; request a smaller render or crop.",
                                }
                            )
                    messages.append({"role": "user", "content": feedback})
                if waiting and not self.allow_auto_commit:
                    run.status = "waiting_approval"
                    self._persist(run)
                    return run
            run.status = "iteration_limit"
            self._persist(run)
            return run
        except Exception as exc:
            run.status = "failed"
            run.error = {"code": getattr(exc, "code", "AGENT_FAILED"), "message": str(exc), "details": getattr(exc, "details", {})}
            self._persist(run)
            return run


def _provider(name: str, api_key: str, base_url: str | None) -> MultimodalProvider:
    try:
        from mbi.ai.providers import AnthropicMessagesProvider, OpenAICompatibleChatProvider, OpenAIResponsesProvider
    except ModuleNotFoundError as exc:
        if exc.name == "httpx":
            raise AppError("PROVIDER_DEPENDENCY", "Live AI providers require the optional ai dependency: pip install .[ai]", exit_code=60) from exc
        raise
    if base_url:
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise AppError("PROVIDER_BASE_URL", "Provider base URL must be HTTP(S).", exit_code=60)
    if name == "openai":
        return OpenAIResponsesProvider(api_key=api_key, base_url=base_url or "https://api.openai.com")
    if name == "anthropic":
        return AnthropicMessagesProvider(api_key=api_key, base_url=base_url or "https://api.anthropic.com")
    if name == "openai-compatible":
        if not base_url:
            raise AppError("PROVIDER_BASE_URL", "OpenAI-compatible provider requires --base-url.", exit_code=60)
        return OpenAICompatibleChatProvider(api_key=api_key, base_url=base_url)
    raise AppError("PROVIDER_NAME", "Unsupported AI provider.", {"provider": name}, 60)


async def run_agent_cli(args: Any) -> dict[str, Any]:
    key = os.getenv(args.api_key_env, "")
    if not key and args.provider != "openai-compatible":
        raise AppError("PROVIDER_API_KEY", f"API key environment variable {args.api_key_env} is empty.", exit_code=60)
    task_path = Path(args.task)
    task = task_path.read_text("utf-8") if task_path.is_file() else str(args.task)
    provider = _provider(args.provider, key, args.base_url)
    agent = MultimodalAgent(
        args.run,
        provider,
        args.model,
        provider_name=args.provider,
        resource_pack=args.resource_pack,
        allow_auto_commit=args.auto_commit,
        max_context_tokens=args.max_context_tokens,
        max_images=args.max_images,
        max_image_bytes=args.max_image_bytes,
        max_output_tokens=args.max_output_tokens,
    )
    run = await agent.run(task, max_iterations=args.max_iterations)
    if run.status == "failed":
        raise AppError(run.error["code"] if run.error else "AGENT_FAILED", run.error["message"] if run.error else "Agent failed.", run.error.get("details", {}) if run.error else {}, 60)
    return asdict(run)


def run_tool_request_file(
    run_root: str | Path,
    request_file: str | Path,
    *,
    resource_pack: str | Path | None = None,
    allow_commit: bool = False,
    result_path: str | Path | None = None,
) -> dict[str, Any]:
    """Execute one or more JSON tool operations in-process.

    Accepted forms:
      {"tool": "get_block", "arguments": {...}}
      {"requests": [{"id": "...", "tool": "...", "arguments": {...}}, ...]}

    A batch shares one PatchEngine so begin/validate/preview/commit operations can
    safely reference earlier patch IDs using "$last_patch_id".
    """
    root = Path(run_root)
    request_path = Path(request_file)
    payload = json.loads(request_path.read_text("utf-8"))
    engine = load_patch_engine(root)
    document = engine.active.document
    executor = AgentToolExecutor(root, engine, resource_pack=resource_pack, allow_commit=allow_commit)
    requests = payload.get("requests") if isinstance(payload, dict) else None
    if requests is None:
        requests = [payload]
    if not isinstance(requests, list) or not requests:
        raise AppError("TOOL_REQUEST", "Tool request must contain a non-empty request or requests array.", exit_code=2)
    results: list[dict[str, Any]] = []
    last_patch_id: str | None = None
    for index, item in enumerate(requests):
        if not isinstance(item, dict):
            raise AppError("TOOL_REQUEST", "Each tool request must be an object.", {"index": index}, 2)
        name = str(item.get("tool") or item.get("name") or "")
        arguments = item.get("arguments", {})
        if not name or not isinstance(arguments, dict):
            raise AppError("TOOL_REQUEST", "Tool request requires a tool name and object arguments.", {"index": index}, 2)
        arguments = json.loads(json.dumps(arguments))
        for key, value in list(arguments.items()):
            if value == "$last_patch_id":
                if not last_patch_id:
                    raise AppError("TOOL_REFERENCE", "$last_patch_id was used before a patch was created.", {"index": index}, 40)
                arguments[key] = last_patch_id
        try:
            output = executor.execute(name, arguments)
            if output.get("patchId"):
                last_patch_id = str(output["patchId"])
            results.append({"id": item.get("id", f"tool_{index}"), "tool": name, "ok": True, "result": output})
        except Exception as exc:
            results.append({
                "id": item.get("id", f"tool_{index}"), "tool": name, "ok": False,
                "error": {"code": getattr(exc, "code", "TOOL_FAILED"), "message": str(exc), "details": getattr(exc, "details", {})},
            })
            if not bool(payload.get("continue_on_error", False)):
                break
    if engine.active.document.content_hash != document.content_hash:
        persist_patch_engine(root, engine)
    response = {
        "schema": "mbi.tool-results.v1",
        "run_root": str(root),
        "request_count": len(requests),
        "completed_count": len(results),
        "active_version_id": engine.active.version_id,
        "active_content_hash": engine.active.document.content_hash,
        "results": results,
    }
    destination = Path(result_path) if result_path else root / "ai" / "tool_results" / (request_path.stem + ".result.json")
    atomic_write_json(destination, response)
    response["result_file"] = str(destination)
    return response
