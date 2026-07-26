from __future__ import annotations

import hashlib
import struct
from collections import Counter
from dataclasses import dataclass
from enum import StrEnum

from .canonical import BuildDocument, IntVector3

CHUNK_SIZE = 16
CHUNK_VOLUME = CHUNK_SIZE**3


class ChunkEncoding(StrEnum):
    SINGLE = "single"
    SPARSE = "sparse"
    U8 = "u8"
    U16 = "u16"
    U32 = "u32"
    RLE = "rle"


@dataclass(frozen=True, slots=True)
class ChunkBlob:
    coordinate: IntVector3
    global_min: IntVector3
    dimensions: IntVector3
    encoding: ChunkEncoding
    palette_ids: tuple[int, ...]
    non_air_count: int
    material_histogram: dict[int, int]
    content_hash: str
    data: bytes


def chunk_coordinate(position: IntVector3) -> IntVector3:
    return IntVector3(position.x // CHUNK_SIZE, position.y // CHUNK_SIZE, position.z // CHUNK_SIZE)


def local_index(position: IntVector3, chunk: IntVector3) -> int:
    lx = position.x - chunk.x * CHUNK_SIZE
    ly = position.y - chunk.y * CHUNK_SIZE
    lz = position.z - chunk.z * CHUNK_SIZE
    return lx + lz * CHUNK_SIZE + ly * CHUNK_SIZE * CHUNK_SIZE


def _rle(values: list[int]) -> bytes:
    out = bytearray()
    start = 0
    while start < len(values):
        value = values[start]
        end = start + 1
        while end < len(values) and values[end] == value and end - start < 0xFFFF:
            end += 1
        out.extend(struct.pack(">HI", end - start, value))
        start = end
    return bytes(out)


def encode_chunk(values: list[int], air_ids: set[int]) -> tuple[ChunkEncoding, bytes]:
    if len(values) != CHUNK_VOLUME:
        raise ValueError("chunk encoder requires exactly 4096 values")
    unique = sorted(set(values))
    if len(unique) == 1:
        return ChunkEncoding.SINGLE, struct.pack(">I", unique[0])
    sparse_items = [(index, value) for index, value in enumerate(values) if value not in air_ids]
    sparse = b"".join(struct.pack(">HI", index, value) for index, value in sparse_items)
    maximum = max(unique)
    if maximum <= 0xFF:
        dense_encoding, dense = ChunkEncoding.U8, bytes(values)
    elif maximum <= 0xFFFF:
        dense_encoding, dense = ChunkEncoding.U16, b"".join(struct.pack(">H", value) for value in values)
    else:
        dense_encoding, dense = ChunkEncoding.U32, b"".join(struct.pack(">I", value) for value in values)
    rle = _rle(values)
    candidates: list[tuple[ChunkEncoding, bytes]] = [(dense_encoding, dense), (ChunkEncoding.RLE, rle)]
    if sparse_items:
        candidates.append((ChunkEncoding.SPARSE, sparse))
    return min(candidates, key=lambda item: (len(item[1]), item[0].value))


def build_chunks(document: BuildDocument) -> list[ChunkBlob]:
    palette = document.palette_by_id()
    air_ids = {entry.palette_id for entry in document.palette if entry.is_air_like}
    default_air = min(air_ids) if air_ids else 0
    grouped: dict[IntVector3, list[int]] = {}
    for position, palette_id in document.blocks.items():
        chunk = chunk_coordinate(position)
        grouped.setdefault(chunk, [default_air] * CHUNK_VOLUME)[local_index(position, chunk)] = palette_id
    blobs: list[ChunkBlob] = []
    for coordinate in sorted(grouped):
        values = grouped[coordinate]
        encoding, data = encode_chunk(values, air_ids)
        histogram = dict(sorted(Counter(values).items()))
        non_air = sum(count for key, count in histogram.items() if key not in air_ids)
        content_hash = hashlib.sha256(encoding.value.encode() + b"\0" + data).hexdigest()
        blobs.append(
            ChunkBlob(
                coordinate=coordinate,
                global_min=IntVector3(coordinate.x * 16, coordinate.y * 16, coordinate.z * 16),
                dimensions=IntVector3(16, 16, 16),
                encoding=encoding,
                palette_ids=tuple(sorted(histogram)),
                non_air_count=non_air,
                material_histogram=histogram,
                content_hash=content_hash,
                data=data,
            )
        )
    return blobs
