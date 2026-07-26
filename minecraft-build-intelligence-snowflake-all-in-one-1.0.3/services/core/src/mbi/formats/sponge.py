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
from ..palette import parse_block_state
from .common import build_id_from_hash, ensure_air_palette, int_value, require_bytes, require_compound, require_list, source_metadata
from .varint import decode_unsigned_varints


def _parse_palette(raw: Any, limits: NBTLimits) -> tuple[list[PaletteEntry], dict[int, int]]:
    compound = require_compound(raw, "Schematic.Blocks.Palette")
    if len(compound) > limits.max_palette_size:
        raise FormatError("PALETTE_SIZE_LIMIT", "Palette exceeds the configured size limit.")
    source_indexes: dict[int, str] = {}
    for state, source_index in compound.items():
        if not isinstance(source_index, int) or source_index < 0:
            raise FormatError("INVALID_PALETTE_INDEX", "Palette index must be a non-negative integer.", {"state": state, "index": source_index})
        if source_index in source_indexes:
            raise FormatError("DUPLICATE_PALETTE_INDEX", "Two palette states use the same index.", {"index": source_index})
        parse_block_state(state)
        source_indexes[source_index] = state
    if source_indexes and set(source_indexes) != set(range(max(source_indexes) + 1)):
        raise FormatError("PALETTE_INDEX_GAP", "Sponge palette indexes must be contiguous.")
    palette = [PaletteEntry.from_state(i, source_indexes[i]) for i in sorted(source_indexes)]
    palette, _ = ensure_air_palette(palette)
    return palette, {index: index for index in source_indexes}


def _position(value: Any, path: str) -> IntVector3:
    if isinstance(value, list) and len(value) == 3 and all(isinstance(v, int) for v in value):
        return IntVector3(*value)
    compound = require_compound(value, path)
    return IntVector3(int_value(compound, "x"), int_value(compound, "y"), int_value(compound, "z"))


def parse_sponge(
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
    version = int_value(schematic, "Version")
    if version not in {1, 2, 3}:
        raise FormatError("SPONGE_UNSUPPORTED_VERSION", "Unsupported Sponge schematic version.", {"version": version})
    data_version = schematic.get("DataVersion") if isinstance(schematic.get("DataVersion"), int) else None
    width = int_value(schematic, "Width") & 0xFFFF
    height = int_value(schematic, "Height") & 0xFFFF
    length = int_value(schematic, "Length") & 0xFFFF
    if max(width, height, length) > limits.max_dimension:
        raise FormatError("STRUCTURE_DIMENSION_LIMIT", "Structure dimension exceeds the configured limit.")
    volume = checked_volume(width, height, length, limits.max_volume)
    offset_raw = schematic.get("Offset", [0, 0, 0])
    if not (isinstance(offset_raw, list) and len(offset_raw) == 3 and all(isinstance(v, int) for v in offset_raw)):
        raise FormatError("INVALID_OFFSET", "Sponge Offset must be an integer array of length three.")
    offset = IntVector3(*offset_raw)

    if version == 3:
        blocks_tag = require_compound(schematic.get("Blocks"), "Schematic.Blocks")
        palette_raw = blocks_tag.get("Palette")
        data_raw = blocks_tag.get("Data")
        block_entities_raw = blocks_tag.get("BlockEntities", [])
    else:
        palette_raw = schematic.get("Palette")
        data_raw = schematic.get("BlockData")
        block_entities_raw = schematic.get("BlockEntities", schematic.get("TileEntities", []))
    palette, source_to_canonical = _parse_palette(palette_raw, limits)
    data = decode_unsigned_varints(require_bytes(data_raw, "BlockData"), expected_count=volume)
    if any(value not in source_to_canonical for value in data):
        bad = next(value for value in data if value not in source_to_canonical)
        raise FormatError("PALETTE_INDEX_OUT_OF_RANGE", "Block data references a palette index that does not exist.", {"index": bad})

    blocks: dict[IntVector3, int] = {}
    palette_by_id = {entry.palette_id: entry for entry in palette}
    for index, source_palette_id in enumerate(data):
        y, rem = divmod(index, width * length)
        z, x = divmod(rem, width)
        canonical_id = source_to_canonical[source_palette_id]
        if not palette_by_id[canonical_id].is_air_like:
            blocks[IntVector3(offset.x + x, offset.y + y, offset.z + z)] = canonical_id

    block_entities: list[CanonicalBlockEntity] = []
    for raw in require_list(block_entities_raw, "BlockEntities"):
        entity = require_compound(raw, "BlockEntity")
        pos_raw = entity.get("Pos")
        if pos_raw is None:
            continue
        local = _position(pos_raw, "BlockEntity.Pos")
        position = IntVector3(offset.x + local.x, offset.y + local.y, offset.z + local.z)
        namespaced_id = entity.get("Id") or entity.get("id")
        block_entities.append(CanonicalBlockEntity(position, namespaced_id if isinstance(namespaced_id, str) else None, entity))
    entities: list[CanonicalEntity] = []
    for raw in require_list(schematic.get("Entities", []), "Entities"):
        entity = require_compound(raw, "Entity")
        pos = entity.get("Pos")
        float_pos = tuple(float(x) for x in pos) if isinstance(pos, list) and len(pos) == 3 else None
        namespaced_id = entity.get("Id") or entity.get("id")
        entities.append(CanonicalEntity(namespaced_id if isinstance(namespaced_id, str) else None, float_pos, entity))

    bounds = IntBoundingBox(offset, IntVector3(offset.x + width - 1, offset.y + height - 1, offset.z + length - 1))
    source = source_metadata(
        filename=filename,
        format_name=f"sponge_schem_v{version}",
        compression=compression,
        compressed=compressed,
        decompressed=decompressed,
        data_version=data_version,
        format_version=version,
    )
    region = BuildRegion("Schematic", offset, IntVector3(width, height, length), bounds, tuple(p.canonical_state for p in palette))
    return BuildDocument(
        schema_version="1.0.0",
        build_id=build_id_from_hash(source.source_sha256),
        source=source,
        metadata=schematic.get("Metadata", {}) if isinstance(schematic.get("Metadata", {}), dict) else {},
        bounds=bounds,
        origin=offset,
        palette=palette,
        regions=[region],
        blocks=blocks,
        block_entities=block_entities,
        entities=entities,
        diagnostics=[ImportDiagnostic("SPONGE_IMPORTED", "info", f"Imported Sponge schematic v{version}.")],
        extension_data={"unknownSchematicFields": {k: v for k, v in schematic.items() if k not in {"Version", "DataVersion", "Metadata", "Width", "Height", "Length", "Offset", "Blocks", "Palette", "BlockData", "BlockEntities", "TileEntities", "Entities", "Biomes"}}},
    )
