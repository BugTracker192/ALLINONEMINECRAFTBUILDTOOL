from __future__ import annotations

from collections import Counter, deque

from ..canonical import BuildDocument, IntBoundingBox, IntVector3
from .rooms import AirVolume
from .block_profiles import block_profile

_NEIGHBORS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def lighting_report(
    document: BuildDocument,
    *,
    bounds: IntBoundingBox | None = None,
    rooms: list[AirVolume] | None = None,
    max_cells: int | None = 10_000_000,
    dark_threshold: int = 7,
    dark_sample_limit: int = 1000,
) -> dict[str, object]:
    scope = document.bounds if bounds is None else document.bounds.intersection(bounds)
    if scope is None:
        raise ValueError("lighting bounds do not intersect the document")
    if max_cells is not None and scope.volume > max_cells:
        return {
            "analysisSkipped": True,
            "status": "rejected",
            "error": "LIGHTING_SCOPE_TOO_LARGE",
            "reason": "volume_limit",
            "limit": max_cells,
            "requiredCells": scope.volume,
            "scope": {"min": scope.min.as_tuple(), "max": scope.max.as_tuple()},
            "suggestions": [
                "Pass --bounds X1,Y1,Z1,X2,Y2,Z2 to analyze a room or structure.",
                "Raise --lighting-max-cells, or pass 0 to remove the cap.",
            ],
        }
    palette = document.palette_by_id()
    sources: list[tuple[IntVector3, int, str]] = []
    for position, palette_id in document.blocks.items():
        if not scope.contains(position):
            continue
        entry = palette[palette_id]
        level = block_profile(entry).light_level
        if level:
            sources.append((position, level, entry.canonical_state))
    levels: dict[IntVector3, int] = {}
    queue: deque[tuple[IntVector3, int]] = deque()
    for position, level, _ in sources:
        if level > levels.get(position, -1):
            levels[position] = level
            queue.append((position, level))
    while queue:
        point, level = queue.popleft()
        if level <= 1:
            continue
        for dx, dy, dz in _NEIGHBORS:
            neighbor = IntVector3(point.x + dx, point.y + dy, point.z + dz)
            if not scope.contains(neighbor):
                continue
            palette_id = document.blocks.get(neighbor)
            attenuation = 1
            if palette_id is not None:
                profile = block_profile(palette[palette_id])
                if not profile.transparent and profile.light_level == 0:
                    continue
                if not profile.passable:
                    attenuation = 2
            next_level = level - attenuation
            if next_level > levels.get(neighbor, -1):
                levels[neighbor] = next_level
                queue.append((neighbor, next_level))
    passable_cells = []
    histogram: Counter[int] = Counter()
    dark = []
    for y in range(scope.min.y, scope.max.y + 1):
        for z in range(scope.min.z, scope.max.z + 1):
            for x in range(scope.min.x, scope.max.x + 1):
                position = IntVector3(x, y, z)
                palette_id = document.blocks.get(position)
                if palette_id is not None and not block_profile(palette[palette_id]).passable:
                    continue
                level = levels.get(position, 0)
                histogram[level] += 1
                passable_cells.append(position)
                if level < dark_threshold and len(dark) < dark_sample_limit:
                    dark.append({"position": position.as_tuple(), "estimatedBlockLight": level})
    room_reports = []
    for room in rooms or []:
        room_scope = room.bounds.intersection(scope)
        if room_scope is None or room.exterior:
            continue
        room_histogram: Counter[int] = Counter()
        room_dark: list[dict[str, object]] = []
        for position in room_scope.iter_points():
            palette_id = document.blocks.get(position)
            if palette_id is not None and not block_profile(palette[palette_id]).passable:
                continue
            level = levels.get(position, 0)
            room_histogram[level] += 1
            if level < dark_threshold and len(room_dark) < min(250, dark_sample_limit):
                room_dark.append(
                    {"position": position.as_tuple(), "estimatedBlockLight": level}
                )
        count = sum(room_histogram.values())
        dark_count = sum(
            value for level, value in room_histogram.items() if level < dark_threshold
        )
        room_reports.append(
            {
                "roomId": room.volume_id,
                "bounds": {
                    "min": room_scope.min.as_tuple(),
                    "max": room_scope.max.as_tuple(),
                },
                "passableCellCount": count,
                "estimatedLevelHistogram": dict(sorted(room_histogram.items())),
                "darkCellCount": dark_count,
                "darkCellRatio": round(dark_count / max(1, count), 6),
                "darkCellSample": room_dark,
            }
        )
    return {
        "analysisSkipped": False,
        "status": "complete",
        "method": "bounded-block-light-bfs-v1",
        "exactMinecraftLightEngine": False,
        "sourceCount": len(sources),
        "sources": [
            {"position": position.as_tuple(), "level": level, "state": state}
            for position, level, state in sources[:500]
        ],
        "passableCellCount": len(passable_cells),
        "estimatedLevelHistogram": dict(sorted(histogram.items())),
        "darkThreshold": dark_threshold,
        "darkCellCount": sum(count for level, count in histogram.items() if level < dark_threshold),
        "darkCellSample": dark,
        "scope": {
            "min": scope.min.as_tuple(),
            "max": scope.max.as_tuple(),
            "volume": scope.volume,
            "maxCells": max_cells,
        },
        "rooms": room_reports,
    }
