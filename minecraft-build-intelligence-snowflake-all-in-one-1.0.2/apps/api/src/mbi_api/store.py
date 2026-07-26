from __future__ import annotations

import json
import threading
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mbi.canonical import BuildDocument, CanonicalBlockEntity, IntBoundingBox, IntVector3
from mbi.chunking import build_chunks
from mbi.patch import PatchEngine
from mbi.patch.engine import BuildVersion
from mbi.patch.model import BlockChange, BlockEntityChange, Patch, PatchStatus, RegionLock
from mbi.serialization import read_document, write_document


def _vec(raw: dict[str, Any] | list[int] | tuple[int, int, int]) -> IntVector3:
    if isinstance(raw, dict):
        return IntVector3(int(raw["x"]), int(raw["y"]), int(raw["z"]))
    return IntVector3(int(raw[0]), int(raw[1]), int(raw[2]))


def _bounds(raw: dict[str, Any]) -> IntBoundingBox:
    return IntBoundingBox(_vec(raw["min"]), _vec(raw["max"]))


def _block_entity(raw: dict[str, Any] | None) -> CanonicalBlockEntity | None:
    if raw is None:
        return None
    return CanonicalBlockEntity(
        position=_vec(raw["position"]),
        namespaced_id=raw.get("namespaced_id"),
        data=dict(raw.get("data", {})),
        region_name=raw.get("region_name"),
    )


def _serialize_patch(patch: Patch) -> dict[str, Any]:
    return {
        "patchId": patch.patch_id,
        "parentVersionId": patch.parent_version_id,
        "author": patch.author,
        "reason": patch.reason,
        "intendedBounds": asdict(patch.intended_bounds),
        "maxAffectedBlocks": patch.max_affected_blocks,
        "operations": patch.operations,
        "coordinateSpace": patch.coordinate_space,
        "preconditions": patch.preconditions,
        "expectedParentHash": patch.expected_parent_hash,
        "targetRegion": patch.target_region,
        "status": patch.status.value,
        "changes": [asdict(item) for item in patch.changes],
        "blockEntityChanges": [asdict(item) for item in patch.block_entity_changes],
        "validationMessages": patch.validation_messages,
        "validationReport": patch.validation_report,
        "previewReport": patch.preview_report,
        "createdAt": patch.created_at,
    }


def _deserialize_patch(patch_id: str, raw: dict[str, Any]) -> Patch:
    changes = [
        BlockChange(
            position=_vec(item["position"]),
            old_palette_id=item.get("old_palette_id"),
            new_palette_id=item.get("new_palette_id"),
            old_state=item.get("old_state"),
            new_state=item.get("new_state"),
        )
        for item in raw.get("changes", [])
    ]
    entity_changes = [
        BlockEntityChange(
            position=_vec(item["position"]),
            old_value=_block_entity(item.get("old_value")),
            new_value=_block_entity(item.get("new_value")),
        )
        for item in raw.get("blockEntityChanges", [])
    ]
    # Graph schema v2 contained only a subset. Defaults keep those graphs loadable.
    return Patch(
        patch_id=raw.get("patchId", patch_id),
        parent_version_id=str(raw["parentVersionId"]),
        author=str(raw.get("author", "unknown")),
        reason=str(raw.get("reason", "Restored patch")),
        intended_bounds=_bounds(raw.get("intendedBounds", {"min": {"x": 0, "y": 0, "z": 0}, "max": {"x": 0, "y": 0, "z": 0}})),
        max_affected_blocks=int(raw.get("maxAffectedBlocks", max(1, len(changes)))),
        operations=list(raw.get("operations", [])),
        coordinate_space=str(raw.get("coordinateSpace", "document")),
        preconditions=list(raw.get("preconditions", [])),
        expected_parent_hash=raw.get("expectedParentHash"),
        target_region=raw.get("targetRegion"),
        status=PatchStatus(str(raw.get("status", "draft"))),
        changes=changes,
        block_entity_changes=entity_changes,
        validation_messages=list(raw.get("validationMessages", [])),
        validation_report=dict(raw.get("validationReport", {})),
        preview_report=dict(raw.get("previewReport", {})),
        created_at=str(raw.get("createdAt", "")),
    )


class LocalBuildStore:
    """Persistent local implementation of the immutable version graph.

    Every canonical version document is immutable on disk. ``graph.json`` records
    branch heads, checkpoints, complete patch drafts/previews, locks, and lineage so
    API restarts do not lose uncommitted work or rollback metadata.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._engines: dict[str, PatchEngine] = {}

    def _build_root(self, build_id: str) -> Path:
        return self.root / build_id

    def _graph_path(self, build_id: str) -> Path:
        return self._build_root(build_id) / "graph.json"

    def _version_path(self, build_id: str, version_id: str) -> Path:
        return self._build_root(build_id) / "versions" / f"{version_id}.json.gz"

    @staticmethod
    def _atomic_json(path: Path, payload: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".writing")
        temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str), "utf-8")
        temporary.replace(path)

    def put(self, document: BuildDocument) -> PatchEngine:
        """Register a newly imported root document; never reset an existing graph."""
        with self._lock:
            if document.build_id in self._engines or self._graph_path(document.build_id).is_file():
                engine = self.engine(document.build_id)
                if engine.active.document.content_hash != document.content_hash:
                    raise ValueError("put() cannot replace an existing build graph; persist the active engine instead")
                return engine
            engine = PatchEngine(document)
            self._engines[document.build_id] = engine
            self.persist_engine(document.build_id)
            return engine

    def persist_engine(self, build_id: str) -> None:
        with self._lock:
            engine = self._engines[build_id]
            root = self._build_root(build_id)
            (root / "versions").mkdir(parents=True, exist_ok=True)
            version_rows: dict[str, dict[str, Any]] = {}
            for version_id, version in engine.versions.items():
                path = self._version_path(build_id, version_id)
                if not path.is_file():
                    write_document(path, version.document)
                version_rows[version_id] = {
                    "parentVersionId": version.parent_version_id,
                    "patchId": version.patch_id,
                    "branchName": version.branch_name,
                    "metadata": version.metadata,
                    "contentHash": version.document.content_hash,
                }
            lock_rows = {
                lock_id: {
                    "bounds": asdict(lock.bounds),
                    "owner": lock.owner,
                    "reason": lock.reason,
                    "protectedStates": list(lock.protected_states),
                }
                for lock_id, lock in engine.locks.items()
            }
            self._atomic_json(
                self._graph_path(build_id),
                {
                    "schemaVersion": 3,
                    "buildId": build_id,
                    "activeVersionId": engine.active_version_id,
                    "currentBranch": engine.current_branch,
                    "branchHeads": engine.branch_heads,
                    "checkpoints": engine.checkpoints,
                    "versions": version_rows,
                    "patches": {patch_id: _serialize_patch(patch) for patch_id, patch in engine.patches.items()},
                    "locks": lock_rows,
                },
            )

    def _load_engine(self, build_id: str) -> PatchEngine:
        graph_path = self._graph_path(build_id)
        legacy = self.root / f"{build_id}.json.gz"
        if not graph_path.is_file() and legacy.is_file():
            document = read_document(legacy)
            engine = PatchEngine(document)
            self._engines[build_id] = engine
            self.persist_engine(build_id)
            return engine
        if not graph_path.is_file():
            raise KeyError(build_id)
        graph = json.loads(graph_path.read_text("utf-8"))
        rows = graph.get("versions", {})
        if not rows:
            raise ValueError(f"build graph {build_id} has no versions")
        root_id = next((vid for vid, row in rows.items() if row.get("parentVersionId") is None), None)
        if root_id is None:
            raise ValueError(f"build graph {build_id} has no root version")
        root_document = read_document(self._version_path(build_id, root_id))
        engine = PatchEngine(root_document)
        engine.versions.clear()
        for version_id, row in rows.items():
            document = read_document(self._version_path(build_id, version_id))
            if document.content_hash != row.get("contentHash"):
                raise ValueError(f"version content hash mismatch: {version_id}")
            engine.versions[version_id] = BuildVersion(
                version_id,
                row.get("parentVersionId"),
                document,
                row.get("patchId"),
                row.get("branchName", "main"),
                row.get("metadata", {}),
            )
        active = graph.get("activeVersionId")
        if active not in engine.versions:
            raise ValueError(f"active version missing from graph: {active}")
        engine.active_version_id = active
        engine.current_branch = graph.get("currentBranch", "main")
        engine.branch_heads = {str(k): str(v) for k, v in graph.get("branchHeads", {"main": root_id}).items()}
        engine.checkpoints = {str(k): str(v) for k, v in graph.get("checkpoints", {}).items()}
        engine.patches = {
            str(patch_id): _deserialize_patch(str(patch_id), dict(row))
            for patch_id, row in graph.get("patches", {}).items()
        }
        engine.locks = {
            str(lock_id): RegionLock(
                lock_id=str(lock_id),
                bounds=_bounds(row["bounds"]),
                owner=str(row["owner"]),
                reason=str(row.get("reason", "")),
                protected_states=tuple(str(item) for item in row.get("protectedStates", [])),
            )
            for lock_id, row in graph.get("locks", {}).items()
        }
        self._engines[build_id] = engine
        return engine

    def engine(self, build_id: str) -> PatchEngine:
        with self._lock:
            return self._engines.get(build_id) or self._load_engine(build_id)

    def get(self, build_id: str, version_id: str | None = None) -> BuildDocument:
        engine = self.engine(build_id)
        if version_id is None:
            return engine.active.document
        try:
            return engine.versions[version_id].document
        except KeyError as exc:
            raise KeyError(version_id) from exc

    def find_patch(self, patch_id: str) -> tuple[str, Patch]:
        with self._lock:
            for build_id, engine in self._engines.items():
                if patch_id in engine.patches:
                    return build_id, engine.patches[patch_id]
            for graph_path in self.root.glob("*/graph.json"):
                try:
                    graph = json.loads(graph_path.read_text("utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                if patch_id in graph.get("patches", {}):
                    build_id = graph_path.parent.name
                    engine = self.engine(build_id)
                    return build_id, engine.patches[patch_id]
        raise KeyError(patch_id)

    def list_versions(self, build_id: str) -> list[dict[str, Any]]:
        engine = self.engine(build_id)
        return [
            {
                "versionId": version.version_id,
                "parentVersionId": version.parent_version_id,
                "patchId": version.patch_id,
                "branchName": version.branch_name,
                "contentHash": version.document.content_hash,
                "active": version.version_id == engine.active_version_id,
                "metadata": version.metadata,
            }
            for version in engine.versions.values()
        ]

    def chunks(self, build_id: str, version_id: str | None = None) -> list[dict[str, Any]]:
        result = []
        for chunk in build_chunks(self.get(build_id, version_id)):
            payload = asdict(chunk)
            payload["data"] = chunk.data.hex()
            result.append(payload)
        return result
