from __future__ import annotations

import json
import math
from collections import Counter
from pathlib import Path
from typing import Any

from mbi.analysis import analyze_document
from mbi.canonical import BuildDocument, IntBoundingBox
from mbi.scoping import scoped_document

from app.project import load_document
from app.storage import atomic_write_json

_WEIGHTS = {
    "lighting": 18.0,
    "interior_coverage": 12.0,
    "furnishing": 16.0,
    "facade": 15.0,
    "structural": 15.0,
    "circulation": 14.0,
    "palette_balance": 5.0,
    "symmetry": 5.0,
}


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, value))


def _packet_coverages(root: Path, content_hash: str) -> list[dict[str, Any]]:
    reports = []
    for path in sorted(root.rglob("interior_packet.json")):
        try:
            packet = json.loads(path.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if packet.get("source", {}).get("content_hash") != content_hash:
            continue
        coverage = packet.get("coverage")
        if isinstance(coverage, dict) and isinstance(coverage.get("achieved"), (int, float)):
            reports.append(
                {
                    "room_id": packet.get("room_id"),
                    "achieved": float(coverage["achieved"]),
                    "minimum": float(coverage.get("minimum", 0.0)),
                    "passed": bool(coverage.get("passed", True)),
                    "packet": str(path),
                }
            )
    return reports


def _scorecard(
    document: BuildDocument,
    analysis: dict[str, Any],
    *,
    packet_coverages: list[dict[str, Any]],
) -> dict[str, Any]:
    block_count = max(1, int(analysis["materials"].get("totalNonAir", 0)))
    dimensions: dict[str, dict[str, Any]] = {}

    lighting = analysis.get("lighting", {})
    lighting_rooms = lighting.get("rooms", [])
    if lighting.get("analysisSkipped"):
        dimensions["lighting"] = {
            "available": False,
            "score": None,
            "reason": lighting.get("error", lighting.get("reason", "unavailable")),
        }
    else:
        if lighting_rooms:
            lit_ratios = [
                1.0 - float(item.get("darkCellRatio", 1.0)) for item in lighting_rooms
            ]
            value = sum(lit_ratios) / len(lit_ratios)
            basis = "mean-per-room-lit-cell-ratio"
        else:
            passable = max(1, int(lighting.get("passableCellCount", 0)))
            value = 1.0 - int(lighting.get("darkCellCount", passable)) / passable
            basis = "scope-lit-cell-ratio"
        dimensions["lighting"] = {
            "available": True,
            "score": round(_clamp(value) * 100.0, 3),
            "basis": basis,
            "dark_threshold": lighting.get("darkThreshold"),
            "source_count": lighting.get("sourceCount", 0),
            "dark_cell_count": lighting.get("darkCellCount", 0),
        }

    if packet_coverages:
        coverage_value = sum(item["achieved"] for item in packet_coverages) / len(
            packet_coverages
        )
        dimensions["interior_coverage"] = {
            "available": True,
            "score": round(_clamp(coverage_value) * 100.0, 3),
            "packet_count": len(packet_coverages),
            "mean_cumulative_coverage": round(coverage_value, 6),
            "rooms": packet_coverages,
        }
    else:
        dimensions["interior_coverage"] = {
            "available": False,
            "score": None,
            "reason": "no-current-interior-packets",
            "suggestion": "Run interior packet with --min-cumulative-coverage.",
        }

    rooms = analysis.get("rooms", {}).get("rooms", [])
    furnishing_rows = [
        item.get("furnishing", item.get("evidence", {}).get("furnishing", {}))
        for item in rooms
    ]
    furnishing_rows = [item for item in furnishing_rows if item]
    if furnishing_rows:
        density_scores = [
            min(1.0, float(item.get("density_per_walkable_cell", 0.0)) / 0.08)
            for item in furnishing_rows
        ]
        hollow_ratio = sum(bool(item.get("is_hollow")) for item in furnishing_rows) / len(
            furnishing_rows
        )
        furnishing_value = 0.7 * (sum(density_scores) / len(density_scores)) + 0.3 * (
            1.0 - hollow_ratio
        )
        dimensions["furnishing"] = {
            "available": True,
            "score": round(_clamp(furnishing_value) * 100.0, 3),
            "room_count": len(furnishing_rows),
            "hollow_room_count": sum(
                bool(item.get("is_hollow")) for item in furnishing_rows
            ),
            "hollow_room_ratio": round(hollow_ratio, 6),
            "mean_density": round(
                sum(
                    float(item.get("density_per_walkable_cell", 0.0))
                    for item in furnishing_rows
                )
                / len(furnishing_rows),
                6,
            ),
        }
    else:
        dimensions["furnishing"] = {
            "available": False,
            "score": None,
            "reason": "no-enclosed-rooms",
        }

    elevations = analysis.get("facade", {}).get("elevationMonotony", {})
    monotony = [float(item.get("score", 1.0)) for item in elevations.values()]
    facade_value = 1.0 - (sum(monotony) / max(1, len(monotony)))
    dimensions["facade"] = {
        "available": bool(monotony),
        "score": round(_clamp(facade_value) * 100.0, 3) if monotony else None,
        "mean_monotony": round(1.0 - facade_value, 6),
        "elevations": elevations,
    }

    support = analysis.get("support", {})
    unsupported = int(support.get("unsupportedBlockCount", 0))
    gravity = int(support.get("gravityIssueCount", 0))
    cantilever = int(support.get("thinCantileverCountLowerBound", 0))
    floating = int(
        analysis.get("components", {}).get("floatingCount", 0)
    )
    structural_penalty = (
        unsupported
        + gravity * 5.0
        + cantilever * 0.5
        + floating * 8.0
    ) / block_count * 20.0
    dimensions["structural"] = {
        "available": True,
        "score": round((1.0 - _clamp(structural_penalty)) * 100.0, 3),
        "unsupported_block_count": unsupported,
        "gravity_issue_count": gravity,
        "thin_cantilever_count_lower_bound": cantilever,
        "floating_component_count": floating,
    }

    navigation = analysis.get("navigation", {})
    if navigation.get("analysisSkipped"):
        dimensions["circulation"] = {
            "available": False,
            "score": None,
            "reason": navigation.get("reason", "unavailable"),
        }
    else:
        nodes = max(1, int(navigation.get("nodeCount", 0)))
        dead = int(navigation.get("deadEndCount", 0))
        blocked = int(navigation.get("blockedDoorApproachCount", 0))
        largest_component = max(
            (
                int(item.get("node_count", 0))
                for item in navigation.get("components", [])
            ),
            default=0,
        )
        unreachable_nodes = max(0, nodes - largest_component)
        room_reachability = navigation.get("roomReachability", [])
        sealed_rooms = sum(
            bool(item.get("sealedFromExterior"))
            for item in room_reachability
        )
        penalty = (
            dead / nodes * 5.0
            + blocked / nodes * 10.0
            + unreachable_nodes / nodes * 0.7
            + sealed_rooms / max(1, len(room_reachability)) * 0.3
        )
        dimensions["circulation"] = {
            "available": True,
            "score": round((1.0 - _clamp(penalty)) * 100.0, 3),
            "node_count": nodes,
            "dead_end_count": dead,
            "blocked_door_approach_count": blocked,
            "unreachable_node_count": unreachable_nodes,
            "navigation_component_count": int(
                navigation.get("componentCount", 0)
            ),
            "sealed_room_count": sealed_rooms,
        }

    counts = Counter(
        {
            state: int(count)
            for state, count in analysis.get("materials", {}).get("states", {}).items()
        }
    )
    total = sum(counts.values())
    if total and len(counts) > 1:
        probabilities = [count / total for count in counts.values()]
        entropy = -sum(value * math.log2(value) for value in probabilities)
        normalized_entropy = entropy / math.log2(min(16, len(counts)))
        dominance = max(probabilities)
        palette_value = 0.65 * _clamp(normalized_entropy) + 0.35 * (1.0 - dominance)
    else:
        normalized_entropy = 0.0
        dominance = 1.0
        palette_value = 0.0
    dimensions["palette_balance"] = {
        "available": bool(total),
        "score": round(_clamp(palette_value) * 100.0, 3) if total else None,
        "normalized_entropy": round(normalized_entropy, 6),
        "dominant_state_ratio": round(dominance, 6),
        "state_count": len(counts),
    }

    symmetry = analysis.get("symmetry", {})
    symmetry_scores = [
        float(item.get("exactScore", item.get("scoreLowerBound", 0.0)))
        for item in symmetry.values()
    ]
    symmetry_value = max(symmetry_scores, default=0.0)
    dimensions["symmetry"] = {
        "available": bool(symmetry_scores),
        "score": round(_clamp(symmetry_value) * 100.0, 3)
        if symmetry_scores
        else None,
        "best_axis_score": round(symmetry_value, 6),
        "axes": symmetry,
    }

    available_weight = sum(
        _WEIGHTS[name]
        for name, item in dimensions.items()
        if item.get("available") and item.get("score") is not None
    )
    overall = (
        sum(
            float(item["score"]) * _WEIGHTS[name]
            for name, item in dimensions.items()
            if item.get("available") and item.get("score") is not None
        )
        / max(1.0, available_weight)
    )
    return {
        "schema": "mbi.quality-scorecard.v1",
        "content_hash": document.content_hash,
        "bounds": {
            "min": document.bounds.min.as_tuple(),
            "max": document.bounds.max.as_tuple(),
        },
        "overall_score": round(overall, 3),
        "score_scale": [0, 100],
        "available_weight": available_weight,
        "dimensions": dimensions,
        "weights": _WEIGHTS,
        "method": "normalized-deterministic-quality-aggregation-v1",
    }


def _analyze(
    document: BuildDocument,
    *,
    seal_structure_envelope: bool = False,
) -> dict[str, Any]:
    return analyze_document(
        document,
        lighting_max_cells=10_000_000,
        seal_structure_envelope=seal_structure_envelope,
    )


def quality_report(
    run: str | Path,
    *,
    bounds: IntBoundingBox | None = None,
    from_version: str | None = None,
    to_version: str | None = None,
    seal_structure_envelope: bool = False,
) -> dict[str, Any]:
    root = Path(run)

    def build(version: str | None) -> dict[str, Any]:
        document = load_document(root, version_id=version) if version else load_document(root)
        if bounds is not None:
            document = scoped_document(document, bounds)
        packets = _packet_coverages(root, document.content_hash)
        return _scorecard(
            document,
            _analyze(
                document,
                seal_structure_envelope=seal_structure_envelope,
            ),
            packet_coverages=packets,
        )

    if from_version or to_version:
        if not from_version or not to_version:
            raise ValueError("--from and --to must be supplied together")
        before = build(from_version)
        after = build(to_version)
        names = sorted(set(before["dimensions"]) | set(after["dimensions"]))
        delta = {}
        for name in names:
            before_score = before["dimensions"].get(name, {}).get("score")
            after_score = after["dimensions"].get(name, {}).get("score")
            delta[name] = {
                "before": before_score,
                "after": after_score,
                "delta": (
                    round(float(after_score) - float(before_score), 3)
                    if before_score is not None and after_score is not None
                    else None
                ),
            }
        report = {
            "schema": "mbi.quality-diff.v1",
            "from_version": from_version,
            "to_version": to_version,
            "before": before,
            "after": after,
            "overall_delta": round(
                after["overall_score"] - before["overall_score"], 3
            ),
            "dimension_deltas": delta,
        }
    else:
        report = build(None)
    atomic_write_json(root / "quality_report.json", report)
    return report
