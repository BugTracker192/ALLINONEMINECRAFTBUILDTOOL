from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    max_visible_blocks: int = 250_000
    max_render_size: int = 4096
    max_total_tile_work: int = 2_147_483_648
    max_texture_dimension: int = 4096
    max_resource_members: int = 100_000
    max_resource_bytes: int = 1_073_741_824
    tile_size: int = 128
    texture_cache_items: int = 2048
    model_cache_items: int = 8192

    @classmethod
    def from_environment(cls) -> "RuntimeConfig":
        defaults = cls()

        def positive(name: str, default: int) -> int:
            raw = os.environ.get(name)
            if raw is None:
                return default
            value = int(raw)
            if value <= 0:
                raise ValueError(f"{name} must be a positive integer")
            return value

        return cls(
            max_visible_blocks=positive(
                "MBI_MAX_VISIBLE_BLOCKS",
                defaults.max_visible_blocks,
            ),
            max_render_size=positive(
                "MBI_MAX_RENDER_SIZE",
                defaults.max_render_size,
            ),
            max_total_tile_work=positive(
                "MBI_MAX_TOTAL_TILE_WORK",
                defaults.max_total_tile_work,
            ),
        )
