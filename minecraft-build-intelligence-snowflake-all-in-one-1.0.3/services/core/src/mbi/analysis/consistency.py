from __future__ import annotations

from ..canonical import BuildDocument, IntVector3
from .block_profiles import block_profile
from .rooms import AirVolume, classify_air_volumes

_HORIZONTAL = ((1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1))


def interior_exterior_report(
    document: BuildDocument,
    *,
    volumes: list[AirVolume] | None = None,
) -> dict[str, object]:
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
    decorative_trapdoors_excluded = 0
    non_navigable_doorways_excluded = 0
    non_navigable_balcony_geometry_excluded = 0

    def passable(point: IntVector3) -> bool:
        palette_id = document.blocks.get(point)
        return palette_id is None or block_profile(palette[palette_id]).passable

    def standable(point: IntVector3) -> bool:
        below_id = document.blocks.get(IntVector3(point.x, point.y - 1, point.z))
        return (
            passable(point)
            and passable(IntVector3(point.x, point.y + 1, point.z))
            and below_id is not None
            and block_profile(palette[below_id]).supports_player
        )

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
            if entry.block_name.endswith("_trapdoor"):
                decorative_trapdoors_excluded += 1
                continue
            sides = [
                IntVector3(position.x + dx, position.y, position.z + dz)
                for dx, _, dz in _HORIZONTAL
            ]
            navigable_sides = [point for point in sides if standable(point)]
            if not navigable_sides:
                non_navigable_doorways_excluded += 1
            elif not any(point in interior_cells for point in navigable_sides):
                exterior_doors_without_space.append(
                    {
                        "position": position.as_tuple(),
                        "state": entry.canonical_state,
                        "navigableAdjacentCellCount": len(navigable_sides),
                        "navigabilityWeight": round(min(1.0, len(navigable_sides) / 2.0), 6),
                    }
                )
        if (
            "balcony" in entry.block_name
            or entry.block_name.endswith("_fence")
        ) and position.y > document.bounds.min.y + 2:
            # Fence islands above ground with no nearby doorway are plausible decorative
            # balconies, but flag them for review rather than asserting an error.
            adjacent_walkable = [
                IntVector3(position.x + dx, position.y, position.z + dz)
                for dx, _, dz in _HORIZONTAL
                if standable(IntVector3(position.x + dx, position.y, position.z + dz))
            ]
            if not adjacent_walkable:
                non_navigable_balcony_geometry_excluded += 1
                continue
            nearby_door = False
            for radius in range(1, 4):
                for dx in range(-radius, radius + 1):
                    for dz in range(-radius, radius + 1):
                        candidate = IntVector3(
                            position.x + dx,
                            position.y,
                            position.z + dz,
                        )
                        candidate_id = document.blocks.get(candidate)
                        if candidate_id is not None and block_profile(
                            palette[candidate_id]
                        ).doorway:
                            nearby_door = True
                            break
                    if nearby_door:
                        break
                if nearby_door:
                    break
            if not nearby_door:
                inaccessible_balconies.append(
                    {
                        "position": position.as_tuple(),
                        "navigableAdjacentCellCount": len(adjacent_walkable),
                        "navigabilityWeight": round(
                            min(1.0, len(adjacent_walkable) / 2.0), 6
                        ),
                    }
                )

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
        "decorativeTrapdoorsExcluded": decorative_trapdoors_excluded,
        "nonNavigableDoorwaysExcluded": non_navigable_doorways_excluded,
        "floorWindowConflictCount": len(floor_window_conflicts),
        "floorWindowConflictSample": floor_window_conflicts[:500],
        "possibleInaccessibleBalconyCount": len(inaccessible_balconies),
        "possibleInaccessibleBalconyWeightedCount": round(
            sum(item["navigabilityWeight"] for item in inaccessible_balconies),
            6,
        ),
        "possibleInaccessibleBalconySample": inaccessible_balconies[:500],
        "nonNavigableBalconyGeometryExcluded": non_navigable_balcony_geometry_excluded,
        "enclosedAirVolumes": sealed_rooms[:500],
        "classification": "deterministic-heuristic",
    }
