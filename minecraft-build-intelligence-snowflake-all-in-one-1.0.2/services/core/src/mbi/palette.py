from __future__ import annotations

import re
from dataclasses import dataclass

from .errors import FormatError

_RESOURCE = re.compile(r"^(?P<namespace>[a-z0-9_.-]+):(?P<path>[a-z0-9_./-]+)$")
_PROPERTY = re.compile(r"^[a-z0-9_.-]+$")


@dataclass(frozen=True, slots=True)
class ParsedBlockState:
    namespace: str
    block_name: str
    properties: dict[str, str]

    @property
    def canonical(self) -> str:
        base = f"{self.namespace}:{self.block_name}"
        if not self.properties:
            return base
        props = ",".join(f"{key}={self.properties[key]}" for key in sorted(self.properties))
        return f"{base}[{props}]"


def parse_block_state(value: str) -> ParsedBlockState:
    value = value.strip()
    if not value:
        raise FormatError("EMPTY_BLOCK_STATE", "Block-state palette entry is empty.")
    if "[" not in value:
        resource, raw_props = value, None
    else:
        open_index = value.find("[")
        if not value.endswith("]") or value.count("[") != 1 or value.count("]") != 1:
            raise FormatError("MALFORMED_BLOCK_STATE", "Block-state brackets are malformed.", {"state": value})
        resource, raw_props = value[:open_index], value[open_index + 1 : -1]
    match = _RESOURCE.fullmatch(resource)
    if not match:
        raise FormatError("INVALID_BLOCK_RESOURCE", "Invalid namespaced block resource.", {"resource": resource})
    properties: dict[str, str] = {}
    if raw_props is not None:
        if raw_props == "":
            raise FormatError("EMPTY_BLOCK_PROPERTIES", "Block-state brackets cannot be empty.", {"state": value})
        for pair in raw_props.split(","):
            if pair.count("=") != 1:
                raise FormatError("MALFORMED_BLOCK_PROPERTY", "Block-state property is malformed.", {"property": pair})
            key, prop_value = pair.split("=", 1)
            if not key or not prop_value or not _PROPERTY.fullmatch(key) or not _PROPERTY.fullmatch(prop_value):
                raise FormatError("INVALID_BLOCK_PROPERTY", "Block-state property key or value is invalid.", {"property": pair})
            if key in properties:
                raise FormatError("DUPLICATE_BLOCK_PROPERTY", "Block-state property key is duplicated.", {"key": key})
            properties[key] = prop_value
    return ParsedBlockState(match.group("namespace"), match.group("path"), properties)


def is_air_like(canonical: str) -> bool:
    base = canonical.split("[", 1)[0]
    return base in {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}


def render_category(canonical: str) -> str:
    base = canonical.split("[", 1)[0]
    if base.endswith(("glass", "glass_pane", "ice")) or base in {"minecraft:water", "minecraft:lava"}:
        return "translucent"
    if any(token in base for token in ("leaves", "sapling", "flower", "grass", "vine", "torch", "rail")):
        return "cutout"
    if any(token in base for token in ("glowstone", "sea_lantern", "shroomlight", "lantern")):
        return "emissive"
    return "opaque"
