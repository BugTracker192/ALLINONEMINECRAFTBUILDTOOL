from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

from ..canonical import CanonicalBlockEntity, IntBoundingBox, IntVector3


class PatchStatus(StrEnum):
    DRAFT = "draft"
    VALIDATED = "validated"
    PREVIEWED = "previewed"
    COMMITTED = "committed"
    REJECTED = "rejected"
    ROLLED_BACK = "rolled_back"
    SUPERSEDED = "superseded"


@dataclass(frozen=True, slots=True)
class BlockChange:
    position: IntVector3
    old_palette_id: int | None
    new_palette_id: int | None
    old_state: str | None = None
    new_state: str | None = None


@dataclass(frozen=True, slots=True)
class BlockEntityChange:
    position: IntVector3
    old_value: CanonicalBlockEntity | None
    new_value: CanonicalBlockEntity | None


@dataclass(frozen=True, slots=True)
class RegionLock:
    lock_id: str
    bounds: IntBoundingBox
    owner: str
    reason: str
    protected_states: tuple[str, ...] = ()


@dataclass(slots=True)
class Patch:
    patch_id: str
    parent_version_id: str
    author: str
    reason: str
    intended_bounds: IntBoundingBox
    max_affected_blocks: int
    operations: list[dict[str, object]]
    coordinate_space: str = "document"
    preconditions: list[dict[str, object]] = field(default_factory=list)
    expected_parent_hash: str | None = None
    target_region: str | None = None
    evidence_refs: list[str] = field(default_factory=list)
    status: PatchStatus = PatchStatus.DRAFT
    changes: list[BlockChange] = field(default_factory=list)
    block_entity_changes: list[BlockEntityChange] = field(default_factory=list)
    validation_messages: list[str] = field(default_factory=list)
    validation_report: dict[str, Any] = field(default_factory=dict)
    preview_report: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: dt.datetime.now(dt.UTC).isoformat())
