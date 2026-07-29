from __future__ import annotations

import json
import mmap
from pathlib import Path
from typing import Any

from .canonical import IntBoundingBox, IntVector3
from .errors import MBIError
from .voxel import ChunkedVoxelMap

_WS = b" \t\r\n"


def _skip_ws(data: mmap.mmap, index: int, end: int) -> int:
    while index < end and data[index] in _WS:
        index += 1
    return index


def _string_end(data: mmap.mmap, start: int, end: int) -> int:
    if start >= end or data[start] != ord('"'):
        raise MBIError("DOCUMENT_JSON_INVALID", "Expected a JSON string.")
    escaped = False
    index = start + 1
    while index < end:
        byte = data[index]
        if escaped:
            escaped = False
        elif byte == ord("\\"):
            escaped = True
        elif byte == ord('"'):
            return index + 1
        index += 1
    raise MBIError("DOCUMENT_JSON_INVALID", "Stored document contains an unterminated string.")


def _value_end(data: mmap.mmap, start: int, end: int) -> int:
    start = _skip_ws(data, start, end)
    if start >= end:
        raise MBIError("DOCUMENT_JSON_INVALID", "Stored document contains a missing value.")
    first = data[start]
    if first == ord('"'):
        return _string_end(data, start, end)
    if first in (ord("["), ord("{")):
        stack = [first]
        index = start + 1
        while index < end and stack:
            byte = data[index]
            if byte == ord('"'):
                index = _string_end(data, index, end)
                continue
            if byte in (ord("["), ord("{")):
                stack.append(byte)
            elif byte in (ord("]"), ord("}")):
                expected = ord("[") if byte == ord("]") else ord("{")
                if not stack or stack[-1] != expected:
                    raise MBIError("DOCUMENT_JSON_INVALID", "Stored document has mismatched JSON delimiters.")
                stack.pop()
            index += 1
        if stack:
            raise MBIError("DOCUMENT_JSON_INVALID", "Stored document has an unterminated JSON container.")
        return index
    index = start
    while index < end and data[index] not in b",}] \t\r\n":
        index += 1
    return index


def _integer(data: mmap.mmap, index: int, end: int) -> tuple[int, int]:
    index = _skip_ws(data, index, end)
    start = index
    if index < end and data[index] == ord("-"):
        index += 1
    digits = index
    while index < end and ord("0") <= data[index] <= ord("9"):
        index += 1
    if index == digits:
        raise MBIError("DOCUMENT_BLOCK_INVALID", "Stored document contains an invalid block integer.")
    return int(data[start:index]), index


def _read_rows(
    data: mmap.mmap,
    start: int,
    end: int,
    *,
    bounds: IntBoundingBox | None,
) -> ChunkedVoxelMap:
    index = _skip_ws(data, start, end)
    if index >= end or data[index] != ord("["):
        raise MBIError("DOCUMENT_BLOCK_INVALID", "Stored document block rows must be a list.")
    index = _skip_ws(data, index + 1, end)
    blocks = ChunkedVoxelMap()
    if index < end and data[index] == ord("]"):
        return blocks
    while index < end:
        if data[index] != ord("["):
            raise MBIError("DOCUMENT_BLOCK_INVALID", "Stored document contains an invalid block record.")
        index += 1
        values: list[int] = []
        for column in range(4):
            value, index = _integer(data, index, end)
            values.append(value)
            index = _skip_ws(data, index, end)
            expected = ord(",") if column < 3 else ord("]")
            if index >= end or data[index] != expected:
                raise MBIError("DOCUMENT_BLOCK_INVALID", "Stored document contains an invalid block record.")
            index = _skip_ws(data, index + 1, end)
        point = IntVector3(values[0], values[1], values[2])
        if bounds is None or bounds.contains(point):
            blocks[point] = values[3]
        if index < end and data[index] == ord(","):
            index = _skip_ws(data, index + 1, end)
            continue
        if index < end and data[index] == ord("]"):
            return blocks
        raise MBIError("DOCUMENT_BLOCK_INVALID", "Stored document contains an invalid block rows delimiter.")
    raise MBIError("DOCUMENT_BLOCK_INVALID", "Stored document block rows are unterminated.")


def _read_region_rows(
    data: mmap.mmap,
    start: int,
    end: int,
    *,
    bounds: IntBoundingBox | None,
) -> dict[str, ChunkedVoxelMap]:
    index = _skip_ws(data, start, end)
    if index >= end or data[index] != ord("{"):
        raise MBIError("DOCUMENT_REGION_BLOCKS_INVALID", "Stored document regionBlocks must be an object.")
    index = _skip_ws(data, index + 1, end)
    regions: dict[str, ChunkedVoxelMap] = {}
    if index < end and data[index] == ord("}"):
        return regions
    while index < end:
        key_end = _string_end(data, index, end)
        name = json.loads(data[index:key_end])
        index = _skip_ws(data, key_end, end)
        if index >= end or data[index] != ord(":"):
            raise MBIError("DOCUMENT_JSON_INVALID", "Stored document contains an invalid regionBlocks object.")
        value_start = _skip_ws(data, index + 1, end)
        value_end = _value_end(data, value_start, end)
        regions[str(name)] = _read_rows(
            data,
            value_start,
            value_end,
            bounds=bounds,
        )
        index = _skip_ws(data, value_end, end)
        if index < end and data[index] == ord(","):
            index = _skip_ws(data, index + 1, end)
            continue
        if index < end and data[index] == ord("}"):
            return regions
        raise MBIError("DOCUMENT_JSON_INVALID", "Stored document contains an invalid regionBlocks delimiter.")
    raise MBIError("DOCUMENT_JSON_INVALID", "Stored document regionBlocks object is unterminated.")


def read_canonical_payload(
    path: str | Path,
    *,
    bounds: IntBoundingBox | None = None,
) -> tuple[dict[str, Any], ChunkedVoxelMap, dict[str, ChunkedVoxelMap]]:
    """Read top-level metadata normally and voxel arrays without row objects."""
    source = Path(path)
    with source.open("rb") as stream:
        if source.stat().st_size == 0:
            raise MBIError("DOCUMENT_JSON_INVALID", "Stored document JSON is empty.")
        with mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as data:
            end = len(data)
            index = _skip_ws(data, 0, end)
            if index >= end or data[index] != ord("{"):
                raise MBIError("DOCUMENT_JSON_INVALID", "Stored document root must be an object.")
            index = _skip_ws(data, index + 1, end)
            payload: dict[str, Any] = {}
            blocks = ChunkedVoxelMap()
            region_blocks: dict[str, ChunkedVoxelMap] = {}
            while index < end and data[index] != ord("}"):
                key_end = _string_end(data, index, end)
                key = json.loads(data[index:key_end])
                index = _skip_ws(data, key_end, end)
                if index >= end or data[index] != ord(":"):
                    raise MBIError("DOCUMENT_JSON_INVALID", "Stored document contains an invalid top-level object.")
                value_start = _skip_ws(data, index + 1, end)
                value_stop = _value_end(data, value_start, end)
                if key == "blocks":
                    blocks = _read_rows(data, value_start, value_stop, bounds=bounds)
                elif key == "regionBlocks":
                    region_blocks = _read_region_rows(
                        data,
                        value_start,
                        value_stop,
                        bounds=bounds,
                    )
                else:
                    try:
                        payload[str(key)] = json.loads(data[value_start:value_stop])
                    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                        raise MBIError("DOCUMENT_JSON_INVALID", "Stored document JSON is invalid.") from exc
                index = _skip_ws(data, value_stop, end)
                if index < end and data[index] == ord(","):
                    index = _skip_ws(data, index + 1, end)
                elif index < end and data[index] != ord("}"):
                    raise MBIError("DOCUMENT_JSON_INVALID", "Stored document contains an invalid top-level delimiter.")
            if index >= end or data[index] != ord("}"):
                raise MBIError("DOCUMENT_JSON_INVALID", "Stored document root is unterminated.")
            return payload, blocks, region_blocks
