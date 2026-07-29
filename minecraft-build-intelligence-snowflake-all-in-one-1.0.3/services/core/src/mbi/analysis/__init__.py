from __future__ import annotations

from dataclasses import asdict

from .components import component_report
from .consistency import interior_exterior_report
from .facade import facade_report
from .lighting import lighting_report
from .materials import material_report
from .navigation import navigation_graph
from .rooms import classify_air_volumes, classify_manual_room, room_report
from .support import support_report
from .surfaces import surface_report
from .symmetry import reflection_symmetry


def analyze_document(
    document,
    *,
    lighting_max_cells: int | None = 10_000_000,
    dark_threshold: int = 7,
    room_max_cells: int = 20_000_000,
    manual_rooms=(),
    seal_structure_envelope: bool = False,
):
    air_volumes = classify_air_volumes(
        document,
        max_cells=room_max_cells,
        seal_structure_envelope=seal_structure_envelope,
    )
    manual_volumes = [
        classify_manual_room(
            document,
            bounds,
            seed=seed,
            room_id=1_000_000 + index,
        )
        for index, (bounds, seed) in enumerate(manual_rooms)
    ]
    interior_volumes = [
        volume
        for volume in air_volumes
        if not volume.exterior and volume.size >= 2
    ]
    room_scopes = interior_volumes + manual_volumes
    rooms = room_report(document, volumes=air_volumes)
    rooms["structureEnvelope"] = {
        "enabled": seal_structure_envelope,
        "method": (
            "ordinary-flood-plus-constructed-envelope-candidates-v1"
            if seal_structure_envelope
            else "disabled"
        ),
        "automaticallySealedRoomCount": sum(
            bool(
                volume.evidence.get(
                    "automatic_structure_envelope_candidate"
                )
            )
            for volume in interior_volumes
        ),
        "ordinaryInteriorVolumeCount": sum(
            not bool(
                volume.evidence.get(
                    "automatic_structure_envelope_candidate"
                )
            )
            for volume in interior_volumes
        ),
    }
    rooms["manualRooms"] = []
    for volume in manual_volumes:
        payload = asdict(volume)
        payload["furnishing"] = payload.get("evidence", {}).get("furnishing", {})
        rooms["manualRooms"].append(payload)
    return {
        "materials": material_report(document),
        "surfaces": surface_report(document),
        "components": component_report(document),
        "support": support_report(document),
        "rooms": rooms,
        "navigation": navigation_graph(
            document,
            room_volumes=room_scopes,
        ),
        "lighting": lighting_report(
            document,
            rooms=room_scopes,
            max_cells=lighting_max_cells,
            dark_threshold=dark_threshold,
        ),
        "facade": facade_report(document),
        "interiorExterior": interior_exterior_report(document, volumes=air_volumes),
        "symmetry": reflection_symmetry(document),
    }


__all__ = [
    "analyze_document",
    "classify_manual_room",
    "component_report",
    "facade_report",
    "interior_exterior_report",
    "lighting_report",
    "material_report",
    "navigation_graph",
    "reflection_symmetry",
    "room_report",
    "support_report",
    "surface_report",
]
