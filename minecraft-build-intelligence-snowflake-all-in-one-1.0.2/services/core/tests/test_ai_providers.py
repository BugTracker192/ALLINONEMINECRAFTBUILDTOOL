from __future__ import annotations

import asyncio
import json

import httpx

from mbi.ai import AnthropicMessagesProvider, ModelRequest, OpenAICompatibleChatProvider, OpenAIResponsesProvider


def test_openai_responses_adapter_and_tools() -> None:
    seen = {}
    async def handler(request: httpx.Request) -> httpx.Response:
        seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={
            "id": "resp_1",
            "output": [
                {"type": "message", "content": [{"type": "output_text", "text": "done"}]},
                {"type": "function_call", "call_id": "call_1", "name": "get_block", "arguments": "{\"position\":[1,2,3]}"},
            ],
            "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14},
        })
    provider = OpenAIResponsesProvider(api_key="secret", base_url="https://example.test", transport=httpx.MockTransport(handler))
    request = ModelRequest("model", ({"role": "user", "content": "hello"},), ({"type": "function", "name": "get_block", "parameters": {"type": "object"}},), 200)
    response = asyncio.run(provider.create_response(request))
    assert response.text == "done"
    assert response.tool_calls[0]["arguments"]["position"] == [1, 2, 3]
    assert seen["payload"]["store"] is False


def test_anthropic_and_local_payload_conversion() -> None:
    anthropic_seen = {}
    chat_seen = {}
    async def anthropic_handler(request: httpx.Request) -> httpx.Response:
        anthropic_seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "msg_1", "content": [{"type": "text", "text": "ok"}], "usage": {"input_tokens": 3, "output_tokens": 2}})
    async def chat_handler(request: httpx.Request) -> httpx.Response:
        chat_seen["payload"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "chat_1", "choices": [{"message": {"content": "ok", "tool_calls": []}}], "usage": {"prompt_tokens": 3, "completion_tokens": 2}})
    messages = (
        {"role": "developer", "content": "rules"},
        {"role": "assistant", "content": "", "tool_calls": [{"id": "call_1", "name": "get_block", "arguments": {"position": [0, 0, 0]}}]},
        {"type": "function_call_output", "call_id": "call_1", "output": "{\"state\":\"minecraft:stone\"}"},
    )
    tools = ({"type": "function", "name": "get_block", "description": "read", "parameters": {"type": "object"}},)
    anthropic = AnthropicMessagesProvider(api_key="secret", base_url="https://anthropic.test", transport=httpx.MockTransport(anthropic_handler))
    local = OpenAICompatibleChatProvider(api_key="secret", base_url="https://local.test", transport=httpx.MockTransport(chat_handler))
    assert asyncio.run(anthropic.create_response(ModelRequest("claude", messages, tools))).text == "ok"
    assert asyncio.run(local.create_response(ModelRequest("local", messages, tools))).text == "ok"
    assert anthropic_seen["payload"]["messages"][-1]["content"][0]["type"] == "tool_result"
    assert chat_seen["payload"]["messages"][-1]["role"] == "tool"
    assert chat_seen["payload"]["tools"][0]["function"]["name"] == "get_block"
