#!/usr/bin/env python3
from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from mbi.ai import AnthropicMessagesProvider, ModelEventType, ModelRequest, OpenAICompatibleChatProvider, OpenAIResponsesProvider

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "var/reports/dynamic-ai-providers.json"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    requests: list[dict] = []

    def log_message(self, *_args) -> None:
        return

    def _read(self) -> dict:
        length = int(self.headers.get("content-length", "0"))
        return json.loads(self.rfile.read(length) or b"{}")

    def _json(self, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _sse(self, events: list[dict | str]) -> None:
        body = b"".join((f"data: {event if isinstance(event, str) else json.dumps(event)}\n\n").encode() for event in events)
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self) -> None:
        payload = self._read()
        self.requests.append({"path": self.path, "headers": dict(self.headers), "payload": payload})
        stream = bool(payload.get("stream"))
        if self.path == "/v1/responses":
            if stream:
                self._sse([
                    {"type": "response.output_text.delta", "delta": "OpenAI "},
                    {"type": "response.output_item.added", "item": {"type": "function_call", "call_id": "oc1", "name": "get_build_summary"}},
                    {"type": "response.function_call_arguments.delta", "call_id": "oc1", "delta": "{}"},
                    {"type": "response.output_item.done", "item": {"type": "function_call", "call_id": "oc1", "name": "get_build_summary", "arguments": "{}"}},
                    {"type": "response.completed", "response": {"id": "resp-stream", "usage": {"input_tokens": 3, "output_tokens": 2, "total_tokens": 5}}},
                    "[DONE]",
                ])
            else:
                self._json({"id":"resp-create","output":[{"type":"message","content":[{"type":"output_text","text":"OpenAI create"}]}],"usage":{"input_tokens":2,"output_tokens":2,"total_tokens":4}})
        elif self.path == "/v1/messages":
            if stream:
                self._sse([
                    {"type":"content_block_start","index":0,"content_block":{"type":"text","text":""}},
                    {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Anthropic "}},
                    {"type":"content_block_start","index":1,"content_block":{"type":"tool_use","id":"ac1","name":"get_build_summary","input":{}}},
                    {"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{}"}},
                    {"type":"content_block_stop","index":1},
                    {"type":"message_delta","usage":{"output_tokens":2}},
                    {"type":"message_stop"},
                ])
            else:
                self._json({"id":"msg-create","content":[{"type":"text","text":"Anthropic create"}],"usage":{"input_tokens":2,"output_tokens":2}})
        elif self.path == "/v1/chat/completions":
            if stream:
                self._sse([
                    {"choices":[{"delta":{"content":"Local "},"finish_reason":None}]},
                    {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"lc1","function":{"name":"get_build_summary","arguments":"{}"}}]},"finish_reason":"tool_calls"}]},
                    {"choices":[],"usage":{"prompt_tokens":2,"completion_tokens":2,"total_tokens":4}},
                    "[DONE]",
                ])
            else:
                self._json({"id":"chat-create","choices":[{"message":{"content":"Local create","tool_calls":[]}}],"usage":{"prompt_tokens":2,"completion_tokens":2,"total_tokens":4}})
        else:
            self.send_error(404)


async def collect(provider, request: ModelRequest) -> list[dict]:
    events = []
    async for event in provider.stream_response(request):
        events.append({"type": event.type.value, "data": event.payload})
    return events


async def run(base_url: str) -> dict:
    request = ModelRequest(
        "test-model",
        ({"role":"user","content":[{"type":"input_text","text":"Analyze"}]},),
        ({"type":"function","name":"get_build_summary","description":"summary","parameters":{"type":"object"}},),
        128,
    )
    providers = {
        "openai_responses": OpenAIResponsesProvider(api_key="secret", base_url=base_url),
        "anthropic_messages": AnthropicMessagesProvider(api_key="secret", base_url=base_url),
        "openai_compatible_chat": OpenAICompatibleChatProvider(api_key="secret", base_url=base_url),
    }
    result = {}
    for name, provider in providers.items():
        capabilities = await provider.get_capabilities()
        created = await provider.create_response(request)
        streamed = await collect(provider, request)
        assert created.text.endswith("create")
        assert any(item["type"] == ModelEventType.TEXT_DELTA.value for item in streamed)
        assert any(item["type"] == ModelEventType.TOOL_CALL.value for item in streamed)
        assert any(item["type"] == ModelEventType.COMPLETE.value for item in streamed)
        estimate = await provider.count_or_estimate_tokens(request)
        await provider.cancel("unknown-request")
        result[name] = {
            "capabilities": {"image": capabilities.image_input, "tools": capabilities.tool_calling, "streaming": capabilities.streaming},
            "create": {"id": created.request_id, "text": created.text, "usage": created.usage},
            "stream": streamed,
            "estimatedTokens": estimate,
        }
    return result


def main() -> int:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        providers = asyncio.run(run(f"http://127.0.0.1:{server.server_port}"))
    finally:
        server.shutdown(); server.server_close(); thread.join(timeout=5)
    report = {"schemaVersion":1,"passed":True,"providers":providers,"httpRequests":len(Handler.requests)}
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
