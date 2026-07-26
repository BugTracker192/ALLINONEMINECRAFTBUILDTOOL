from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from ..canonical import BuildDocument, IntVector3
from ..importer import import_build


@dataclass(frozen=True, slots=True)
class RoundTripReport:
    valid: bool
    source_hash: str
    exported_hash: str
    mismatch_count: int
    messages: tuple[str, ...]


def _normalized_nbt(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"bytes": value.hex()}
    if isinstance(value, dict):
        return {str(key): _normalized_nbt(item) for key, item in sorted(value.items()) if not str(key).startswith("$")}
    if isinstance(value, (list, tuple)):
        return [_normalized_nbt(item) for item in value]
    return value


def _state(document: BuildDocument, position: IntVector3) -> str:
    palette_id = document.blocks.get(position)
    if palette_id is None:
        return "minecraft:air"
    return document.palette_by_id()[palette_id].canonical_state


def verify_round_trip(original: BuildDocument, exported: bytes, filename: str) -> RoundTripReport:
    reparsed = import_build(exported, filename)
    messages: list[str] = []
    mismatches = 0
    if original.bounds != reparsed.bounds:
        messages.append(f"Bounds mismatch: {original.bounds} != {reparsed.bounds}")
        mismatches += 1
    union_min = IntVector3(
        min(original.bounds.min.x, reparsed.bounds.min.x),
        min(original.bounds.min.y, reparsed.bounds.min.y),
        min(original.bounds.min.z, reparsed.bounds.min.z),
    )
    union_max = IntVector3(
        max(original.bounds.max.x, reparsed.bounds.max.x),
        max(original.bounds.max.y, reparsed.bounds.max.y),
        max(original.bounds.max.z, reparsed.bounds.max.z),
    )
    for y in range(union_min.y, union_max.y + 1):
        for z in range(union_min.z, union_max.z + 1):
            for x in range(union_min.x, union_max.x + 1):
                position = IntVector3(x, y, z)
                a = _state(original, position)
                b = _state(reparsed, position)
                if a != b:
                    mismatches += 1
                    if len(messages) < 50:
                        messages.append(f"Block mismatch at ({x},{y},{z}): {a} != {b}")

    if filename.lower().endswith(".litematic") and original.regions:
        original_regions = {region.name: region for region in original.regions}
        reparsed_regions = {region.name: region for region in reparsed.regions}
        if set(original_regions) != set(reparsed_regions):
            mismatches += 1
            messages.append(
                f"Region-name mismatch: {sorted(original_regions)} != {sorted(reparsed_regions)}"
            )
        for name in sorted(set(original_regions) & set(reparsed_regions)):
            a = original_regions[name]
            b = reparsed_regions[name]
            if a.source_position != b.source_position or a.source_signed_size != b.source_signed_size:
                mismatches += 1
                messages.append(
                    f"Region transform mismatch for {name}: "
                    f"{a.source_position}/{a.source_signed_size} != {b.source_position}/{b.source_signed_size}"
                )
            original_values = original.region_blocks.get(name, {})
            reparsed_values = reparsed.region_blocks.get(name, {})
            original_palette = original.palette_by_id()
            reparsed_palette = reparsed.palette_by_id()
            positions = set(original_values) | set(reparsed_values)
            for position in sorted(positions):
                a_state = (
                    original_palette[original_values[position]].canonical_state
                    if position in original_values
                    else "minecraft:air"
                )
                b_state = (
                    reparsed_palette[reparsed_values[position]].canonical_state
                    if position in reparsed_values
                    else "minecraft:air"
                )
                if a_state != b_state:
                    mismatches += 1
                    if len(messages) < 50:
                        messages.append(f"Region {name} mismatch at {position.as_tuple()}: {a_state} != {b_state}")

    is_litematic = filename.lower().endswith(".litematic")

    def normalized_entity_data(item: Any) -> Any:
        raw = dict(item.data) if isinstance(item.data, dict) else {}
        nested = raw.get("Data") if isinstance(raw.get("Data"), dict) else {}
        merged = {
            **{key: value for key, value in raw.items() if key not in {"Pos", "Id", "id", "Data"}},
            **nested,
        }
        return _normalized_nbt(merged)

    def entity_key(item: Any) -> tuple[Any, ...]:
        region = item.region_name if is_litematic else None
        return (region, item.namespaced_id, item.position)

    original_entities = {
        entity_key(item): json.dumps(normalized_entity_data(item), sort_keys=True, separators=(",", ":"))
        for item in original.entities
    }
    reparsed_entities = {
        entity_key(item): json.dumps(normalized_entity_data(item), sort_keys=True, separators=(",", ":"))
        for item in reparsed.entities
    }
    if original_entities != reparsed_entities:
        mismatches += len(set(original_entities) ^ set(reparsed_entities)) or 1
        messages.append("Entity identity or normalized NBT mismatch after export round trip.")

    def block_entity_key(item: Any) -> tuple[Any, ...]:
        region = item.region_name if is_litematic else None
        return (region, item.position, item.namespaced_id)

    original_block_entities = {
        block_entity_key(item): normalized_entity_data(item)
        for item in original.block_entities
    }
    reparsed_block_entities = {
        block_entity_key(item): normalized_entity_data(item)
        for item in reparsed.block_entities
    }
    if original_block_entities != reparsed_block_entities:
        mismatches += len(set(original_block_entities) ^ set(reparsed_block_entities)) or 1
        messages.append("Block-entity identity or normalized NBT mismatch after export round trip.")

    return RoundTripReport(
        mismatches == 0,
        original.content_hash,
        reparsed.content_hash,
        mismatches,
        tuple(messages[:100]),
    )
