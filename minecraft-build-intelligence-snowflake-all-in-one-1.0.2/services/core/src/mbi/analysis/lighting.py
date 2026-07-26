from __future__ import annotations

from collections import Counter, deque

from ..canonical import BuildDocument, IntVector3
from .block_profiles import block_profile

_NEIGHBORS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def lighting_report(document: BuildDocument, *, max_cells: int = 2_000_000, dark_threshold: int = 7) -> dict[str, object]:
    if document.bounds.volume > max_cells:
        return {"analysisSkipped": True, "reason": "volume_limit", "limit": max_cells}
    palette = document.palette_by_id()
    sources: list[tuple[IntVector3, int, str]] = []
    for position, palette_id in document.blocks.items():
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
            if not document.bounds.contains(neighbor):
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
    for y in range(document.bounds.min.y, document.bounds.max.y + 1):
        for z in range(document.bounds.min.z, document.bounds.max.z + 1):
            for x in range(document.bounds.min.x, document.bounds.max.x + 1):
                position = IntVector3(x, y, z)
                palette_id = document.blocks.get(position)
                if palette_id is not None and not block_profile(palette[palette_id]).passable:
                    continue
                level = levels.get(position, 0)
                histogram[level] += 1
                passable_cells.append(position)
                if level < dark_threshold and len(dark) < 1000:
                    dark.append({"position": position.as_tuple(), "estimatedBlockLight": level})
    return {
        "analysisSkipped": False,
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
    }
