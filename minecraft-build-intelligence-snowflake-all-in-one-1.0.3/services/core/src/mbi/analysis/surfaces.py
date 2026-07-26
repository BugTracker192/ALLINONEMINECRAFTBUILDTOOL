from __future__ import annotations

from collections import Counter

from ..canonical import BuildDocument, IntVector3
from .block_profiles import block_profile

_DIRECTIONS = {
    "east": (1, 0, 0),
    "west": (-1, 0, 0),
    "up": (0, 1, 0),
    "down": (0, -1, 0),
    "south": (0, 0, 1),
    "north": (0, 0, -1),
}


def surface_report(document: BuildDocument) -> dict[str, object]:
    palette = document.palette_by_id()
    exposed_by_direction: Counter[str] = Counter()
    exposed_by_state: Counter[str] = Counter()
    fully_enclosed = 0
    touches_cavity = 0
    exterior_faces: list[dict[str, object]] = []
    solid_positions = set(document.blocks)
    for position, palette_id in document.blocks.items():
        entry = palette[palette_id]
        if entry.is_air_like:
            continue
        exposed = 0
        for direction, (dx, dy, dz) in _DIRECTIONS.items():
            neighbor = IntVector3(position.x + dx, position.y + dy, position.z + dz)
            neighbor_id = document.blocks.get(neighbor)
            visible = neighbor_id is None or block_profile(palette[neighbor_id]).transparent
            if visible:
                exposed += 1
                exposed_by_direction[direction] += 1
                exposed_by_state[entry.canonical_state] += 1
                if len(exterior_faces) < 1000:
                    exterior_faces.append({"position": position.as_tuple(), "direction": direction, "state": entry.canonical_state})
        if exposed == 0:
            fully_enclosed += 1
        elif any(
            IntVector3(position.x + dx, position.y + dy, position.z + dz) not in solid_positions
            and document.bounds.contains(IntVector3(position.x + dx, position.y + dy, position.z + dz))
            for dx, dy, dz in _DIRECTIONS.values()
        ):
            touches_cavity += 1
    return {
        "exposedFaceCount": sum(exposed_by_direction.values()),
        "exposedByDirection": dict(exposed_by_direction),
        "exposedByState": dict(exposed_by_state.most_common()),
        "fullyEnclosedBlockCount": fully_enclosed,
        "blocksTouchingAir": touches_cavity,
        "sampleFaces": exterior_faces,
        "sampleCapped": len(exterior_faces) == 1000,
    }
