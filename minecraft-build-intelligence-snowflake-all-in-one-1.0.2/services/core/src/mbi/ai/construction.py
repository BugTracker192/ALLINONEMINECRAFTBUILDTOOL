from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any

from ..analysis import analyze_document
from ..canonical import BuildDocument, BuildRegion, BuildSource, IntBoundingBox, IntVector3, PaletteEntry
from ..patch import PatchEngine


class ConstructionStage(StrEnum):
    REQUIREMENTS = "requirements"
    DESIGN = "design"
    PALETTE = "palette"
    MASSING = "massing"
    LAYOUT = "layout"
    FACADE = "facade"
    INTERIOR = "interior"
    DETAIL = "detail"
    CRITIQUE = "critique"
    FINAL_VERIFICATION = "final_verification"
    COMPLETE = "complete"


@dataclass(frozen=True, slots=True)
class ConstructionBrief:
    name: str
    build_type: str = "building"
    style: str = "medieval"
    dimensions: tuple[int, int, int] = (32, 20, 32)
    floors: int = 2
    primary_axis: str = "north_south"
    interior_required: bool = True
    symmetry: str = "balanced"
    detail_density: str = "medium"
    export_format: str = "schem"
    palette: dict[str, str] = field(
        default_factory=lambda: {
            "foundation": "minecraft:stone_bricks",
            "wall": "minecraft:oak_planks",
            "trim": "minecraft:spruce_log[axis=y]",
            "roof": "minecraft:deepslate_tiles",
            "floor": "minecraft:spruce_planks",
            "window": "minecraft:glass_pane[north=false,east=false,south=false,west=false,waterlogged=false]",
            "light": "minecraft:lantern[hanging=true,waterlogged=false]",
            "door": "minecraft:oak_door[facing=north,half=lower,hinge=left,open=false,powered=false]",
        }
    )


@dataclass(slots=True)
class ConstructionRun:
    run_id: str
    brief: ConstructionBrief
    stage: ConstructionStage = ConstructionStage.REQUIREMENTS
    version_ids: list[str] = field(default_factory=list)
    stage_reports: list[dict[str, Any]] = field(default_factory=list)
    final_analysis: dict[str, Any] | None = None


def create_blank_document(brief: ConstructionBrief) -> BuildDocument:
    width, height, length = brief.dimensions
    if min(width, height, length) < 5:
        raise ValueError("construction dimensions must be at least 5 blocks on every axis")
    bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(width - 1, height - 1, length - 1))
    source_hash = hashlib.sha256((brief.name + repr(brief)).encode()).hexdigest()
    source = BuildSource(
        original_filename=f"{brief.name}.generated",
        detected_format="generated",
        compression="raw_nbt",
        source_sha256=source_hash,
        uploaded_size_bytes=0,
        decompressed_size_bytes=0,
    )
    palette = [PaletteEntry.from_state(0, "minecraft:air")]
    region = BuildRegion("Generated", bounds.min, bounds.dimensions, bounds, ("minecraft:air",))
    return BuildDocument(
        schema_version="1.1.0",
        build_id="build_" + source_hash[:20],
        source=source,
        metadata={"Name": brief.name, "generated": True, "brief": asdict(brief)},
        bounds=bounds,
        origin=bounds.min,
        palette=palette,
        regions=[region],
        blocks={},
        region_blocks={"Generated": {}},
    )


class AutonomousConstructionExecutor:
    """Deterministic staged construction and critique executor.

    It can run without an external model, while model-driven systems can produce or
    revise the structured ConstructionBrief before invoking the same safe patch path.
    """

    def __init__(self, brief: ConstructionBrief) -> None:
        self.brief = brief
        self.document = create_blank_document(brief)
        self.engine = PatchEngine(self.document)
        self.run = ConstructionRun("construct_" + self.document.source.source_sha256[:16], brief)

    def _commit(self, stage: ConstructionStage, operations: list[dict[str, object]], reason: str) -> None:
        patch = self.engine.create_patch(
            reason,
            "autonomous_constructor",
            self.document.bounds,
            self.document.bounds.volume,
            operations,
            expected_parent_hash=self.engine.active.document.content_hash,
            target_region="Generated",
        )
        self.engine.validate(patch)
        preview = self.engine.preview(patch)
        version = self.engine.commit(patch)
        self.document = version.document
        self.run.version_ids.append(version.version_id)
        self.run.stage = stage
        analysis = analyze_document(preview)
        self.run.stage_reports.append(
            {
                "stage": stage,
                "reason": reason,
                "patchId": patch.patch_id,
                "versionId": version.version_id,
                "changes": len(patch.changes),
                "previewHash": preview.content_hash,
                "summary": preview.to_summary(),
                "analysis": {
                    "components": analysis["components"]["count"],
                    "rooms": analysis["rooms"]["interiorVolumeCount"],
                    "navigationComponents": analysis["navigation"].get("componentCount"),
                    "darkCells": analysis["lighting"].get("darkCellCount"),
                    "largeFlatPatches": analysis["facade"].get("largeFlatPatchCount"),
                },
            }
        )

    def execute(self, *, critique_iterations: int = 2) -> ConstructionRun:
        width, height, length = self.brief.dimensions
        palette = self.brief.palette
        floor_height = max(4, (height - 4) // max(1, self.brief.floors))
        shell_max_y = min(height - 4, floor_height * self.brief.floors)

        self.run.stage = ConstructionStage.DESIGN
        self.run.stage_reports.append(
            {
                "stage": ConstructionStage.DESIGN,
                "design": {
                    "concept": f"{self.brief.style} {self.brief.build_type}",
                    "dimensions": self.brief.dimensions,
                    "floors": self.brief.floors,
                    "floorHeight": floor_height,
                    "primaryAxis": self.brief.primary_axis,
                    "constructionPhases": [stage.value for stage in ConstructionStage if stage not in {ConstructionStage.REQUIREMENTS, ConstructionStage.COMPLETE}],
                },
            }
        )
        self.run.stage = ConstructionStage.PALETTE
        self.run.stage_reports.append({"stage": ConstructionStage.PALETTE, "palette": palette})

        self._commit(
            ConstructionStage.MASSING,
            [
                {"type": "fill_cuboid", "min": [0, 0, 0], "max": [width - 1, 0, length - 1], "state": palette["foundation"]},
                {"type": "hollow_cuboid", "min": [1, 1, 1], "max": [width - 2, shell_max_y, length - 2], "state": palette["wall"]},
                {"type": "draw_roof", "min": [0, shell_max_y + 1, 0], "max": [width - 1, height - 1, length - 1], "state": palette["roof"], "style": "gable", "axis": "x" if self.brief.primary_axis == "east_west" else "z"},
            ],
            "Create foundation, primary shell, and roof massing.",
        )

        layout_ops: list[dict[str, object]] = []
        for floor in range(self.brief.floors):
            y = 1 + floor * floor_height
            layout_ops.append({"type": "draw_floor", "min": [2, y, 2], "max": [width - 3, y, length - 3], "state": palette["floor"], "y": y})
            if floor > 0:
                # A clear stairwell prevents disconnected floors; stairs are represented
                # as a navigable stepped line using exact state orientation.
                start_x = max(3, width // 4)
                start_z = max(3, length // 4)
                for step in range(floor_height):
                    layout_ops.append(
                        {
                            "type": "set_block",
                            "position": [start_x + step, y - floor_height + step, start_z],
                            "state": "minecraft:oak_stairs[facing=east,half=bottom,shape=straight,waterlogged=false]",
                        }
                    )
        # Main corridor partition and door openings.
        layout_ops.append({"type": "draw_wall", "start": [width // 2, 1, 2], "end": [width // 2, 1, length - 3], "height": shell_max_y, "state": palette["wall"]})
        for floor in range(self.brief.floors):
            base_y = 2 + floor * floor_height
            for dy in (0, 1):
                layout_ops.append({"type": "set_block", "position": [width // 2, base_y + dy, length // 2], "state": "minecraft:air"})
        self._commit(ConstructionStage.LAYOUT, layout_ops, "Create floor slabs, rooms, corridors, and vertical circulation.")

        facade_ops: list[dict[str, object]] = []
        spacing = 4 if self.brief.detail_density != "high" else 3
        for x in range(3, width - 3, spacing):
            for floor in range(self.brief.floors):
                y = 3 + floor * floor_height
                for z in (1, length - 2):
                    facade_ops.append({"type": "set_block", "position": [x, y, z], "state": palette["window"]})
                    facade_ops.append({"type": "set_block", "position": [x, y + 1, z], "state": palette["window"]})
        for z in range(3, length - 3, spacing):
            for floor in range(self.brief.floors):
                y = 3 + floor * floor_height
                for x in (1, width - 2):
                    facade_ops.append({"type": "set_block", "position": [x, y, z], "state": palette["window"]})
                    facade_ops.append({"type": "set_block", "position": [x, y + 1, z], "state": palette["window"]})
        # Trim columns at regular intervals.
        for x in range(1, width - 1, max(4, spacing * 2)):
            for z in (1, length - 2):
                facade_ops.append({"type": "draw_line", "start": [x, 1, z], "end": [x, shell_max_y, z], "state": palette["trim"]})
        for z in range(1, length - 1, max(4, spacing * 2)):
            for x in (1, width - 2):
                facade_ops.append({"type": "draw_line", "start": [x, 1, z], "end": [x, shell_max_y, z], "state": palette["trim"]})
        # Front entrance opening and two-block door.
        door_x = width // 2
        for y in (1, 2):
            facade_ops.append({"type": "set_block", "position": [door_x, y, 1], "state": "minecraft:air"})
        facade_ops.extend(
            [
                {"type": "set_block", "position": [door_x, 1, 1], "state": palette["door"]},
                {"type": "set_block", "position": [door_x, 2, 1], "state": palette["door"].replace("half=lower", "half=upper")},
            ]
        )
        self._commit(ConstructionStage.FACADE, facade_ops, "Add facade depth, windows, entrance, and trim rhythm.")

        if self.brief.interior_required:
            interior_ops: list[dict[str, object]] = []
            for floor in range(self.brief.floors):
                y = 3 + floor * floor_height
                for x in range(4, width - 4, 6):
                    interior_ops.append({"type": "set_block", "position": [x, y, length // 4], "state": palette["light"]})
                    interior_ops.append({"type": "set_block", "position": [x, y, 3 * length // 4], "state": palette["light"]})
                # Simple furnishing zones with tables and seating.
                interior_ops.append({"type": "fill_cuboid", "min": [3, 2 + floor * floor_height, 3], "max": [5, 2 + floor * floor_height, 5], "state": "minecraft:oak_slab[type=bottom,waterlogged=false]"})
                interior_ops.append({"type": "fill_cuboid", "min": [width - 6, 2 + floor * floor_height, length - 6], "max": [width - 4, 2 + floor * floor_height, length - 4], "state": "minecraft:bookshelf"})
            self._commit(ConstructionStage.INTERIOR, interior_ops, "Create lit, furnished, navigable interiors on every floor.")

        detail_ops: list[dict[str, object]] = []
        detail_state = "minecraft:cracked_stone_bricks" if "stone" in palette["foundation"] else palette["trim"]
        detail_ops.append({"type": "replace_blocks", "from": [palette["foundation"]], "to": detail_state, "min": [0, 0, 0], "max": [width - 1, 0, length - 1], "mask": {"type": "surface_noise", "seed": 91241, "probability": 0.08}})
        self._commit(ConstructionStage.DETAIL, detail_ops, "Apply restrained deterministic material variation.")

        for iteration in range(max(0, critique_iterations)):
            analysis = analyze_document(self.document)
            critique_ops: list[dict[str, object]] = []
            dark_cells = analysis["lighting"].get("darkCellSample", [])
            for item in dark_cells[: min(12, len(dark_cells))]:
                x, y, z = item["position"]
                if y + 1 < height:
                    critique_ops.append({"type": "set_block", "position": [x, y + 1, z], "state": palette["light"]})
            if not critique_ops:
                break
            self._commit(ConstructionStage.CRITIQUE, critique_ops, f"Critique iteration {iteration + 1}: improve dark interior areas.")

        self.run.stage = ConstructionStage.FINAL_VERIFICATION
        self.run.final_analysis = analyze_document(self.document)
        self.run.stage_reports.append(
            {
                "stage": ConstructionStage.FINAL_VERIFICATION,
                "summary": self.document.to_summary(),
                "checks": {
                    "unknownBlocks": [entry.canonical_state for entry in self.document.palette if entry.render_category == "unknown"],
                    "floatingComponents": self.run.final_analysis["components"]["floatingCount"],
                    "navigationComponents": self.run.final_analysis["navigation"].get("componentCount"),
                    "darkCells": self.run.final_analysis["lighting"].get("darkCellCount"),
                    "largeFlatPatches": self.run.final_analysis["facade"].get("largeFlatPatchCount"),
                },
            }
        )
        self.run.stage = ConstructionStage.COMPLETE
        return self.run
