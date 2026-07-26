from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RuntimeConfig:
    max_visible_blocks: int = 250_000
    max_render_size: int = 4096
    max_texture_dimension: int = 4096
    max_resource_members: int = 100_000
    max_resource_bytes: int = 1_073_741_824
    tile_size: int = 128
    texture_cache_items: int = 2048
    model_cache_items: int = 8192
