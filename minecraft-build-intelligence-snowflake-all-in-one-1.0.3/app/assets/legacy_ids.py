from __future__ import annotations

from dataclasses import dataclass


# Asset aliases are deliberately versioned and never mutate the canonical build.
# They bridge older schematic identifiers to names used by the bundled modern
# resource pack.
LEGACY_ASSET_MIGRATION_VERSION = "java-1.20-through-1.21.5-v1"

LEGACY_BLOCK_ALIASES: dict[str, str] = {
    # 1.21.5 resource-location renames.
    "chain": "iron_chain",
    "grass": "short_grass",
    # Older Java names still encountered in converted WorldEdit schematics.
    "grass_path": "dirt_path",
    "melon_block": "melon",
    "mob_spawner": "spawner",
    "nether_brick": "nether_bricks",
    "quartz_ore": "nether_quartz_ore",
    "red_nether_brick": "red_nether_bricks",
    "reeds": "sugar_cane",
    "slime": "slime_block",
    "snow_layer": "snow",
    "stonebrick": "stone_bricks",
    "waterlily": "lily_pad",
    "wooden_button": "oak_button",
    "wooden_door": "oak_door",
    "wooden_pressure_plate": "oak_pressure_plate",
    "wooden_slab": "oak_slab",
}


@dataclass(frozen=True, slots=True)
class AssetStateMigration:
    source_state: str
    target_state: str
    source_block: str
    target_block: str
    table_version: str = LEGACY_ASSET_MIGRATION_VERSION


def migrate_asset_state(canonical_state: str) -> AssetStateMigration | None:
    """Return an asset-only state migration while preserving all properties."""
    base, separator, suffix = canonical_state.partition("[")
    namespace, colon, block = base.partition(":")
    if not colon:
        namespace, block = "minecraft", namespace
    if namespace != "minecraft":
        return None
    target = LEGACY_BLOCK_ALIASES.get(block)
    if target is None:
        return None
    target_state = f"minecraft:{target}"
    if separator:
        target_state += f"[{suffix}"
    return AssetStateMigration(
        source_state=canonical_state,
        target_state=target_state,
        source_block=block,
        target_block=target,
    )
