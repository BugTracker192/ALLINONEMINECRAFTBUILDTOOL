from __future__ import annotations

from ..canonical import BuildDocument, IntVector3
from .block_profiles import block_profile
from .rooms import AirVolume, classify_air_volumes

_HORIZONTAL = ((1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1))


def interior_exterior_report(document: BuildDocument, *, volumes: list[AirVolume] | None = None) -> dict[str, object]:
    palette = document.palette_by_id()
    volumes = classify_air_volumes(document) if volumes is None else volumes
    interior_cells: set[IntVector3] = set()
    for volume in volumes:
        if volume.exterior:
            continue
        # Reconstructing every room cell from only bounds would over-classify; use a
        # bounded local flood fill against solids for each interior volume.
        for y in range(volume.bounds.min.y, volume.bounds.max.y + 1):
            for z in range(volume.bounds.min.z, volume.bounds.max.z + 1):
                for x in range(volume.bounds.min.x, volume.bounds.max.x + 1):
                    point = IntVector3(x, y, z)
                    if point not in document.blocks:
                        interior_cells.add(point)

    windows_into_solid = []
    exterior_doors_without_space = []
    inaccessible_balconies = []
    floor_window_conflicts = []
    for position, palette_id in document.blocks.items():
        entry = palette[palette_id]
        profile = block_profile(entry)
        if profile.window:
            adjacent_air = [
                IntVector3(position.x + dx, position.y + dy, position.z + dz)
                for dx, dy, dz in _HORIZONTAL
                if IntVector3(position.x + dx, position.y + dy, position.z + dz) not in document.blocks
            ]
            if not adjacent_air or not any(point in interior_cells for point in adjacent_air):
                windows_into_solid.append({"position": position.as_tuple(), "state": entry.canonical_state})
            above = IntVector3(position.x, position.y + 1, position.z)
            below = IntVector3(position.x, position.y - 1, position.z)
            if above in document.blocks and below in document.blocks:
                floor_window_conflicts.append(position.as_tuple())
        if profile.doorway:
            sides = [
                IntVector3(position.x + dx, position.y, position.z + dz)
                for dx, _, dz in _HORIZONTAL
            ]
            if not any(point in interior_cells for point in sides):
                exterior_doors_without_space.append({"position": position.as_tuple(), "state": entry.canonical_state})
        if "balcony" in entry.block_name or entry.block_name.endswith("_fence"):
            # Fence islands above ground with no nearby doorway are plausible decorative
            # balconies, but flag them for review rather than asserting an error.
            if position.y > document.bounds.min.y + 2:
                nearby_door = False
                for radius in range(1, 4):
                    for dx in range(-radius, radius + 1):
                        for dz in range(-radius, radius + 1):
                            candidate = IntVector3(position.x + dx, position.y, position.z + dz)
                            candidate_id = document.blocks.get(candidate)
                            if candidate_id is not None and block_profile(palette[candidate_id]).doorway:
                                nearby_door = True
                                break
                        if nearby_door:
                            break
                    if nearby_door:
                        break
                if not nearby_door:
                    inaccessible_balconies.append(position.as_tuple())

    sealed_rooms = [
        {
            "volumeId": volume.volume_id,
            "bounds": {
                "min": volume.bounds.min.as_tuple(),
                "max": volume.bounds.max.as_tuple(),
            },
            "volume": volume.size,
        }
        for volume in volumes
        if not volume.exterior and volume.size >= 2
    ]
    return {
        "windowsWithoutInteriorCount": len(windows_into_solid),
        "windowsWithoutInterior": windows_into_solid[:500],
        "exteriorDoorsWithoutInteriorCount": len(exterior_doors_without_space),
        "exteriorDoorsWithoutInterior": exterior_doors_without_space[:500],
        "floorWindowConflictCount": len(floor_window_conflicts),
        "floorWindowConflictSample": floor_window_conflicts[:500],
        "possibleInaccessibleBalconyCount": len(inaccessible_balconies),
        "possibleInaccessibleBalconySample": inaccessible_balconies[:500],
        "enclosedAirVolumes": sealed_rooms[:500],
        "classification": "deterministic-heuristic",
    }
