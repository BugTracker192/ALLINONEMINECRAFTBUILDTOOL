from __future__ import annotations

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
from ..voxel import ChunkedVoxelMap
from .common import (
    build_id_from_hash,
    ensure_air_palette,
    int_value,
    require_bytes,
    require_compound,
    require_list,
    source_metadata,
)

# Exact mappings are intentionally conservative. Unmapped values are preserved as typed placeholders.
_LEGACY_EXACT: dict[tuple[int, int], str] = {
    (0, 0): "minecraft:air",
    (1, 0): "minecraft:stone",
    (2, 0): "minecraft:grass_block[snowy=false]",
    (3, 0): "minecraft:dirt",
    (4, 0): "minecraft:cobblestone",
    (5, 0): "minecraft:oak_planks",
    (7, 0): "minecraft:bedrock",
    (12, 0): "minecraft:sand",
    (13, 0): "minecraft:gravel",
    (17, 0): "minecraft:oak_log[axis=y]",
    (20, 0): "minecraft:glass",
    (45, 0): "minecraft:bricks",
    (50, 0): "minecraft:torch[facing=up]",
    (89, 0): "minecraft:glowstone",
}


def _legacy_state(block_id: int, data: int) -> tuple[str, tuple[str, ...]]:
    exact = _LEGACY_EXACT.get((block_id, data))
    if exact:
        return exact, ()
    # Preserve source numeric semantics in the canonical palette rather than silently substituting air.
    return f"legacy:numeric_{block_id}[data={data}]", ("unresolved_legacy_mapping",)


def parse_legacy(
    root: dict[str, Any],
    *,
    filename: str,
    compressed: bytes,
    decompressed: bytes,
    compression: Compression,
    limits: NBTLimits,
) -> BuildDocument:
    schematic = root.get("Schematic") if isinstance(root.get("Schematic"), dict) else root
    schematic = require_compound(schematic, "Schematic")
    width = int_value(schematic, "Width") & 0xFFFF
    height = int_value(schematic, "Height") & 0xFFFF
    length = int_value(schematic, "Length") & 0xFFFF
    volume = checked_volume(width, height, length, limits.max_volume)
    low_ids = require_bytes(schematic.get("Blocks"), "Blocks")
    data = require_bytes(schematic.get("Data"), "Data")
    add = schematic.get("AddBlocks")
    if len(low_ids) != volume or len(data) != volume:
        raise FormatError("LEGACY_ARRAY_LENGTH", "Legacy Blocks/Data arrays must equal the structure volume.", {"volume": volume, "blocks": len(low_ids), "data": len(data)})
    if add is not None and not isinstance(add, bytes):
        raise FormatError("INVALID_NBT_TYPE", "Legacy AddBlocks must be a byte array.")
    if add is not None and len(add) < (volume + 1) // 2:
        raise FormatError("LEGACY_ADDBLOCKS_LENGTH", "Legacy AddBlocks array is too short.")

    offset = IntVector3(
        int(schematic.get("WEOffsetX", 0)),
        int(schematic.get("WEOffsetY", 0)),
        int(schematic.get("WEOffsetZ", 0)),
    )
    palette_map: dict[tuple[int, int], int] = {}
    palette: list[PaletteEntry] = []
    blocks = ChunkedVoxelMap()
    unresolved = 0
    for index in range(volume):
        high = 0
        if add is not None:
            packed = add[index // 2]
            high = (packed & 0x0F) if index % 2 == 0 else ((packed >> 4) & 0x0F)
        block_id = low_ids[index] | (high << 8)
        metadata = data[index] & 0x0F
        key = (block_id, metadata)
        palette_id = palette_map.get(key)
        if palette_id is None:
            state, diagnostics = _legacy_state(block_id, metadata)
            palette_id = len(palette)
            palette_map[key] = palette_id
            parsed_entry = PaletteEntry.from_state(
                palette_id,
                state,
                source_legacy_id=block_id,
                source_legacy_data=metadata,
                diagnostics=diagnostics,
            )
            palette.append(parsed_entry)
            unresolved += int(bool(diagnostics))
        if palette[palette_id].is_air_like:
            continue
        y, rem = divmod(index, width * length)
        z, x = divmod(rem, width)
        blocks[IntVector3(offset.x + x, offset.y + y, offset.z + z)] = palette_id
    palette, _ = ensure_air_palette(palette)

    block_entities: list[CanonicalBlockEntity] = []
    for raw in require_list(schematic.get("TileEntities", []), "TileEntities"):
        be = require_compound(raw, "TileEntity")
        if all(isinstance(be.get(axis), int) for axis in ("x", "y", "z")):
            pos = IntVector3(be["x"], be["y"], be["z"])
            block_entities.append(CanonicalBlockEntity(pos, be.get("id") if isinstance(be.get("id"), str) else None, be))
    entities: list[CanonicalEntity] = []
    for raw in require_list(schematic.get("Entities", []), "Entities"):
        entity = require_compound(raw, "Entity")
        pos = entity.get("Pos")
        float_pos = tuple(float(v) for v in pos) if isinstance(pos, list) and len(pos) == 3 else None
        entities.append(CanonicalEntity(entity.get("id") if isinstance(entity.get("id"), str) else None, float_pos, entity))

    bounds = IntBoundingBox(offset, IntVector3(offset.x + width - 1, offset.y + height - 1, offset.z + length - 1))
    source = source_metadata(
        filename=filename,
        format_name="legacy_mcedit_schematic",
        compression=compression,
        compressed=compressed,
        decompressed=decompressed,
        data_version=None,
        format_version=None,
    )
    diagnostics = [ImportDiagnostic("LEGACY_IMPORTED", "warning", "Imported legacy MCEdit/Schematica Alpha structure using a conservative mapping profile.")]
    if unresolved:
        diagnostics.append(ImportDiagnostic("LEGACY_UNRESOLVED_STATES", "warning", "Some legacy numeric block states remain unresolved placeholders.", {"unresolvedPaletteEntries": unresolved}))
    return BuildDocument(
        schema_version="1.0.0",
        build_id=build_id_from_hash(source.source_sha256),
        source=source,
        metadata={"Materials": schematic.get("Materials"), "legacySourceVersion": "auto"},
        bounds=bounds,
        origin=offset,
        palette=palette,
        regions=[BuildRegion("Schematic", offset, IntVector3(width, height, length), bounds, tuple(p.canonical_state for p in palette))],
        blocks=blocks,
        block_entities=block_entities,
        entities=entities,
        diagnostics=diagnostics,
        extension_data={"legacyRoot": schematic},
    )
