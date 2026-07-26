from __future__ import annotations

from dataclasses import dataclass

from .errors import MBIError


@dataclass(frozen=True, slots=True)
class NBTLimits:
    max_compressed_bytes: int = 512 * 1024 * 1024
    max_decompressed_bytes: int = 2 * 1024 * 1024 * 1024
    max_depth: int = 128
    max_tags: int = 10_000_000
    max_list_length: int = 10_000_000
    max_array_length: int = 1_000_000_000
    max_string_bytes: int = 1_048_576
    max_palette_size: int = 1_000_000
    max_dimension: int = 65_535
    max_volume: int = 1_000_000_000
    max_regions: int = 10_000
    max_block_entities: int = 10_000_000
    max_entities: int = 10_000_000
    max_diagnostics: int = 10_000


def checked_volume(width: int, height: int, length: int, limit: int) -> int:
    if width < 0 or height < 0 or length < 0:
        raise MBIError("NEGATIVE_DIMENSION", "Canonical dimensions must be non-negative")
    volume = width * height * length
    if volume > limit:
        raise MBIError(
            "STRUCTURE_VOLUME_LIMIT",
            "Structure volume exceeds the configured limit.",
            {"width": width, "height": height, "length": length, "volume": volume, "limit": limit},
        )
    return volume
