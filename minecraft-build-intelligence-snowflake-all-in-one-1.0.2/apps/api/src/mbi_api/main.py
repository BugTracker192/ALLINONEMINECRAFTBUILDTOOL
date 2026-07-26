from __future__ import annotations

import asyncio
import hashlib
import json
import queue
import uuid
from dataclasses import asdict
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, Response, StreamingResponse

from mbi.ai import AutonomousConstructionExecutor, ConstructionBrief, ContextBudget
from mbi.analysis import analyze_document
from mbi.assets import ResourcePack
from mbi.canonical import IntBoundingBox, IntVector3
from mbi.errors import MBIError
from mbi.export import export_litematic, export_sponge_v3, verify_round_trip
from mbi.snapshot import render_global_snapshot, render_palette_layer

from .ai_manager import AIExecutionManager
from .artifacts import ArtifactSigner
from .config import get_settings
from .idempotency import IdempotencyStore
from .jobs import CeleryJobManager, LocalJobManager
from .middleware import install_security_middleware
from .observability import BUILD_OPERATIONS, configure_logging, configure_opentelemetry, install_observability_middleware, metrics_response
from .retention import RetentionManager
from .renderer_client import RendererServiceClient, RendererServiceError
from .schemas import AIRunCreate, BlockQuery, ConstructionCreate, PatchCreate, PresentationSnapshotCreate, SnapshotCreate
from .store import LocalBuildStore

configure_logging()
settings = get_settings()
store = LocalBuildStore(settings.object_store_root / "builds")
jobs = LocalJobManager(store) if settings.demo_inline_jobs else CeleryJobManager(store, settings.redis_url)
idempotency = IdempotencyStore(settings.object_store_root / "idempotency")
ai_manager = AIExecutionManager(store, settings)
artifact_signer = ArtifactSigner(settings.artifact_signing_secret, settings.artifact_url_ttl_seconds)
renderer_client = RendererServiceClient(settings.renderer_service_url, settings.renderer_timeout_seconds)
retention = RetentionManager(
    settings.object_store_root,
    {
        "uploads": settings.upload_retention_days,
        "snapshots": settings.snapshot_retention_days,
        "exports": settings.export_retention_days,
        "jobs": settings.job_retention_days,
        "ai-runs": settings.ai_run_retention_days,
        "idempotency": settings.idempotency_retention_days,
    },
)
patch_registry: dict[str, tuple[str, object]] = {}
app = FastAPI(title="Minecraft Build Intelligence API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[item.strip() for item in settings.cors_origins.split(",") if item.strip()],
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["content-type", "authorization", "x-api-key", "x-request-id", "idempotency-key", "x-provider-api-key"],
)
install_observability_middleware(app)
def _valid_signed_request(request: Request) -> bool:
    if request.method != "GET" or not request.url.path.startswith("/api/v1/exports/"):
        return False
    filename = Path(request.query_params.get("filename", "build.schem")).name
    try:
        expires = int(request.query_params.get("expires", ""))
    except ValueError:
        return False
    return artifact_signer.verify(
        request.url.path, filename, expires, request.query_params.get("signature")
    )


install_security_middleware(
    app,
    api_key_hashes=settings.api_key_hashes,
    rate_limit_requests=settings.rate_limit_requests,
    rate_limit_window_seconds=settings.rate_limit_window_seconds,
    signed_request_validator=_valid_signed_request,
)
configure_opentelemetry(app)


def _idempotent(request: Request, response: Response, *, scope: str, payload: object, producer):
    result, replayed = idempotency.execute(
        scope=scope,
        key=request.headers.get("idempotency-key"),
        payload=payload,
        producer=producer,
    )
    response.headers["Idempotency-Replayed"] = "true" if replayed else "false"
    return result


@app.exception_handler(MBIError)
async def mbi_error_handler(_: Request, exc: MBIError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": {"code": exc.code, "message": exc.message, "details": exc.details, "recoverable": exc.recoverable}},
    )


@app.exception_handler(KeyError)
async def key_error_handler(_: Request, exc: KeyError) -> JSONResponse:
    return JSONResponse(status_code=404, content={"error": {"code": "NOT_FOUND", "message": str(exc), "recoverable": False}})


@app.get("/healthz")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/metrics", include_in_schema=False)
def metrics() -> Response:
    return metrics_response()


@app.get("/readyz")
def readiness() -> dict[str, object]:
    roots = [settings.object_store_root / name for name in ("uploads", "builds", "snapshots", "exports")]
    for root in roots:
        root.mkdir(parents=True, exist_ok=True)
    return {
        "status": "ready",
        "assetPackConfigured": bool(settings.asset_pack_path and settings.asset_pack_path.exists()),
        "storageWritable": all(root.is_dir() for root in roots),
        "artifactSigningConfigured": artifact_signer.enabled,
        "durableJobs": not settings.demo_inline_jobs,
    }


@app.post("/api/v1/uploads", status_code=202)
async def upload(file: UploadFile = File(...)) -> dict[str, object]:
    filename = Path(file.filename or "upload.nbt").name
    upload_id = "upload_" + uuid.uuid4().hex[:20]
    upload_dir = settings.object_store_root / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)
    target = upload_dir / upload_id
    hasher = hashlib.sha256()
    size = 0
    try:
        with target.open("xb") as output:
            while chunk := await file.read(1024 * 1024):
                size += len(chunk)
                if size > settings.max_upload_bytes:
                    raise HTTPException(413, detail={"code": "UPLOAD_SIZE_LIMIT", "limit": settings.max_upload_bytes})
                hasher.update(chunk)
                output.write(chunk)
    except Exception:
        target.unlink(missing_ok=True)
        raise
    return {"uploadId": upload_id, "filename": filename, "sizeBytes": size, "sha256": hasher.hexdigest()}


@app.post("/api/v1/builds/import", status_code=202)
def import_uploaded(payload: dict[str, str], request: Request, response: Response) -> dict[str, object]:
    upload_id = str(payload.get("uploadId", ""))
    filename = Path(payload.get("filename", "upload.nbt")).name
    if not upload_id.startswith("upload_"):
        raise HTTPException(422, detail={"code": "UPLOAD_ID_INVALID"})
    path = settings.object_store_root / "uploads" / upload_id
    if not path.is_file():
        raise HTTPException(404, detail={"code": "UPLOAD_NOT_FOUND"})
    return _idempotent(
        request, response, scope="build.import", payload={"uploadId": upload_id, "filename": filename},
        producer=lambda: asdict(jobs.create_import(path, filename)),
    )


@app.get("/api/v1/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, object]:
    try:
        return asdict(jobs.get(job_id))
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND"}) from exc


@app.post("/api/v1/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict[str, object]:
    try:
        return asdict(jobs.cancel(job_id))
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "JOB_NOT_FOUND"}) from exc


def _document(build_id: str, version_id: str | None = None):
    try:
        return store.get(build_id, version_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "BUILD_OR_VERSION_NOT_FOUND"}) from exc


@app.post("/api/v1/builds/generate", status_code=201)
def generate_build(payload: ConstructionCreate, request: Request, response: Response) -> dict[str, object]:
    raw_payload = payload.model_dump()

    def produce() -> dict[str, object]:
        values = dict(raw_payload)
        palette = values.pop("palette")
        critique = values.pop("critiqueIterations")
        mapping = {
            "buildType": "build_type", "primaryAxis": "primary_axis", "interiorRequired": "interior_required",
            "detailDensity": "detail_density", "exportFormat": "export_format",
        }
        brief_args = {mapping.get(key, key): value for key, value in values.items()}
        if palette:
            brief_args["palette"] = palette
        brief = ConstructionBrief(**brief_args)
        executor = AutonomousConstructionExecutor(brief)
        run = executor.execute(critique_iterations=critique)
        store.put(executor.document)
        BUILD_OPERATIONS.labels("autonomous_construction", "completed").inc()
        return {"buildId": executor.document.build_id, "summary": executor.document.to_summary(), "run": asdict(run)}

    return _idempotent(request, response, scope="build.generate", payload=raw_payload, producer=produce)


@app.get("/api/v1/builds/{build_id}")
def get_build(build_id: str) -> dict[str, object]:
    document = _document(build_id)
    engine = store.engine(build_id)
    return {**document.to_summary(), "activeVersionId": engine.active_version_id, "currentBranch": engine.current_branch}


@app.get("/api/v1/builds/{build_id}/versions")
def get_versions(build_id: str) -> list[dict[str, object]]:
    return store.list_versions(build_id)


@app.get("/api/v1/builds/{build_id}/versions/{version_id}")
def get_version(build_id: str, version_id: str) -> dict[str, object]:
    return _document(build_id, version_id).to_summary()


@app.get("/api/v1/builds/{build_id}/palette")
def get_palette(build_id: str) -> list[dict[str, object]]:
    return [asdict(item) for item in _document(build_id).palette]


@app.get("/api/v1/builds/{build_id}/regions")
def get_regions(build_id: str) -> list[dict[str, object]]:
    return [asdict(item) for item in _document(build_id).regions]


@app.get("/api/v1/builds/{build_id}/chunks")
def get_chunks(build_id: str, includeData: bool = Query(False), versionId: str | None = None) -> list[dict[str, object]]:
    chunks = store.chunks(build_id, versionId)
    if not includeData:
        for chunk in chunks:
            chunk.pop("data", None)
    return chunks


@app.get("/api/v1/builds/{build_id}/blocks")
def list_blocks(build_id: str, cursor: int = Query(0, ge=0), limit: int = Query(100000, ge=1, le=250000)) -> dict[str, object]:
    document = _document(build_id)
    ordered = sorted(document.blocks.items())
    page = ordered[cursor : cursor + min(limit, settings.max_query_blocks)]
    next_cursor = cursor + len(page) if cursor + len(page) < len(ordered) else None
    return {
        "coordinateSpace": "document",
        "items": [{"position": asdict(position), "paletteId": palette_id} for position, palette_id in page],
        "nextCursor": next_cursor,
        "total": len(ordered),
    }


@app.post("/api/v1/builds/{build_id}/blocks/query")
def query_blocks(build_id: str, payload: BlockQuery) -> dict[str, object]:
    document = _document(build_id)
    bounds = IntBoundingBox(IntVector3(**payload.bounds.min.model_dump()), IntVector3(**payload.bounds.max.model_dump()))
    palette = document.palette_by_id()
    state_filter = set(payload.states)
    rows = []
    for point in bounds.iter_points():
        palette_id = document.blocks.get(point)
        state = palette[palette_id].canonical_state if palette_id is not None else "minecraft:air"
        if not payload.includeAir and palette_id is None:
            continue
        if state_filter and state not in state_filter:
            continue
        rows.append({"position": point.as_tuple(), "paletteId": palette_id, "state": state})
        if len(rows) >= min(payload.limit, settings.max_query_blocks):
            break
    return {"coordinateSpace": "document", "items": rows, "truncated": len(rows) >= payload.limit}


@app.get("/api/v1/builds/{build_id}/blocks/{x}/{y}/{z}")
def get_block(build_id: str, x: int, y: int, z: int) -> dict[str, object]:
    document = _document(build_id)
    position = IntVector3(x, y, z)
    entry = document.state_at(position)
    entity = next((be for be in document.block_entities if be.position == position), None)
    return {"coordinateSpace": "document", "position": asdict(position), "palette": asdict(entry), "blockEntity": asdict(entity) if entity else None}


@app.get("/api/v1/builds/{build_id}/analysis")
def get_analysis(build_id: str) -> dict[str, object]:
    return analyze_document(_document(build_id))


@app.get("/api/v1/builds/{build_id}/rooms")
def get_rooms(build_id: str) -> dict[str, object]:
    return analyze_document(_document(build_id))["rooms"]


@app.get("/api/v1/builds/{build_id}/components")
def get_components(build_id: str) -> dict[str, object]:
    return analyze_document(_document(build_id))["components"]


def _snapshot_root(snapshot_id: str) -> Path:
    return settings.object_store_root / "snapshots" / snapshot_id


@app.post("/api/v1/builds/{build_id}/snapshots")
def create_snapshot(build_id: str, payload: SnapshotCreate, request: Request, response: Response) -> dict[str, object]:
    raw_payload = payload.model_dump()

    def produce() -> dict[str, object]:
        document = _document(build_id)
        if payload.type == "layer_palette":
            if payload.y is None:
                raise HTTPException(422, detail={"code": "SNAPSHOT_LAYER_REQUIRED"})
            image, manifest = render_palette_layer(document, payload.y, pixels_per_block=payload.pixelsPerBlock)
            root = _snapshot_root(manifest.snapshot_id)
            root.mkdir(parents=True, exist_ok=True)
            (root / "color.png").write_bytes(image)
            (root / "manifest.json").write_text(json.dumps(asdict(manifest), sort_keys=True), "utf-8")
            return {"snapshotId": manifest.snapshot_id, "manifest": asdict(manifest), "artifacts": {"color": f"/api/v1/snapshots/{manifest.snapshot_id}/artifacts/color"}}
        bundle = render_global_snapshot(
            document,
            payload.direction,
            pixels_per_block=payload.pixelsPerBlock,
            hidden_palette_ids=frozenset(payload.hiddenPaletteIds),
        )
        root = _snapshot_root(bundle.manifest.snapshot_id)
        root.mkdir(parents=True, exist_ok=True)
        artifacts = {
            "color": ("color.png", bundle.color_png), "palette": ("palette.png", bundle.palette_png),
            "depth": ("depth.png", bundle.depth_png), "normal": ("normal.png", bundle.normal_png),
            "coordinates": ("coordinates.bin.gz", bundle.coordinate_map_gzip),
        }
        for _, (filename, data) in artifacts.items():
            (root / filename).write_bytes(data)
        (root / "manifest.json").write_bytes(bundle.manifest_json())
        return {
            "snapshotId": bundle.manifest.snapshot_id,
            "manifest": asdict(bundle.manifest),
            "artifacts": {name: f"/api/v1/snapshots/{bundle.manifest.snapshot_id}/artifacts/{name}" for name in artifacts},
        }

    return _idempotent(request, response, scope=f"build.snapshot:{build_id}", payload=raw_payload, producer=produce)


@app.post("/api/v1/builds/{build_id}/presentation-snapshots", status_code=202)
def create_presentation_snapshot(
    build_id: str,
    payload: PresentationSnapshotCreate,
    request: Request,
    response: Response,
) -> dict[str, object]:
    document = _document(build_id, payload.versionId)
    raw_payload = payload.model_dump()

    def produce() -> dict[str, object]:
        render_payload = {
            "buildId": build_id,
            "versionId": payload.versionId or store.engine(build_id).active_version_id,
            "camera": payload.camera,
            "projection": payload.projection,
            "width": payload.width,
            "height": payload.height,
            "transparent": payload.transparent,
            "quality": payload.quality,
        }
        try:
            manifest = renderer_client.render(render_payload)
        except RendererServiceError as exc:
            raise HTTPException(503, detail={"code": "RENDERER_UNAVAILABLE", "message": str(exc)}) from exc
        if manifest.get("buildId") != document.build_id:
            raise HTTPException(502, detail={"code": "RENDERER_BUILD_MISMATCH"})
        return {
            "snapshotId": manifest["snapshotId"],
            "manifest": manifest,
            "artifacts": {
                "color": f"/api/v1/snapshots/{manifest['snapshotId']}/artifacts/color",
            },
        }

    return _idempotent(
        request, response, scope=f"build.presentation-snapshot:{build_id}", payload=raw_payload, producer=produce
    )


@app.get("/api/v1/snapshots/{snapshot_id}/manifest")
def snapshot_manifest(snapshot_id: str) -> FileResponse:
    path = _snapshot_root(snapshot_id) / "manifest.json"
    if not path.is_file():
        raise HTTPException(404, detail={"code": "SNAPSHOT_NOT_FOUND"})
    return FileResponse(path, media_type="application/json")


@app.get("/api/v1/snapshots/{snapshot_id}/image")
def snapshot_image_compat(snapshot_id: str) -> FileResponse:
    return snapshot_artifact(snapshot_id, "color")


@app.get("/api/v1/snapshots/{snapshot_id}/artifacts/{artifact}")
def snapshot_artifact(snapshot_id: str, artifact: str) -> FileResponse:
    mapping = {
        "color": ("color.png", "image/png"), "palette": ("palette.png", "image/png"),
        "depth": ("depth.png", "image/png"), "normal": ("normal.png", "image/png"),
        "coordinates": ("coordinates.bin.gz", "application/gzip"),
    }
    if artifact not in mapping:
        raise HTTPException(404, detail={"code": "SNAPSHOT_ARTIFACT_UNKNOWN"})
    filename, media_type = mapping[artifact]
    path = _snapshot_root(snapshot_id) / filename
    if not path.is_file():
        raise HTTPException(404, detail={"code": "SNAPSHOT_ARTIFACT_NOT_FOUND"})
    return FileResponse(path, media_type=media_type)


def _patch(patch_id: str):
    try:
        return patch_registry[patch_id]
    except KeyError:
        result = store.find_patch(patch_id)
        patch_registry[patch_id] = result
        return result


def _new_patch(build_id: str, payload: PatchCreate):
    engine = store.engine(build_id)
    if payload.buildVersionId != engine.active_version_id:
        raise HTTPException(409, detail={"code": "PATCH_STALE_PARENT", "activeVersionId": engine.active_version_id})
    bounds = IntBoundingBox(IntVector3(**payload.bounds.min.model_dump()), IntVector3(**payload.bounds.max.model_dump()))
    patch = engine.create_patch(
        payload.reason, payload.author, bounds, payload.maxAffectedBlocks, payload.operations,
        coordinate_space=payload.coordinateSpace, preconditions=payload.preconditions,
        expected_parent_hash=engine.active.document.content_hash, target_region=payload.targetRegion,
    )
    patch_registry[patch.patch_id] = (build_id, patch)
    return engine, patch


@app.post("/api/v1/builds/{build_id}/patches")
def create_patch(build_id: str, payload: PatchCreate, request: Request, response: Response) -> dict[str, object]:
    raw_payload = payload.model_dump()

    def produce() -> dict[str, object]:
        engine, patch = _new_patch(build_id, payload)
        engine.validate(patch)
        store.persist_engine(build_id)
        return {"patchId": patch.patch_id, "status": patch.status, "changeCount": len(patch.changes), "validation": patch.validation_report}

    return _idempotent(request, response, scope=f"build.patch:{build_id}", payload=raw_payload, producer=produce)


@app.post("/api/v1/patches/{patch_id}/validate")
def validate_patch(patch_id: str) -> dict[str, object]:
    build_id, patch = _patch(patch_id)
    engine = store.engine(build_id)
    engine.validate(patch)
    store.persist_engine(build_id)
    return {"patchId": patch.patch_id, "status": patch.status, "validation": patch.validation_report}


@app.post("/api/v1/patches/{patch_id}/preview")
def preview_patch(patch_id: str) -> dict[str, object]:
    build_id, patch = _patch(patch_id)
    engine = store.engine(build_id)
    preview = engine.preview(patch)
    store.persist_engine(build_id)
    return {"patchId": patch.patch_id, "status": patch.status, "preview": patch.preview_report, "summary": preview.to_summary()}


@app.post("/api/v1/patches/{patch_id}/commit")
def commit_patch(patch_id: str, request: Request, response: Response) -> dict[str, object]:
    build_id, patch = _patch(patch_id)

    def produce() -> dict[str, object]:
        engine = store.engine(build_id)
        if patch.status.value == "draft":
            engine.validate(patch)
        if patch.status.value == "validated":
            engine.preview(patch)
        version = engine.commit(patch)
        store.persist_engine(build_id)
        BUILD_OPERATIONS.labels("patch_commit", "completed").inc()
        return {"patchId": patch.patch_id, "status": patch.status, "versionId": version.version_id, "contentHash": version.document.content_hash}

    return _idempotent(request, response, scope=f"patch.commit:{patch_id}", payload={"patchId": patch_id}, producer=produce)


@app.post("/api/v1/patches/{patch_id}/rollback")
def rollback_patch(patch_id: str) -> dict[str, object]:
    build_id, _ = _patch(patch_id)
    version = store.engine(build_id).rollback_patch(patch_id)
    store.persist_engine(build_id)
    return {"activeVersionId": version.version_id, "contentHash": version.document.content_hash}


@app.post("/api/v1/builds/{build_id}/undo")
def undo(build_id: str) -> dict[str, object]:
    version = store.engine(build_id).undo()
    store.persist_engine(build_id)
    return {"activeVersionId": version.version_id, "contentHash": version.document.content_hash}


@app.post("/api/v1/builds/{build_id}/checkpoints/{name}")
def checkpoint(build_id: str, name: str) -> dict[str, object]:
    version_id = store.engine(build_id).create_checkpoint(name)
    store.persist_engine(build_id)
    return {"name": name, "versionId": version_id}


@app.post("/api/v1/builds/{build_id}/branches/{name}")
def branch(build_id: str, name: str) -> dict[str, object]:
    engine = store.engine(build_id)
    version = engine.branch_version(name)
    store.persist_engine(build_id)
    return {"name": name, "versionId": version.version_id}


@app.post("/api/v1/builds/{build_id}/merge/{source_version_id}")
def merge(build_id: str, source_version_id: str, payload: dict[str, str]) -> dict[str, object]:
    engine = store.engine(build_id)
    version = engine.merge_versions(source_version_id, author=payload.get("author", "user"), reason=payload.get("reason", "Merge version"))
    store.persist_engine(build_id)
    return {"versionId": version.version_id, "contentHash": version.document.content_hash}


@app.post("/api/v1/builds/{build_id}/ai-runs", status_code=202)
def create_ai_run(build_id: str, payload: AIRunCreate, request: Request, response: Response) -> dict[str, object]:
    _document(build_id)
    raw = payload.model_dump()
    if payload.maxIterations > settings.ai_max_iterations:
        raise HTTPException(422, detail={"code": "AI_ITERATION_LIMIT", "limit": settings.ai_max_iterations})
    if payload.maxTextTokens > settings.ai_max_context_tokens:
        raise HTTPException(422, detail={"code": "AI_CONTEXT_LIMIT", "limit": settings.ai_max_context_tokens})
    if payload.reserveOutputTokens > settings.ai_max_output_tokens:
        raise HTTPException(422, detail={"code": "AI_OUTPUT_LIMIT", "limit": settings.ai_max_output_tokens})
    provider_key = request.headers.get("x-provider-api-key", "")

    def produce() -> dict[str, object]:
        record = ai_manager.start(
            build_id=build_id,
            provider_name=payload.provider,
            model=payload.model,
            task=payload.task,
            api_key=provider_key,
            budget=ContextBudget(
                max_text_tokens=payload.maxTextTokens,
                max_images=payload.maxImages,
                max_image_pixels=payload.maxImagePixels,
                reserve_output_tokens=payload.reserveOutputTokens,
            ),
            max_iterations=payload.maxIterations,
            allow_auto_commit=payload.allowAutoCommit,
        )
        return {"runId": record.run_id, "status": record.status.value, "eventsUrl": f"/api/v1/ai-runs/{record.run_id}/events"}

    return _idempotent(request, response, scope=f"build.ai-run:{build_id}", payload=raw, producer=produce)


@app.get("/api/v1/ai-runs/{run_id}")
def get_ai_run(run_id: str) -> dict[str, object]:
    try:
        return ai_manager.get(run_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "AI_RUN_NOT_FOUND"}) from exc


@app.get("/api/v1/ai-runs/{run_id}/events")
async def stream_ai_run(run_id: str) -> StreamingResponse:
    try:
        events = ai_manager.event_queue(run_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "AI_RUN_NOT_FOUND"}) from exc

    async def stream():
        yield "event: snapshot\ndata: " + json.dumps(ai_manager.get(run_id), sort_keys=True, default=str) + "\n\n"
        closed = False
        while not closed:
            try:
                event = await asyncio.to_thread(events.get, True, 1.0)
            except queue.Empty:
                if ai_manager.is_terminal(run_id):
                    break
                yield ": keepalive\n\n"
                continue
            closed = event.get("event") == "ai.stream.closed"
            yield "event: " + str(event.get("event", "message")) + "\ndata: " + json.dumps(event, sort_keys=True, default=str) + "\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.post("/api/v1/ai-runs/{run_id}/cancel")
def cancel_ai_run(run_id: str) -> dict[str, object]:
    try:
        return ai_manager.cancel(run_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "AI_RUN_NOT_FOUND"}) from exc


@app.post("/api/v1/ai-runs/{run_id}/patches/{patch_id}/approve")
def approve_ai_patch(run_id: str, patch_id: str) -> dict[str, object]:
    try:
        return ai_manager.approve_patch(run_id, patch_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "AI_RUN_OR_PATCH_NOT_FOUND"}) from exc


@app.post("/api/v1/ai-runs/{run_id}/patches/{patch_id}/reject")
def reject_ai_patch(run_id: str, patch_id: str) -> dict[str, object]:
    try:
        return ai_manager.reject_patch(run_id, patch_id)
    except KeyError as exc:
        raise HTTPException(404, detail={"code": "AI_RUN_OR_PATCH_NOT_FOUND"}) from exc


@app.post("/api/v1/builds/{build_id}/exports")
def create_export(build_id: str, payload: dict[str, object], request: Request, response: Response) -> dict[str, object]:
    def produce() -> dict[str, object]:
        document = _document(build_id, str(payload["versionId"]) if payload.get("versionId") else None)
        kind = str(payload.get("format", "schem"))
        if kind == "schem":
            data, filename = export_sponge_v3(document), f"{build_id}.schem"
        elif kind == "litematic":
            data, filename = export_litematic(document, preserve_regions=bool(payload.get("preserveRegions", True))), f"{build_id}.litematic"
        else:
            raise HTTPException(422, detail={"code": "EXPORT_FORMAT_UNSUPPORTED"})
        report = verify_round_trip(document, data, filename)
        if not report.valid:
            raise HTTPException(500, detail={"code": "EXPORT_ROUND_TRIP_FAILED", "messages": report.messages})
        root = settings.object_store_root / "exports"
        root.mkdir(parents=True, exist_ok=True)
        export_id = "export_" + hashlib.sha256(data).hexdigest()[:20]
        path = root / export_id
        if not path.exists():
            path.write_bytes(data)
        return {
            "exportId": export_id, "filename": filename, "sizeBytes": len(data), "roundTrip": asdict(report),
            "downloadUrl": f"/api/v1/exports/{export_id}?{artifact_signer.create_query(f'/api/v1/exports/{export_id}', filename)}",
        }

    return _idempotent(request, response, scope=f"build.export:{build_id}", payload=payload, producer=produce)

@app.get("/api/v1/exports/{export_id}")
def download_export(
    export_id: str,
    filename: str = "build.schem",
    expires: int | None = None,
    signature: str | None = None,
) -> FileResponse:
    if not export_id.startswith("export_"):
        raise HTTPException(422, detail={"code": "EXPORT_ID_INVALID"})
    safe_filename = Path(filename).name
    if artifact_signer.enabled and (expires is not None or signature is not None):
        resource = f"/api/v1/exports/{export_id}"
        if not artifact_signer.verify(resource, safe_filename, expires, signature):
            raise HTTPException(403, detail={"code": "ARTIFACT_SIGNATURE_INVALID"})
    path = settings.object_store_root / "exports" / export_id
    if not path.is_file():
        raise HTTPException(404, detail={"code": "EXPORT_NOT_FOUND"})
    return FileResponse(path, filename=safe_filename, media_type="application/octet-stream")


@app.post("/api/v1/admin/retention/run")
def run_retention() -> dict[str, object]:
    result = retention.run()
    return result.to_dict()


@app.get("/api/v1/assets/raw/{namespace}/{kind}/{resource:path}")
def raw_asset(namespace: str, kind: str, resource: str) -> Response:
    if not settings.asset_pack_path:
        raise HTTPException(404, detail={"code": "ASSET_PACK_NOT_CONFIGURED"})
    pack = ResourcePack(settings.asset_pack_path)
    if kind == "texture":
        return FileResponse(pack.texture_path(namespace, resource), media_type="image/png")
    mapping = {"blockstate": "blockstates", "model": "models/block"}
    if kind not in mapping:
        raise HTTPException(404, detail={"code": "ASSET_KIND_UNKNOWN"})
    return JSONResponse(pack.json(namespace, mapping[kind], resource))
