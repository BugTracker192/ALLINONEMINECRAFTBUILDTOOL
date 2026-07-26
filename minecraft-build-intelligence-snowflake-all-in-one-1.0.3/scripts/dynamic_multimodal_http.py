from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app.ai.multimodal import MultimodalAgent
from app.workflows import import_file
from mbi.ai.providers import AnthropicMessagesProvider, OpenAICompatibleChatProvider, OpenAIResponsesProvider


class Harness:
    def __init__(self) -> None:
        self.requests: dict[str, list[dict[str, Any]]] = {"openai": [], "anthropic": [], "compatible": []}


HARNESS = Harness()


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_: Any) -> None:
        return None

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/v1/responses":
            name = "openai"
        elif self.path == "/v1/messages":
            name = "anthropic"
        elif self.path == "/v1/chat/completions":
            name = "compatible"
        else:
            self.send_error(404)
            return
        HARNESS.requests[name].append(payload)
        first = len(HARNESS.requests[name]) == 1
        if name == "openai":
            response = {
                "id": f"resp_{len(HARNESS.requests[name])}",
                "output": ([{"type": "function_call", "call_id": "call_view", "name": "render_view", "arguments": "{\"view\":\"south\",\"size\":256}"}] if first else [{"type": "message", "content": [{"type": "output_text", "text": "Visual feedback received."}]}]),
                "usage": {"input_tokens": 12, "output_tokens": 3, "total_tokens": 15},
            }
        elif name == "anthropic":
            response = {
                "id": f"msg_{len(HARNESS.requests[name])}",
                "content": ([{"type": "tool_use", "id": "call_view", "name": "render_view", "input": {"view": "south", "size": 256}}] if first else [{"type": "text", "text": "Visual feedback received."}]),
                "usage": {"input_tokens": 12, "output_tokens": 3},
            }
        else:
            response = {
                "id": f"chat_{len(HARNESS.requests[name])}",
                "choices": [{"message": ({"role": "assistant", "content": None, "tool_calls": [{"id": "call_view", "type": "function", "function": {"name": "render_view", "arguments": "{\"view\":\"south\",\"size\":256}"}}]} if first else {"role": "assistant", "content": "Visual feedback received."})}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3, "total_tokens": 15},
            }
        body = json.dumps(response, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _contains_data_image(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("data:image/png;base64,")
    if isinstance(value, dict):
        if value.get("type") == "image" and isinstance(value.get("source"), dict):
            source = value["source"]
            return source.get("type") == "base64" and bool(source.get("data"))
        return any(_contains_data_image(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_data_image(item) for item in value)
    return False


async def main_async(reference: Path, pack: Path, output: Path) -> dict[str, Any]:
    output.mkdir(parents=True, exist_ok=True)
    run = output / "run"
    import_file(reference, run)
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        providers = {
            "openai": OpenAIResponsesProvider(api_key="test", base_url=base),
            "anthropic": AnthropicMessagesProvider(api_key="test", base_url=base),
            "compatible": OpenAICompatibleChatProvider(api_key="test", base_url=base),
        }
        results = {}
        for name, provider in providers.items():
            agent = MultimodalAgent(run, provider, "dynamic-model", provider_name=name, resource_pack=pack)
            agent_run = await agent.run("Inspect the rear facade using rendered evidence", max_iterations=3)
            requests = HARNESS.requests[name]
            if agent_run.status != "completed" or len(requests) != 2:
                raise AssertionError({"provider": name, "status": agent_run.status, "requests": len(requests), "error": agent_run.error})
            if not _contains_data_image(requests[0]):
                raise AssertionError(f"{name} initial request did not contain a literal PNG image")
            if not _contains_data_image(requests[1]):
                raise AssertionError(f"{name} feedback request did not contain a fresh PNG image")
            results[name] = {
                "passed": True,
                "request_count": len(requests),
                "initial_image_attached": True,
                "feedback_image_attached": True,
                "tool_calls": agent_run.tool_calls,
                "images_sent": agent_run.images_sent,
                "status": agent_run.status,
            }
        return {"passed": True, "base_url": base, "providers": results}
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("reference", type=Path)
    parser.add_argument("resource_pack", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    report = asyncio.run(main_async(args.reference, args.resource_pack, args.output))
    path = args.output / "dynamic_multimodal_http.json"
    path.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", "utf-8")
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
