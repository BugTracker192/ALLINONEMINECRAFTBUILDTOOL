from __future__ import annotations

import hashlib
import uuid
from collections.abc import Iterable
from typing import Any

from ..canonical import BuildSource, IntBoundingBox, IntVector3, PaletteEntry
from ..compression import Compression
from ..errors import FormatError


def require_compound(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise FormatError("INVALID_NBT_TYPE", f"Expected compound at {path}.", {"path": path})
    return value


def require_list(value: Any, path: str) -> list[Any]:
    if not isinstance(value, list):
        raise FormatError("INVALID_NBT_TYPE", f"Expected list at {path}.", {"path": path})
    return value


def require_bytes(value: Any, path: str) -> bytes:
    if not isinstance(value, bytes):
        raise FormatError("INVALID_NBT_TYPE", f"Expected byte array at {path}.", {"path": path})
    return value


def int_value(compound: dict[str, Any], key: str, *, required: bool = True, default: int = 0) -> int:
    value = compound.get(key)
    if value is None and not required:
        return default
    if not isinstance(value, int):
        raise FormatError("INVALID_NBT_TYPE", f"Expected integer field '{key}'.", {"field": key})
    return value


def vector_from_compound(value: Any, path: str) -> IntVector3:
    compound = require_compound(value, path)
    return IntVector3(int_value(compound, "X"), int_value(compound, "Y"), int_value(compound, "Z"))


def bounds_from_positions(positions: Iterable[IntVector3], fallback: IntBoundingBox) -> IntBoundingBox:
    points = list(positions)
    if not points:
        return fallback
    return IntBoundingBox(
        IntVector3(min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)),
        IntVector3(max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)),
    )


def source_metadata(
    *,
    filename: str,
    format_name: str,
    compression: Compression,
    compressed: bytes,
    decompressed: bytes,
    data_version: int | None,
    format_version: int | None,
) -> BuildSource:
    return BuildSource(
        original_filename=filename,
        detected_format=format_name,
        compression=compression.value,
        source_sha256=hashlib.sha256(compressed).hexdigest(),
        uploaded_size_bytes=len(compressed),
        decompressed_size_bytes=len(decompressed),
        source_data_version=data_version,
        source_format_version=format_version,
    )


def build_id_from_hash(source_hash: str) -> str:
    return "build_" + uuid.uuid5(uuid.NAMESPACE_URL, f"mbi:{source_hash}").hex[:20]


def ensure_air_palette(palette: list[PaletteEntry]) -> tuple[list[PaletteEntry], int]:
    for entry in palette:
        if entry.is_air_like:
            return palette, entry.palette_id
    next_id = max((p.palette_id for p in palette), default=-1) + 1
    return [*palette, PaletteEntry.from_state(next_id, "minecraft:air")], next_id
