from __future__ import annotations

import asyncio
import json
import queue
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from mbi.ai import (
    AIOrchestrator,
    AIRunRecord,
    AIRunStatus,
    AnthropicMessagesProvider,
    BuildToolExecutor,
    ContextBudget,
    OpenAICompatibleChatProvider,
    OpenAIResponsesProvider,
)
from mbi.patch.model import PatchStatus

from .config import Settings
from .observability import AI_OPERATIONS
from .store import LocalBuildStore

_TERMINAL = {AIRunStatus.COMPLETED, AIRunStatus.FAILED, AIRunStatus.CANCELLED}


def record_payload(record: AIRunRecord) -> dict[str, Any]:
    payload = asdict(record)
    payload["status"] = record.status.value
    return payload


@dataclass(slots=True)
class AIRunSession:
    build_id: str
    record: AIRunRecord
    tools: BuildToolExecutor
    events: queue.Queue[dict[str, Any]]
    thread: threading.Thread | None = None
    loop: asyncio.AbstractEventLoop | None = None


class AIExecutionManager:
    """Executes provider-backed tool runs without exposing provider secrets.

    A configured provider base URL is selected server-side. API keys are accepted
    only for the lifetime of the run and are never written to the run record.
    """

    def __init__(self, store: LocalBuildStore, settings: Settings) -> None:
        self.store = store
        self.settings = settings
        self.orchestrator = AIOrchestrator()
        self.root = settings.object_store_root / "ai-runs"
        self.root.mkdir(parents=True, exist_ok=True)
        self._sessions: dict[str, AIRunSession] = {}
        self._locks: dict[str, threading.RLock] = {}
        self._lock = threading.RLock()

    def _run_path(self, run_id: str) -> Path:
        return self.root / f"{run_id}.json"

    def _persist(self, record: AIRunRecord, *, build_id: str, provider: str) -> None:
        path = self._run_path(record.run_id)
        temp = path.with_suffix(".writing")
        temp.write_text(
            json.dumps({"buildId": build_id, "provider": provider, **record_payload(record)}, sort_keys=True, separators=(",", ":"), default=str),
            "utf-8",
        )
        temp.replace(path)

    def _provider(self, provider: str, api_key: str):
        if provider == "openai":
            if not api_key:
                raise ValueError("OpenAI runs require an API key")
            return OpenAIResponsesProvider(api_key=api_key, base_url=self.settings.openai_base_url, timeout_seconds=self.settings.ai_timeout_seconds)
        if provider == "anthropic":
            if not api_key:
                raise ValueError("Anthropic runs require an API key")
            return AnthropicMessagesProvider(api_key=api_key, base_url=self.settings.anthropic_base_url, timeout_seconds=self.settings.ai_timeout_seconds)
        if provider == "local":
            return OpenAICompatibleChatProvider(api_key=api_key, base_url=self.settings.local_ai_base_url, timeout_seconds=self.settings.ai_timeout_seconds)
        raise ValueError(f"Unsupported AI provider: {provider}")

    def start(
        self,
        *,
        build_id: str,
        provider_name: str,
        model: str,
        task: str,
        api_key: str,
        budget: ContextBudget,
        max_iterations: int,
        allow_auto_commit: bool,
    ) -> AIRunRecord:
        engine = self.store.engine(build_id)
        provider = self._provider(provider_name, api_key)
        run_id = "airun_" + uuid.uuid4().hex[:20]
        record = AIRunRecord(run_id, task, model)
        self.orchestrator.runs[run_id] = record
        event_queue: queue.Queue[dict[str, Any]] = queue.Queue(maxsize=10_000)
        tools = BuildToolExecutor(lambda: engine.active.document, engine)
        session = AIRunSession(build_id, record, tools, event_queue)
        with self._lock:
            self._sessions[run_id] = session
            build_lock = self._locks.setdefault(build_id, threading.RLock())
        self._persist(record, build_id=build_id, provider=provider_name)
        event_queue.put({"event": "ai.run.queued", "runId": run_id, "status": record.status.value})

        async def emit(event: dict[str, Any]) -> None:
            try:
                event_queue.put_nowait(event)
            except queue.Full:
                # Keep the run alive; polling still exposes the complete record.
                pass
            self._persist(record, build_id=build_id, provider=provider_name)

        def target() -> None:
            loop = asyncio.new_event_loop()
            session.loop = loop
            asyncio.set_event_loop(loop)
            outcome = "failed"
            try:
                with build_lock:
                    result = loop.run_until_complete(
                        self.orchestrator.run(
                            provider=provider,
                            model=model,
                            task=task,
                            document_getter=lambda: engine.active.document,
                            tools=tools,
                            budget=budget,
                            max_iterations=max_iterations,
                            allow_auto_commit=allow_auto_commit,
                            run_id=run_id,
                            event_callback=emit,
                        )
                    )
                    if engine.active.document.content_hash != self.store.get(build_id).content_hash or allow_auto_commit:
                        self.store.persist_engine(build_id)
                    outcome = result.status.value
            finally:
                self._persist(record, build_id=build_id, provider=provider_name)
                AI_OPERATIONS.labels(provider_name, outcome).inc()
                try:
                    event_queue.put_nowait({"event": "ai.stream.closed", "runId": run_id, "status": record.status.value})
                except queue.Full:
                    pass
                loop.close()

        thread = threading.Thread(target=target, name=f"mbi-ai-{run_id}", daemon=True)
        session.thread = thread
        thread.start()
        return record

    def get(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(run_id)
        if session:
            return {"buildId": session.build_id, **record_payload(session.record)}
        path = self._run_path(run_id)
        if not path.is_file():
            raise KeyError(run_id)
        return json.loads(path.read_text("utf-8"))

    def cancel(self, run_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._sessions.get(run_id)
        if session is None:
            raise KeyError(run_id)
        if session.loop and session.loop.is_running():
            future = asyncio.run_coroutine_threadsafe(self.orchestrator.cancel(run_id), session.loop)
            future.result(timeout=5)
        else:
            session.record.status = AIRunStatus.CANCELLED
        return record_payload(session.record)

    def approve_patch(self, run_id: str, patch_id: str) -> dict[str, Any]:
        session = self._sessions[run_id]
        patch = session.tools.pending_patches[patch_id]
        if patch.status is PatchStatus.VALIDATED:
            session.tools.engine.preview(patch)
        version = session.tools.engine.commit(patch)
        self.store.persist_engine(session.build_id)
        session.record.pending_patch_ids = [item for item in session.record.pending_patch_ids if item != patch_id]
        if not session.record.pending_patch_ids:
            session.record.status = AIRunStatus.COMPLETED
        return {"run": record_payload(session.record), "patchId": patch_id, "versionId": version.version_id, "contentHash": version.document.content_hash}

    def reject_patch(self, run_id: str, patch_id: str) -> dict[str, Any]:
        session = self._sessions[run_id]
        patch = session.tools.pending_patches[patch_id]
        patch.status = PatchStatus.REJECTED
        session.record.pending_patch_ids = [item for item in session.record.pending_patch_ids if item != patch_id]
        session.record.status = AIRunStatus.COMPLETED if not session.record.pending_patch_ids else AIRunStatus.WAITING_APPROVAL
        self.store.persist_engine(session.build_id)
        return {"run": record_payload(session.record), "patchId": patch_id, "status": patch.status.value}

    def event_queue(self, run_id: str) -> queue.Queue[dict[str, Any]]:
        return self._sessions[run_id].events

    def is_terminal(self, run_id: str) -> bool:
        try:
            status = AIRunStatus(self.get(run_id)["status"])
        except (KeyError, ValueError):
            return True
        return status in _TERMINAL
