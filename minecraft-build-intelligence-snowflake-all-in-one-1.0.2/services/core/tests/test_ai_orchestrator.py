from __future__ import annotations

import asyncio

from mbi.ai import AIOrchestrator, AIRunStatus, BuildToolExecutor, ContextBudget, ModelRequest, ModelResponse, ProviderCapabilities
from mbi.patch import PatchEngine


class FakeProvider:
    def __init__(self) -> None:
        self.calls = 0

    async def get_capabilities(self):
        return ProviderCapabilities(tool_calling=True)

    async def count_or_estimate_tokens(self, request: ModelRequest) -> int:
        return 100

    async def create_response(self, request: ModelRequest) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            return ModelResponse("r1", "Inspecting. ", ({"id": "c1", "name": "get_build_summary", "arguments": {}},), {"input_tokens": 10, "output_tokens": 3, "total_tokens": 13})
        return ModelResponse("r2", "Evidence confirms the summary.", (), {"input_tokens": 12, "output_tokens": 5, "total_tokens": 17})

    async def stream_response(self, request):
        if False:
            yield None

    async def cancel(self, request_id: str) -> None:
        return None


def test_orchestrator_executes_tools_and_completes(sample_document) -> None:
    engine = PatchEngine(sample_document)
    tools = BuildToolExecutor(lambda: engine.active.document, engine)
    orchestrator = AIOrchestrator()
    record = asyncio.run(orchestrator.run(
        provider=FakeProvider(), model="fake", task="Analyze the build", document_getter=lambda: engine.active.document,
        tools=tools, budget=ContextBudget(10000, 4, 4_000_000, 1000), max_iterations=4,
    ))
    assert record.status == AIRunStatus.COMPLETED
    assert len(record.tool_calls) == 1
    assert record.tool_calls[0]["name"] == "get_build_summary"
    assert record.usage["total_tokens"] == 30


def test_ai_rollback_requires_explicit_commit_permission(sample_document) -> None:
    from mbi.ai.tools import BuildToolExecutor
    from mbi.patch import PatchEngine

    engine = PatchEngine(sample_document)
    executor = BuildToolExecutor(lambda: engine.active.document, engine)
    point = sample_document.bounds.min
    patch = engine.create_patch(
        "change",
        "test",
        sample_document.bounds,
        1,
        [{"type": "set_block", "position": list(point.as_tuple()), "state": "minecraft:gold_block"}],
    )
    engine.validate(patch)
    engine.preview(patch)
    engine.commit(patch)
    denied = executor.execute("rollback_patch", {"patchId": patch.patch_id}, allow_commit=False)
    assert denied == {"requiresApproval": True, "patchId": patch.patch_id, "operation": "rollback"}
    assert engine.active.document.state_at(point).canonical_state == "minecraft:gold_block"
    allowed = executor.execute("rollback_patch", {"patchId": patch.patch_id}, allow_commit=True)
    assert str(allowed["activeVersionId"]).startswith("ver_")
    assert engine.active.document.state_at(point).canonical_state == "minecraft:stone_bricks"
