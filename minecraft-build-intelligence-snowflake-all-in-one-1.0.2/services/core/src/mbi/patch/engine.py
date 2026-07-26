from __future__ import annotations

import copy
import hashlib
import math
import uuid
from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from ..canonical import BuildDocument, BuildRegion, CanonicalBlockEntity, IntBoundingBox, IntVector3
from ..errors import PatchError
from ..palette import parse_block_state
from .geometry import (
    arch,
    bezier,
    cuboid,
    cylinder,
    deterministic_mask,
    ellipse,
    extrude_profile,
    integer_scale,
    line,
    loft_profiles,
    mirror,
    normalize_box,
    polyline,
    rotate_y,
    sphere,
)
from .model import BlockChange, BlockEntityChange, Patch, PatchStatus, RegionLock

_AIR_STATES = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air"}


@dataclass(frozen=True, slots=True)
class BuildVersion:
    version_id: str
    parent_version_id: str | None
    document: BuildDocument
    patch_id: str | None
    branch_name: str = "main"
    metadata: dict[str, Any] = field(default_factory=dict)


def _vec(raw: object, field_name: str) -> IntVector3:
    if not isinstance(raw, (list, tuple)) or len(raw) != 3 or not all(isinstance(item, int) for item in raw):
        raise PatchError("PATCH_VECTOR_INVALID", f"{field_name} must be a three-integer vector.")
    return IntVector3(int(raw[0]), int(raw[1]), int(raw[2]))


def _bounds(operation: dict[str, object], min_key: str = "min", max_key: str = "max") -> IntBoundingBox:
    return normalize_box(_vec(operation[min_key], min_key), _vec(operation[max_key], max_key))


def _canonical_state(raw: object) -> str:
    try:
        return parse_block_state(str(raw)).canonical
    except Exception as exc:
        raise PatchError("PATCH_STATE_INVALID", "Patch contains an invalid block state.", {"state": str(raw)}) from exc


def _state_transform(state: str, *, quarter_turns: int = 0, mirror_axis: str | None = None) -> str:
    parsed = parse_block_state(state)
    properties = dict(parsed.properties)
    facing = properties.get("facing")
    if facing in {"north", "east", "south", "west"}:
        order = ["north", "east", "south", "west"]
        index = order.index(facing)
        if mirror_axis == "x":
            facing = {"east": "west", "west": "east"}.get(facing, facing)
        elif mirror_axis == "z":
            facing = {"north": "south", "south": "north"}.get(facing, facing)
        facing = order[(order.index(facing) + quarter_turns) % 4]
        properties["facing"] = facing
    axis = properties.get("axis")
    if axis in {"x", "z"} and quarter_turns % 2:
        properties["axis"] = "z" if axis == "x" else "x"
    rotation = properties.get("rotation")
    if rotation is not None and rotation.isdigit():
        value = int(rotation) % 16
        if mirror_axis == "x":
            value = (-value) % 16
        elif mirror_axis == "z":
            value = (8 - value) % 16
        value = (value + quarter_turns * 4) % 16
        properties["rotation"] = str(value)
    shape = properties.get("shape")
    if shape and mirror_axis and ("left" in shape or "right" in shape):
        properties["shape"] = shape.replace("left", "__tmp__").replace("right", "left").replace("__tmp__", "right")
    if not properties:
        return f"{parsed.namespace}:{parsed.block_name}"
    return f"{parsed.namespace}:{parsed.block_name}[" + ",".join(f"{key}={properties[key]}" for key in sorted(properties)) + "]"


class PatchEngine:
    def __init__(self, root: BuildDocument) -> None:
        root_id = "ver_" + root.content_hash[:20]
        self.versions: dict[str, BuildVersion] = {
            root_id: BuildVersion(root_id, None, root, None, "main", {"root": True})
        }
        self.active_version_id = root_id
        self.branch_heads: dict[str, str] = {"main": root_id}
        self.current_branch = "main"
        self.checkpoints: dict[str, str] = {}
        self.patches: dict[str, Patch] = {}
        self.locks: dict[str, RegionLock] = {}

    @property
    def active(self) -> BuildVersion:
        return self.versions[self.active_version_id]

    def create_patch(
        self,
        reason: str,
        author: str,
        bounds: IntBoundingBox,
        max_affected_blocks: int,
        operations: list[dict[str, object]],
        *,
        coordinate_space: str = "document",
        preconditions: list[dict[str, object]] | None = None,
        expected_parent_hash: str | None = None,
        target_region: str | None = None,
        evidence_refs: list[str] | None = None,
    ) -> Patch:
        if coordinate_space != "document":
            raise PatchError("PATCH_COORDINATE_SPACE", "Only document coordinates are accepted by the canonical patch engine.")
        patch = Patch(
            "patch_" + uuid.uuid4().hex[:20],
            self.active_version_id,
            author,
            reason,
            bounds,
            max_affected_blocks,
            operations,
            coordinate_space,
            preconditions or [],
            expected_parent_hash,
            target_region,
            list(evidence_refs or []),
        )
        self.patches[patch.patch_id] = patch
        return patch

    def lock_region(
        self,
        bounds: IntBoundingBox,
        owner: str,
        reason: str,
        protected_states: Iterable[str] = (),
    ) -> RegionLock:
        lock = RegionLock(
            "lock_" + uuid.uuid4().hex[:16],
            bounds,
            owner,
            reason,
            tuple(sorted(_canonical_state(state) for state in protected_states)),
        )
        self.locks[lock.lock_id] = lock
        return lock

    def unlock_region(self, lock_id: str, owner: str) -> None:
        lock = self.locks.get(lock_id)
        if lock is None:
            raise PatchError("PATCH_LOCK_NOT_FOUND", "Region lock does not exist.")
        if lock.owner != owner:
            raise PatchError("PATCH_LOCK_OWNER", "Only the lock owner can remove the region lock.")
        del self.locks[lock_id]

    def _state_map(self, document: BuildDocument) -> dict[IntVector3, str]:
        palette = document.palette_by_id()
        return {position: palette[palette_id].canonical_state for position, palette_id in document.blocks.items()}

    def _entity_map(self, document: BuildDocument) -> dict[IntVector3, CanonicalBlockEntity]:
        return {entity.position: entity for entity in document.block_entities}

    def _check_preconditions(self, patch: Patch, states: dict[IntVector3, str]) -> None:
        document = self.active.document
        if patch.expected_parent_hash and patch.expected_parent_hash != document.content_hash:
            raise PatchError(
                "PATCH_PARENT_HASH_MISMATCH",
                "Patch expected a different parent content hash.",
                {"expected": patch.expected_parent_hash, "actual": document.content_hash},
            )
        for precondition in patch.preconditions:
            kind = precondition.get("type")
            if kind == "block_state":
                position = _vec(precondition.get("position"), "precondition.position")
                expected = _canonical_state(precondition.get("state"))
                actual = states.get(position, "minecraft:air")
                if actual != expected:
                    raise PatchError(
                        "PATCH_PRECONDITION_STATE",
                        "Block-state precondition failed.",
                        {"position": position.as_tuple(), "expected": expected, "actual": actual},
                    )
            elif kind == "chunk_hash":
                # A deterministic local hash avoids coupling validation to storage encoding.
                chunk = _vec(precondition.get("chunk"), "precondition.chunk")
                rows = [
                    (point.as_tuple(), state)
                    for point, state in states.items()
                    if point.x // 16 == chunk.x and point.y // 16 == chunk.y and point.z // 16 == chunk.z
                ]
                actual = hashlib.sha256(repr(sorted(rows)).encode()).hexdigest()
                if actual != precondition.get("hash"):
                    raise PatchError("PATCH_PRECONDITION_CHUNK_HASH", "Chunk-hash precondition failed.", {"actual": actual})
            elif kind == "version":
                if precondition.get("versionId") != self.active_version_id:
                    raise PatchError("PATCH_PRECONDITION_VERSION", "Version precondition failed.")
            else:
                raise PatchError("PATCH_PRECONDITION_UNKNOWN", "Unknown patch precondition.", {"type": kind})

    def _write(self, target: dict[IntVector3, str], position: IntVector3, state: str | None) -> None:
        if state is None or state in _AIR_STATES:
            target.pop(position, None)
        else:
            target[position] = state

    def _points_with_state(self, points: Iterable[IntVector3], state: str) -> dict[IntVector3, str]:
        return {point: state for point in points}

    def _operation_changes(
        self,
        operation: dict[str, object],
        states: dict[IntVector3, str],
        entities: dict[IntVector3, CanonicalBlockEntity],
    ) -> tuple[dict[IntVector3, str | None], dict[IntVector3, CanonicalBlockEntity | None]]:
        op = operation.get("type")
        block_updates: dict[IntVector3, str | None] = {}
        entity_updates: dict[IntVector3, CanonicalBlockEntity | None] = {}

        if op == "set_block":
            block_updates[_vec(operation.get("position"), "position")] = _canonical_state(operation.get("state"))
        elif op in {"set_blocks", "paste_template"}:
            raw_blocks = operation.get("blocks")
            if not isinstance(raw_blocks, list):
                raise PatchError("PATCH_BLOCKS_INVALID", "set_blocks requires a blocks list.")
            offset = _vec(operation.get("offset", [0, 0, 0]), "offset")
            for item in raw_blocks:
                if not isinstance(item, dict):
                    raise PatchError("PATCH_BLOCK_INVALID", "set_blocks entries must be objects.")
                point = _vec(item.get("position"), "blocks.position") + offset
                block_updates[point] = _canonical_state(item.get("state"))
        elif op in {"fill_cuboid", "hollow_cuboid", "clear_region"}:
            box = _bounds(operation)
            state = None if op == "clear_region" else _canonical_state(operation.get("state"))
            for point in cuboid(box, hollow=op == "hollow_cuboid"):
                block_updates[point] = state
        elif op == "replace_blocks":
            from_states = {_canonical_state(item) for item in operation.get("from", [])}  # type: ignore[arg-type]
            to_state = _canonical_state(operation.get("to"))
            candidates = [point for point, state in states.items() if state in from_states]
            if "min" in operation and "max" in operation:
                box = _bounds(operation)
                candidates = [point for point in candidates if box.contains(point)]
            mask = operation.get("mask")
            if isinstance(mask, dict) and mask.get("type") == "surface_noise":
                candidates = sorted(
                    deterministic_mask(
                        candidates,
                        seed=int(mask.get("seed", 0)),
                        probability=float(mask.get("probability", 1.0)),
                    )
                )
            for point in candidates:
                block_updates[point] = to_state
        elif op == "draw_line":
            state = _canonical_state(operation.get("state"))
            block_updates.update(self._points_with_state(line(_vec(operation.get("start"), "start"), _vec(operation.get("end"), "end")), state))
        elif op == "draw_polyline":
            raw_points = operation.get("points")
            if not isinstance(raw_points, list):
                raise PatchError("PATCH_POINTS_INVALID", "draw_polyline requires points.")
            state = _canonical_state(operation.get("state"))
            block_updates.update(self._points_with_state(polyline([_vec(item, "points[]") for item in raw_points]), state))
        elif op == "draw_wall":
            start = _vec(operation.get("start"), "start")
            end = _vec(operation.get("end"), "end")
            height = int(operation.get("height", 1))
            thickness = int(operation.get("thickness", 1))
            state = _canonical_state(operation.get("state"))
            base = line(start, end)
            for point in base:
                for dy in range(height):
                    for offset in range(thickness):
                        block_updates[IntVector3(point.x, point.y + dy, point.z + offset)] = state
        elif op in {"draw_floor", "draw_roof"}:
            box = _bounds(operation)
            state = _canonical_state(operation.get("state"))
            if op == "draw_floor" or operation.get("style", "flat") == "flat":
                y = int(operation.get("y", box.min.y if op == "draw_floor" else box.max.y))
                for z in range(box.min.z, box.max.z + 1):
                    for x in range(box.min.x, box.max.x + 1):
                        block_updates[IntVector3(x, y, z)] = state
            else:
                # Gable roof along the selected axis.
                axis = str(operation.get("axis", "x"))
                if axis == "x":
                    half = max(1, math.ceil(box.dimensions.z / 2))
                    for z in range(box.min.z, box.max.z + 1):
                        rise = min(z - box.min.z, box.max.z - z)
                        y = min(box.max.y, box.min.y + min(rise, half))
                        # A one-block diagonal shell is disconnected under face
                        # adjacency. Include the immediately lower course so
                        # each stepped row is structurally contiguous.
                        courses = range(max(box.min.y, y - 1), y + 1)
                        for course_y in courses:
                            for x in range(box.min.x, box.max.x + 1):
                                block_updates[IntVector3(x, course_y, z)] = state
                else:
                    half = max(1, math.ceil(box.dimensions.x / 2))
                    for x in range(box.min.x, box.max.x + 1):
                        rise = min(x - box.min.x, box.max.x - x)
                        y = min(box.max.y, box.min.y + min(rise, half))
                        courses = range(max(box.min.y, y - 1), y + 1)
                        for course_y in courses:
                            for z in range(box.min.z, box.max.z + 1):
                                block_updates[IntVector3(x, course_y, z)] = state
        elif op in {"draw_circle", "draw_ellipse"}:
            center = _vec(operation.get("center"), "center")
            radius_a = int(operation.get("radius", operation.get("radiusA", 1)))
            radius_b = int(operation.get("radius", operation.get("radiusB", radius_a)))
            points = ellipse(center, radius_a, radius_b, plane=str(operation.get("plane", "xz")), filled=bool(operation.get("filled", False)))
            block_updates.update(self._points_with_state(points, _canonical_state(operation.get("state"))))
        elif op == "draw_cylinder":
            center = _vec(operation.get("center"), "center")
            points = cylinder(
                center,
                int(operation.get("radiusX", operation.get("radius", 1))),
                int(operation.get("radiusZ", operation.get("radius", 1))),
                int(operation.get("height", 1)),
                hollow=bool(operation.get("hollow", False)),
            )
            block_updates.update(self._points_with_state(points, _canonical_state(operation.get("state"))))
        elif op in {"draw_sphere", "draw_dome"}:
            points = sphere(
                _vec(operation.get("center"), "center"),
                int(operation.get("radius", 1)),
                hollow=bool(operation.get("hollow", False)),
                dome=op == "draw_dome",
            )
            block_updates.update(self._points_with_state(points, _canonical_state(operation.get("state"))))
        elif op == "draw_arch":
            points = arch(
                _vec(operation.get("start"), "start"),
                _vec(operation.get("end"), "end"),
                int(operation.get("height", 1)),
                thickness=int(operation.get("thickness", 1)),
            )
            block_updates.update(self._points_with_state(points, _canonical_state(operation.get("state"))))
        elif op == "draw_bezier":
            raw_points = operation.get("controlPoints", operation.get("points"))
            if not isinstance(raw_points, list):
                raise PatchError("PATCH_POINTS_INVALID", "draw_bezier requires controlPoints.")
            points = bezier([_vec(item, "controlPoints[]") for item in raw_points], samples=int(operation.get("samples", 0)) or None)
            block_updates.update(self._points_with_state(points, _canonical_state(operation.get("state"))))
        elif op == "extrude_profile":
            raw_profile = operation.get("profile")
            if not isinstance(raw_profile, list):
                raise PatchError("PATCH_PROFILE_INVALID", "extrude_profile requires a profile list.")
            points = extrude_profile(
                [_vec(item, "profile[]") for item in raw_profile],
                _vec(operation.get("offset"), "offset"),
                steps=int(operation.get("steps", 1)),
            )
            block_updates.update(self._points_with_state(points, _canonical_state(operation.get("state"))))
        elif op == "loft_profiles":
            raw_profiles = operation.get("profiles")
            if not isinstance(raw_profiles, list) or not all(isinstance(item, list) for item in raw_profiles):
                raise PatchError("PATCH_PROFILES_INVALID", "loft_profiles requires a list of profiles.")
            profiles = [[_vec(point, "profiles[][]") for point in profile] for profile in raw_profiles]
            points = loft_profiles(profiles, steps_per_pair=int(operation.get("stepsPerPair", 8)))
            block_updates.update(self._points_with_state(points, _canonical_state(operation.get("state"))))
        elif op in {"copy_region", "move_region", "rotate_region", "mirror_region", "scale_pattern_integer"}:
            source_min = operation.get("sourceMin", operation.get("min"))
            source_max = operation.get("sourceMax", operation.get("max"))
            source_box = normalize_box(_vec(source_min, "sourceMin"), _vec(source_max, "sourceMax"))
            source_values = {point: state for point, state in states.items() if source_box.contains(point)}
            if op in {"copy_region", "move_region"}:
                offset = _vec(operation.get("offset"), "offset")
                for point, state in source_values.items():
                    block_updates[point + offset] = state
                if op == "move_region":
                    for point in source_values:
                        block_updates[point] = None
            elif op == "rotate_region":
                origin = _vec(operation.get("origin", source_box.min.as_tuple()), "origin")
                turns = int(operation.get("quarterTurns", 1))
                for point, state in source_values.items():
                    block_updates[rotate_y(point, origin, turns)] = _state_transform(state, quarter_turns=turns)
                if bool(operation.get("clearSource", False)):
                    for point in source_values:
                        block_updates[point] = None
            elif op == "mirror_region":
                origin = _vec(operation.get("origin", source_box.min.as_tuple()), "origin")
                axis = str(operation.get("axis", "x"))
                for point, state in source_values.items():
                    block_updates[mirror(point, origin, axis)] = _state_transform(state, mirror_axis=axis)
                if bool(operation.get("clearSource", False)):
                    for point in source_values:
                        block_updates[point] = None
            else:
                origin = _vec(operation.get("origin", source_box.min.as_tuple()), "origin")
                factor = _vec(operation.get("factor", [1, 1, 1]), "factor")
                if min(factor.as_tuple()) < 1:
                    raise PatchError("PATCH_SCALE_FACTOR", "Integer scale factors must be positive.")
                for point, state in source_values.items():
                    for target in integer_scale(point, origin, factor):
                        block_updates[target] = state
        elif op == "apply_noise_mask":
            box = _bounds(operation)
            probability = float(operation.get("probability", 0.5))
            state = _canonical_state(operation.get("state"))
            candidates = list(box.iter_points())
            from_states = {_canonical_state(item) for item in operation.get("from", [])}  # type: ignore[arg-type]
            if from_states:
                candidates = [point for point in candidates if states.get(point, "minecraft:air") in from_states]
            for point in deterministic_mask(candidates, seed=int(operation.get("seed", 0)), probability=probability):
                block_updates[point] = state
        elif op == "apply_gradient_palette":
            box = _bounds(operation)
            raw_palette = operation.get("palette")
            if not isinstance(raw_palette, list) or not raw_palette:
                raise PatchError("PATCH_GRADIENT_PALETTE", "Gradient palette must be a non-empty list.")
            gradient = [_canonical_state(item) for item in raw_palette]
            axis = str(operation.get("axis", "y"))
            minimum = getattr(box.min, axis)
            maximum = getattr(box.max, axis)
            span = max(1, maximum - minimum)
            for point in box.iter_points():
                index = min(len(gradient) - 1, round((getattr(point, axis) - minimum) / span * (len(gradient) - 1)))
                block_updates[point] = gradient[index]
        elif op == "set_block_entity":
            position = _vec(operation.get("position"), "position")
            data = operation.get("data")
            if not isinstance(data, dict):
                raise PatchError("PATCH_BLOCK_ENTITY_DATA", "Block entity data must be an object.")
            namespaced_id = operation.get("id")
            entity_updates[position] = CanonicalBlockEntity(position, str(namespaced_id) if namespaced_id else None, copy.deepcopy(data), operation.get("region") if isinstance(operation.get("region"), str) else None)
        elif op == "remove_block_entity":
            entity_updates[_vec(operation.get("position"), "position")] = None
        else:
            raise PatchError("PATCH_UNKNOWN_OPERATION", "Patch contains an unsupported operation.", {"type": op})
        return block_updates, entity_updates

    def validate(self, patch: Patch) -> Patch:
        if patch.parent_version_id != self.active_version_id:
            raise PatchError("PATCH_STALE_PARENT", "Patch parent is not the active build version.")
        document = self.active.document
        if not document.bounds.contains(patch.intended_bounds.min) or not document.bounds.contains(patch.intended_bounds.max):
            raise PatchError("PATCH_OUT_OF_BOUNDS", "Patch intended bounds exceed the build bounds.")
        states = self._state_map(document)
        original_states = dict(states)
        entities = self._entity_map(document)
        original_entities = dict(entities)
        self._check_preconditions(patch, states)

        for operation in patch.operations:
            updates, entity_updates = self._operation_changes(operation, states, entities)
            for position, state in updates.items():
                if not patch.intended_bounds.contains(position):
                    raise PatchError(
                        "PATCH_OPERATION_OUTSIDE_INTENDED_BOUNDS",
                        "Patch operation exceeds intended bounds.",
                        {"position": position.as_tuple(), "operation": operation.get("type")},
                    )
                if not document.bounds.contains(position):
                    raise PatchError("PATCH_OPERATION_OUTSIDE_BUILD", "Patch operation exceeds build bounds.", {"position": position.as_tuple()})
                old_state = states.get(position, "minecraft:air")
                for lock in self.locks.values():
                    if lock.bounds.contains(position) and lock.owner != patch.author:
                        if not lock.protected_states or old_state in lock.protected_states:
                            raise PatchError(
                                "PATCH_REGION_LOCKED",
                                "Patch intersects a locked region.",
                                {"lockId": lock.lock_id, "owner": lock.owner, "position": position.as_tuple()},
                            )
                self._write(states, position, state)
            for position, entity in entity_updates.items():
                if not patch.intended_bounds.contains(position):
                    raise PatchError("PATCH_OPERATION_OUTSIDE_INTENDED_BOUNDS", "Block-entity edit exceeds intended bounds.")
                if entity is None:
                    entities.pop(position, None)
                else:
                    entities[position] = entity
            changed_positions = {
                point for point in set(original_states) | set(states)
                if original_states.get(point, "minecraft:air") != states.get(point, "minecraft:air")
            }
            if len(changed_positions) > patch.max_affected_blocks:
                raise PatchError(
                    "PATCH_AFFECTED_BLOCK_LIMIT",
                    "Patch exceeds maxAffectedBlocks.",
                    {"limit": patch.max_affected_blocks, "actual": len(changed_positions)},
                )

        state_to_id = {entry.canonical_state: entry.palette_id for entry in document.palette}
        changes = []
        for position in sorted(set(original_states) | set(states)):
            old_state = original_states.get(position, "minecraft:air")
            new_state = states.get(position, "minecraft:air")
            if old_state == new_state:
                continue
            changes.append(
                BlockChange(
                    position,
                    state_to_id.get(old_state),
                    state_to_id.get(new_state),
                    old_state,
                    new_state,
                )
            )
        entity_changes = []
        for position in sorted(set(original_entities) | set(entities)):
            old_value = original_entities.get(position)
            new_value = entities.get(position)
            if old_value != new_value:
                entity_changes.append(BlockEntityChange(position, old_value, new_value))
        patch.changes = changes
        patch.block_entity_changes = entity_changes
        patch.status = PatchStatus.VALIDATED
        patch.validation_messages.append(f"Validated {len(changes)} unique block changes and {len(entity_changes)} block-entity changes.")
        patch.validation_report = {
            "changeCount": len(changes),
            "blockEntityChangeCount": len(entity_changes),
            "affectedBounds": asdict(
                IntBoundingBox(
                    IntVector3(min(change.position.x for change in changes), min(change.position.y for change in changes), min(change.position.z for change in changes)),
                    IntVector3(max(change.position.x for change in changes), max(change.position.y for change in changes), max(change.position.z for change in changes)),
                )
            ) if changes else None,
            "parentHash": document.content_hash,
            "locksChecked": len(self.locks),
        }
        return patch

    def _apply(self, parent: BuildDocument, patch: Patch) -> BuildDocument:
        document = copy.deepcopy(parent)
        for change in patch.changes:
            new_state = change.new_state or "minecraft:air"
            if new_state in _AIR_STATES:
                document.blocks.pop(change.position, None)
            else:
                palette_id = document.ensure_palette_state(new_state)
                document.blocks[change.position] = palette_id

            target_names: list[str] = []
            if patch.target_region:
                target_names = [patch.target_region]
            else:
                target_names = [region.name for region in document.regions if region.bounds.contains(change.position)]
            if not target_names:
                edits_name = "Edits"
                if not any(region.name == edits_name for region in document.regions):
                    document.regions.append(
                        BuildRegion(
                            edits_name,
                            patch.intended_bounds.min,
                            patch.intended_bounds.dimensions,
                            patch.intended_bounds,
                            tuple(entry.canonical_state for entry in document.palette),
                        )
                    )
                target_names = [edits_name]
            for name in target_names:
                values = document.region_blocks.setdefault(name, {})
                if new_state in _AIR_STATES:
                    values.pop(change.position, None)
                else:
                    values[change.position] = document.palette_id_for_state(new_state)  # type: ignore[assignment]

        entity_map = self._entity_map(document)
        for change in patch.block_entity_changes:
            if change.new_value is None:
                entity_map.pop(change.position, None)
            else:
                entity_map[change.position] = change.new_value
        document.block_entities = [entity_map[position] for position in sorted(entity_map)]
        if patch.target_region:
            document.rebuild_flattened_from_regions()
        document.content_hash = document.compute_content_hash()
        return document

    def reject(self, patch: Patch, *, reason: str = "Rejected by operator") -> Patch:
        if patch.status in {PatchStatus.COMMITTED, PatchStatus.ROLLED_BACK, PatchStatus.SUPERSEDED}:
            raise PatchError("PATCH_REJECT_STATE", "Committed, rolled-back, or superseded patches cannot be rejected.")
        patch.status = PatchStatus.REJECTED
        patch.validation_messages.append(reason)
        patch.validation_report = {**patch.validation_report, "rejectionReason": reason}
        return patch

    def preview(self, patch: Patch) -> BuildDocument:
        if patch.status is PatchStatus.DRAFT:
            self.validate(patch)
        if patch.status not in {PatchStatus.VALIDATED, PatchStatus.PREVIEWED}:
            raise PatchError("PATCH_NOT_VALIDATED", "Patch must be validated before preview.")
        document = self._apply(self.active.document, patch)
        patch.status = PatchStatus.PREVIEWED
        patch.preview_report = {
            "parentHash": self.active.document.content_hash,
            "previewHash": document.content_hash,
            "changedBlocks": len(patch.changes),
            "paletteSizeBefore": len(self.active.document.palette),
            "paletteSizeAfter": len(document.palette),
        }
        return document

    def commit(self, patch: Patch) -> BuildVersion:
        if patch.status is PatchStatus.DRAFT:
            self.validate(patch)
        if patch.status not in {PatchStatus.VALIDATED, PatchStatus.PREVIEWED}:
            raise PatchError("PATCH_NOT_VALIDATED", "Patch must be validated before commit.")
        if patch.parent_version_id != self.active_version_id:
            raise PatchError("PATCH_STALE_PARENT", "Patch parent is no longer active.")
        document = self._apply(self.active.document, patch)
        version_id = "ver_" + document.content_hash[:20]
        if version_id in self.versions and self.versions[version_id].document.content_hash == document.content_hash:
            version_id = "ver_" + document.content_hash[:16] + uuid.uuid4().hex[:4]
        version = BuildVersion(
            version_id,
            self.active_version_id,
            document,
            patch.patch_id,
            self.current_branch,
            {"reason": patch.reason, "author": patch.author},
        )
        self.versions[version_id] = version
        self.active_version_id = version_id
        self.branch_heads[self.current_branch] = version_id
        patch.status = PatchStatus.COMMITTED
        return version

    def rollback_patch(self, patch_id: str) -> BuildVersion:
        patch = self.patches.get(patch_id)
        if patch is None:
            raise PatchError("PATCH_NOT_FOUND", "Patch does not exist.")
        version = next((item for item in self.versions.values() if item.patch_id == patch_id), None)
        if version is None:
            raise PatchError("PATCH_NOT_COMMITTED", "Patch has no committed version.")
        if self.active_version_id != version.version_id:
            raise PatchError("PATCH_NOT_ACTIVE", "Only the active committed patch can be rolled back directly.")
        patch.status = PatchStatus.ROLLED_BACK
        return self.undo()

    def undo(self) -> BuildVersion:
        active = self.active
        if active.parent_version_id is None:
            raise PatchError("VERSION_HAS_NO_PARENT", "The root version cannot be undone.")
        self.active_version_id = active.parent_version_id
        self.branch_heads[self.current_branch] = self.active_version_id
        return self.active

    def checkout(self, version_id: str, *, branch_name: str | None = None) -> BuildVersion:
        if version_id not in self.versions:
            raise PatchError("VERSION_NOT_FOUND", "Build version does not exist.")
        self.active_version_id = version_id
        if branch_name:
            self.current_branch = branch_name
            self.branch_heads[branch_name] = version_id
        return self.active

    def branch_version(self, name: str, version_id: str | None = None) -> BuildVersion:
        if not name or name in self.branch_heads:
            raise PatchError("BRANCH_NAME", "Branch name is empty or already exists.")
        target = version_id or self.active_version_id
        if target not in self.versions:
            raise PatchError("VERSION_NOT_FOUND", "Build version does not exist.")
        self.branch_heads[name] = target
        self.current_branch = name
        self.active_version_id = target
        return self.active

    def create_checkpoint(self, name: str) -> str:
        if not name:
            raise PatchError("CHECKPOINT_NAME", "Checkpoint name cannot be empty.")
        self.checkpoints[name] = self.active_version_id
        return self.active_version_id

    def restore_checkpoint(self, name: str) -> BuildVersion:
        version_id = self.checkpoints.get(name)
        if version_id is None:
            raise PatchError("CHECKPOINT_NOT_FOUND", "Checkpoint does not exist.")
        return self.checkout(version_id)

    def _ancestor_chain(self, version_id: str) -> list[str]:
        result = []
        current: str | None = version_id
        while current is not None:
            result.append(current)
            current = self.versions[current].parent_version_id
        return result

    def merge_versions(self, source_version_id: str, *, author: str, reason: str) -> BuildVersion:
        if source_version_id not in self.versions:
            raise PatchError("VERSION_NOT_FOUND", "Source version does not exist.")
        target_version_id = self.active_version_id
        target_chain = self._ancestor_chain(target_version_id)
        source_chain = self._ancestor_chain(source_version_id)
        common = next((version_id for version_id in target_chain if version_id in set(source_chain)), None)
        if common is None:
            raise PatchError("MERGE_NO_COMMON_ANCESTOR", "Versions do not share an ancestor.")
        base = self._state_map(self.versions[common].document)
        target = self._state_map(self.versions[target_version_id].document)
        source = self._state_map(self.versions[source_version_id].document)
        conflicts = []
        merged = dict(target)
        for point in set(base) | set(target) | set(source):
            base_state = base.get(point, "minecraft:air")
            target_state = target.get(point, "minecraft:air")
            source_state = source.get(point, "minecraft:air")
            target_changed = target_state != base_state
            source_changed = source_state != base_state
            if target_changed and source_changed and target_state != source_state:
                conflicts.append({"position": point.as_tuple(), "base": base_state, "target": target_state, "source": source_state})
            elif source_changed:
                self._write(merged, point, source_state)
        if conflicts:
            raise PatchError("MERGE_CONFLICT", "Version merge contains conflicting block edits.", {"conflicts": conflicts[:500], "count": len(conflicts)})
        document = copy.deepcopy(self.active.document)
        document.blocks.clear()
        for point, state in merged.items():
            if state not in _AIR_STATES:
                document.blocks[point] = document.ensure_palette_state(state)
        document.content_hash = document.compute_content_hash()
        version_id = "ver_" + document.content_hash[:16] + uuid.uuid4().hex[:4]
        version = BuildVersion(version_id, target_version_id, document, None, self.current_branch, {"mergeSource": source_version_id, "author": author, "reason": reason})
        self.versions[version_id] = version
        self.active_version_id = version_id
        self.branch_heads[self.current_branch] = version_id
        return version
