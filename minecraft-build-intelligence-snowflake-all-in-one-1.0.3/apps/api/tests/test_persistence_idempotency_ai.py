from __future__ import annotations

import json
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from fastapi.testclient import TestClient

from mbi.canonical import IntBoundingBox, IntVector3
from mbi.importer import import_build
from mbi_api.idempotency import IdempotencyStore
from mbi_api.main import ai_manager, app
from mbi_api.store import LocalBuildStore


def test_idempotency_store_replays_and_rejects_conflicts(tmp_path: Path) -> None:
    store = IdempotencyStore(tmp_path)
    calls = 0

    def produce() -> dict[str, int]:
        nonlocal calls
        calls += 1
        return {"value": calls}

    first, replayed = store.execute(scope="test", key="same", payload={"a": 1}, producer=produce)
    second, replayed_again = store.execute(scope="test", key="same", payload={"a": 1}, producer=produce)
    assert first == second == {"value": 1}
    assert replayed is False and replayed_again is True
    assert calls == 1


def test_draft_patch_and_lock_survive_store_restart(tmp_path: Path) -> None:
    fixture = Path(__file__).parents[3] / "packages" / "test-fixtures" / "generated" / "one-block.schem"
    document = import_build(fixture.read_bytes(), fixture.name)
    first = LocalBuildStore(tmp_path / "builds")
    engine = first.put(document)
    point = document.bounds.min
    patch = engine.create_patch(
        "persist draft",
        "test",
        IntBoundingBox(point, point),
        1,
        [{"type": "set_block", "position": list(point.as_tuple()), "state": "minecraft:diamond_block"}],
    )
    engine.validate(patch)
    engine.preview(patch)
    lock = engine.lock_region(IntBoundingBox(point, point), "test", "protect")
    first.persist_engine(document.build_id)

    second = LocalBuildStore(tmp_path / "builds")
    restored = second.engine(document.build_id)
    assert restored.patches[patch.patch_id].status.value == "previewed"
    assert len(restored.patches[patch.patch_id].changes) == 1
    assert restored.locks[lock.lock_id].owner == "test"
    version = restored.commit(restored.patches[patch.patch_id])
    second.persist_engine(document.build_id)
    assert version.document.state_at(point).canonical_state == "minecraft:diamond_block"


class _ChatHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(size))
        assert body["model"] == "fake-model"
        payload = {
            "id": "chat_fake",
            "choices": [{"message": {"role": "assistant", "content": "Verified from exact build evidence.", "tool_calls": []}}],
            "usage": {"prompt_tokens": 20, "completion_tokens": 7, "total_tokens": 27},
        }
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_: object) -> None:
        return


def test_real_local_provider_ai_api_execution() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _ChatHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    original = ai_manager.settings.local_ai_base_url
    ai_manager.settings.local_ai_base_url = f"http://127.0.0.1:{server.server_port}"
    client = TestClient(app)
    try:
        generated = client.post(
            "/api/v1/builds/generate",
            json={"name": "AI fixture", "dimensions": [8, 7, 8], "floors": 1, "critiqueIterations": 0},
        )
        assert generated.status_code == 201, generated.text
        build_id = generated.json()["buildId"]
        started = client.post(
            f"/api/v1/builds/{build_id}/ai-runs",
            json={
                "provider": "local",
                "model": "fake-model",
                "task": "Analyze the build and cite evidence.",
                "maxIterations": 2,
                "maxTextTokens": 32000,
                "reserveOutputTokens": 1024,
            },
        )
        assert started.status_code == 202, started.text
        run_id = started.json()["runId"]
        for _ in range(200):
            record = client.get(f"/api/v1/ai-runs/{run_id}").json()
            if record["status"] in {"completed", "failed", "cancelled", "waiting_approval"}:
                break
            time.sleep(0.01)
        assert record["status"] == "completed", record
        assert "Verified" in record["text"]
        persisted = (ai_manager.root / f"{run_id}.json").read_text("utf-8")
        assert "x-provider-api-key" not in persisted
    finally:
        ai_manager.settings.local_ai_base_url = original
        server.shutdown()
        server.server_close()


def test_metrics_endpoint_exposes_request_metrics() -> None:
    client = TestClient(app)
    client.get("/healthz")
    response = client.get("/metrics")
    assert response.status_code == 200
    assert "mbi_http_requests_total" in response.text
