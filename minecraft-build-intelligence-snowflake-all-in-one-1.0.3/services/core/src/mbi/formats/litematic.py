from __future__ import annotations

import math
from typing import Any

from ..canonical import (
    BuildDocument,
    BuildRegion,
    CanonicalBlockEntity,
    CanonicalEntity,
    ImportDiagnostic,
    IntBoundingBox,
    IntVector3,
    PaletteEntry,
)
from ..compression import Compression
from ..errors import FormatError
from ..limits import NBTLimits, checked_volume
from .common import (
    build_id_from_hash,
    ensure_air_palette,
    require_compound,
    require_list,
    source_metadata,
    vector_from_compound,
)


def normalize_region(position: IntVector3, size: IntVector3) -> IntBoundingBox:
    def axis(pos: int, signed_size: int) -> tuple[int, int]:
        if signed_size == 0:
            raise FormatError("LITEMATIC_ZERO_REGION_SIZE", "Litematic region size cannot be zero.")
        return (pos, pos + signed_size - 1) if signed_size > 0 else (pos + signed_size + 1, pos)

    min_x, max_x = axis(position.x, size.x)
    min_y, max_y = axis(position.y, size.y)
    min_z, max_z = axis(position.z, size.z)
    return IntBoundingBox(IntVector3(min_x, min_y, min_z), IntVector3(max_x, max_y, max_z))


def bits_per_entry(palette_size: int) -> int:
    return max(2, math.ceil(math.log2(max(1, palette_size))))


def unpack_block_states(words: list[int], volume: int, bits: int, *, allow_trailing_words: bool = True) -> list[int]:
    if bits < 1 or bits > 32:
        raise FormatError("LITEMATIC_BITS_INVALID", "Litematic bits per entry is outside the supported range.", {"bits": bits})
    expected_words = math.ceil(volume * bits / 64)
    if len(words) < expected_words:
        raise FormatError(
            "LITEMATIC_BLOCKSTATE_ARRAY_TOO_SHORT",
            "Litematic region does not contain enough packed words.",
            {"expectedWords": expected_words, "actualWords": len(words)},
        )
    if not allow_trailing_words and len(words) != expected_words:
        raise FormatError(
            "LITEMATIC_BLOCKSTATE_ARRAY_TRAILING",
            "Litematic region contains trailing packed words.",
            {"expectedWords": expected_words, "actualWords": len(words)},
        )
    unsigned = [word & 0xFFFFFFFFFFFFFFFF for word in words]
    mask = (1 << bits) - 1
    values: list[int] = []
    for index in range(volume):
        start_bit = index * bits
        start_word = start_bit // 64
        end_word = ((index + 1) * bits - 1) // 64
        bit_offset = start_bit % 64
        low = unsigned[start_word] >> bit_offset
        if end_word == start_word:
            value = low & mask
        else:
            high = unsigned[end_word] << (64 - bit_offset)
            value = (low | high) & mask
        values.append(value)
    return values


def pack_block_states(values: list[int], bits: int) -> list[int]:
    if bits < 1 or bits > 32:
        raise ValueError("bits must be between 1 and 32")
    limit = 1 << bits
    if any(value < 0 or value >= limit for value in values):
        raise ValueError("palette index does not fit selected bit width")
    words = [0] * math.ceil(len(values) * bits / 64)
    mask = limit - 1
    for index, raw in enumerate(values):
        value = raw & mask
        start_bit = index * bits
        word_index = start_bit // 64
        offset = start_bit % 64
        words[word_index] |= (value << offset) & 0xFFFFFFFFFFFFFFFF
        if offset + bits > 64:
            words[word_index + 1] |= value >> (64 - offset)
    return [word if word < 1 << 63 else word - (1 << 64) for word in words]


def _palette_state(raw: Any) -> str:
    compound = require_compound(raw, "BlockStatePalette[]")
    name = compound.get("Name")
    if not isinstance(name, str):
        raise FormatError("LITEMATIC_PALETTE_NAME", "Litematic palette entry lacks a string Name.")
    props = compound.get("Properties", {})
    if not isinstance(props, dict):
        raise FormatError("LITEMATIC_PALETTE_PROPERTIES", "Litematic palette Properties must be a compound.")
    if not props:
        return name
    ordered = ",".join(f"{key}={props[key]}" for key in sorted(props))
    return f"{name}[{ordered}]"


def _entity_position(raw: dict[str, Any]) -> tuple[float, float, float] | None:
    pos = raw.get("Pos")
    if isinstance(pos, list) and len(pos) == 3 and all(isinstance(value, (int, float)) for value in pos):
        return tuple(float(value) for value in pos)
    return None


def _entity_id(raw: dict[str, Any]) -> str | None:
    for key in ("id", "Id"):
        value = raw.get(key)
        if isinstance(value, str):
            return value
    nested = raw.get("Data")
    if isinstance(nested, dict):
        for key in ("id", "Id"):
            value = nested.get(key)
            if isinstance(value, str):
                return value
    return None


def parse_litematic(
    root: dict[str, Any],
    *,
    filename: str,
    compressed: bytes,
    decompressed: bytes,
    compression: Compression,
    limits: NBTLimits,
) -> BuildDocument:
    regions_raw = require_compound(root.get("Regions"), "Regions")
    if len(regions_raw) > limits.max_regions:
        raise FormatError("REGION_LIMIT", "Litematic region count exceeds the configured limit.")
    global_state_to_id: dict[str, int] = {}
    palette: list[PaletteEntry] = []
    regions: list[BuildRegion] = []
    region_blocks: dict[str, dict[IntVector3, int]] = {}
    blocks: dict[IntVector3, int] = {}
    block_entities: list[CanonicalBlockEntity] = []
    entities: list[CanonicalEntity] = []
    pending_block_ticks: list[dict[str, Any]] = []
    pending_fluid_ticks: list[dict[str, Any]] = []
    overlap_count = 0
    all_bounds: list[IntBoundingBox] = []

    # Sorted region names make the flattened overlap policy reproducible.
    for region_name in sorted(regions_raw):
        raw_region = require_compound(regions_raw[region_name], f"Regions.{region_name}")
        position = vector_from_compound(raw_region.get("Position"), f"Regions.{region_name}.Position")
        signed_size = vector_from_compound(raw_region.get("Size"), f"Regions.{region_name}.Size")
        bounds = normalize_region(position, signed_size)
        dimensions = bounds.dimensions
        volume = checked_volume(dimensions.x, dimensions.y, dimensions.z, limits.max_volume)
        palette_raw = require_list(raw_region.get("BlockStatePalette"), f"Regions.{region_name}.BlockStatePalette")
        if not palette_raw:
            raise FormatError("LITEMATIC_EMPTY_PALETTE", "Litematic region palette cannot be empty.", {"region": region_name})
        if len(palette_raw) > limits.max_palette_size:
            raise FormatError("PALETTE_SIZE_LIMIT", "Region palette exceeds the configured limit.")
        local_states = [_palette_state(item) for item in palette_raw]
        local_to_global: list[int] = []
        for state in local_states:
            if state not in global_state_to_id:
                new_id = len(palette)
                global_state_to_id[state] = new_id
                palette.append(PaletteEntry.from_state(new_id, state))
            local_to_global.append(global_state_to_id[state])
        words = raw_region.get("BlockStates")
        if not isinstance(words, list) or not all(isinstance(word, int) and not isinstance(word, bool) for word in words):
            raise FormatError("LITEMATIC_BLOCKSTATES_TYPE", "BlockStates must be an NBT long array.")
        values = unpack_block_states(words, volume, bits_per_entry(len(local_states)))
        if any(value >= len(local_states) for value in values):
            bad = next(value for value in values if value >= len(local_states))
            raise FormatError(
                "PALETTE_INDEX_OUT_OF_RANGE",
                "Litematic block data references a missing palette entry.",
                {"index": bad, "region": region_name},
            )
        region_values: dict[IntVector3, int] = {}
        for index, local_palette_id in enumerate(values):
            y, rem = divmod(index, dimensions.x * dimensions.z)
            z, x = divmod(rem, dimensions.x)
            # Litematica's container dimensions are absolute and the voxel array is based
            # on the normalized minimum corner; the signed source size is selection metadata.
            world = IntVector3(bounds.min.x + x, bounds.min.y + y, bounds.min.z + z)
            global_id = local_to_global[local_palette_id]
            if palette[global_id].is_air_like:
                continue
            region_values[world] = global_id
            if world in blocks:
                overlap_count += 1
            blocks[world] = global_id
        region_blocks[region_name] = region_values

        for raw_be in require_list(raw_region.get("TileEntities", []), f"Regions.{region_name}.TileEntities"):
            be = require_compound(raw_be, "TileEntity")
            pos = be.get("Pos")
            if isinstance(pos, list) and len(pos) == 3 and all(isinstance(v, int) for v in pos):
                world = position + IntVector3(*pos)
                block_entities.append(
                    CanonicalBlockEntity(
                        world,
                        _entity_id(be),
                        be,
                        region_name,
                    )
                )
        for raw_entity in require_list(raw_region.get("Entities", []), f"Regions.{region_name}.Entities"):
            entity = require_compound(raw_entity, "Entity")
            entities.append(
                CanonicalEntity(
                    _entity_id(entity),
                    _entity_position(entity),
                    entity,
                    region_name,
                )
            )
        for raw_tick in require_list(raw_region.get("PendingBlockTicks", []), f"Regions.{region_name}.PendingBlockTicks"):
            tick = require_compound(raw_tick, "PendingBlockTick")
            pending_block_ticks.append({**tick, "$regionName": region_name})
        for raw_tick in require_list(raw_region.get("PendingFluidTicks", []), f"Regions.{region_name}.PendingFluidTicks"):
            tick = require_compound(raw_tick, "PendingFluidTick")
            pending_fluid_ticks.append({**tick, "$regionName": region_name})

        regions.append(
            BuildRegion(
                region_name,
                position,
                signed_size,
                bounds,
                tuple(local_states),
                {
                    k: v
                    for k, v in raw_region.items()
                    if k
                    not in {
                        "Position",
                        "Size",
                        "BlockStatePalette",
                        "BlockStates",
                        "TileEntities",
                        "Entities",
                        "PendingBlockTicks",
                        "PendingFluidTicks",
                    }
                },
            )
        )
        all_bounds.append(bounds)

    palette, inserted_air = ensure_air_palette(palette)
    if inserted_air is not None:
        # Existing palette IDs remain stable because ensure_air_palette appends.
        global_state_to_id[palette[inserted_air].canonical_state] = inserted_air
    if not all_bounds:
        raise FormatError("LITEMATIC_NO_REGIONS", "Litematic contains no regions.")
    bounds = IntBoundingBox(
        IntVector3(
            min(b.min.x for b in all_bounds),
            min(b.min.y for b in all_bounds),
            min(b.min.z for b in all_bounds),
        ),
        IntVector3(
            max(b.max.x for b in all_bounds),
            max(b.max.y for b in all_bounds),
            max(b.max.z for b in all_bounds),
        ),
    )
    version = root.get("Version") if isinstance(root.get("Version"), int) else None
    data_version = root.get("MinecraftDataVersion") if isinstance(root.get("MinecraftDataVersion"), int) else None
    source = source_metadata(
        filename=filename,
        format_name="litematic",
        compression=compression,
        compressed=compressed,
        decompressed=decompressed,
        data_version=data_version,
        format_version=version,
    )
    diagnostics = [ImportDiagnostic("LITEMATIC_IMPORTED", "info", f"Imported {len(regions)} Litematic regions.")]
    if overlap_count:
        diagnostics.append(
            ImportDiagnostic(
                "LITEMATIC_REGION_OVERLAP",
                "warning",
                "Source regions overlap in the flattened view.",
                {
                    "overlappingVoxelWrites": overlap_count,
                    "flattenPolicy": "sorted-region-name-last-wins",
                    "sourceRegionsPreserved": True,
                },
            )
        )
    return BuildDocument(
        schema_version="1.1.0",
        build_id=build_id_from_hash(source.source_sha256),
        source=source,
        metadata=root.get("Metadata", {}) if isinstance(root.get("Metadata"), dict) else {},
        bounds=bounds,
        origin=bounds.min,
        palette=palette,
        regions=regions,
        blocks=blocks,
        region_blocks=region_blocks,
        block_entities=block_entities,
        entities=entities,
        pending_block_ticks=pending_block_ticks,
        pending_fluid_ticks=pending_fluid_ticks,
        diagnostics=diagnostics,
        extension_data={
            "subVersion": root.get("SubVersion"),
            "unknownRootFields": {
                k: v
                for k, v in root.items()
                if k not in {"Version", "SubVersion", "MinecraftDataVersion", "Metadata", "Regions"}
            },
        },
    )
