from __future__ import annotations

from dataclasses import dataclass

from ..canonical import PaletteEntry


@dataclass(frozen=True, slots=True)
class BlockProfile:
    passable: bool
    supports_player: bool
    collision_height: float
    light_level: int = 0
    gravity_affected: bool = False
    climbable: bool = False
    transparent: bool = False
    doorway: bool = False
    window: bool = False


_AIRLIKE_SUFFIXES = (
    "air",
    "grass",
    "fern",
    "flower",
    "sapling",
    "mushroom",
    "torch",
    "wall_torch",
    "redstone_wire",
    "rail",
    "button",
    "pressure_plate",
    "tripwire",
    "vine",
    "lichen",
)
_LIGHT_LEVELS = {
    "minecraft:torch": 14,
    "minecraft:wall_torch": 14,
    "minecraft:lantern": 15,
    "minecraft:soul_lantern": 10,
    "minecraft:glowstone": 15,
    "minecraft:sea_lantern": 15,
    "minecraft:shroomlight": 15,
    "minecraft:jack_o_lantern": 15,
    "minecraft:redstone_lamp": 15,
    "minecraft:beacon": 15,
    "minecraft:end_rod": 14,
    "minecraft:campfire": 15,
    "minecraft:soul_campfire": 10,
    "minecraft:lava": 15,
}


def base_state(entry: PaletteEntry) -> str:
    return f"{entry.namespace}:{entry.block_name}"


def block_profile(entry: PaletteEntry) -> BlockProfile:
    base = base_state(entry)
    name = entry.block_name
    props = entry.properties
    light = _LIGHT_LEVELS.get(base, 0)
    if base == "minecraft:redstone_lamp" and props.get("lit") == "false":
        light = 0
    if base == "minecraft:campfire" and props.get("lit") == "false":
        light = 0

    if entry.is_air_like or entry.is_fluid:
        return BlockProfile(True, False, 0.0, light_level=light, transparent=True)
    if any(name.endswith(suffix) for suffix in _AIRLIKE_SUFFIXES):
        return BlockProfile(True, False, 0.0, light_level=light, transparent=True)
    if name.endswith("_door"):
        is_open = props.get("open", "false") == "true"
        return BlockProfile(is_open, not is_open, 1.0, transparent=True, doorway=True)
    if name.endswith("_trapdoor"):
        is_open = props.get("open", "false") == "true"
        return BlockProfile(is_open, not is_open, 1.0 if not is_open else 0.0, transparent=True, doorway=True)
    if name.endswith("_slab"):
        slab_type = props.get("type", "bottom")
        height = 1.0 if slab_type == "double" else 0.5
        return BlockProfile(False, True, height, light_level=light)
    if name.endswith("_stairs"):
        return BlockProfile(False, True, 1.0, light_level=light)
    if name.endswith("_carpet") or base == "minecraft:moss_carpet":
        return BlockProfile(False, True, 1 / 16, light_level=light, transparent=True)
    if base == "minecraft:snow":
        layers = max(1, min(8, int(props.get("layers", "1"))))
        return BlockProfile(False, True, layers / 8, light_level=light, transparent=layers < 8)
    if name.endswith("_fence") or name.endswith("_wall") or name.endswith("_fence_gate"):
        gate_open = name.endswith("_fence_gate") and props.get("open", "false") == "true"
        return BlockProfile(gate_open, not gate_open, 1.5 if not gate_open else 0.0, transparent=True, doorway=gate_open)
    if name in {"ladder", "scaffolding", "twisting_vines", "weeping_vines", "cave_vines"}:
        return BlockProfile(True, False, 0.0, transparent=True, climbable=True)
    if "glass" in name or name in {"ice", "packed_ice", "blue_ice"}:
        return BlockProfile(False, True, 1.0, transparent=True, window=True)
    if name in {"sand", "red_sand", "gravel", "concrete_powder", "anvil", "dragon_egg"} or name.endswith("_concrete_powder"):
        return BlockProfile(False, True, 1.0, light_level=light, gravity_affected=True)
    if entry.render_category in {"cutout", "translucent"}:
        return BlockProfile(False, True, 1.0, light_level=light, transparent=True)
    return BlockProfile(False, True, 1.0, light_level=light)
