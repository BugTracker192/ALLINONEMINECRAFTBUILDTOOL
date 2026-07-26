from __future__ import annotations

from pathlib import Path

import pytest

from app.ai.multimodal import MultimodalAgent
from app.workflows import import_file
from mbi.ai.protocol import ModelRequest, ModelResponse, ProviderCapabilities


class RecordingProvider:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []

    async def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(text_input=True, image_input=True, tool_calling=True, max_images=8)

    async def count_or_estimate_tokens(self, request: ModelRequest) -> int:
        return 100

    async def create_response(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if len(self.requests) == 1:
            return ModelResponse("r1", "I need a fresh rear view.", ({"id": "c1", "name": "render_view", "arguments": {"view": "south", "size": 256}},), {"input_tokens": 10})
        return ModelResponse("r2", "The rendered evidence is visible and grounded.", (), {"output_tokens": 8})

    async def stream_response(self, request: ModelRequest):
        if False:
            yield None

    async def cancel(self, request_id: str) -> None:
        return None


@pytest.mark.asyncio
async def test_agent_receives_initial_and_feedback_pngs(reference_schem: Path, tiny_resource_pack: Path, tmp_path: Path) -> None:
    run = tmp_path / "run"
    import_file(reference_schem, run)
    provider = RecordingProvider()
    agent = MultimodalAgent(run, provider, "test-model", provider_name="recording", resource_pack=tiny_resource_pack)
    result = await agent.run("Inspect the rear facade", max_iterations=3)
    assert result.status == "completed"
    assert len(provider.requests) == 2
    first_content = provider.requests[0].messages[1]["content"]
    assert any(item.get("type") == "input_image" and item["image_url"].startswith("data:image/png;base64,") for item in first_content)
    # The second request includes a new user visual-feedback message produced by render_view.
    assert any(
        isinstance(message.get("content"), list)
        and any(item.get("type") == "input_image" for item in message["content"] if isinstance(item, dict))
        for message in provider.requests[1].messages
    )
    assert len(result.images_sent) >= 5


class BuildingProvider:
    def __init__(self) -> None:
        self.requests: list[ModelRequest] = []
        self.patch_id: str | None = None

    async def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(text_input=True, image_input=True, tool_calling=True, max_images=8)

    async def count_or_estimate_tokens(self, request: ModelRequest) -> int:
        return 100

    def _tool_outputs(self, request: ModelRequest) -> list[dict]:
        import json
        rows = []
        for message in request.messages:
            if message.get("type") == "function_call_output":
                rows.append(json.loads(message["output"]))
        return rows

    async def create_response(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        outputs = self._tool_outputs(request)
        if len(self.requests) == 1:
            return ModelResponse("b1", "Inspect exact source block.", ({"id": "q1", "name": "get_block", "arguments": {"position": [-2, 3, 5]}},), {})
        if len(self.requests) == 2:
            return ModelResponse(
                "b2", "Create a bounded evidence-backed edit.",
                ({
                    "id": "p1", "name": "set_block",
                    "arguments": {
                        "bounds": {"min": [-2, 3, 5], "max": [-2, 3, 5]},
                        "maxAffectedBlocks": 1,
                        "reason": "Replace the inspected corner after exact query.",
                        "operation": {"position": [-2, 3, 5], "state": "minecraft:gold_block"},
                        "evidenceRefs": ["view:global_isometric_ne"],
                        "preconditions": [],
                    },
                },), {},
            )
        if len(self.requests) == 3:
            patch = next(row["patchId"] for row in outputs if row.get("patchId"))
            self.patch_id = patch
            return ModelResponse("b3", "Preview before commit.", ({"id": "pv1", "name": "preview_patch", "arguments": {"patchId": patch}},), {})
        if len(self.requests) == 4:
            assert self.patch_id
            return ModelResponse("b4", "Commit the validated patch.", ({"id": "c1", "name": "commit_patch", "arguments": {"patchId": self.patch_id}},), {})
        return ModelResponse("b5", "The post-commit render is visible; exact queried coordinate and visual evidence agree.", (), {})

    async def stream_response(self, request: ModelRequest):
        if False:
            yield None

    async def cancel(self, request_id: str) -> None:
        return None


@pytest.mark.asyncio
async def test_agent_exact_query_patch_preview_commit_and_visual_reinspection(reference_schem: Path, tiny_resource_pack: Path, tmp_path: Path) -> None:
    from app.project import load_document

    run = tmp_path / "build-loop"
    import_file(reference_schem, run)
    provider = BuildingProvider()
    agent = MultimodalAgent(
        run, provider, "test-model", provider_name="recording",
        resource_pack=tiny_resource_pack, allow_auto_commit=True,
    )
    result = await agent.run("Improve the inspected corner and visually verify it", max_iterations=7)
    assert result.status == "completed"
    assert len(provider.requests) == 5
    assert any(call["name"] == "get_block" for call in result.tool_calls)
    assert any(call["name"] == "preview_patch" and call["output"].get("visual_evidence") for call in result.tool_calls)
    assert any(call["name"] == "commit_patch" and call["output"].get("post_commit_visual_evidence") for call in result.tool_calls)
    document = load_document(run)
    assert document.state_at(type(document.bounds.min)(-2, 3, 5)).canonical_state == "minecraft:gold_block"
    # Both preview and committed feedback messages contain literal PNG image content.
    feedback_image_requests = 0
    for request in provider.requests[3:]:
        if any(
            isinstance(message.get("content"), list)
            and any(item.get("type") == "input_image" and item.get("image_url", "").startswith("data:image/png;base64,") for item in message["content"] if isinstance(item, dict))
            for message in request.messages
        ):
            feedback_image_requests += 1
    assert feedback_image_requests >= 2


class RollbackProvider(BuildingProvider):
    async def create_response(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        outputs = self._tool_outputs(request)
        if len(self.requests) == 1:
            return ModelResponse("r1", "Inspect.", ({"id": "q1", "name": "get_block", "arguments": {"position": [-2, 3, 5]}},), {})
        if len(self.requests) == 2:
            return ModelResponse("r2", "Edit.", ({"id": "p1", "name": "set_block", "arguments": {
                "bounds": {"min": [-2, 3, 5], "max": [-2, 3, 5]}, "maxAffectedBlocks": 1,
                "reason": "Temporary visual test", "operation": {"position": [-2, 3, 5], "state": "minecraft:gold_block"},
                "evidenceRefs": ["view:test"], "preconditions": [],
            }},), {})
        if len(self.requests) == 3:
            self.patch_id = next(row["patchId"] for row in outputs if row.get("patchId"))
            return ModelResponse("r3", "Preview.", ({"id": "pv", "name": "preview_patch", "arguments": {"patchId": self.patch_id}},), {})
        if len(self.requests) == 4:
            return ModelResponse("r4", "Commit.", ({"id": "co", "name": "commit_patch", "arguments": {"patchId": self.patch_id}},), {})
        if len(self.requests) == 5:
            return ModelResponse("r5", "Rollback after visual inspection.", ({"id": "rb", "name": "rollback_patch", "arguments": {"patchId": self.patch_id}},), {})
        return ModelResponse("r6", "Rollback visual confirms restoration.", (), {})


@pytest.mark.asyncio
async def test_agent_rollback_persists_and_rerenders(reference_schem: Path, tiny_resource_pack: Path, tmp_path: Path) -> None:
    from app.project import load_document

    run = tmp_path / "rollback-loop"
    import_file(reference_schem, run)
    provider = RollbackProvider()
    agent = MultimodalAgent(run, provider, "test-model", provider_name="recording", resource_pack=tiny_resource_pack, allow_auto_commit=True)
    result = await agent.run("Temporarily edit then rollback with visual verification", max_iterations=8)
    assert result.status == "completed"
    rollback = next(call for call in result.tool_calls if call["name"] == "rollback_patch")
    assert rollback["output"].get("post_rollback_visual_evidence")
    restored = load_document(run)
    assert restored.state_at(type(restored.bounds.min)(-2, 3, 5)).canonical_state == "minecraft:stone"
    assert any(
        isinstance(message.get("content"), list)
        and any(item.get("type") == "input_image" for item in message["content"] if isinstance(item, dict))
        for message in provider.requests[-1].messages
    )


class OversizedContextProvider(RecordingProvider):
    async def count_or_estimate_tokens(self, request: ModelRequest) -> int:
        return 10_000


@pytest.mark.asyncio
async def test_agent_enforces_context_budget(reference_schem: Path, tmp_path: Path) -> None:
    run = tmp_path / "budget-run"
    import_file(reference_schem, run)
    provider = OversizedContextProvider()
    agent = MultimodalAgent(
        run,
        provider,
        "test-model",
        provider_name="recording",
        max_context_tokens=100,
        max_images=2,
    )
    result = await agent.run("Inspect within a deliberately tiny context budget", max_iterations=1)
    assert result.status == "failed"
    assert result.error is not None
    assert result.error["code"] == "AI_CONTEXT_BUDGET"
    assert result.context_estimates


class RollingVisualProvider(RecordingProvider):
    async def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(text_input=True, image_input=True, tool_calling=True, max_images=2)

    async def create_response(self, request: ModelRequest) -> ModelResponse:
        self.requests.append(request)
        if len(self.requests) <= 4:
            return ModelResponse(
                f"roll-{len(self.requests)}",
                "Request a fresh bounded view.",
                ({"id": f"view-{len(self.requests)}", "name": "render_view", "arguments": {"view": "south", "size": 192}},),
                {},
            )
        return ModelResponse("roll-done", "Fresh visual evidence remained available.", (), {})


@pytest.mark.asyncio
async def test_agent_rolls_visual_context_without_losing_fresh_images(
    reference_schem: Path,
    tiny_resource_pack: Path,
    tmp_path: Path,
) -> None:
    run = tmp_path / "rolling-images"
    import_file(reference_schem, run)
    provider = RollingVisualProvider()
    agent = MultimodalAgent(
        run,
        provider,
        "test-model",
        provider_name="recording",
        resource_pack=tiny_resource_pack,
        max_images=2,
        max_image_bytes=4 * 1024 * 1024,
    )
    result = await agent.run("Repeatedly inspect a fresh rear view", max_iterations=7)
    assert result.status == "completed"
    assert len(result.images_sent) >= 6
    for request in provider.requests:
        count = sum(
            1
            for message in request.messages
            if isinstance(message.get("content"), list)
            for item in message["content"]
            if isinstance(item, dict) and item.get("type") == "input_image"
        )
        assert 1 <= count <= 2
