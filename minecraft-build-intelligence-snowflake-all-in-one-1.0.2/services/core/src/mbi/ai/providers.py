from __future__ import annotations

import asyncio
import json
import uuid
from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

import httpx

from ..errors import MBIError
from .protocol import (
    ModelEvent,
    ModelEventType,
    ModelRequest,
    ModelResponse,
    ProviderCapabilities,
)


@dataclass(slots=True)
class _ActiveRequest:
    cancel_event: asyncio.Event = field(default_factory=asyncio.Event)
    task: asyncio.Task[Any] | None = None


class HTTPProviderBase:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        timeout_seconds: float = 120.0,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.transport = transport
        self._active: dict[str, _ActiveRequest] = {}

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout_seconds),
            transport=self.transport,
            follow_redirects=False,
        )

    async def count_or_estimate_tokens(self, request: ModelRequest) -> int:
        encoded = json.dumps(
            {"messages": request.messages, "tools": request.tools},
            separators=(",", ":"),
            default=str,
        )
        image_cost = encoded.count('"type":"input_image"') * 1024
        return max(1, len(encoded) // 4) + image_cost

    async def cancel(self, request_id: str) -> None:
        active = self._active.get(request_id)
        if active is None:
            return
        active.cancel_event.set()
        if active.task and not active.task.done():
            active.task.cancel()


class OpenAIResponsesProvider(HTTPProviderBase):
    async def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            text_input=True,
            image_input=True,
            tool_calling=True,
            structured_output=True,
            streaming=True,
            max_images=100,
            max_context_tokens=0,
            max_output_tokens=0,
            supported_image_formats=("png", "jpeg", "webp", "gif"),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "authorization": f"Bearer {self.api_key}",
            "content-type": "application/json",
        }

    def _payload(self, request: ModelRequest, *, stream: bool) -> dict[str, Any]:
        input_items: list[dict[str, Any]] = []
        for message in request.messages:
            if message.get("type") == "function_call_output":
                input_items.append(dict(message))
                continue
            if message.get("role") == "assistant" and message.get("tool_calls"):
                if message.get("content"):
                    input_items.append({"role": "assistant", "content": message.get("content")})
                for call in message.get("tool_calls", []):
                    input_items.append(
                        {
                            "type": "function_call",
                            "call_id": str(call.get("id", "")),
                            "name": str(call.get("name", "")),
                            "arguments": json.dumps(call.get("arguments", {}), separators=(",", ":")),
                        }
                    )
                continue
            input_items.append(dict(message))
        payload: dict[str, Any] = {
            "model": request.model,
            "input": input_items,
            "tools": list(request.tools),
            "stream": stream,
            "store": False,
            "metadata": {str(key): str(value)[:512] for key, value in request.metadata.items()},
        }
        if request.max_output_tokens is not None:
            payload["max_output_tokens"] = request.max_output_tokens
        return payload

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> ModelResponse:
        text: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for item in data.get("output", []):
            if not isinstance(item, dict):
                continue
            if item.get("type") == "message":
                for content in item.get("content", []):
                    if isinstance(content, dict) and content.get("type") == "output_text":
                        text.append(str(content.get("text", "")))
            elif item.get("type") in {"function_call", "custom_tool_call"}:
                arguments = item.get("arguments", "{}")
                try:
                    parsed = json.loads(arguments) if isinstance(arguments, str) else arguments
                except json.JSONDecodeError:
                    parsed = {"$raw": arguments}
                tool_calls.append(
                    {
                        "id": item.get("call_id") or item.get("id"),
                        "name": item.get("name"),
                        "arguments": parsed,
                    }
                )
        usage = data.get("usage", {}) if isinstance(data.get("usage"), dict) else {}
        return ModelResponse(
            str(data.get("id", "resp_unknown")),
            "".join(text),
            tuple(tool_calls),
            {
                "input_tokens": int(usage.get("input_tokens", 0) or 0),
                "output_tokens": int(usage.get("output_tokens", 0) or 0),
                "total_tokens": int(usage.get("total_tokens", 0) or 0),
            },
        )

    async def create_response(self, request: ModelRequest) -> ModelResponse:
        request_id = "local_" + uuid.uuid4().hex
        active = _ActiveRequest()
        self._active[request_id] = active
        try:
            async with self._client() as client:
                response = await client.post(
                    f"{self.base_url}/v1/responses",
                    headers=self._headers(),
                    json=self._payload(request, stream=False),
                )
                response.raise_for_status()
                return self._parse_response(response.json())
        except httpx.HTTPStatusError as exc:
            raise MBIError(
                "AI_PROVIDER_HTTP",
                "OpenAI-compatible provider returned an HTTP error.",
                {"status": exc.response.status_code, "body": exc.response.text[:2000]},
            ) from exc
        except httpx.HTTPError as exc:
            raise MBIError("AI_PROVIDER_NETWORK", "OpenAI-compatible provider request failed.", {"error": str(exc)}) from exc
        finally:
            self._active.pop(request_id, None)

    async def stream_response(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        local_id = "local_" + uuid.uuid4().hex
        active = _ActiveRequest(task=asyncio.current_task())
        self._active[local_id] = active
        tool_arguments: dict[str, str] = {}
        tool_metadata: dict[str, dict[str, Any]] = {}
        try:
            async with self._client() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/v1/responses",
                    headers=self._headers(),
                    json=self._payload(request, stream=True),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if active.cancel_event.is_set():
                            raise asyncio.CancelledError
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw or raw == "[DONE]":
                            continue
                        event = json.loads(raw)
                        event_type = event.get("type")
                        if event_type == "response.output_text.delta":
                            yield ModelEvent(ModelEventType.TEXT_DELTA, {"delta": event.get("delta", "")})
                        elif event_type == "response.output_item.added":
                            item = event.get("item", {})
                            if isinstance(item, dict) and item.get("type") == "function_call":
                                call_id = str(item.get("call_id") or item.get("id"))
                                tool_metadata[call_id] = {"id": call_id, "name": item.get("name")}
                                tool_arguments[call_id] = ""
                        elif event_type == "response.function_call_arguments.delta":
                            call_id = str(event.get("item_id") or event.get("call_id"))
                            tool_arguments[call_id] = tool_arguments.get(call_id, "") + str(event.get("delta", ""))
                        elif event_type == "response.output_item.done":
                            item = event.get("item", {})
                            if isinstance(item, dict) and item.get("type") == "function_call":
                                call_id = str(item.get("call_id") or item.get("id"))
                                raw_args = str(item.get("arguments", tool_arguments.get(call_id, "{}")))
                                try:
                                    arguments = json.loads(raw_args)
                                except json.JSONDecodeError:
                                    arguments = {"$raw": raw_args}
                                yield ModelEvent(
                                    ModelEventType.TOOL_CALL,
                                    {**tool_metadata.get(call_id, {"id": call_id}), "arguments": arguments},
                                )
                        elif event_type == "response.completed":
                            response_data = event.get("response", {})
                            usage = response_data.get("usage", {}) if isinstance(response_data, dict) else {}
                            yield ModelEvent(ModelEventType.USAGE, dict(usage) if isinstance(usage, dict) else {})
                            yield ModelEvent(ModelEventType.COMPLETE, {"requestId": response_data.get("id", local_id)})
        except httpx.HTTPStatusError as exc:
            raise MBIError("AI_PROVIDER_HTTP", "OpenAI streaming request failed.", {"status": exc.response.status_code}) from exc
        finally:
            self._active.pop(local_id, None)


class AnthropicMessagesProvider(HTTPProviderBase):
    def __init__(self, *, api_key: str, base_url: str = "https://api.anthropic.com", anthropic_version: str = "2023-06-01", **kwargs: Any) -> None:
        super().__init__(api_key=api_key, base_url=base_url, **kwargs)
        self.anthropic_version = anthropic_version

    async def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            text_input=True,
            image_input=True,
            tool_calling=True,
            structured_output=True,
            streaming=True,
            max_images=100,
            supported_image_formats=("png", "jpeg", "webp", "gif"),
        )

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.api_key,
            "anthropic-version": self.anthropic_version,
            "content-type": "application/json",
        }

    @staticmethod
    def _message_content(content: Any) -> Any:
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            converted = []
            for item in content:
                if not isinstance(item, dict):
                    continue
                if item.get("type") in {"input_text", "text"}:
                    converted.append({"type": "text", "text": str(item.get("text", ""))})
                elif item.get("type") in {"input_image", "image"}:
                    image_url = item.get("image_url") or item.get("url")
                    if isinstance(image_url, str) and image_url.startswith("data:"):
                        header, data = image_url.split(",", 1)
                        media_type = header.split(";", 1)[0].split(":", 1)[1]
                        converted.append({"type": "image", "source": {"type": "base64", "media_type": media_type, "data": data}})
            return converted
        return str(content)

    def _payload(self, request: ModelRequest, *, stream: bool) -> dict[str, Any]:
        system_parts = []
        messages = []
        for message in request.messages:
            if message.get("type") == "function_call_output":
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": str(message.get("call_id", "")),
                                "content": str(message.get("output", "")),
                            }
                        ],
                    }
                )
                continue
            role = message.get("role")
            if role in {"system", "developer"}:
                system_parts.append(str(message.get("content", "")))
            elif role == "assistant" and message.get("tool_calls"):
                content: list[dict[str, Any]] = []
                if message.get("content"):
                    content.append({"type": "text", "text": str(message.get("content", ""))})
                for call in message.get("tool_calls", []):
                    content.append(
                        {
                            "type": "tool_use",
                            "id": str(call.get("id", "")),
                            "name": str(call.get("name", "")),
                            "input": call.get("arguments", {}),
                        }
                    )
                messages.append({"role": "assistant", "content": content})
            else:
                messages.append({"role": role, "content": self._message_content(message.get("content", ""))})
        tools = []
        for tool in request.tools:
            function = tool.get("function", tool)
            tools.append(
                {
                    "name": function.get("name"),
                    "description": function.get("description", ""),
                    "input_schema": function.get("parameters", function.get("input_schema", {"type": "object"})),
                }
            )
        return {
            "model": request.model,
            "system": "\n\n".join(system_parts),
            "messages": messages,
            "tools": tools,
            "max_tokens": request.max_output_tokens or 4096,
            "stream": stream,
        }

    @staticmethod
    def _parse_response(data: dict[str, Any]) -> ModelResponse:
        text = []
        tool_calls = []
        for block in data.get("content", []):
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text":
                text.append(str(block.get("text", "")))
            elif block.get("type") == "tool_use":
                tool_calls.append({"id": block.get("id"), "name": block.get("name"), "arguments": block.get("input", {})})
        usage = data.get("usage", {}) if isinstance(data.get("usage"), dict) else {}
        input_tokens = int(usage.get("input_tokens", 0) or 0)
        output_tokens = int(usage.get("output_tokens", 0) or 0)
        return ModelResponse(
            str(data.get("id", "msg_unknown")),
            "".join(text),
            tuple(tool_calls),
            {"input_tokens": input_tokens, "output_tokens": output_tokens, "total_tokens": input_tokens + output_tokens},
        )

    async def create_response(self, request: ModelRequest) -> ModelResponse:
        try:
            async with self._client() as client:
                response = await client.post(
                    f"{self.base_url}/v1/messages",
                    headers=self._headers(),
                    json=self._payload(request, stream=False),
                )
                response.raise_for_status()
                return self._parse_response(response.json())
        except httpx.HTTPStatusError as exc:
            raise MBIError("AI_PROVIDER_HTTP", "Anthropic provider returned an HTTP error.", {"status": exc.response.status_code, "body": exc.response.text[:2000]}) from exc
        except httpx.HTTPError as exc:
            raise MBIError("AI_PROVIDER_NETWORK", "Anthropic provider request failed.", {"error": str(exc)}) from exc

    async def stream_response(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        local_id = "local_" + uuid.uuid4().hex
        active = _ActiveRequest(task=asyncio.current_task())
        self._active[local_id] = active
        blocks: dict[int, dict[str, Any]] = {}
        try:
            async with self._client() as client:
                async with client.stream(
                    "POST",
                    f"{self.base_url}/v1/messages",
                    headers=self._headers(),
                    json=self._payload(request, stream=True),
                ) as response:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if active.cancel_event.is_set():
                            raise asyncio.CancelledError
                        if not line.startswith("data:"):
                            continue
                        raw = line[5:].strip()
                        if not raw:
                            continue
                        event = json.loads(raw)
                        event_type = event.get("type")
                        if event_type == "content_block_start":
                            blocks[int(event.get("index", 0))] = dict(event.get("content_block", {}))
                        elif event_type == "content_block_delta":
                            delta = event.get("delta", {})
                            if delta.get("type") == "text_delta":
                                yield ModelEvent(ModelEventType.TEXT_DELTA, {"delta": delta.get("text", "")})
                            elif delta.get("type") == "input_json_delta":
                                index = int(event.get("index", 0))
                                block = blocks.setdefault(index, {})
                                block["partial_json"] = str(block.get("partial_json", "")) + str(delta.get("partial_json", ""))
                        elif event_type == "content_block_stop":
                            index = int(event.get("index", 0))
                            block = blocks.get(index, {})
                            if block.get("type") == "tool_use":
                                raw_args = block.get("partial_json", "{}")
                                try:
                                    args = json.loads(raw_args)
                                except json.JSONDecodeError:
                                    args = block.get("input", {"$raw": raw_args})
                                yield ModelEvent(ModelEventType.TOOL_CALL, {"id": block.get("id"), "name": block.get("name"), "arguments": args})
                        elif event_type == "message_delta":
                            usage = event.get("usage", {})
                            yield ModelEvent(ModelEventType.USAGE, dict(usage) if isinstance(usage, dict) else {})
                        elif event_type == "message_stop":
                            yield ModelEvent(ModelEventType.COMPLETE, {"requestId": local_id})
        finally:
            self._active.pop(local_id, None)


class OpenAICompatibleChatProvider(HTTPProviderBase):
    """Adapter for local and hosted OpenAI-compatible Chat Completions servers."""

    async def get_capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(text_input=True, image_input=True, tool_calling=True, structured_output=True, streaming=True, max_images=32)

    def _payload(self, request: ModelRequest, *, stream: bool) -> dict[str, Any]:
        messages: list[dict[str, Any]] = []
        for message in request.messages:
            if message.get("type") == "function_call_output":
                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": str(message.get("call_id", "")),
                        "content": str(message.get("output", "")),
                    }
                )
                continue
            converted = dict(message)
            if converted.get("role") == "developer":
                converted["role"] = "system"
            content = converted.get("content")
            if isinstance(content, list):
                converted_content = []
                for item in content:
                    if not isinstance(item, dict):
                        continue
                    if item.get("type") in {"input_text", "text"}:
                        converted_content.append({"type": "text", "text": str(item.get("text", ""))})
                    elif item.get("type") in {"input_image", "image"}:
                        image_url = item.get("image_url") or item.get("url")
                        if isinstance(image_url, str):
                            converted_content.append({"type": "image_url", "image_url": {"url": image_url}})
                    elif item.get("type") == "image_url":
                        converted_content.append(item)
                converted["content"] = converted_content
            if converted.get("tool_calls"):
                converted["tool_calls"] = [
                    {
                        "id": str(call.get("id", "")),
                        "type": "function",
                        "function": {
                            "name": str(call.get("name", "")),
                            "arguments": json.dumps(call.get("arguments", {}), separators=(",", ":")),
                        },
                    }
                    for call in converted["tool_calls"]
                ]
            messages.append(converted)
        tools = []
        for tool in request.tools:
            function = tool.get("function", tool)
            tools.append(
                {
                    "type": "function",
                    "function": {
                        "name": function.get("name"),
                        "description": function.get("description", ""),
                        "parameters": function.get("parameters", {"type": "object"}),
                    },
                }
            )
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": messages,
            "tools": tools,
            "stream": stream,
        }
        if request.max_output_tokens is not None:
            payload["max_tokens"] = request.max_output_tokens
        if stream:
            payload["stream_options"] = {"include_usage": True}
        return payload

    async def create_response(self, request: ModelRequest) -> ModelResponse:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        async with self._client() as client:
            response = await client.post(f"{self.base_url}/v1/chat/completions", headers=headers, json=self._payload(request, stream=False))
            response.raise_for_status()
            data = response.json()
        choice = data.get("choices", [{}])[0]
        message = choice.get("message", {})
        calls = []
        for call in message.get("tool_calls", []) or []:
            function = call.get("function", {})
            raw = function.get("arguments", "{}")
            try:
                args = json.loads(raw)
            except json.JSONDecodeError:
                args = {"$raw": raw}
            calls.append({"id": call.get("id"), "name": function.get("name"), "arguments": args})
        usage = data.get("usage", {}) or {}
        return ModelResponse(str(data.get("id", "chat_unknown")), str(message.get("content", "") or ""), tuple(calls), {str(k): int(v) for k, v in usage.items() if isinstance(v, int)})

    async def stream_response(self, request: ModelRequest) -> AsyncIterator[ModelEvent]:
        headers = {"content-type": "application/json"}
        if self.api_key:
            headers["authorization"] = f"Bearer {self.api_key}"
        calls: dict[int, dict[str, Any]] = {}
        async with self._client() as client:
            async with client.stream("POST", f"{self.base_url}/v1/chat/completions", headers=headers, json=self._payload(request, stream=True)) as response:
                response.raise_for_status()
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[5:].strip()
                    if raw == "[DONE]":
                        yield ModelEvent(ModelEventType.COMPLETE, {})
                        break
                    chunk = json.loads(raw)
                    if chunk.get("usage"):
                        yield ModelEvent(ModelEventType.USAGE, dict(chunk["usage"]))
                    for choice in chunk.get("choices", []):
                        delta = choice.get("delta", {})
                        if delta.get("content"):
                            yield ModelEvent(ModelEventType.TEXT_DELTA, {"delta": delta["content"]})
                        for call in delta.get("tool_calls", []) or []:
                            index = int(call.get("index", 0))
                            record = calls.setdefault(index, {"id": call.get("id"), "name": None, "arguments": ""})
                            function = call.get("function", {})
                            record["name"] = function.get("name") or record["name"]
                            record["arguments"] += function.get("arguments", "")
                        if choice.get("finish_reason") == "tool_calls":
                            for record in calls.values():
                                try:
                                    args = json.loads(record["arguments"] or "{}")
                                except json.JSONDecodeError:
                                    args = {"$raw": record["arguments"]}
                                yield ModelEvent(ModelEventType.TOOL_CALL, {"id": record["id"], "name": record["name"], "arguments": args})
