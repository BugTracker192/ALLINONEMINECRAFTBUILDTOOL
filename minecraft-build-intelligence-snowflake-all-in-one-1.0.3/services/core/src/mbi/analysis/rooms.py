from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass

from ..canonical import BuildDocument, IntBoundingBox, IntVector3


@dataclass(frozen=True, slots=True)
class AirVolume:
    volume_id: int
    size: int
    bounds: IntBoundingBox
    exterior: bool
    floor_area: int
    min_ceiling_height: int
    max_ceiling_height: int


def classify_air_volumes(document: BuildDocument, *, max_cells: int = 5_000_000) -> list[AirVolume]:
    """Classify air with a compact integer-index flood fill.

    The previous implementation materialized every air cell as an ``IntVector3``
    inside a Python set.  That was exact but prohibitively expensive for sparse
    structures near one million cells.  This implementation uses one byte per
    expanded cell and integer queue entries while preserving the same 6-neighbor
    semantics and deterministic component order.
    """

    expanded = IntBoundingBox(
        IntVector3(document.bounds.min.x - 1, document.bounds.min.y - 1, document.bounds.min.z - 1),
        IntVector3(document.bounds.max.x + 1, document.bounds.max.y + 1, document.bounds.max.z + 1),
    )
    dx, dy, dz = expanded.dimensions.as_tuple()
    volume = dx * dy * dz
    if volume > max_cells:
        return []

    plane = dx * dz
    visited = bytearray(volume)

    def index_of(point: IntVector3) -> int:
        return (
            point.x - expanded.min.x
            + (point.z - expanded.min.z) * dx
            + (point.y - expanded.min.y) * plane
        )

    for point in document.blocks:
        if expanded.contains(point):
            visited[index_of(point)] = 1

    result: list[AirVolume] = []
    for start in range(volume):
        if visited[start]:
            continue
        visited[start] = 1
        queue: deque[int] = deque([start])
        size = 0
        exterior = False
        min_x = min_y = min_z = 1 << 60
        max_x = max_y = max_z = -(1 << 60)
        columns: dict[tuple[int, int], tuple[int, int]] = {}
        while queue:
            current = queue.popleft()
            local_y, rem = divmod(current, plane)
            local_z, local_x = divmod(rem, dx)
            x = expanded.min.x + local_x
            y = expanded.min.y + local_y
            z = expanded.min.z + local_z
            size += 1
            min_x, max_x = min(min_x, x), max(max_x, x)
            min_y, max_y = min(min_y, y), max(max_y, y)
            min_z, max_z = min(min_z, z), max(max_z, z)
            exterior |= (
                local_x in {0, dx - 1}
                or local_y in {0, dy - 1}
                or local_z in {0, dz - 1}
            )
            column = (x, z)
            previous = columns.get(column)
            columns[column] = (y, y) if previous is None else (min(previous[0], y), max(previous[1], y))

            if local_x > 0:
                neighbor = current - 1
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if local_x + 1 < dx:
                neighbor = current + 1
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if local_z > 0:
                neighbor = current - dx
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if local_z + 1 < dz:
                neighbor = current + dx
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if local_y > 0:
                neighbor = current - plane
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)
            if local_y + 1 < dy:
                neighbor = current + plane
                if not visited[neighbor]:
                    visited[neighbor] = 1
                    queue.append(neighbor)

        heights = [maximum - minimum + 1 for minimum, maximum in columns.values()]
        result.append(
            AirVolume(
                len(result),
                size,
                IntBoundingBox(IntVector3(min_x, min_y, min_z), IntVector3(max_x, max_y, max_z)),
                exterior,
                len(columns),
                min(heights),
                max(heights),
            )
        )
    return sorted(result, key=lambda item: (item.exterior, -item.size, item.bounds.min))


def room_report(
    document: BuildDocument,
    *,
    volumes: list[AirVolume] | None = None,
    max_cells: int = 5_000_000,
) -> dict[str, object]:
    volumes = classify_air_volumes(document, max_cells=max_cells) if volumes is None else volumes
    interiors = [item for item in volumes if not item.exterior and item.size >= 2]
    expanded_volume = (
        (document.bounds.dimensions.x + 2)
        * (document.bounds.dimensions.y + 2)
        * (document.bounds.dimensions.z + 2)
    )
    return {
        "analysisSkipped": not volumes and expanded_volume > max_cells,
        "interiorVolumeCount": len(interiors),
        "rooms": [asdict(item) for item in interiors],
    }
