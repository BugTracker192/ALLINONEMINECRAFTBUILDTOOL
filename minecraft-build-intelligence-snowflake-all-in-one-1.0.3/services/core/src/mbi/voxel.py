from __future__ import annotations

import heapq
from collections.abc import Iterator, Mapping, MutableMapping
from typing import Any

import numpy as np

from .canonical import IntVector3

CHUNK_EDGE = 16
_EMPTY = np.uint32(np.iinfo(np.uint32).max)


def _chunk_and_index(point: IntVector3) -> tuple[tuple[int, int, int], int]:
    chunk_x = point.x // CHUNK_EDGE
    chunk_y = point.y // CHUNK_EDGE
    chunk_z = point.z // CHUNK_EDGE
    local_x = point.x - chunk_x * CHUNK_EDGE
    local_y = point.y - chunk_y * CHUNK_EDGE
    local_z = point.z - chunk_z * CHUNK_EDGE
    return (
        (chunk_x, chunk_y, chunk_z),
        (local_y * CHUNK_EDGE + local_z) * CHUNK_EDGE + local_x,
    )


class ChunkedVoxelMap(MutableMapping[IntVector3, int]):
    """Sparse mutable voxel mapping backed by dense uint32 16³ chunks.

    Coordinates are materialized only at API boundaries. A full chunk costs
    16 KiB regardless of Python object overhead, while empty chunks cost
    nothing.
    """

    __slots__ = ("_chunks", "_count")

    def __init__(self, values: Mapping[IntVector3, int] | None = None) -> None:
        self._chunks: dict[tuple[int, int, int], np.ndarray[Any, np.dtype[np.uint32]]] = {}
        self._count = 0
        if values:
            for point, palette_id in values.items():
                self[point] = palette_id

    @classmethod
    def from_filled_chunk_box(
        cls,
        chunks_x: int,
        chunks_y: int,
        chunks_z: int,
        palette_id: int,
        *,
        chunk_origin: tuple[int, int, int] = (0, 0, 0),
    ) -> "ChunkedVoxelMap":
        if min(chunks_x, chunks_y, chunks_z) < 0:
            raise ValueError("chunk dimensions cannot be negative")
        if palette_id < 0 or palette_id >= int(_EMPTY):
            raise ValueError("palette id is outside uint32 storage range")
        result = cls()
        template = np.full(CHUNK_EDGE**3, palette_id, dtype=np.uint32)
        origin_x, origin_y, origin_z = chunk_origin
        for chunk_x in range(origin_x, origin_x + chunks_x):
            for chunk_y in range(origin_y, origin_y + chunks_y):
                for chunk_z in range(origin_z, origin_z + chunks_z):
                    result._chunks[(chunk_x, chunk_y, chunk_z)] = template.copy()
        result._count = chunks_x * chunks_y * chunks_z * CHUNK_EDGE**3
        return result

    def __getitem__(self, point: IntVector3) -> int:
        key, index = _chunk_and_index(point)
        chunk = self._chunks.get(key)
        if chunk is None or chunk[index] == _EMPTY:
            raise KeyError(point)
        return int(chunk[index])

    def __setitem__(self, point: IntVector3, palette_id: int) -> None:
        if not isinstance(point, IntVector3):
            raise TypeError("voxel keys must be IntVector3")
        if palette_id < 0 or palette_id >= int(_EMPTY):
            raise ValueError("palette id is outside uint32 storage range")
        key, index = _chunk_and_index(point)
        chunk = self._chunks.get(key)
        if chunk is None:
            chunk = np.full(CHUNK_EDGE**3, _EMPTY, dtype=np.uint32)
            self._chunks[key] = chunk
        if chunk[index] == _EMPTY:
            self._count += 1
        chunk[index] = np.uint32(palette_id)

    def __delitem__(self, point: IntVector3) -> None:
        key, index = _chunk_and_index(point)
        chunk = self._chunks.get(key)
        if chunk is None or chunk[index] == _EMPTY:
            raise KeyError(point)
        chunk[index] = _EMPTY
        self._count -= 1
        if not np.any(chunk != _EMPTY):
            del self._chunks[key]

    def __iter__(self) -> Iterator[IntVector3]:
        for point, _ in self.iter_items_sorted():
            yield point

    def __len__(self) -> int:
        return self._count

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Mapping):
            return False
        return voxel_maps_equal(self, other)

    def __contains__(self, point: object) -> bool:
        if not isinstance(point, IntVector3):
            return False
        key, index = _chunk_and_index(point)
        chunk = self._chunks.get(key)
        return chunk is not None and chunk[index] != _EMPTY

    def get(self, point: IntVector3, default: Any = None) -> Any:
        key, index = _chunk_and_index(point)
        chunk = self._chunks.get(key)
        if chunk is None or chunk[index] == _EMPTY:
            return default
        return int(chunk[index])

    def copy(self) -> "ChunkedVoxelMap":
        result = ChunkedVoxelMap()
        result._chunks = {key: chunk.copy() for key, chunk in self._chunks.items()}
        result._count = self._count
        return result

    @property
    def storage_bytes(self) -> int:
        return sum(chunk.nbytes for chunk in self._chunks.values())

    @property
    def chunk_count(self) -> int:
        return len(self._chunks)

    def _chunk_items(
        self,
        key: tuple[int, int, int],
        chunk: np.ndarray[Any, np.dtype[np.uint32]],
    ) -> Iterator[tuple[IntVector3, int]]:
        base_x, base_y, base_z = (axis * CHUNK_EDGE for axis in key)
        # IntVector3 ordering is x, then y, then z.
        for local_x in range(CHUNK_EDGE):
            for local_y in range(CHUNK_EDGE):
                row = (local_y * CHUNK_EDGE) * CHUNK_EDGE + local_x
                for local_z in range(CHUNK_EDGE):
                    value = chunk[row + local_z * CHUNK_EDGE]
                    if value != _EMPTY:
                        yield (
                            IntVector3(
                                base_x + local_x,
                                base_y + local_y,
                                base_z + local_z,
                            ),
                            int(value),
                        )

    def iter_items_sorted(self) -> Iterator[tuple[IntVector3, int]]:
        iterators = [
            self._chunk_items(key, chunk)
            for key, chunk in sorted(self._chunks.items())
        ]
        yield from heapq.merge(*iterators, key=lambda item: item[0])


class RegionOverlayVoxelMap(MutableMapping[IntVector3, int]):
    """Lazy deterministic flattened view over independent region voxel maps."""

    __slots__ = ("_count", "_materialized", "_order", "_regions")

    def __init__(
        self,
        regions: Mapping[str, Mapping[IntVector3, int]],
        *,
        order: list[str] | None = None,
        count: int | None = None,
    ) -> None:
        self._regions = regions
        self._order = order or sorted(regions)
        self._materialized: ChunkedVoxelMap | None = None
        self._count = count

    def _materialize(self) -> ChunkedVoxelMap:
        if self._materialized is None:
            values = ChunkedVoxelMap()
            for point, palette_id in self.iter_items_sorted():
                values[point] = palette_id
            self._materialized = values
            self._count = len(values)
        return self._materialized

    def __getitem__(self, point: IntVector3) -> int:
        if self._materialized is not None:
            return self._materialized[point]
        for name in reversed(self._order):
            values = self._regions[name]
            palette_id = values.get(point)
            if palette_id is not None:
                return int(palette_id)
        raise KeyError(point)

    def __setitem__(self, point: IntVector3, palette_id: int) -> None:
        self._materialize()[point] = palette_id
        self._count = len(self._materialized)

    def __delitem__(self, point: IntVector3) -> None:
        del self._materialize()[point]
        self._count = len(self._materialized)

    def __iter__(self) -> Iterator[IntVector3]:
        for point, _ in self.iter_items_sorted():
            yield point

    def __len__(self) -> int:
        if self._materialized is not None:
            return len(self._materialized)
        if self._count is None:
            self._count = sum(1 for _ in self.iter_items_sorted())
        return self._count

    def get(self, point: IntVector3, default: Any = None) -> Any:
        try:
            return self[point]
        except KeyError:
            return default

    def iter_items_sorted(self) -> Iterator[tuple[IntVector3, int]]:
        if self._materialized is not None:
            yield from self._materialized.iter_items_sorted()
            return
        sources: list[Iterator[tuple[IntVector3, tuple[int, int]]]] = []
        def prioritized(
            priority: int,
            values: Mapping[IntVector3, int],
        ) -> Iterator[tuple[IntVector3, tuple[int, int]]]:
            for point, palette_id in iter_items_sorted(values):
                yield point, (priority, palette_id)

        for priority, name in enumerate(self._order):
            values = self._regions[name]
            sources.append(prioritized(priority, values))
        merged = heapq.merge(*sources, key=lambda item: item[0])
        pending: IntVector3 | None = None
        selected: tuple[int, int] | None = None
        for point, candidate in merged:
            if pending is not None and point != pending:
                assert selected is not None
                yield pending, selected[1]
                selected = None
            pending = point
            if selected is None or candidate[0] >= selected[0]:
                selected = candidate
        if pending is not None and selected is not None:
            yield pending, selected[1]


def iter_items_sorted(
    values: Mapping[IntVector3, int],
) -> Iterator[tuple[IntVector3, int]]:
    method = getattr(values, "iter_items_sorted", None)
    if method is not None:
        yield from method()
    else:
        yield from sorted(values.items())


def voxel_maps_equal(
    left: Mapping[IntVector3, int],
    right: Mapping[IntVector3, int],
) -> bool:
    if len(left) != len(right):
        return False
    return all(a == b for a, b in zip(iter_items_sorted(left), iter_items_sorted(right), strict=True))
