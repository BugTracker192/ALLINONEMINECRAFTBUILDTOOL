from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import asdict, dataclass, field
from enum import StrEnum
from typing import Any, Awaitable, Callable

from ..canonical import BuildDocument
from ..errors import MBIError
from .context import ContextBudget, choose_context
from .protocol import ModelRequest, MultimodalProvider
from .tools import BuildToolExecutor


class AIRunStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass(slots=True)
class AIRunRecord:
    run_id: str
    task: str
    model: str
    status: AIRunStatus = AIRunStatus.QUEUED
    iteration: int = 0
    text: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)
    pending_patch_ids: list[str] = field(default_factory=list)
    usage: dict[str, int] = field(default_factory=dict)
    error: dict[str, Any] | None = None


class AIOrchestrator:
    def __init__(self) -> None:
        self.runs: dict[str, AIRunRecord] = {}
        self._cancel_events: dict[str, asyncio.Event] = {}

    async def cancel(self, run_id: str) -> None:
        event = self._cancel_events.get(run_id)
        if event:
            event.set()
        record = self.runs.get(run_id)
        if record:
            record.status = AIRunStatus.CANCELLED

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are the Minecraft Build Intelligence architect. Every claim must cite an evidence ID or exact coordinate. "
            "Never invent block data. Query tools when evidence is insufficient. All edits must be bounded transactional patches. "
            "Preview edits before requesting commit. Keep exact namespaced states and properties."
        )

    async def run(
        self,
        *,
        provider: MultimodalProvider,
        model: str,
        task: str,
        document_getter,
        tools: BuildToolExecutor,
        budget: ContextBudget,
        max_iterations: int = 12,
        allow_auto_commit: bool = False,
        run_id: str | None = None,
        event_callback: Callable[[dict[str, Any]], Awaitable[None] | None] | None = None,
    ) -> AIRunRecord:
        run_id = run_id or "airun_" + uuid.uuid4().hex[:20]
        record = self.runs.get(run_id) or AIRunRecord(run_id, task, model)
        record.task = task
        record.model = model
        self.runs[run_id] = record

        async def emit(event: str, **payload: Any) -> None:
            if event_callback is None:
                return
            result = event_callback({"event": event, "runId": run_id, **payload})
            if asyncio.iscoroutine(result):
                await result
        cancel_event = asyncio.Event()
        self._cancel_events[run_id] = cancel_event
        try:
            record.status = AIRunStatus.RUNNING
            await emit("ai.run.started", status=record.status.value, model=model)
            document: BuildDocument = document_getter()
            evidence = choose_context(document, budget)
            record.evidence_ids = [item.evidence_id for item in evidence]
            context_payload = [asdict(item) for item in evidence]
            messages: list[dict[str, Any]] = [
                {"role": "developer", "content": self._system_prompt()},
                {
                    "role": "user",
                    "content": (
                        f"Task: {task}\n\nEvidence JSON:\n"
                        + json.dumps(context_payload, sort_keys=True, separators=(",", ":"), default=str)
                    ),
                },
            ]
            for iteration in range(max_iterations):
                if cancel_event.is_set():
                    record.status = AIRunStatus.CANCELLED
                    return record
                record.iteration = iteration + 1
                await emit("ai.run.iteration", iteration=record.iteration)
                request = ModelRequest(
                    model=model,
                    messages=tuple(messages),
                    tools=BuildToolExecutor.definitions(),
                    max_output_tokens=budget.reserve_output_tokens,
                    metadata={"run_id": run_id, "iteration": iteration + 1},
                )
                estimated = await provider.count_or_estimate_tokens(request)
                if estimated > budget.max_text_tokens:
                    raise MBIError(
                        "AI_CONTEXT_BUDGET",
                        "AI request exceeds the configured context budget.",
                        {"estimatedTokens": estimated, "limit": budget.max_text_tokens},
                    )
                response = await provider.create_response(request)
                record.text += response.text
                await emit("ai.run.response", iteration=record.iteration, textDelta=response.text, toolCallCount=len(response.tool_calls))
                for key, value in response.usage.items():
                    record.usage[key] = record.usage.get(key, 0) + int(value)
                if not response.tool_calls:
                    record.status = AIRunStatus.COMPLETED
                    await emit("ai.run.completed", status=record.status.value, usage=record.usage)
                    return record
                messages.append({"role": "assistant", "content": response.text, "tool_calls": list(response.tool_calls)})
                for call in response.tool_calls:
                    call_id = str(call.get("id") or "call_" + uuid.uuid4().hex[:12])
                    name = str(call.get("name"))
                    arguments = call.get("arguments", {})
                    if not isinstance(arguments, dict):
                        arguments = {"$raw": arguments}
                    try:
                        output = tools.execute(name, arguments, allow_commit=allow_auto_commit)
                    except Exception as exc:
                        output = {
                            "error": {
                                "code": getattr(exc, "code", "TOOL_EXECUTION_FAILED"),
                                "message": str(exc),
                                "details": getattr(exc, "details", {}),
                            }
                        }
                    record.tool_calls.append({"id": call_id, "name": name, "arguments": arguments, "output": output})
                    await emit("ai.run.tool_call", id=call_id, name=name, output=output)
                    if output.get("patchId"):
                        record.pending_patch_ids.append(str(output["patchId"]))
                    if output.get("requiresApproval"):
                        record.status = AIRunStatus.WAITING_APPROVAL
                    messages.append(BuildToolExecutor.tool_output_message(call_id, output))
                if record.status is AIRunStatus.WAITING_APPROVAL and not allow_auto_commit:
                    await emit("ai.run.waiting_approval", status=record.status.value, patchIds=record.pending_patch_ids)
                    return record
            raise MBIError("AI_ITERATION_LIMIT", "AI run exhausted its configured iteration limit.", {"limit": max_iterations})
        except asyncio.CancelledError:
            record.status = AIRunStatus.CANCELLED
            await emit("ai.run.cancelled", status=record.status.value)
            return record
        except Exception as exc:
            record.status = AIRunStatus.FAILED
            record.error = {
                "code": getattr(exc, "code", "AI_RUN_FAILED"),
                "message": str(exc),
                "details": getattr(exc, "details", {}),
            }
            await emit("ai.run.failed", status=record.status.value, error=record.error)
            return record
        finally:
            self._cancel_events.pop(run_id, None)
