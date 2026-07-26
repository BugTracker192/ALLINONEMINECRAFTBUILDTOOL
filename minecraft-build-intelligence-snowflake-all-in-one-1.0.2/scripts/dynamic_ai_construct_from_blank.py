from __future__ import annotations

import argparse
import asyncio
import json
import shutil
from pathlib import Path
from typing import Any

from app.ai.multimodal import MultimodalAgent
from app.project import load_document, save_document
from app.workflows import analyze_run, export_run
from mbi.ai.construction import ConstructionBrief, create_blank_document
from mbi.ai.protocol import ModelRequest, ModelResponse, ProviderCapabilities


class ArchitectProvider:
    """Deterministic provider harness that behaves like a tool-using architect.

    It deliberately starts from an all-air canonical document and can only create
    the build through the public AI tool protocol. Every geometry stage is
    previewed, committed, and followed by literal rendered-image feedback.
    """

    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []
        self.first_patch: str | None = None
        self.second_patch: str | None = None

    async def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(text_input=True, image_input=True, tool_calling=True, max_images=32)

    async def count_or_estimate_tokens(self, request: ModelRequest) -> int:
        return 2000 + 400 * sum(
            1
            for message in request.messages
            if isinstance(message.get("content"), list)
            for item in message["content"]
            if isinstance(item, dict) and item.get("type") == "input_image"
        )

    @staticmethod
    def _outputs(request: ModelRequest) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for message in request.messages:
            if message.get("type") == "function_call_output":
                rows.append(json.loads(message["output"]))
        return rows

    @staticmethod
    def _call(identifier: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        return {"id": identifier, "name": name, "arguments": arguments}

    async def create_response(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        n = len(self.requests)
        outputs = self._outputs(request)
        if n == 1:
            return ModelResponse(
                "a1",
                "Define an evidence-backed design before placing blocks.",
                (self._call("brief", "create_design_brief", {"artifact": {
                    "concept": "compact fortified observatory",
                    "dimensions": [16, 12, 16],
                    "floors": 2,
                    "rooms": ["entry hall", "workshop", "upper observatory"],
                    "circulation": "central stair",
                    "palette": ["stone_bricks", "spruce", "deepslate_tiles", "glass", "lantern"],
                }}),),
                {},
            )
        if n == 2:
            massing = {
                "reason": "Construct the planned foundation, shell, tower mass, and roof.",
                "author": "architect-agent",
                "bounds": {"min": [0, 0, 0], "max": [15, 11, 15]},
                "maxAffectedBlocks": 4096,
                "evidenceRefs": ["plan:create_design_brief"],
                "operations": [
                    {"type": "fill_cuboid", "min": [0, 0, 0], "max": [15, 0, 15], "state": "minecraft:stone_bricks"},
                    {"type": "hollow_cuboid", "min": [1, 1, 1], "max": [14, 8, 14], "state": "minecraft:stone_bricks"},
                    {"type": "hollow_cuboid", "min": [5, 1, 5], "max": [10, 10, 10], "state": "minecraft:spruce_planks"},
                    {"type": "draw_roof", "min": [0, 9, 0], "max": [15, 11, 15], "state": "minecraft:deepslate_tiles", "style": "gable", "axis": "z"},
                ],
            }
            return ModelResponse("a2", "Build macro forms transactionally.", (self._call("mass", "begin_patch", massing),), {})
        if n == 3:
            self.first_patch = next(row["patchId"] for row in outputs if row.get("patchId"))
            return ModelResponse("a3", "Preview massing before commit.", (self._call("preview1", "preview_patch", {"patchId": self.first_patch}),), {})
        if n == 4:
            return ModelResponse("a4", "Commit accepted massing.", (self._call("commit1", "commit_patch", {"patchId": self.first_patch}),), {})
        if n == 5:
            return ModelResponse(
                "a5",
                "Inspect the committed silhouette from two sides.",
                (
                    self._call("north", "render_view", {"view": "north", "size": 384}),
                    self._call("iso", "render_view", {"view": "isometric_ne", "size": 384}),
                ),
                {},
            )
        if n == 6:
            detail = {
                "reason": "Add aligned floors, circulation, windows, entrance, lighting, and functional interior details after visual inspection.",
                "author": "architect-agent",
                "bounds": {"min": [0, 0, 0], "max": [15, 11, 15]},
                "maxAffectedBlocks": 4096,
                "evidenceRefs": ["view:north", "view:isometric_ne"],
                "operations": [
                    {"type": "draw_floor", "min": [2, 4, 2], "max": [13, 4, 13], "y": 4, "state": "minecraft:spruce_planks"},
                    {"type": "draw_wall", "start": [8, 1, 2], "end": [8, 1, 13], "height": 7, "state": "minecraft:spruce_planks"},
                    {"type": "set_blocks", "blocks": [
                        {"position": [7, 1, 1], "state": "minecraft:air"},
                        {"position": [7, 2, 1], "state": "minecraft:air"},
                        {"position": [7, 1, 1], "state": "minecraft:oak_door[facing=north,half=lower,hinge=left,open=false,powered=false]"},
                        {"position": [7, 2, 1], "state": "minecraft:oak_door[facing=north,half=upper,hinge=left,open=false,powered=false]"},
                        {"position": [3, 3, 1], "state": "minecraft:glass"},
                        {"position": [12, 3, 1], "state": "minecraft:glass"},
                        {"position": [3, 6, 14], "state": "minecraft:glass"},
                        {"position": [12, 6, 14], "state": "minecraft:glass"},
                        {"position": [4, 3, 4], "state": "minecraft:lantern[hanging=false,waterlogged=false]"},
                        {"position": [11, 3, 11], "state": "minecraft:lantern[hanging=false,waterlogged=false]"},
                        {"position": [7, 5, 7], "state": "minecraft:lantern[hanging=true,waterlogged=false]"}
                    ]},
                    {"type": "draw_line", "start": [3, 1, 7], "end": [7, 5, 7], "state": "minecraft:oak_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]"},
                    {"type": "fill_cuboid", "min": [3, 1, 3], "max": [5, 1, 5], "state": "minecraft:oak_slab[type=bottom,waterlogged=false]"},
                    {"type": "fill_cuboid", "min": [10, 5, 10], "max": [12, 5, 12], "state": "minecraft:bookshelf"}
                ],
            }
            return ModelResponse("a6", "Apply the visual critique as a bounded second phase.", (self._call("detail", "begin_patch", detail),), {})
        if n == 7:
            patch_ids = [row["patchId"] for row in outputs if row.get("patchId")]
            self.second_patch = patch_ids[-1]
            return ModelResponse("a7", "Preview interior and facade changes.", (self._call("preview2", "preview_patch", {"patchId": self.second_patch}),), {})
        if n == 8:
            return ModelResponse("a8", "Commit the reviewed detail phase.", (self._call("commit2", "commit_patch", {"patchId": self.second_patch}),), {})
        if n == 9:
            return ModelResponse(
                "a9",
                "Re-render the completed build and inspect navigation, rooms, facade, and exact slices.",
                (
                    self._call("finaliso", "render_view", {"view": "isometric_sw", "size": 512}),
                    self._call("rooms", "get_rooms", {}),
                    self._call("nav", "get_navigation_graph", {}),
                    self._call("facade", "get_facade_report", {}),
                    self._call("slice", "get_slice", {"axis": "y", "index": 4, "limit": 10000}),
                ),
                {},
            )
        if n == 10:
            return ModelResponse("a10", "Export the visually and structurally reviewed build with exact round-trip verification.", (self._call("export", "export_schem", {}),), {})
        return ModelResponse("a11", "Construction, visual critique, exact-data inspection, and verified export are complete.", (), {})

    async def stream_response(self, request: ModelRequest):
        if False:
            yield None

    async def cancel(self, request_id: str) -> None:
        return None


def _has_literal_image(request: ModelRequest) -> bool:
    return any(
        isinstance(message.get("content"), list)
        and any(
            isinstance(item, dict)
            and item.get("type") == "input_image"
            and str(item.get("image_url", "")).startswith("data:image/png;base64,")
            for item in message["content"]
        )
        for message in request.messages
    )


async def main_async(args: argparse.Namespace) -> dict[str, Any]:
    root = args.root.resolve()
    if root.exists():
        shutil.rmtree(root)
    root.mkdir(parents=True)
    brief = ConstructionBrief(
        name="AI Fortified Observatory",
        build_type="fortified observatory",
        style="medieval scientific",
        dimensions=(16, 12, 16),
        floors=2,
        interior_required=True,
    )
    blank = create_blank_document(brief)
    save_document(root, blank)
    provider = ArchitectProvider()
    agent = MultimodalAgent(
        root,
        provider,
        "architect-harness",
        provider_name="dynamic-local",
        resource_pack=args.resource_pack,
        allow_auto_commit=True,
        max_images=24,
        max_context_tokens=1_000_000,
    )
    run = await agent.run("Design and construct a complete fortified observatory, inspect it visually and symbolically, revise it, and export it.", max_iterations=16)
    document = load_document(root)
    analysis = analyze_run(root)["results"]
    export = export_run(root, format_name="schem", verify=True)
    tool_names = [item["name"] for item in run.tool_calls]
    required = {
        "create_design_brief", "begin_patch", "preview_patch", "commit_patch",
        "render_view", "get_rooms", "get_navigation_graph", "get_facade_report",
        "get_slice", "export_schem",
    }
    image_requests = [index + 1 for index, request in enumerate(provider.requests) if _has_literal_image(request)]
    result = {
        "schema": "mbi.dynamic-ai-construct-from-blank.v1",
        "passed": (
            run.status == "completed"
            and required.issubset(tool_names)
            and len(document.blocks) > 500
            and len(image_requests) >= 5
            and export["passed"]
            and export["coordinate_mismatches"] == 0
            and export["state_mismatches"] == 0
        ),
        "status": run.status,
        "request_count": len(provider.requests),
        "literal_image_request_numbers": image_requests,
        "tool_sequence": tool_names,
        "non_air_blocks": len(document.blocks),
        "palette_size": len(document.palette),
        "room_count": analysis["rooms"].get("interiorVolumeCount", 0),
        "navigation_components": analysis["navigation"].get("componentCount", 0),
        "images_sent": run.images_sent,
        "version_count": len(json.loads((root / "versions" / "manifest.json").read_text("utf-8"))["versions"]),
        "export": export,
    }
    (root / "dynamic_ai_construct_report.json").write_text(json.dumps(result, sort_keys=True, indent=2) + "\n", "utf-8")
    if not result["passed"]:
        raise SystemExit(json.dumps(result, indent=2, default=str))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resource-pack", required=True, type=Path)
    parser.add_argument("--root", required=True, type=Path)
    args = parser.parse_args()
    print(json.dumps(asyncio.run(main_async(args)), sort_keys=True, indent=2, default=str))


if __name__ == "__main__":
    main()
