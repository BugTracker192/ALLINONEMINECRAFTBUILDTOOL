from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mbi.importer import import_build

from .observability import BUILD_OPERATIONS
from .store import LocalBuildStore


@dataclass(slots=True)
class Job:
    job_id: str
    status: str = "queued"
    stage: str = "queued"
    progress: float = 0.0
    message: str = ""
    result: dict[str, Any] | None = None
    error: dict[str, Any] | None = None
    cancel_requested: bool = False


class LocalJobManager:
    """Non-blocking durable local job adapter.

    Job state is atomically persisted, so polling and idempotent import creation
    remain meaningful after process restarts. Production can replace execution with
    Celery while preserving the same records and API shape.
    """

    def __init__(self, store: LocalBuildStore) -> None:
        self.store = store
        self.root = store.root.parent / "jobs"
        self.root.mkdir(parents=True, exist_ok=True)
        self.jobs: dict[str, Job] = {}
        self.lock = threading.RLock()
        self._load()

    def _path(self, job_id: str) -> Path:
        return self.root / f"{job_id}.json"

    def _persist(self, job: Job) -> None:
        path = self._path(job.job_id)
        temporary = path.with_suffix(".writing")
        temporary.write_text(json.dumps(asdict(job), sort_keys=True, separators=(",", ":"), default=str), "utf-8")
        temporary.replace(path)

    def _load(self) -> None:
        for path in self.root.glob("job_*.json"):
            try:
                raw = json.loads(path.read_text("utf-8"))
                job = Job(**raw)
            except (OSError, json.JSONDecodeError, TypeError):
                continue
            if job.status in {"queued", "running"}:
                job.status = "failed"
                job.stage = "interrupted"
                job.error = {
                    "code": "JOB_INTERRUPTED",
                    "message": "The API process stopped before this local job completed.",
                    "details": {},
                    "recoverable": True,
                }
                self._persist(job)
            self.jobs[job.job_id] = job

    def _update(self, job: Job, **values: Any) -> None:
        with self.lock:
            for key, value in values.items():
                setattr(job, key, value)
            self._persist(job)

    def create_import(self, path: Path, filename: str) -> Job:
        job = Job("job_" + uuid.uuid4().hex[:20])
        with self.lock:
            self.jobs[job.job_id] = job
            self._persist(job)
        thread = threading.Thread(
            target=self._import,
            args=(job, path, filename),
            name=f"mbi-import-{job.job_id}",
            daemon=True,
        )
        thread.start()
        return job

    def _import(self, job: Job, path: Path, filename: str) -> None:
        outcome = "failed"
        try:
            self._update(job, status="running", stage="reading_upload", progress=0.1)
            data = path.read_bytes()
            if job.cancel_requested:
                self._update(job, status="cancelled", stage="cancelled")
                outcome = "cancelled"
                return
            self._update(job, stage="parsing_nbt", progress=0.3)
            document = import_build(data, filename)
            if job.cancel_requested:
                self._update(job, status="cancelled", stage="cancelled")
                outcome = "cancelled"
                return
            self._update(job, stage="chunking", progress=0.75)
            self.store.put(document)
            self._update(
                job,
                status="completed",
                stage="completed",
                progress=1.0,
                result={"buildId": document.build_id, "summary": document.to_summary()},
            )
            outcome = "completed"
        except Exception as exc:  # external boundary -> stable error payload
            self._update(
                job,
                status="failed",
                stage="failed",
                error={
                    "code": getattr(exc, "code", "IMPORT_FAILED"),
                    "message": str(exc),
                    "details": getattr(exc, "details", {}),
                    "recoverable": getattr(exc, "recoverable", False),
                },
            )
        finally:
            BUILD_OPERATIONS.labels("import", outcome).inc()

    def get(self, job_id: str) -> Job:
        with self.lock:
            return self.jobs[job_id]

    def cancel(self, job_id: str) -> Job:
        job = self.get(job_id)
        self._update(job, cancel_requested=True)
        if job.status == "queued":
            self._update(job, status="cancelled", stage="cancelled")
        return job


class CeleryJobManager:
    """Durable production adapter backed by Redis/Celery."""

    def __init__(self, store: LocalBuildStore, redis_url: str) -> None:
        try:
            from celery import Celery
        except ImportError as exc:
            raise RuntimeError("Celery is required when MBI_DEMO_INLINE_JOBS is false") from exc
        self.store = store
        self.client = Celery("mbi-api-dispatch", broker=redis_url, backend=redis_url)

    @staticmethod
    def _job(result) -> Job:
        state = str(result.state).lower()
        status_map = {
            "pending": "queued",
            "received": "queued",
            "started": "running",
            "progress": "running",
            "success": "completed",
            "failure": "failed",
            "revoked": "cancelled",
            "retry": "running",
        }
        status = status_map.get(state, state)
        info = result.info
        progress = 0.0
        stage = state
        error = None
        payload = None
        if isinstance(info, dict):
            progress = float(info.get("progress", 0.0))
            stage = str(info.get("stage", state))
        if status == "completed":
            payload = result.result if isinstance(result.result, dict) else {"result": result.result}
            progress = 1.0
            stage = "completed"
        elif status == "failed":
            error = {
                "code": "WORKER_TASK_FAILED",
                "message": str(result.result),
                "details": {},
                "recoverable": True,
            }
        return Job(str(result.id), status, stage, progress, result=payload, error=error)

    def create_import(self, path: Path, filename: str) -> Job:
        root = self.store.root.parent.resolve()
        try:
            relative = path.resolve().relative_to(root).as_posix()
        except ValueError as exc:
            raise ValueError("upload path is outside the configured object-store root") from exc
        result = self.client.send_task("mbi.import_build", args=[relative, filename])
        return self._job(result)

    def get(self, job_id: str) -> Job:
        return self._job(self.client.AsyncResult(job_id))

    def cancel(self, job_id: str) -> Job:
        result = self.client.AsyncResult(job_id)
        result.revoke(terminate=True, signal="SIGTERM")
        return Job(job_id, status="cancelled", stage="cancelled", cancel_requested=True)
