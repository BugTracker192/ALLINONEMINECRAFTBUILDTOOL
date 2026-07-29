from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from mbi.analysis.structures import (
    classify_block_name,
    structure_inventory_payload,
)
from mbi.canonical import IntBoundingBox, IntVector3
from mbi.importer import import_build

from app.cli import LEGACY, build_parser
from app.errors import AppError
from app.structures import _sample_sightline, _surface_route


def test_structure_inventory_streams_spatial_classification(
    reference_schem: Path,
) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    report = structure_inventory_payload(
        document,
        minimum_blocks=1,
        window_edge=8,
    )
    streaming = report["classification"]["streaming"]

    assert streaming["method"] == "single-pass-spatial-window-aggregation-v1"
    assert streaming["processedPlacedBlocks"] == len(document.blocks)
    assert streaming["additionalCoordinateClassificationMap"] is False
    assert streaming["peakPlacedBlocksInWindow"] <= len(document.blocks)
    assert classify_block_name("grass_block") == "terrain"
    assert classify_block_name("bamboo_trapdoor") == "built"
    assert classify_block_name("sandstone_wall") == "built"
    assert classify_block_name("stripped_dark_oak_log") == "built"
    assert classify_block_name("grindstone") == "prop"
    assert classify_block_name("dark_oak_log") == "vegetation"
    assert report["configuration"]["analysis_window_edge_blocks"] == 8


def test_approach_sightline_names_exact_blockers() -> None:
    blocker = IntVector3(2, 1, 0)
    document = SimpleNamespace(blocks={blocker: 0})
    target_bounds = IntBoundingBox(
        IntVector3(5, 0, -1),
        IntVector3(6, 3, 1),
    )
    result = _sample_sightline(
        document,
        (0.5, 1.5, 0.5),
        (5.5, 1.5, 0.5),
        target_bounds,
    )

    assert result["visible"] is False
    assert result["blockerCount"] == 1
    assert result["blockers"] == [[2, 1, 0]]


def test_settlement_route_uses_walkable_surface_and_elevation_cost() -> None:
    surface = {
        (0, 0): 4,
        (1, 0): 4,
        (2, 0): 5,
        (3, 0): 5,
    }
    route = _surface_route(surface, (0, 0), (3, 0))

    assert route["reachable"] is True
    assert route["pathLengthBlocks"] == 3
    assert route["elevationChange"] == 1
    assert route["path"] == [
        [0, 5, 0],
        [1, 5, 0],
        [2, 6, 0],
        [3, 6, 0],
    ]


def test_analyze_structure_resolves_bounds_before_cloning(
    monkeypatch,
    tmp_path: Path,
) -> None:
    bounds = IntBoundingBox(IntVector3(1, 2, 3), IntVector3(4, 5, 6))
    captured = {}
    parser = build_parser()
    args = parser.parse_args(
        [
            "analyze",
            str(tmp_path / "source"),
            "--structure",
            "keep",
            "--out",
            str(tmp_path / "scoped"),
        ]
    )
    monkeypatch.setattr(
        "app.structures.resolve_structure_bounds",
        lambda run, identifier: bounds,
    )
    monkeypatch.setattr(
        LEGACY,
        "clone_run_base",
        lambda source, output: Path(output),
    )

    def fake_analyze(target, **kwargs):
        captured.update(target=target, **kwargs)
        return {"ok": True}

    monkeypatch.setattr(LEGACY, "analyze_run", fake_analyze)

    assert LEGACY.dispatch(args) == {"ok": True}
    assert captured["bounds"] == bounds
    assert captured["seal_structure_envelope"] is True
    assert captured["target"] == tmp_path / "scoped"


def test_analyze_bounds_can_enable_structure_envelope(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "analyze",
            str(tmp_path),
            "--bounds",
            "0,0,0,4,3,4",
            "--seal-structure-envelope",
        ]
    )

    assert args.seal_structure_envelope is True


def test_analyze_rejects_conflicting_structure_and_bounds(tmp_path: Path) -> None:
    parser = build_parser()
    args = parser.parse_args(
        [
            "analyze",
            str(tmp_path),
            "--structure",
            "keep",
            "--bounds",
            "0,0,0,1,1,1",
        ]
    )
    with pytest.raises(AppError, match="cannot be supplied together"):
        LEGACY.dispatch(args)
