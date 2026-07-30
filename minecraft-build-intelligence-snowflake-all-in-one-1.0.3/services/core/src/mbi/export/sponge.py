from __future__ import annotations

import gzip

from ..canonical import BuildDocument, IntVector3
from ..formats.varint import encode_unsigned_varints
from ..nbt import NBTWriter, Tag
from .nbt_utils import typed_compound


def _entity_payload(item, bounds_min: IntVector3, *, block_entity: bool) -> dict[str, tuple[Tag, object]]:
    raw = dict(item.data) if isinstance(item.data, dict) else {}
    nested = raw.get("Data") if isinstance(raw.get("Data"), dict) else {}
    custom = {
        **{key: value for key, value in raw.items() if key not in {"Pos", "Id", "id", "Data"}},
        **nested,
    }
    if block_entity:
        position = item.position
        pos: object = [
            position.x - bounds_min.x,
            position.y - bounds_min.y,
            position.z - bounds_min.z,
        ]
    else:
        position = item.position
        pos = list(position) if position is not None else [0.0, 0.0, 0.0]
    payload: dict[str, tuple[Tag, object]] = {
        "Pos": (Tag.INT_ARRAY if block_entity else Tag.LIST, pos if block_entity else (Tag.DOUBLE, pos)),
        "Data": (Tag.COMPOUND, typed_compound(custom)),
    }
    if item.namespaced_id:
        payload["Id"] = (Tag.STRING, item.namespaced_id)
    return payload


def export_sponge_v3(document: BuildDocument, *, data_version: int | None = None) -> bytes:
    dimensions = document.bounds.dimensions
    ordered_states = sorted(
        {entry.canonical_state for entry in document.palette},
        key=lambda state: (state != "minecraft:air", state),
    )
    if "minecraft:air" not in ordered_states:
        ordered_states.insert(0, "minecraft:air")
    state_to_export = {state: index for index, state in enumerate(ordered_states)}
    palette_by_id = document.palette_by_id()
    def values():
        for y in range(dimensions.y):
            for z in range(dimensions.z):
                for x in range(dimensions.x):
                    position = IntVector3(
                        document.bounds.min.x + x,
                        document.bounds.min.y + y,
                        document.bounds.min.z + z,
                    )
                    source_id = document.blocks.get(position)
                    state = (
                        palette_by_id[source_id].canonical_state
                        if source_id is not None
                        else "minecraft:air"
                    )
                    yield state_to_export[state]
    palette_compound = {state: (Tag.INT, index) for state, index in state_to_export.items()}
    block_entities = [
        _entity_payload(item, document.bounds.min, block_entity=True)
        for item in sorted(document.block_entities, key=lambda item: item.position)
    ]
    entities = [
        _entity_payload(item, document.bounds.min, block_entity=False)
        for item in sorted(
            document.entities,
            key=lambda item: (item.position is None, item.position or (0.0, 0.0, 0.0), item.namespaced_id or ""),
        )
    ]
    blocks_compound = {
        "Palette": (Tag.COMPOUND, palette_compound),
        "Data": (Tag.BYTE_ARRAY, encode_unsigned_varints(values())),
        "BlockEntities": (Tag.LIST, (Tag.COMPOUND, block_entities)),
    }
    schematic = {
        "Version": (Tag.INT, 3),
        "DataVersion": (
            Tag.INT,
            data_version if data_version is not None else (document.source.source_data_version or 0),
        ),
        "Metadata": (
            Tag.COMPOUND,
            {
                "Name": (
                    Tag.STRING,
                    str(document.metadata.get("Name", document.source.original_filename)),
                )
            },
        ),
        "Width": (Tag.SHORT, dimensions.x if dimensions.x < 32768 else dimensions.x - 65536),
        "Height": (Tag.SHORT, dimensions.y if dimensions.y < 32768 else dimensions.y - 65536),
        "Length": (Tag.SHORT, dimensions.z if dimensions.z < 32768 else dimensions.z - 65536),
        "Offset": (Tag.INT_ARRAY, list(document.bounds.min.as_tuple())),
        "Blocks": (Tag.COMPOUND, blocks_compound),
        "Entities": (Tag.LIST, (Tag.COMPOUND, entities)),
    }
    raw = NBTWriter().root("", {"Schematic": (Tag.COMPOUND, schematic)})
    return gzip.compress(raw, mtime=0)
