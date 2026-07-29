from __future__ import annotations

import copy
import json
from collections import Counter
from pathlib import Path
from statistics import median
from typing import Any

from mbi.analysis import analyze_document
from mbi.analysis.structures import roof_pitch_estimate_degrees
from mbi.canonical import IntVector3
from mbi.patch.assemblies import fixture_catalog

from app.project import load_document
from app.storage import atomic_write_json


def _anchor_path(run: str | Path) -> Path:
    return Path(run) / "anchors.json"


def load_anchors(run: str | Path) -> dict[str, Any]:
    path = _anchor_path(run)
    if path.is_file():
        return json.loads(path.read_text("utf-8"))
    document = load_document(run)
    return {
        "schema": "mbi.anchor-registry.v1",
        "content_hash": document.content_hash,
        "anchors": {},
    }


def set_anchor(
    run: str | Path,
    name: str,
    position: IntVector3,
    *,
    kind: str = "landmark",
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    registry = load_anchors(run)
    registry["content_hash"] = load_document(run).content_hash
    registry["anchors"][name] = {
        "name": name,
        "position": position.as_tuple(),
        "kind": kind,
        "metadata": metadata or {},
    }
    atomic_write_json(_anchor_path(run), registry)
    return registry["anchors"][name]


def set_room_face_anchor(
    run: str | Path,
    name: str,
    room_id: str,
    face: str,
) -> dict[str, Any]:
    analysis_path = Path(run) / "analysis.json"
    analysis = json.loads(analysis_path.read_text("utf-8"))
    rooms = analysis["results"]["rooms"].get("rooms", [])
    room = next(
        (
            item
            for item in rooms
            if str(item.get("id", item.get("volume_id"))) == str(room_id)
        ),
        None,
    )
    if room is None:
        raise ValueError(f"room not found: {room_id}")
    minimum = room["bounds"]["min"]
    maximum = room["bounds"]["max"]
    center = {
        "x": (minimum["x"] + maximum["x"]) // 2,
        "y": (minimum["y"] + maximum["y"]) // 2,
        "z": (minimum["z"] + maximum["z"]) // 2,
    }
    if face == "north":
        center["z"] = minimum["z"]
    elif face == "south":
        center["z"] = maximum["z"]
    elif face == "west":
        center["x"] = minimum["x"]
    elif face == "east":
        center["x"] = maximum["x"]
    elif face == "floor":
        center["y"] = minimum["y"]
    elif face == "ceiling":
        center["y"] = maximum["y"]
    else:
        raise ValueError(f"unknown room face: {face}")
    return set_anchor(
        run,
        name,
        IntVector3(center["x"], center["y"], center["z"]),
        kind="room-face",
        metadata={"room_id": room_id, "face": face},
    )


def set_structure_bay_anchor(
    run: str | Path,
    name: str,
    structure_id: str,
    face: str,
    bay_index: int,
    bay_count: int,
) -> dict[str, Any]:
    from app.structures import resolve_structure_bounds

    bounds = resolve_structure_bounds(run, structure_id)
    bay_index = max(1, min(bay_count, bay_index))
    fraction = (bay_index - 0.5) / max(1, bay_count)
    x = round(bounds.min.x + fraction * (bounds.max.x - bounds.min.x))
    z = round(bounds.min.z + fraction * (bounds.max.z - bounds.min.z))
    if face in {"north", "south"}:
        z = bounds.min.z if face == "north" else bounds.max.z
    elif face in {"west", "east"}:
        x = bounds.min.x if face == "west" else bounds.max.x
    else:
        raise ValueError(f"unknown structure face: {face}")
    return set_anchor(
        run,
        name,
        IntVector3(x, bounds.max.y, z),
        kind="structure-bay",
        metadata={
            "structure_id": structure_id,
            "face": face,
            "bay_index": bay_index,
            "bay_count": bay_count,
        },
    )


def resolve_anchored_operations(
    run: str | Path,
    operations: list[dict[str, object]],
) -> list[dict[str, object]]:
    anchors = load_anchors(run)["anchors"]
    coordinate_keys = (
        "position",
        "origin",
        "start",
        "end",
        "center",
        "min",
        "max",
        "sourceMin",
        "sourceMax",
    )

    def resolve(operation: dict[str, object]) -> dict[str, object]:
        item = copy.deepcopy(operation)
        nested = item.get("operations")
        if isinstance(nested, list):
            item["operations"] = [
                resolve(value) if isinstance(value, dict) else value for value in nested
            ]
        single = item.get("operation")
        if isinstance(single, dict):
            item["operation"] = resolve(single)
        anchor_name = item.pop("anchor", None)
        if anchor_name is None:
            return item
        anchor = anchors.get(str(anchor_name))
        if anchor is None:
            raise ValueError(f"anchor not found: {anchor_name}")
        base = IntVector3(*anchor["position"])
        offset_raw = item.pop("anchorOffset", [0, 0, 0])
        offset = IntVector3(*(int(value) for value in offset_raw))
        translated = False
        for key in coordinate_keys:
            local = item.get(key)
            if (
                isinstance(local, (list, tuple))
                and len(local) == 3
            ):
                relative = IntVector3(*(int(value) for value in local))
                item[key] = list(
                    (base + offset + relative).as_tuple()
                )
                translated = True
        if not translated:
            target_key = (
                "position"
                if item.get("type")
                in {
                    "set_block",
                    "set_block_entity",
                    "remove_block_entity",
                }
                else "origin"
            )
            item[target_key] = list((base + offset).as_tuple())
        item["resolvedAnchor"] = str(anchor_name)
        return item

    return [resolve(operation) for operation in operations]


def extract_style_profile(
    run: str | Path,
    *,
    name: str = "reference",
) -> dict[str, Any]:
    root = Path(run)
    document = load_document(root)
    analysis = analyze_document(document, lighting_max_cells=10_000_000)
    material = analysis["materials"]
    states = Counter({key: int(value) for key, value in material["states"].items()})
    total = max(1, sum(states.values()))
    trim = {
        state: count
        for state, count in states.most_common()
        if any(token in state for token in ("stairs", "slab", "fence", "trapdoor", "wall"))
    }
    window_spacing = [
        spacing
        for face in analysis["facade"]["faces"].values()
        for spacing in face.get("windowSpacing", [])
        if spacing > 0
    ]
    dimensions = document.bounds.dimensions
    symmetry = analysis["symmetry"]
    profile = {
        "schema": "mbi.style-profile.v1",
        "name": name,
        "source_content_hash": document.content_hash,
        "palette": {
            "state_ratios": {
                state: round(count / total, 8)
                for state, count in states.most_common(32)
            },
            "dominant_states": [state for state, _ in states.most_common(12)],
            "trim_grammar": dict(list(trim.items())[:20]),
        },
        "proportions": {
            "dimensions": dimensions.as_tuple(),
            "width_to_height": round(dimensions.x / max(1, dimensions.y), 6),
            "length_to_height": round(dimensions.z / max(1, dimensions.y), 6),
        },
        "rhythm": {
            "median_window_spacing": (
                round(float(median(window_spacing)), 6) if window_spacing else None
            ),
            "window_spacing_sample": window_spacing[:500],
        },
        "roof": {
            "pitch_estimate_degrees": roof_pitch_estimate_degrees(
                document,
                list(document.blocks),
            ),
            "method": "median-adjacent-roof-surface-rise-v1",
        },
        "symmetry": {
            axis: {
                "exact_score": value.get(
                    "exactScore", value.get("scoreLowerBound", 0.0)
                ),
                "mismatch_count": value.get("mismatchCount"),
            }
            for axis, value in symmetry.items()
        },
        "facade_monotony_baseline": {
            axis: value["score"]
            for axis, value in analysis["facade"]["elevationMonotony"].items()
        },
        "fixture_catalog": fixture_catalog(),
        "method": "palette-proportion-rhythm-trim-extraction-v1",
    }
    destination = root / "style_profiles" / f"{name}.json"
    atomic_write_json(destination, profile)
    return profile


def critique_build(
    run: str | Path,
    *,
    style_profile: str | Path | None = None,
) -> dict[str, Any]:
    root = Path(run)
    document = load_document(root)
    analysis = analyze_document(document, lighting_max_cells=10_000_000)
    findings = []
    for direction, monotony in analysis["facade"]["elevationMonotony"].items():
        if float(monotony["score"]) >= 0.55:
            findings.append(
                {
                    "code": "FACADE_MONOTONY",
                    "severity": "high" if float(monotony["score"]) >= 0.72 else "medium",
                    "direction": direction,
                    "score": monotony["score"],
                    "patch_targets": monotony["worstRegions"][:10],
                    "suggestion": "Apply a seeded greeble_surface pass or a repeated bay assembly.",
                }
            )
    support = analysis["support"]
    if support["unsupportedBlockCount"]:
        findings.append(
            {
                "code": "UNSUPPORTED_BLOCKS",
                "severity": "high",
                "count": support["unsupportedBlockCount"],
                "coordinates": support["unsupportedSample"],
            }
        )
    hollow = [
        item
        for item in analysis["rooms"]["rooms"]
        if item.get("furnishing", {}).get("is_hollow")
    ]
    if hollow:
        findings.append(
            {
                "code": "HOLLOW_INTERIORS",
                "severity": "high",
                "count": len(hollow),
                "rooms": [
                    {
                        "room_id": item.get("volume_id"),
                        "bounds": item["bounds"],
                        "furnishing": item["furnishing"],
                    }
                    for item in hollow
                ],
                "suggestion": "Place fixtures from the interior kit and rerun quality-report.",
            }
        )
    if analysis["navigation"].get("deadEndCount", 0):
        findings.append(
            {
                "code": "CIRCULATION_DEAD_ENDS",
                "severity": "medium",
                "count": analysis["navigation"]["deadEndCount"],
                "coordinates": analysis["navigation"]["deadEndSample"],
            }
        )
    style_delta = None
    if style_profile is not None:
        profile = json.loads(Path(style_profile).read_text("utf-8"))
        expected = profile["palette"]["state_ratios"]
        actual = analysis["materials"]["percentages"]
        divergences = sorted(
            (
                {
                    "state": state,
                    "expected": expected_ratio,
                    "actual": float(actual.get(state, 0.0)),
                    "absolute_delta": abs(
                        expected_ratio - float(actual.get(state, 0.0))
                    ),
                }
                for state, expected_ratio in expected.items()
            ),
            key=lambda item: -item["absolute_delta"],
        )
        style_delta = {
            "source_profile": str(style_profile),
            "largest_palette_divergences": divergences[:20],
        }
        if sum(item["absolute_delta"] for item in divergences[:12]) > 0.35:
            findings.append(
                {
                    "code": "STYLE_PALETTE_DIVERGENCE",
                    "severity": "medium",
                    "details": divergences[:12],
                }
            )
    report = {
        "schema": "mbi.critique-linter.v1",
        "content_hash": document.content_hash,
        "finding_count": len(findings),
        "findings": findings,
        "style_delta": style_delta,
        "actionable": True,
    }
    atomic_write_json(root / "critique_report.json", report)
    return report
