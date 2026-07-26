from __future__ import annotations

import hashlib
import json
import sys
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Any

from .storage import atomic_write_json

_PROGRESS_ENABLED = False
_PROGRESS_JSON = False


def configure_progress(*, enabled: bool, json_mode: bool = False) -> None:
    global _PROGRESS_ENABLED, _PROGRESS_JSON
    _PROGRESS_ENABLED = bool(enabled)
    _PROGRESS_JSON = bool(json_mode)


def _emit_progress(job: "JobRecord") -> None:
    if not _PROGRESS_ENABLED:
        return
    event = {
        "event": "job.progress",
        "job_id": job.job_id,
        "job_type": job.job_type,
        "state": job.state.value,
        "stage": job.stage,
        "progress": job.progress,
    }
    if _PROGRESS_JSON:
        print(json.dumps(event, sort_keys=True, separators=(",", ":")), file=sys.stderr, flush=True)
    else:
        print(f"[{job.job_type}:{job.stage}] {job.progress * 100:.0f}% ({job.state.value})", file=sys.stderr, flush=True)



class JobState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class JobRecord:
    job_id: str
    job_type: str
    input_hashes: dict[str, str]
    configuration: dict[str, Any]
    state: JobState = JobState.PENDING
    stage: str = "pending"
    progress: float = 0.0
    result_refs: list[str] = field(default_factory=list)
    error: dict[str, Any] | None = None

    @classmethod
    def create(cls, job_type: str, input_hashes: dict[str, str], configuration: dict[str, Any]) -> "JobRecord":
        seed = f"{job_type}|{sorted(input_hashes.items())}|{sorted(configuration.items())}".encode()
        return cls("job_" + hashlib.sha256(seed).hexdigest()[:20], job_type, input_hashes, configuration)

    def progress_event(self, stage: str, progress: float, message: str, metrics: dict[str, Any] | None = None) -> dict[str, Any]:
        self.stage = stage
        self.progress = max(0.0, min(1.0, float(progress)))
        return {
            "event": "job.progress",
            "job_id": self.job_id,
            "stage": self.stage,
            "progress": self.progress,
            "message": message,
            "metrics": metrics or {},
        }

    def persist(self, run_root: Path) -> None:
        path = run_root / "jobs.json"
        existing: list[dict[str, Any]] = []
        if path.exists():
            loaded = json.loads(path.read_text("utf-8"))
            existing = loaded if isinstance(loaded, list) else []
        payload = asdict(self)
        payload["state"] = self.state.value
        existing = [item for item in existing if item.get("job_id") != self.job_id]
        existing.append(payload)
        atomic_write_json(path, sorted(existing, key=lambda item: item["job_id"]))
        _emit_progress(self)
