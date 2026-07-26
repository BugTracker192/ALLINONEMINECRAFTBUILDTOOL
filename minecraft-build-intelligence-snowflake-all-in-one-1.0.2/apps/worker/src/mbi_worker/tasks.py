from __future__ import annotations

import json
import os
from dataclasses import asdict
from pathlib import Path

from mbi.analysis import analyze_document
from mbi.chunking import build_chunks
from mbi.export import export_litematic, export_sponge_v3, verify_round_trip
from mbi.importer import import_build
from mbi.patch import PatchEngine
from mbi.snapshot import render_palette_layer
from mbi.serialization import read_document, write_document

from .app import celery_app

ROOT = Path(os.getenv("MBI_OBJECT_STORE_ROOT", "var"))


def _atomic_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".writing")
    temporary.write_text(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str), "utf-8")
    temporary.replace(path)


def _persist_root_document(document) -> tuple[Path, str]:
    """Write the same immutable graph layout consumed by the API."""
    engine = PatchEngine(document)
    version = engine.active
    build_dir = ROOT / "builds" / document.build_id
    version_dir = build_dir / "versions"
    version_dir.mkdir(parents=True, exist_ok=True)
    write_document(version_dir / f"{version.version_id}.json.gz", document)
    _atomic_json(
        build_dir / "graph.json",
        {
            "schemaVersion": 3,
            "buildId": document.build_id,
            "activeVersionId": version.version_id,
            "currentBranch": "main",
            "branchHeads": {"main": version.version_id},
            "checkpoints": {},
            "versions": {
                version.version_id: {
                    "parentVersionId": None,
                    "patchId": None,
                    "branchName": "main",
                    "metadata": {"root": True},
                    "contentHash": document.content_hash,
                }
            },
            "patches": {},
            "locks": {},
        },
    )
    return build_dir, version.version_id


def _active_document(build_id: str):
    build_dir = ROOT / "builds" / build_id
    graph = json.loads((build_dir / "graph.json").read_text("utf-8"))
    version_id = str(graph["activeVersionId"])
    return read_document(build_dir / "versions" / f"{version_id}.json.gz")


@celery_app.task(bind=True, name="mbi.import_build")
def import_build_task(self, upload_key: str, filename: str) -> dict[str, object]:
    path = ROOT / upload_key
    self.update_state(state="PROGRESS", meta={"stage": "reading_upload", "progress": 0.05})
    data = path.read_bytes()
    self.update_state(state="PROGRESS", meta={"stage": "parsing_nbt", "progress": 0.20})
    document = import_build(data, filename)
    self.update_state(state="PROGRESS", meta={"stage": "chunking", "progress": 0.65})
    chunks = build_chunks(document)
    build_dir, version_id = _persist_root_document(document)
    chunk_dir = build_dir / "chunks"
    chunk_dir.mkdir(parents=True, exist_ok=True)
    manifest = []
    for chunk in chunks:
        target = chunk_dir / chunk.content_hash
        if not target.exists():
            target.write_bytes(chunk.data)
        payload = asdict(chunk)
        payload.pop("data")
        manifest.append(payload)
    _atomic_json(build_dir / "manifest.json", {"versionId": version_id, "chunks": manifest})
    self.update_state(state="PROGRESS", meta={"stage": "analysis", "progress": 0.85})
    analysis = analyze_document(document)
    _atomic_json(build_dir / "analysis.json", analysis)
    return {"buildId": document.build_id, "versionId": version_id, "summary": document.to_summary(), "chunkCount": len(chunks)}


@celery_app.task(bind=True, name="mbi.render_layer")
def render_layer_task(self, build_id: str, y: int, pixels_per_block: int = 4) -> dict[str, object]:
    document = _active_document(build_id)
    image, manifest = render_palette_layer(document, y, pixels_per_block=pixels_per_block)
    destination = ROOT / "snapshots" / manifest.snapshot_id
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "color.png").write_bytes(image)
    _atomic_json(destination / "manifest.json", asdict(manifest))
    return {"snapshotId": manifest.snapshot_id, "manifest": asdict(manifest)}


@celery_app.task(bind=True, name="mbi.export_build")
def export_build_task(self, build_id: str, format_name: str, preserve_regions: bool = True) -> dict[str, object]:
    document = _active_document(build_id)
    if format_name == "schem":
        data, filename = export_sponge_v3(document), f"{build_id}.schem"
    elif format_name == "litematic":
        data, filename = export_litematic(document, preserve_regions=preserve_regions), f"{build_id}.litematic"
    else:
        raise ValueError("unsupported export format")
    report = verify_round_trip(document, data, filename)
    if not report.valid:
        raise ValueError(f"round-trip verification failed: {report.messages[:5]}")
    destination = ROOT / "exports"
    destination.mkdir(parents=True, exist_ok=True)
    key = f"{build_id}-{format_name}-{document.content_hash[:12]}"
    (destination / key).write_bytes(data)
    return {"exportKey": key, "filename": filename, "sizeBytes": len(data), "roundTrip": asdict(report)}


@celery_app.task(bind=True, name="mbi.render_global_snapshot")
def render_global_snapshot_task(self, build_id: str, direction: str, pixels_per_block: int = 4) -> dict[str, object]:
    from mbi.snapshot import render_global_snapshot

    document = _active_document(build_id)
    self.update_state(state="PROGRESS", meta={"stage": "rendering", "progress": 0.25})
    bundle = render_global_snapshot(document, direction, pixels_per_block=pixels_per_block)
    destination = ROOT / "snapshots" / bundle.manifest.snapshot_id
    destination.mkdir(parents=True, exist_ok=True)
    (destination / "color.png").write_bytes(bundle.color_png)
    (destination / "palette.png").write_bytes(bundle.palette_png)
    (destination / "depth.png").write_bytes(bundle.depth_png)
    (destination / "normal.png").write_bytes(bundle.normal_png)
    (destination / "coordinates.bin.gz").write_bytes(bundle.coordinate_map_gzip)
    (destination / "manifest.json").write_bytes(bundle.manifest_json())
    return {"snapshotId": bundle.manifest.snapshot_id, "manifest": asdict(bundle.manifest)}


@celery_app.task(bind=True, name="mbi.autonomous_construct")
def autonomous_construct_task(self, brief_payload: dict[str, object], critique_iterations: int = 2) -> dict[str, object]:
    from mbi.ai import AutonomousConstructionExecutor, ConstructionBrief

    self.update_state(state="PROGRESS", meta={"stage": "requirements", "progress": 0.05})
    executor = AutonomousConstructionExecutor(ConstructionBrief(**brief_payload))
    run = executor.execute(critique_iterations=critique_iterations)
    build_dir, version_id = _persist_root_document(executor.document)
    _atomic_json(build_dir / "construction-run.json", asdict(run))
    return {"buildId": executor.document.build_id, "versionId": version_id, "summary": executor.document.to_summary(), "run": asdict(run)}
