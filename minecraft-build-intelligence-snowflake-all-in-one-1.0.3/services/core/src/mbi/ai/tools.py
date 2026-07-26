from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from ..analysis import analyze_document
from ..canonical import BuildDocument, IntBoundingBox, IntVector3
from ..chunking import CHUNK_SIZE, build_chunks
from ..patch import PatchEngine
from ..snapshot import render_palette_layer
from .context import run_length_slice


class BuildToolExecutor:
    def __init__(self, document_getter, engine: PatchEngine) -> None:
        self._document_getter = document_getter
        self.engine = engine
        self.pending_patches: dict[str, Any] = {}

    @property
    def document(self) -> BuildDocument:
        return self._document_getter()

    @staticmethod
    def definitions() -> tuple[dict[str, Any], ...]:
        def tool(name: str, description: str, properties: dict[str, Any], required: list[str] | None = None) -> dict[str, Any]:
            return {
                "type": "function",
                "name": name,
                "description": description,
                "parameters": {
                    "type": "object",
                    "properties": properties,
                    "required": required or [],
                    "additionalProperties": False,
                },
            }

        vector = {"type": "array", "items": {"type": "integer"}, "minItems": 3, "maxItems": 3}
        bounds = {
            "type": "object",
            "properties": {"min": vector, "max": vector},
            "required": ["min", "max"],
            "additionalProperties": False,
        }
        return (
            tool("get_build_summary", "Return the canonical build summary.", {}),
            tool("get_analysis", "Return deterministic structural analyses.", {}),
            tool("get_material_histogram", "Return exact canonical-state and base-block material histograms.", {}),
            tool("get_palette", "Return exact canonical palette states.", {}),
            tool("get_block", "Return the exact block state and block entity at a coordinate.", {"position": vector}, ["position"]),
            tool("query_blocks", "Return exact non-air blocks inside a bounding box.", {"bounds": bounds, "limit": {"type": "integer", "minimum": 1, "maximum": 100000}}, ["bounds"]),
            tool("get_chunk", "Return exact non-air blocks and deterministic metadata for a 16x16x16 canonical chunk.", {"chunk": vector}, ["chunk"]),
            tool("get_slice", "Return exact blocks for an X, Y, or Z slice; Y slices also include run-length rows.", {"axis": {"type": "string", "enum": ["x", "y", "z"]}, "index": {"type": "integer"}, "y": {"type": "integer"}, "limit": {"type": "integer", "minimum": 1, "maximum": 100000}}, []),
            tool("render_layer", "Generate a deterministic semantic layer PNG manifest.", {"y": {"type": "integer"}, "pixelsPerBlock": {"type": "integer", "minimum": 1, "maximum": 32}}, ["y"]),
            tool("begin_patch", "Create and validate a bounded transactional patch.", {"reason": {"type": "string"}, "author": {"type": "string"}, "bounds": bounds, "maxAffectedBlocks": {"type": "integer", "minimum": 1, "maximum": 10000000}, "operations": {"type": "array", "items": {"type": "object"}}, "preconditions": {"type": "array", "items": {"type": "object"}}, "expectedParentHash": {"type": "string"}, "targetRegion": {"type": "string"}, "evidenceRefs": {"type": "array", "items": {"type": "string"}}}, ["reason", "bounds", "maxAffectedBlocks", "operations"]),
            tool("preview_patch", "Preview a previously created patch.", {"patchId": {"type": "string"}}, ["patchId"]),
            tool("commit_patch", "Commit a previously validated patch when automatic commit is permitted.", {"patchId": {"type": "string"}}, ["patchId"]),
            tool("rollback_patch", "Rollback the active committed patch.", {"patchId": {"type": "string"}}, ["patchId"]),
            tool("reject_patch", "Reject a pending patch without applying it.", {"patchId": {"type": "string"}, "reason": {"type": "string"}}, ["patchId"]),
            tool("compare_versions", "Compare exact canonical states between two versions.", {"a": {"type": "string"}, "b": {"type": "string"}}, ["a", "b"]),
        )

    @staticmethod
    def _vec(raw: Any) -> IntVector3:
        if not isinstance(raw, list) or len(raw) != 3:
            raise ValueError("position must contain three integers")
        return IntVector3(*(int(value) for value in raw))

    @classmethod
    def _bounds(cls, raw: Any) -> IntBoundingBox:
        if not isinstance(raw, dict):
            raise ValueError("bounds must be an object")
        return IntBoundingBox(cls._vec(raw["min"]), cls._vec(raw["max"]))

    def execute(self, name: str, arguments: dict[str, Any], *, allow_commit: bool = False) -> dict[str, Any]:
        document = self.document
        if name == "get_build_summary":
            return document.to_summary()
        if name == "get_analysis":
            return analyze_document(document)
        if name == "get_material_histogram":
            return {"evidenceId": f"materials:{document.content_hash[:12]}", "result": analyze_document(document)["materials"]}
        if name == "get_palette":
            return {"palette": [asdict(entry) for entry in document.palette]}
        if name == "get_block":
            position = self._vec(arguments["position"])
            entry = document.state_at(position)
            entity = next((item for item in document.block_entities if item.position == position), None)
            return {"position": position.as_tuple(), "state": asdict(entry), "blockEntity": asdict(entity) if entity else None}
        if name == "query_blocks":
            bounds = self._bounds(arguments["bounds"])
            limit = int(arguments.get("limit", 10000))
            palette = document.palette_by_id()
            rows = []
            for position, palette_id in sorted(document.blocks.items()):
                if bounds.contains(position):
                    rows.append({"position": position.as_tuple(), "state": palette[palette_id].canonical_state})
                    if len(rows) >= limit:
                        break
            return {"coordinateSpace": "document", "items": rows, "truncated": len(rows) == limit}
        if name == "get_chunk":
            chunk = self._vec(arguments["chunk"])
            blob = next((item for item in build_chunks(document) if item.coordinate == chunk), None)
            palette = document.palette_by_id()
            minimum = IntVector3(chunk.x * CHUNK_SIZE, chunk.y * CHUNK_SIZE, chunk.z * CHUNK_SIZE)
            maximum = IntVector3(minimum.x + CHUNK_SIZE - 1, minimum.y + CHUNK_SIZE - 1, minimum.z + CHUNK_SIZE - 1)
            exact = [
                {"position": position.as_tuple(), "paletteId": palette_id, "state": palette[palette_id].canonical_state}
                for position, palette_id in sorted(document.blocks.items())
                if minimum.x <= position.x <= maximum.x and minimum.y <= position.y <= maximum.y and minimum.z <= position.z <= maximum.z
            ]
            return {
                "evidenceId": f"chunk:{chunk.x}:{chunk.y}:{chunk.z}:{document.content_hash[:12]}",
                "coordinateSpace": "document",
                "chunk": chunk.as_tuple(),
                "metadata": ({
                    "encoding": blob.encoding.value, "contentHash": blob.content_hash, "nonAirCount": blob.non_air_count,
                    "materialHistogram": blob.material_histogram, "byteLength": len(blob.data),
                } if blob else {"encoding": "single-air", "contentHash": None, "nonAirCount": 0, "materialHistogram": {}, "byteLength": 0}),
                "blocks": exact,
            }
        if name == "get_slice":
            axis = str(arguments.get("axis", "y"))
            index = int(arguments.get("index", arguments.get("y", 0)))
            if axis not in {"x", "y", "z"}:
                raise ValueError("slice axis must be x, y, or z")
            limit = int(arguments.get("limit", 100000))
            palette = document.palette_by_id()
            rows = []
            for position, palette_id in sorted(document.blocks.items()):
                if getattr(position, axis) == index:
                    rows.append({"position": position.as_tuple(), "paletteId": palette_id, "state": palette[palette_id].canonical_state})
                    if len(rows) >= limit:
                        break
            result = {
                "evidenceId": f"slice:{axis}:{index}:{document.content_hash[:12]}",
                "coordinateSpace": "document", "axis": axis, "index": index, "items": rows, "truncated": len(rows) == limit,
            }
            if axis == "y":
                result["runLengthRows"] = asdict(run_length_slice(document, index))
            return result
        if name == "render_layer":
            image, manifest = render_palette_layer(document, int(arguments["y"]), pixels_per_block=int(arguments.get("pixelsPerBlock", 4)))
            return {"manifest": asdict(manifest), "imageBytes": len(image)}
        if name == "begin_patch":
            patch = self.engine.create_patch(
                str(arguments["reason"]),
                str(arguments.get("author", "ai")),
                self._bounds(arguments["bounds"]),
                int(arguments["maxAffectedBlocks"]),
                list(arguments["operations"]),
                preconditions=list(arguments.get("preconditions", [])),
                expected_parent_hash=str(arguments.get("expectedParentHash", document.content_hash)),
                target_region=arguments.get("targetRegion"),
                evidence_refs=[str(item) for item in arguments.get("evidenceRefs", [])],
            )
            self.engine.validate(patch)
            self.pending_patches[patch.patch_id] = patch
            return {"patchId": patch.patch_id, "status": patch.status, "validation": patch.validation_report}
        if name == "preview_patch":
            patch = self.pending_patches[str(arguments["patchId"])]
            preview = self.engine.preview(patch)
            return {"patchId": patch.patch_id, "status": patch.status, "preview": patch.preview_report, "summary": preview.to_summary()}
        if name == "commit_patch":
            if not allow_commit:
                return {"requiresApproval": True, "patchId": str(arguments["patchId"])}
            patch = self.pending_patches[str(arguments["patchId"])]
            version = self.engine.commit(patch)
            return {"patchId": patch.patch_id, "status": patch.status, "versionId": version.version_id, "contentHash": version.document.content_hash}
        if name == "rollback_patch":
            if not allow_commit:
                return {"requiresApproval": True, "patchId": str(arguments["patchId"]), "operation": "rollback"}
            version = self.engine.rollback_patch(str(arguments["patchId"]))
            return {"activeVersionId": version.version_id, "contentHash": version.document.content_hash}
        if name == "reject_patch":
            patch = self.pending_patches[str(arguments["patchId"])]
            self.engine.reject(patch, reason=str(arguments.get("reason", "Rejected by operator")))
            return {"patchId": patch.patch_id, "status": patch.status.value, "rejectionReason": patch.validation_report.get("rejectionReason")}
        if name == "compare_versions":
            a = self.engine.versions[str(arguments["a"])].document
            b = self.engine.versions[str(arguments["b"])].document
            a_palette = a.palette_by_id()
            b_palette = b.palette_by_id()
            changes = []
            for position in sorted(set(a.blocks) | set(b.blocks)):
                a_state = a_palette[a.blocks[position]].canonical_state if position in a.blocks else "minecraft:air"
                b_state = b_palette[b.blocks[position]].canonical_state if position in b.blocks else "minecraft:air"
                if a_state != b_state:
                    changes.append({"position": position.as_tuple(), "before": a_state, "after": b_state})
                    if len(changes) >= 10000:
                        break
            return {"changes": changes, "truncated": len(changes) == 10000}
        raise ValueError(f"unknown tool {name}")

    @staticmethod
    def tool_output_message(call_id: str, output: dict[str, Any]) -> dict[str, Any]:
        return {
            "type": "function_call_output",
            "call_id": call_id,
            "output": json.dumps(output, sort_keys=True, separators=(",", ":"), default=str),
        }
