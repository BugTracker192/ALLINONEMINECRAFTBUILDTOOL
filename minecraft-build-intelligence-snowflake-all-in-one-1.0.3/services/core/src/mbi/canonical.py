from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from .palette import is_air_like, parse_block_state, render_category


@dataclass(frozen=True, order=True, slots=True)
class IntVector3:
    x: int
    y: int
    z: int

    def as_tuple(self) -> tuple[int, int, int]:
        return self.x, self.y, self.z

    def __add__(self, other: "IntVector3") -> "IntVector3":
        return IntVector3(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: "IntVector3") -> "IntVector3":
        return IntVector3(self.x - other.x, self.y - other.y, self.z - other.z)


@dataclass(frozen=True, slots=True)
class IntBoundingBox:
    min: IntVector3
    max: IntVector3

    def __post_init__(self) -> None:
        if self.min.x > self.max.x or self.min.y > self.max.y or self.min.z > self.max.z:
            raise ValueError("bounding-box minimum must not exceed maximum")

    @property
    def dimensions(self) -> IntVector3:
        return IntVector3(
            self.max.x - self.min.x + 1,
            self.max.y - self.min.y + 1,
            self.max.z - self.min.z + 1,
        )

    @property
    def volume(self) -> int:
        dimensions = self.dimensions
        return dimensions.x * dimensions.y * dimensions.z

    def contains(self, point: IntVector3) -> bool:
        return (
            self.min.x <= point.x <= self.max.x
            and self.min.y <= point.y <= self.max.y
            and self.min.z <= point.z <= self.max.z
        )

    def intersects(self, other: "IntBoundingBox") -> bool:
        return not (
            self.max.x < other.min.x
            or other.max.x < self.min.x
            or self.max.y < other.min.y
            or other.max.y < self.min.y
            or self.max.z < other.min.z
            or other.max.z < self.min.z
        )

    def intersection(self, other: "IntBoundingBox") -> "IntBoundingBox | None":
        if not self.intersects(other):
            return None
        return IntBoundingBox(
            IntVector3(
                max(self.min.x, other.min.x),
                max(self.min.y, other.min.y),
                max(self.min.z, other.min.z),
            ),
            IntVector3(
                min(self.max.x, other.max.x),
                min(self.max.y, other.max.y),
                min(self.max.z, other.max.z),
            ),
        )

    def iter_points(self) -> Iterable[IntVector3]:
        for y in range(self.min.y, self.max.y + 1):
            for z in range(self.min.z, self.max.z + 1):
                for x in range(self.min.x, self.max.x + 1):
                    yield IntVector3(x, y, z)


@dataclass(frozen=True, slots=True)
class BuildSource:
    original_filename: str
    detected_format: str
    compression: str
    source_sha256: str
    uploaded_size_bytes: int
    decompressed_size_bytes: int
    source_data_version: int | None = None
    source_format_version: int | None = None


@dataclass(frozen=True, slots=True)
class ImportDiagnostic:
    code: str
    severity: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PaletteEntry:
    palette_id: int
    namespace: str
    block_name: str
    properties: dict[str, str]
    canonical_state: str
    is_air_like: bool
    is_fluid: bool
    render_category: str
    source_legacy_id: int | None = None
    source_legacy_data: int | None = None
    required_mod_namespace: str | None = None
    diagnostics: tuple[str, ...] = ()

    @classmethod
    def from_state(cls, palette_id: int, state: str, **extra: Any) -> "PaletteEntry":
        parsed = parse_block_state(state)
        canonical = parsed.canonical
        return cls(
            palette_id=palette_id,
            namespace=parsed.namespace,
            block_name=parsed.block_name,
            properties=dict(parsed.properties),
            canonical_state=canonical,
            is_air_like=is_air_like(canonical),
            is_fluid=canonical.split("[", 1)[0] in {"minecraft:water", "minecraft:lava"},
            render_category=render_category(canonical),
            required_mod_namespace=None if parsed.namespace == "minecraft" else parsed.namespace,
            **extra,
        )


@dataclass(frozen=True, slots=True)
class CanonicalBlockEntity:
    position: IntVector3
    namespaced_id: str | None
    data: dict[str, Any]
    region_name: str | None = None


@dataclass(frozen=True, slots=True)
class CanonicalEntity:
    namespaced_id: str | None
    position: tuple[float, float, float] | None
    data: dict[str, Any]
    region_name: str | None = None


@dataclass(frozen=True, slots=True)
class BuildRegion:
    name: str
    source_position: IntVector3
    source_signed_size: IntVector3
    bounds: IntBoundingBox
    palette_states: tuple[str, ...]
    extension_data: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class BuildDocument:
    schema_version: str
    build_id: str
    source: BuildSource
    metadata: dict[str, Any]
    bounds: IntBoundingBox
    origin: IntVector3
    palette: list[PaletteEntry]
    regions: list[BuildRegion]
    blocks: dict[IntVector3, int]
    # Each source region retains its independent global-coordinate voxel field. This is
    # essential for lossless overlap handling and preserved multi-region Litematic export.
    region_blocks: dict[str, dict[IntVector3, int]] = field(default_factory=dict)
    block_entities: list[CanonicalBlockEntity] = field(default_factory=list)
    entities: list[CanonicalEntity] = field(default_factory=list)
    pending_block_ticks: list[dict[str, Any]] = field(default_factory=list)
    pending_fluid_ticks: list[dict[str, Any]] = field(default_factory=list)
    diagnostics: list[ImportDiagnostic] = field(default_factory=list)
    extension_data: dict[str, Any] = field(default_factory=dict)
    content_hash: str = ""

    def __post_init__(self) -> None:
        if not self.region_blocks and self.regions:
            # Single-region formats and older stored documents still receive a useful
            # region field without changing their flattened semantics.
            if len(self.regions) == 1:
                self.region_blocks = {self.regions[0].name: dict(self.blocks)}
        if not self.content_hash:
            self.content_hash = self.compute_content_hash()

    def palette_by_id(self) -> dict[int, PaletteEntry]:
        return {entry.palette_id: entry for entry in self.palette}

    def palette_id_for_state(self, canonical_state: str) -> int | None:
        for entry in self.palette:
            if entry.canonical_state == canonical_state:
                return entry.palette_id
        return None

    def ensure_palette_state(self, canonical_state: str) -> int:
        existing = self.palette_id_for_state(canonical_state)
        if existing is not None:
            return existing
        palette_id = max((entry.palette_id for entry in self.palette), default=-1) + 1
        self.palette.append(PaletteEntry.from_state(palette_id, canonical_state))
        return palette_id

    def state_at(self, position: IntVector3) -> PaletteEntry:
        palette = self.palette_by_id()
        palette_id = self.blocks.get(position)
        if palette_id is None:
            for entry in self.palette:
                if entry.is_air_like:
                    return entry
            raise KeyError(f"No block stored at {position} and no air-like palette entry exists")
        return palette[palette_id]

    def iter_non_air(self) -> Iterable[tuple[IntVector3, PaletteEntry]]:
        palette = self.palette_by_id()
        for position, palette_id in sorted(self.blocks.items()):
            entry = palette[palette_id]
            if not entry.is_air_like:
                yield position, entry

    def rebuild_flattened_from_regions(self, order: Iterable[str] | None = None) -> None:
        if not self.region_blocks:
            return
        ordered_names = list(order) if order is not None else sorted(self.region_blocks)
        flattened: dict[IntVector3, int] = {}
        palette = self.palette_by_id()
        for name in ordered_names:
            for position, palette_id in sorted(self.region_blocks.get(name, {}).items()):
                if palette[palette_id].is_air_like:
                    flattened.pop(position, None)
                else:
                    flattened[position] = palette_id
        self.blocks = flattened
        self.content_hash = self.compute_content_hash()

    def compute_content_hash(self) -> str:
        palette_payload = [
            {"id": p.palette_id, "state": p.canonical_state}
            for p in sorted(self.palette, key=lambda p: p.palette_id)
        ]
        block_payload = [
            [position.x, position.y, position.z, palette_id]
            for position, palette_id in sorted(self.blocks.items())
        ]
        region_payload = {
            name: [
                [position.x, position.y, position.z, palette_id]
                for position, palette_id in sorted(region.items())
            ]
            for name, region in sorted(self.region_blocks.items())
        }
        block_entities = [
            {
                "pos": be.position.as_tuple(),
                "id": be.namespaced_id,
                "region": be.region_name,
                "data": be.data,
            }
            for be in sorted(self.block_entities, key=lambda be: (be.region_name or "", be.position))
        ]
        entities = [
            {"pos": entity.position, "id": entity.namespaced_id, "region": entity.region_name, "data": entity.data}
            for entity in sorted(self.entities, key=lambda entity: (entity.region_name or "", entity.position or (0, 0, 0)))
        ]
        encoded = json.dumps(
            {
                "palette": palette_payload,
                "blocks": block_payload,
                "regions": region_payload,
                "blockEntities": block_entities,
                "entities": entities,
                "pendingBlockTicks": self.pending_block_ticks,
                "pendingFluidTicks": self.pending_fluid_ticks,
            },
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode()
        return hashlib.sha256(encoded).hexdigest()

    def to_summary(self) -> dict[str, Any]:
        non_air = sum(1 for _ in self.iter_non_air())
        return {
            "schemaVersion": self.schema_version,
            "buildId": self.build_id,
            "source": asdict(self.source),
            "bounds": asdict(self.bounds),
            "origin": asdict(self.origin),
            "paletteSize": len(self.palette),
            "regionCount": len(self.regions),
            "regionVoxelCounts": {name: len(values) for name, values in sorted(self.region_blocks.items())},
            "nonAirCount": non_air,
            "blockEntityCount": len(self.block_entities),
            "entityCount": len(self.entities),
            "diagnostics": [asdict(item) for item in self.diagnostics],
            "contentHash": self.content_hash,
        }
