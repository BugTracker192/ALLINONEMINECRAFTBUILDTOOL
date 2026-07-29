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
    bounds_mismatches: int
    coordinate_mismatches: int
    state_mismatches: int
    region_mismatches: int
    block_entity_mismatches: int
    entity_mismatches: int
    messages: tuple[str, ...]

    @property
    def mismatch_count(self) -> int:
        return (
            self.bounds_mismatches
            + self.coordinate_mismatches
            + self.state_mismatches
            + self.region_mismatches
            + self.block_entity_mismatches
            + self.entity_mismatches
        )


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
    bounds_mismatches = 0
    coordinate_mismatches = 0
    state_mismatches = 0
    region_mismatches = 0
    block_entity_mismatches = 0
    entity_mismatches = 0
    if original.bounds != reparsed.bounds:
        messages.append(f"Bounds mismatch: {original.bounds} != {reparsed.bounds}")
        bounds_mismatches = 1
    original_positions = set(original.blocks)
    reparsed_positions = set(reparsed.blocks)
    missing_positions = original_positions - reparsed_positions
    extra_positions = reparsed_positions - original_positions
    coordinate_mismatches = len(missing_positions) + len(extra_positions)
    for position in sorted(missing_positions)[:25]:
        messages.append(f"Missing exported block coordinate: {position.as_tuple()}")
    for position in sorted(extra_positions)[:25]:
        messages.append(f"Unexpected exported block coordinate: {position.as_tuple()}")
    for position in sorted(original_positions & reparsed_positions):
        a = _state(original, position)
        b = _state(reparsed, position)
        if a != b:
            state_mismatches += 1
            if len(messages) < 50:
                messages.append(f"Block state mismatch at {position.as_tuple()}: {a} != {b}")

    if filename.lower().endswith(".litematic") and original.regions:
        original_regions = {region.name: region for region in original.regions}
        reparsed_regions = {region.name: region for region in reparsed.regions}
        if set(original_regions) != set(reparsed_regions):
            region_mismatches += len(set(original_regions) ^ set(reparsed_regions)) or 1
            messages.append(
                f"Region-name mismatch: {sorted(original_regions)} != {sorted(reparsed_regions)}"
            )
        for name in sorted(set(original_regions) & set(reparsed_regions)):
            a = original_regions[name]
            b = reparsed_regions[name]
            if a.source_position != b.source_position or a.source_signed_size != b.source_signed_size:
                region_mismatches += 1
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
                    region_mismatches += 1
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

    def effective_region(item: Any, document: BuildDocument) -> str | None:
        if not is_litematic:
            return None
        if item.region_name is not None:
            return str(item.region_name)
        position = item.position
        if position is None or not hasattr(position, "x"):
            return None
        matches = sorted(
            region.name for region in document.regions if region.bounds.contains(position)
        )
        return matches[0] if len(matches) == 1 else None

    def entity_key(item: Any, document: BuildDocument) -> tuple[Any, ...]:
        region = effective_region(item, document)
        return (region, item.namespaced_id, item.position)

    original_entities = {
        entity_key(item, original): json.dumps(
            normalized_entity_data(item), sort_keys=True, separators=(",", ":")
        )
        for item in original.entities
    }
    reparsed_entities = {
        entity_key(item, reparsed): json.dumps(
            normalized_entity_data(item), sort_keys=True, separators=(",", ":")
        )
        for item in reparsed.entities
    }
    if original_entities != reparsed_entities:
        entity_mismatches = len(set(original_entities) ^ set(reparsed_entities))
        entity_mismatches += sum(
            original_entities[key] != reparsed_entities[key]
            for key in set(original_entities) & set(reparsed_entities)
        )
        entity_mismatches = entity_mismatches or 1
        messages.append("Entity identity or normalized NBT mismatch after export round trip.")

    def block_entity_key(item: Any, document: BuildDocument) -> tuple[Any, ...]:
        region = effective_region(item, document)
        return (region, item.position, item.namespaced_id)

    original_block_entities = {
        block_entity_key(item, original): normalized_entity_data(item)
        for item in original.block_entities
    }
    reparsed_block_entities = {
        block_entity_key(item, reparsed): normalized_entity_data(item)
        for item in reparsed.block_entities
    }
    if original_block_entities != reparsed_block_entities:
        block_entity_mismatches = len(
            set(original_block_entities) ^ set(reparsed_block_entities)
        )
        block_entity_mismatches += sum(
            original_block_entities[key] != reparsed_block_entities[key]
            for key in set(original_block_entities) & set(reparsed_block_entities)
        )
        block_entity_mismatches = block_entity_mismatches or 1
        messages.append("Block-entity identity or normalized NBT mismatch after export round trip.")

    mismatch_count = (
        bounds_mismatches
        + coordinate_mismatches
        + state_mismatches
        + region_mismatches
        + block_entity_mismatches
        + entity_mismatches
    )
    return RoundTripReport(
        mismatch_count == 0,
        original.content_hash,
        reparsed.content_hash,
        bounds_mismatches,
        coordinate_mismatches,
        state_mismatches,
        region_mismatches,
        block_entity_mismatches,
        entity_mismatches,
        tuple(messages[:100]),
    )
