from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass

from ..canonical import BuildDocument, IntBoundingBox, IntVector3

_NEIGHBORS = (
    (1, 0, 0), (-1, 0, 0),
    (0, 1, 0), (0, -1, 0),
    (0, 0, 1), (0, 0, -1),
)


@dataclass(frozen=True, slots=True)
class Component:
    component_id: int
    size: int
    bounds: IntBoundingBox
    touches_foundation: bool
    palette_ids: tuple[int, ...]


def connected_components(document: BuildDocument) -> list[Component]:
    palette = document.palette_by_id()
    solid = {position for position, pid in document.blocks.items() if not palette[pid].is_air_like}
    unseen = set(solid)
    result: list[Component] = []
    while unseen:
        start = min(unseen)
        unseen.remove(start)
        queue = deque([start])
        points: list[IntVector3] = []
        ids: set[int] = set()
        while queue:
            point = queue.popleft()
            points.append(point)
            ids.add(document.blocks[point])
            for dx, dy, dz in _NEIGHBORS:
                neighbor = IntVector3(point.x + dx, point.y + dy, point.z + dz)
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
        bounds = IntBoundingBox(
            IntVector3(min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)),
            IntVector3(max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)),
        )
        result.append(Component(len(result), len(points), bounds, any(p.y == document.bounds.min.y for p in points), tuple(sorted(ids))))
    return sorted(result, key=lambda item: (-item.size, item.bounds.min))


def component_report(document: BuildDocument) -> dict[str, object]:
    components = connected_components(document)
    return {
        "count": len(components),
        "mainComponentSize": components[0].size if components else 0,
        "floatingCount": sum(not item.touches_foundation for item in components),
        "components": [asdict(item) for item in components],
    }
