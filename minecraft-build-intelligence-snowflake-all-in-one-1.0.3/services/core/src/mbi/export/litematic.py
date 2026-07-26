from __future__ import annotations

import gzip
from typing import Any

from ..canonical import BuildDocument, BuildRegion, IntVector3
from ..formats.litematic import bits_per_entry, pack_block_states
from ..nbt import NBTWriter, Tag
from .nbt_utils import typed_compound

_AIR_STATES = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}


def _state_compound(state: str) -> dict[str, tuple[Tag, object]]:
    if "[" not in state:
        return {"Name": (Tag.STRING, state)}
    name, raw = state[:-1].split("[", 1)
    properties = {}
    for pair in raw.split(","):
        key, value = pair.split("=", 1)
        properties[key] = (Tag.STRING, value)
    return {"Name": (Tag.STRING, name), "Properties": (Tag.COMPOUND, properties)}


def _region_values(document: BuildDocument, region: BuildRegion) -> dict[IntVector3, int]:
    if region.name in document.region_blocks:
        values = {
            position: palette_id
            for position, palette_id in document.region_blocks[region.name].items()
            if region.bounds.contains(position)
        }
        # Include changes that target this region and have no explicit membership yet.
        # For overlapping regions, explicit per-region values win and the flattened field
        # only fills previously empty coordinates.
        for position, palette_id in document.blocks.items():
            if region.bounds.contains(position) and position not in values:
                values[position] = palette_id
        return values
    return {position: palette_id for position, palette_id in document.blocks.items() if region.bounds.contains(position)}


def _region_compound(document: BuildDocument, region: BuildRegion) -> tuple[dict[str, tuple[Tag, Any]], int, int]:
    palette_by_id = document.palette_by_id()
    region_values = _region_values(document, region)
    used_states = {
        palette_by_id[palette_id].canonical_state
        for palette_id in region_values.values()
        if palette_id in palette_by_id
    }
    states = sorted(used_states - _AIR_STATES)
    states.insert(0, "minecraft:air")
    state_to_id = {state: index for index, state in enumerate(states)}
    dimensions = region.bounds.dimensions
    values: list[int] = []
    non_air = 0
    for y in range(dimensions.y):
        for z in range(dimensions.z):
            for x in range(dimensions.x):
                position = IntVector3(region.bounds.min.x + x, region.bounds.min.y + y, region.bounds.min.z + z)
                source_id = region_values.get(position)
                state = palette_by_id[source_id].canonical_state if source_id is not None else "minecraft:air"
                local_id = state_to_id.get(state)
                if local_id is None:
                    # This can only happen for an air-like variant; normalize all absent air
                    # cells to minecraft:air while preserving non-air exact states.
                    local_id = 0
                values.append(local_id)
                non_air += int(state not in _AIR_STATES)
    words = pack_block_states(values, bits_per_entry(len(states)))

    block_entities = []
    for item in document.block_entities:
        if item.region_name not in {None, region.name}:
            continue
        if not region.bounds.contains(item.position):
            continue
        raw = dict(item.data)
        raw["Pos"] = list(item.position.as_tuple())
        if item.namespaced_id and "id" not in raw:
            raw["id"] = item.namespaced_id
        block_entities.append(typed_compound(raw))

    entities = []
    for item in document.entities:
        if item.region_name not in {None, region.name}:
            continue
        raw = dict(item.data)
        if item.position is not None:
            raw["Pos"] = list(item.position)
        if item.namespaced_id and "id" not in raw:
            raw["id"] = item.namespaced_id
        entities.append(typed_compound(raw))

    block_ticks = [
        typed_compound({key: value for key, value in item.items() if key != "$regionName"})
        for item in document.pending_block_ticks
        if item.get("$regionName") in {None, region.name}
    ]
    fluid_ticks = [
        typed_compound({key: value for key, value in item.items() if key != "$regionName"})
        for item in document.pending_fluid_ticks
        if item.get("$regionName") in {None, region.name}
    ]

    known: dict[str, tuple[Tag, Any]] = {
        "Position": (
            Tag.COMPOUND,
            {
                "X": (Tag.INT, region.source_position.x),
                "Y": (Tag.INT, region.source_position.y),
                "Z": (Tag.INT, region.source_position.z),
            },
        ),
        "Size": (
            Tag.COMPOUND,
            {
                "X": (Tag.INT, region.source_signed_size.x),
                "Y": (Tag.INT, region.source_signed_size.y),
                "Z": (Tag.INT, region.source_signed_size.z),
            },
        ),
        "BlockStatePalette": (Tag.LIST, (Tag.COMPOUND, [_state_compound(state) for state in states])),
        "BlockStates": (Tag.LONG_ARRAY, words),
        "TileEntities": (Tag.LIST, (Tag.COMPOUND, block_entities)),
        "Entities": (Tag.LIST, (Tag.COMPOUND, entities)),
        "PendingBlockTicks": (Tag.LIST, (Tag.COMPOUND, block_ticks)),
        "PendingFluidTicks": (Tag.LIST, (Tag.COMPOUND, fluid_ticks)),
    }
    extensions = typed_compound(region.extension_data)
    return {**extensions, **known}, non_air, dimensions.x * dimensions.y * dimensions.z


def _fallback_region(document: BuildDocument) -> BuildRegion:
    dimensions = document.bounds.dimensions
    return BuildRegion(
        "Main",
        document.bounds.min,
        dimensions,
        document.bounds,
        tuple(entry.canonical_state for entry in document.palette),
    )


def export_litematic(
    document: BuildDocument,
    *,
    data_version: int | None = None,
    preserve_regions: bool = True,
) -> bytes:
    regions = document.regions if preserve_regions and document.regions else [_fallback_region(document)]
    region_compounds: dict[str, tuple[Tag, Any]] = {}
    total_non_air = 0
    total_volume = 0
    for region in sorted(regions, key=lambda item: item.name):
        compound, non_air, volume = _region_compound(document, region)
        region_compounds[region.name] = (Tag.COMPOUND, compound)
        total_non_air += non_air
        total_volume += volume

    dimensions = document.bounds.dimensions
    source_metadata = document.metadata if isinstance(document.metadata, dict) else {}
    metadata = {
        "Name": (Tag.STRING, str(source_metadata.get("Name", document.source.original_filename))),
        "Author": (Tag.STRING, str(source_metadata.get("Author", "Minecraft Build Intelligence"))),
        "Description": (Tag.STRING, str(source_metadata.get("Description", "Deterministic preserved-region export"))),
        "RegionCount": (Tag.INT, len(regions)),
        "TotalVolume": (Tag.LONG, total_volume),
        "TotalBlocks": (Tag.LONG, total_non_air),
        "EnclosingSize": (
            Tag.COMPOUND,
            {
                "x": (Tag.INT, dimensions.x),
                "y": (Tag.INT, dimensions.y),
                "z": (Tag.INT, dimensions.z),
            },
        ),
        "TimeCreated": (Tag.LONG, int(source_metadata.get("TimeCreated", 0) or 0)),
        "TimeModified": (Tag.LONG, int(source_metadata.get("TimeModified", 0) or 0)),
    }
    root_extensions = document.extension_data.get("unknownRootFields", {})
    root = {
        **(typed_compound(root_extensions) if isinstance(root_extensions, dict) else {}),
        "Version": (Tag.INT, int(document.source.source_format_version or 6)),
        "SubVersion": (Tag.INT, int(document.extension_data.get("subVersion") or 1)),
        "MinecraftDataVersion": (
            Tag.INT,
            data_version if data_version is not None else (document.source.source_data_version or 0),
        ),
        "Metadata": (Tag.COMPOUND, metadata),
        "Regions": (Tag.COMPOUND, region_compounds),
    }
    return gzip.compress(NBTWriter().root("Litematic", root), mtime=0)
