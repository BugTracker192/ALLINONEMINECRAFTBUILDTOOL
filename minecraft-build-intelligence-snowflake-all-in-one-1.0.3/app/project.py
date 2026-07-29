from __future__ import annotations

import hashlib
import json
import shutil
import struct
from dataclasses import asdict
from pathlib import Path
from typing import Any

from mbi.canonical import BuildDocument, IntBoundingBox, IntVector3
from mbi.chunking import build_chunks
from mbi.serialization import document_from_payload, document_to_payload
from mbi.patch import BuildVersion, PatchEngine
from mbi.patch.model import RegionLock

from .errors import AppError
from .storage import atomic_write_bytes, atomic_write_json


_CANONICAL_SCHEMA = "mbi.offline-run.v1"


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def initialize_layout(root: Path) -> None:
    for relative in (
        "chunks", "raw_preserved/extensions", "versions", "patches/previews", "snapshots",
        "semantic_maps", "analysis_artifacts", "ai/context_manifests", "ai/evidence",
        "ai/runs", "ai/tool_results", "export",
    ):
        (root / relative).mkdir(parents=True, exist_ok=True)


def save_document(
    root: Path,
    document: BuildDocument,
    *,
    active_version_id: str | None = None,
    parent_version_id: str | None = None,
    patch_id: str | None = None,
    branch_name: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> str:
    initialize_layout(root)
    chunks = build_chunks(document)
    chunk_rows = []
    for chunk in chunks:
        header = {
            "coordinate": chunk.coordinate.as_tuple(),
            "global_min": chunk.global_min.as_tuple(),
            "dimensions": chunk.dimensions.as_tuple(),
            "encoding": chunk.encoding.value,
            "palette_ids": chunk.palette_ids,
            "non_air_count": chunk.non_air_count,
            "material_histogram": chunk.material_histogram,
            "content_hash": chunk.content_hash,
            "byte_length": len(chunk.data),
        }
        header_bytes = json.dumps(header, sort_keys=True, separators=(",", ":")).encode("utf-8")
        blob = b"MBICHUNK1" + struct.pack("<I", len(header_bytes)) + header_bytes + chunk.data
        atomic_write_bytes(root / "chunks" / f"{chunk.content_hash}.chunk", blob)
        chunk_rows.append(header)
    atomic_write_json(root / "chunks" / "manifest.json", {"schema": "mbi.chunk-manifest.v1", "chunks": chunk_rows})

    payload = document_to_payload(document)
    payload["offlineRunSchema"] = _CANONICAL_SCHEMA
    payload["chunkManifest"] = "chunks/manifest.json"
    atomic_write_json(root / "canonical.json", payload)
    version_id = active_version_id or "ver_" + document.content_hash[:20]
    atomic_write_json(root / "versions" / f"{version_id}.json", payload)
    manifest_path = root / "versions" / "manifest.json"
    manifest = {"schema": "mbi.version-manifest.v2", "active_version_id": version_id, "versions": []}
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text("utf-8"))
    old = next((item for item in manifest.get("versions", []) if item.get("version_id") == version_id), {})
    row = {
        "version_id": version_id,
        "content_hash": document.content_hash,
        "path": f"versions/{version_id}.json",
        "parent_version_id": parent_version_id if parent_version_id is not None else old.get("parent_version_id"),
        "patch_id": patch_id if patch_id is not None else old.get("patch_id"),
        "branch_name": branch_name if branch_name is not None else old.get("branch_name", "main"),
        "metadata": metadata if metadata is not None else old.get("metadata", {}),
    }
    versions = [item for item in manifest.get("versions", []) if item.get("version_id") != version_id]
    versions.append(row)
    manifest.update({
        "schema": "mbi.version-manifest.v2",
        "active_version_id": version_id,
        "versions": sorted(versions, key=lambda item: item["version_id"]),
    })
    atomic_write_json(manifest_path, manifest)
    return version_id


def load_document(root: str | Path, *, version_id: str | None = None) -> BuildDocument:
    root = Path(root)
    if version_id:
        path = root / "versions" / f"{version_id}.json"
    else:
        path = root / "canonical.json"
    payload = json.loads(path.read_text("utf-8"))
    return document_from_payload(payload)



def clone_run_base(source: str | Path, destination: str | Path) -> Path:
    source_root = Path(source).resolve()
    destination_root = Path(destination).resolve()
    if source_root == destination_root:
        return destination_root
    if source_root in destination_root.parents:
        suggestion = source_root.parent / f"{source_root.name}-output"
        raise AppError(
            "OUTPUT_NESTED_IN_SOURCE",
            "The output run cannot be nested inside the source run.",
            {
                "source": str(source_root),
                "output": str(destination_root),
                "suggested_output": str(suggestion),
            },
            2,
        )
    if not (source_root / "canonical.json").is_file():
        raise FileNotFoundError(f"source run is missing canonical.json: {source_root}")
    initialize_layout(destination_root)
    for filename in ("canonical.json", "diagnostics.json", "analysis.json", "jobs.json", "quality_gates.json"):
        source_file = source_root / filename
        if source_file.is_file():
            shutil.copy2(source_file, destination_root / filename)
    for dirname in ("chunks", "raw_preserved", "versions"):
        source_dir = source_root / dirname
        if source_dir.is_dir():
            shutil.copytree(source_dir, destination_root / dirname, dirs_exist_ok=True, symlinks=False)
    return destination_root

def preserve_source(root: Path, source: Path, data: bytes) -> None:
    initialize_layout(root)
    atomic_write_bytes(root / "raw_preserved" / "source.original", data)
    atomic_write_json(
        root / "raw_preserved" / "source.json",
        {"filename": source.name, "sha256": _sha256(data), "size_bytes": len(data)},
    )


def write_diagnostics(root: Path, document: BuildDocument, *, render: dict[str, Any] | None = None) -> None:
    render = render or {"render_mode": "software-flat", "render_tier": 0, "resource_pack": {"provided": False}}
    payload = {
        **render,
        "fallbacks": render.get("fallbacks", []),
        "unsupported_models": render.get("unsupported_models", []),
        "asset_diagnostics": render.get("asset_diagnostics", []),
        "unknown_blocks": [asdict(item) for item in document.diagnostics if "UNKNOWN" in item.code],
        "import_diagnostics": [asdict(item) for item in document.diagnostics],
        "degraded_features": ["no-live-browser-viewport", "no-real-time-orbit-controls"],
    }
    atomic_write_json(root / "diagnostics.json", payload)



def persist_patch_engine(root: str | Path, engine: PatchEngine) -> None:
    root = Path(root)
    initialize_layout(root)
    for version in engine.versions.values():
        save_document(
            root,
            version.document,
            active_version_id=version.version_id,
            parent_version_id=version.parent_version_id,
            patch_id=version.patch_id,
            branch_name=version.branch_name,
            metadata=version.metadata,
        )
    active = engine.active
    save_document(
        root,
        active.document,
        active_version_id=active.version_id,
        parent_version_id=active.parent_version_id,
        patch_id=active.patch_id,
        branch_name=active.branch_name,
        metadata=active.metadata,
    )
    graph = {
        "schema": "mbi.version-graph.v1",
        "active_version_id": engine.active_version_id,
        "current_branch": engine.current_branch,
        "branch_heads": dict(sorted(engine.branch_heads.items())),
        "checkpoints": dict(sorted(engine.checkpoints.items())),
        "locks": [
            {
                "lock_id": lock.lock_id,
                "bounds": asdict(lock.bounds),
                "owner": lock.owner,
                "reason": lock.reason,
                "protected_states": list(lock.protected_states),
            }
            for lock in sorted(engine.locks.values(), key=lambda item: item.lock_id)
        ],
    }
    atomic_write_json(root / "versions" / "graph.json", graph)


def load_patch_engine(root: str | Path) -> PatchEngine:
    root = Path(root)
    manifest_path = root / "versions" / "manifest.json"
    document = load_document(root)
    engine = PatchEngine(document)
    if not manifest_path.exists():
        return engine
    manifest = json.loads(manifest_path.read_text("utf-8"))
    versions: dict[str, BuildVersion] = {}
    for row in manifest.get("versions", []):
        version_id = str(row["version_id"])
        versions[version_id] = BuildVersion(
            version_id=version_id,
            parent_version_id=row.get("parent_version_id"),
            document=load_document(root, version_id=version_id),
            patch_id=row.get("patch_id"),
            branch_name=str(row.get("branch_name", "main")),
            metadata=dict(row.get("metadata", {})),
        )
    if versions:
        engine.versions = versions
        engine.active_version_id = str(manifest.get("active_version_id") or next(iter(versions)))
    graph_path = root / "versions" / "graph.json"
    if graph_path.exists():
        graph = json.loads(graph_path.read_text("utf-8"))
        active = str(graph.get("active_version_id", engine.active_version_id))
        if active in engine.versions:
            engine.active_version_id = active
        engine.current_branch = str(graph.get("current_branch", "main"))
        engine.branch_heads = {str(k): str(v) for k, v in graph.get("branch_heads", {}).items() if str(v) in engine.versions}
        engine.checkpoints = {str(k): str(v) for k, v in graph.get("checkpoints", {}).items() if str(v) in engine.versions}
        locks: dict[str, RegionLock] = {}
        for row in graph.get("locks", []):
            minimum = row["bounds"]["min"]
            maximum = row["bounds"]["max"]
            lock = RegionLock(
                str(row["lock_id"]),
                IntBoundingBox(IntVector3(**minimum), IntVector3(**maximum)),
                str(row["owner"]),
                str(row["reason"]),
                tuple(str(item) for item in row.get("protected_states", [])),
            )
            locks[lock.lock_id] = lock
        engine.locks = locks
    if not engine.branch_heads:
        engine.branch_heads = {engine.current_branch: engine.active_version_id}
    return engine

def parse_vec(text: str) -> IntVector3:
    values = [int(part.strip()) for part in text.split(",")]
    if len(values) != 3:
        raise ValueError("expected x,y,z")
    return IntVector3(*values)


def parse_box(minimum: str, maximum: str) -> IntBoundingBox:
    return IntBoundingBox(parse_vec(minimum), parse_vec(maximum))
