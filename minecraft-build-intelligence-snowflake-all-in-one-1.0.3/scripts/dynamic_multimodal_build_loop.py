from __future__ import annotations

import asyncio
import json
import shutil
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app.ai.multimodal import MultimodalAgent
from app.project import load_document
from app.storage import atomic_write_json
from app.workflows import import_file
from mbi.ai.providers import AnthropicMessagesProvider, OpenAICompatibleChatProvider, OpenAIResponsesProvider
from mbi.canonical import IntVector3


REQUESTS: dict[str, list[dict[str, Any]]] = {"openai": [], "anthropic": [], "compatible": []}


def contains_image(value: Any) -> bool:
    if isinstance(value, str):
        return value.startswith("data:image/png;base64,")
    if isinstance(value, dict):
        source = value.get("source")
        if value.get("type") == "image" and isinstance(source, dict):
            return source.get("type") == "base64" and bool(source.get("data"))
        return any(contains_image(item) for item in value.values())
    if isinstance(value, list):
        return any(contains_image(item) for item in value)
    return False


def patch_id(value: Any) -> str | None:
    if isinstance(value, dict):
        direct = value.get("patchId") or value.get("patch_id")
        if isinstance(direct, str):
            return direct
        for item in value.values():
            found = patch_id(item)
            if found:
                return found
    elif isinstance(value, list):
        for item in value:
            found = patch_id(item)
            if found:
                return found
    elif isinstance(value, str) and "patch" in value.lower():
        try:
            return patch_id(json.loads(value))
        except Exception:
            return None
    return None


def tool_for(step: int, pid: str | None) -> tuple[str, dict[str, Any]] | None:
    if step == 1:
        return "get_block", {"position": [-2, 3, 5]}
    if step == 2:
        return "set_block", {
            "bounds": {"min": [-2, 3, 5], "max": [-2, 3, 5]},
            "maxAffectedBlocks": 1,
            "reason": "Dynamic provider image-grounded edit",
            "operation": {"position": [-2, 3, 5], "state": "minecraft:gold_block"},
            "evidenceRefs": ["view:global_isometric_ne"],
            "preconditions": [],
        }
    if step == 3:
        assert pid
        return "preview_patch", {"patchId": pid}
    if step == 4:
        assert pid
        return "commit_patch", {"patchId": pid}
    if step == 5:
        assert pid
        return "rollback_patch", {"patchId": pid}
    return None


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *_: Any) -> None:
        return None

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("content-length", "0"))
        payload = json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/v1/responses":
            provider = "openai"
        elif self.path == "/v1/messages":
            provider = "anthropic"
        elif self.path == "/v1/chat/completions":
            provider = "compatible"
        else:
            self.send_error(404)
            return
        REQUESTS[provider].append(payload)
        step = len(REQUESTS[provider])
        pid = patch_id(payload)
        selected = tool_for(step, pid)
        if provider == "openai":
            if selected:
                name, arguments = selected
                response = {"id": f"resp_{step}", "output": [{"type": "function_call", "call_id": f"call_{step}", "name": name, "arguments": json.dumps(arguments, separators=(",", ":"))}], "usage": {"input_tokens": 10, "output_tokens": 2, "total_tokens": 12}}
            else:
                response = {"id": f"resp_{step}", "output": [{"type": "message", "content": [{"type": "output_text", "text": "Commit and rollback visual evidence inspected; original exact state restored."}]}], "usage": {"input_tokens": 10, "output_tokens": 4, "total_tokens": 14}}
        elif provider == "anthropic":
            if selected:
                name, arguments = selected
                content = [{"type": "tool_use", "id": f"call_{step}", "name": name, "input": arguments}]
            else:
                content = [{"type": "text", "text": "Commit and rollback visual evidence inspected; original exact state restored."}]
            response = {"id": f"msg_{step}", "content": content, "usage": {"input_tokens": 10, "output_tokens": 2}}
        else:
            if selected:
                name, arguments = selected
                message = {"role": "assistant", "content": None, "tool_calls": [{"id": f"call_{step}", "type": "function", "function": {"name": name, "arguments": json.dumps(arguments, separators=(",", ":"))}}]}
            else:
                message = {"role": "assistant", "content": "Commit and rollback visual evidence inspected; original exact state restored."}
            response = {"id": f"chat_{step}", "choices": [{"message": message}], "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
        raw = json.dumps(response, separators=(",", ":")).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)


async def execute(reference: Path, pack: Path, output: Path) -> dict[str, Any]:
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
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
        results: dict[str, Any] = {}
        for name, provider in providers.items():
            run_root = output / name
            import_file(reference, run_root)
            agent = MultimodalAgent(run_root, provider, "dynamic-model", provider_name=name, resource_pack=pack, allow_auto_commit=True)
            result = await agent.run("Inspect, edit, preview, commit, visually review, rollback, and visually verify exact restoration.", max_iterations=8)
            requests = REQUESTS[name]
            rollback_call = next(call for call in result.tool_calls if call["name"] == "rollback_patch")
            restored = load_document(run_root).state_at(IntVector3(-2, 3, 5)).canonical_state
            image_requests = [index + 1 for index, request in enumerate(requests) if contains_image(request)]
            passed = (
                result.status == "completed"
                and len(requests) == 6
                and restored == "minecraft:stone"
                and rollback_call["output"].get("post_rollback_visual_evidence") is not None
                and {1, 4, 5, 6}.issubset(set(image_requests))
            )
            results[name] = {
                "passed": passed,
                "status": result.status,
                "request_count": len(requests),
                "literal_image_request_numbers": image_requests,
                "tool_sequence": [call["name"] for call in result.tool_calls],
                "restored_state": restored,
                "images_sent": result.images_sent,
                "rollback_visual": rollback_call["output"].get("post_rollback_visual_evidence"),
            }
        report = {"schema": "mbi.dynamic-multimodal-build-loop.v1", "passed": all(item["passed"] for item in results.values()), "base_url": base, "providers": results}
        return report
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
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    report = asyncio.run(execute(args.reference, args.resource_pack, args.output))
    report_path = args.report or args.output / "dynamic_multimodal_build_loop.json"
    atomic_write_json(report_path, report)
    print(json.dumps(report, indent=2, default=str))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
