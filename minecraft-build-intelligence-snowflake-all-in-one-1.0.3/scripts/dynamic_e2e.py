#!/usr/bin/env python3
from __future__ import annotations

import contextlib
import hashlib
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urljoin

import httpx

from mbi.canonical import (
    BuildDocument, BuildRegion, BuildSource, CanonicalBlockEntity, CanonicalEntity,
    IntBoundingBox, IntVector3, PaletteEntry,
)
from mbi.export.litematic import export_litematic

REPO = Path(__file__).resolve().parents[1]
ASSET_PACK = REPO / "var/assets/minecraft-index-full"



def make_multiregion_fixture(path: Path) -> None:
    palette = [
        PaletteEntry.from_state(0, "minecraft:air"),
        PaletteEntry.from_state(1, "minecraft:stone"),
        PaletteEntry.from_state(2, "minecraft:gold_block"),
    ]
    a = BuildRegion(
        "A", IntVector3(3, 0, 0), IntVector3(-3, 2, 2),
        IntBoundingBox(IntVector3(1, 0, 0), IntVector3(3, 1, 1)),
        tuple(item.canonical_state for item in palette),
    )
    b = BuildRegion(
        "B", IntVector3(2, 0, 0), IntVector3(3, 2, 2),
        IntBoundingBox(IntVector3(2, 0, 0), IntVector3(4, 1, 1)),
        tuple(item.canonical_state for item in palette),
    )
    a_values = {point: 1 for point in a.bounds.iter_points()}
    b_values = {point: 2 for point in b.bounds.iter_points()}
    flattened = dict(a_values)
    flattened.update(b_values)
    source = BuildSource(
        path.name, "litematic", "gzip", hashlib.sha256(b"dynamic-overlap").hexdigest(),
        0, 0, 3953, 6,
    )
    document = BuildDocument(
        "1.1.0", "build_dynamic_overlap", source, {"Name": "Dynamic overlap"},
        IntBoundingBox(IntVector3(1, 0, 0), IntVector3(4, 1, 1)),
        IntVector3(1, 0, 0), palette, [a, b], flattened,
        region_blocks={"A": a_values, "B": b_values},
        block_entities=[CanonicalBlockEntity(IntVector3(1, 0, 0), "minecraft:chest", {"CustomName": "A"}, "A")],
        entities=[CanonicalEntity("minecraft:armor_stand", (2.5, 1.0, 0.5), {"Invisible": 1}, "B")],
        pending_block_ticks=[{"$regionName": "A", "x": 1, "y": 0, "z": 0, "i": "minecraft:stone"}],
        pending_fluid_ticks=[{"$regionName": "B", "x": 2, "y": 0, "z": 0, "i": "minecraft:water"}],
    )
    path.write_bytes(export_litematic(document, preserve_regions=True))


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


class FakeProviderHandler(BaseHTTPRequestHandler):
    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(size))
        assert self.path == "/v1/chat/completions"
        assert body["model"] == "dynamic-fake"
        encoded = json.dumps(
            {
                "id": "chat_dynamic",
                "choices": [
                    {
                        "message": {
                            "role": "assistant",
                            "content": "Dynamic provider execution completed with exact build evidence.",
                            "tool_calls": [],
                        }
                    }
                ],
                "usage": {"prompt_tokens": 31, "completion_tokens": 9, "total_tokens": 40},
            }
        ).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_: object) -> None:
        return


class FakeRendererHandler(BaseHTTPRequestHandler):
    output_root: Path

    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("content-length", "0"))
        body = json.loads(self.rfile.read(size))
        assert self.path == "/render"
        request_hash = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
        snapshot_id = "snap_" + request_hash[:20]
        target = self.output_root / snapshot_id
        target.mkdir(parents=True, exist_ok=True)
        # Valid 1x1 transparent PNG; the service contract is what is under test here.
        png = bytes.fromhex(
            "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489"
            "0000000d49444154789c6360000000020001e221bc330000000049454e44ae426082"
        )
        manifest = {
            "snapshotId": snapshot_id,
            "buildId": body["buildId"],
            "buildVersionId": body.get("versionId"),
            "direction": body["camera"],
            "type": body["projection"],
            "resolution": [body["width"], body["height"]],
            "rendererVersion": "dynamic-fake-1",
            "contentHash": hashlib.sha256(png).hexdigest(),
        }
        (target / "color.png").write_bytes(png)
        (target / "manifest.json").write_text(json.dumps(manifest), "utf-8")
        encoded = json.dumps(manifest).encode()
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self) -> None:  # noqa: N802
        if self.path in {"/healthz", "/readyz"}:
            encoded = b'{"status":"ready"}'
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.send_header("content-length", str(len(encoded)))
            self.end_headers()
            self.wfile.write(encoded)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *_: object) -> None:
        return


@contextlib.contextmanager
def threaded_server(handler, port: int):
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield server
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class APIServer:
    def __init__(self, root: Path, port: int, provider_port: int, renderer_port: int) -> None:
        self.root = root
        self.port = port
        self.provider_port = provider_port
        self.renderer_port = renderer_port
        self.process: subprocess.Popen[str] | None = None
        self.log = root / "api.log"

    def start(self) -> None:
        env = os.environ.copy()
        env.update(
            {
                "PYTHONPATH": os.pathsep.join(
                    [
                        str(REPO / "services/core/src"),
                        str(REPO / "apps/api/src"),
                        str(REPO / "apps/worker/src"),
                    ]
                ),
                "MBI_OBJECT_STORE_ROOT": str(self.root),
                "MBI_DEMO_INLINE_JOBS": "true",
                "MBI_API_KEYS": "dynamic-key",
                "MBI_ARTIFACT_SIGNING_SECRET": "dynamic-signing-secret-at-least-32-bytes",
                "MBI_LOCAL_AI_BASE_URL": f"http://127.0.0.1:{self.provider_port}",
                "MBI_RENDERER_SERVICE_URL": f"http://127.0.0.1:{self.renderer_port}",
                "MBI_ASSET_PACK_PATH": str(ASSET_PACK),
                "MBI_RATE_LIMIT_REQUESTS": "10000",
                "MBI_LOG_LEVEL": "WARNING",
            }
        )
        log = self.log.open("a", encoding="utf-8")
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "mbi_api.main:app", "--host", "127.0.0.1", "--port", str(self.port)],
            cwd=REPO,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        deadline = time.time() + 30
        while time.time() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError(f"API exited early; log:\n{self.log.read_text('utf-8')}")
            try:
                response = httpx.get(f"http://127.0.0.1:{self.port}/healthz", timeout=1)
                if response.status_code == 200:
                    return
            except httpx.HTTPError:
                pass
            time.sleep(0.1)
        raise RuntimeError(f"API did not become ready; log:\n{self.log.read_text('utf-8')}")

    def stop(self) -> None:
        if not self.process or self.process.poll() is not None:
            return
        self.process.send_signal(signal.SIGTERM)
        try:
            self.process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)


def require(response: httpx.Response, expected: int = 200) -> dict | list:
    if response.status_code != expected:
        raise AssertionError(f"{response.request.method} {response.request.url}: {response.status_code} {response.text}")
    if response.headers.get("content-type", "").startswith("application/json"):
        return response.json()
    raise AssertionError(f"Expected JSON from {response.request.url}")


def poll(client: httpx.Client, path: str, terminal: set[str], timeout: float = 30) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        record = require(client.get(path))
        assert isinstance(record, dict)
        if str(record.get("status")) in terminal:
            return record
        time.sleep(0.05)
    raise TimeoutError(path)


def run() -> dict[str, object]:
    started = time.time()
    root = Path(tempfile.mkdtemp(prefix="mbi-dynamic-", dir="/mnt/data"))
    fixture = root / "dynamic-overlap.litematic"
    make_multiregion_fixture(fixture)
    api_port, provider_port, renderer_port = free_port(), free_port(), free_port()
    FakeRendererHandler.output_root = root / "snapshots"
    api = APIServer(root, api_port, provider_port, renderer_port)
    steps: list[dict[str, object]] = []

    def mark(name: str, **metrics: object) -> None:
        steps.append({"name": name, "passed": True, **metrics})

    headers = {"x-api-key": "dynamic-key"}
    with threaded_server(FakeProviderHandler, provider_port), threaded_server(FakeRendererHandler, renderer_port):
        try:
            api.start()
            base = f"http://127.0.0.1:{api_port}"
            with httpx.Client(base_url=base, headers=headers, timeout=30) as client:
                assert httpx.get(base + "/openapi.json", timeout=5).status_code == 401
                health = httpx.get(base + "/healthz", timeout=5)
                assert health.status_code == 200 and health.headers["x-content-type-options"] == "nosniff"
                mark("authentication_and_security_headers")

                with fixture.open("rb") as handle:
                    upload = require(client.post("/api/v1/uploads", files={"file": (fixture.name, handle, "application/octet-stream")}), 202)
                import_headers = {"idempotency-key": "dynamic-import"}
                imported = require(
                    client.post(
                        "/api/v1/builds/import",
                        json={"uploadId": upload["uploadId"], "filename": fixture.name},
                        headers=import_headers,
                    ),
                    202,
                )
                replay = require(
                    client.post(
                        "/api/v1/builds/import",
                        json={"uploadId": upload["uploadId"], "filename": fixture.name},
                        headers=import_headers,
                    ),
                    202,
                )
                assert imported["job_id"] == replay["job_id"]
                job = poll(client, f"/api/v1/jobs/{imported['job_id']}", {"completed", "failed"})
                assert job["status"] == "completed", job
                build_id = job["result"]["buildId"]
                mark("stream_upload_import_idempotency", buildId=build_id)

                summary = require(client.get(f"/api/v1/builds/{build_id}"))
                analysis = require(client.get(f"/api/v1/builds/{build_id}/analysis"))
                assert summary["regionCount"] == 2
                for key in ("materials", "components", "rooms", "symmetry", "surfaces", "support", "navigation", "facade", "lighting", "interiorExterior"):
                    assert key in analysis, key
                mark("canonical_multiregion_and_advanced_analysis", nonAir=summary["nonAirCount"])

                block = require(client.get(f"/api/v1/builds/{build_id}/blocks/0/0/0"))
                assert block["palette"]["canonical_state"].startswith("minecraft:")
                queried = require(
                    client.post(
                        f"/api/v1/builds/{build_id}/blocks/query",
                        json={
                            "bounds": summary["bounds"],
                            "includeAir": True,
                            "limit": 100,
                        },
                    )
                )
                assert queried["items"]
                mark("exact_block_query")

                semantic = require(
                    client.post(
                        f"/api/v1/builds/{build_id}/snapshots",
                        json={"type": "global", "direction": "isometric_se", "pixelsPerBlock": 4},
                        headers={"idempotency-key": "semantic-snapshot"},
                    )
                )
                for name in ("color", "palette", "depth", "normal", "coordinates"):
                    artifact = client.get(semantic["artifacts"][name])
                    assert artifact.status_code == 200 and artifact.content
                mark("deterministic_semantic_snapshot_suite", snapshotId=semantic["snapshotId"])

                presentation = require(
                    client.post(
                        f"/api/v1/builds/{build_id}/presentation-snapshots",
                        json={"camera": "isometric_ne", "projection": "orthographic", "width": 512, "height": 512},
                        headers={"idempotency-key": "presentation-snapshot"},
                    ),
                    202,
                )
                rendered = client.get(presentation["artifacts"]["color"])
                assert rendered.status_code == 200 and rendered.content.startswith(b"\x89PNG")
                mark("headless_renderer_service_contract", snapshotId=presentation["snapshotId"])

                active_version = summary["activeVersionId"]
                point = summary["bounds"]["min"]
                patch_payload = {
                    "buildVersionId": active_version,
                    "coordinateSpace": "document",
                    "bounds": {"min": point, "max": point},
                    "maxAffectedBlocks": 1,
                    "operations": [{"type": "set_block", "position": [point["x"], point["y"], point["z"]], "state": "minecraft:diamond_block"}],
                    "reason": "Dynamic restart persistence test",
                    "author": "dynamic-analysis",
                    "preconditions": [],
                }
                patch = require(
                    client.post(
                        f"/api/v1/builds/{build_id}/patches",
                        json=patch_payload,
                        headers={"idempotency-key": "dynamic-patch"},
                    )
                )
                patch_id = patch["patchId"]
                preview = require(client.post(f"/api/v1/patches/{patch_id}/preview"))
                assert preview["preview"]["changedBlocks"] == 1
                mark("transactional_patch_preview", patchId=patch_id)

            api.stop()
            api.start()
            base = f"http://127.0.0.1:{api_port}"
            with httpx.Client(base_url=base, headers=headers, timeout=30) as client:
                committed = require(
                    client.post(f"/api/v1/patches/{patch_id}/commit", headers={"idempotency-key": "dynamic-commit"})
                )
                replayed_commit = require(
                    client.post(f"/api/v1/patches/{patch_id}/commit", headers={"idempotency-key": "dynamic-commit"})
                )
                assert committed == replayed_commit
                after = require(client.get(f"/api/v1/builds/{build_id}/blocks/{point['x']}/{point['y']}/{point['z']}"))
                assert after["palette"]["canonical_state"] == "minecraft:diamond_block"
                mark("restart_safe_patch_and_idempotent_commit", versionId=committed["versionId"])

                export_results = {}
                for kind in ("schem", "litematic"):
                    exported = require(
                        client.post(
                            f"/api/v1/builds/{build_id}/exports",
                            json={"format": kind, "preserveRegions": True},
                            headers={"idempotency-key": f"export-{kind}"},
                        )
                    )
                    assert exported["roundTrip"]["valid"] is True
                    # Signed URLs must work without the API key.
                    download = httpx.get(urljoin(base, exported["downloadUrl"]), timeout=30)
                    assert download.status_code == 200 and len(download.content) == exported["sizeBytes"]
                    export_results[kind] = hashlib.sha256(download.content).hexdigest()
                mark("schem_and_multiregion_litematic_roundtrip", hashes=export_results)

                started_ai = require(
                    client.post(
                        f"/api/v1/builds/{build_id}/ai-runs",
                        json={
                            "provider": "local",
                            "model": "dynamic-fake",
                            "task": "Analyze exact evidence and report completion.",
                            "maxIterations": 2,
                            "maxTextTokens": 32000,
                            "maxImages": 4,
                            "maxImagePixels": 4000000,
                            "reserveOutputTokens": 1024,
                        },
                        headers={"idempotency-key": "dynamic-ai"},
                    ),
                    202,
                )
                ai = poll(client, f"/api/v1/ai-runs/{started_ai['runId']}", {"completed", "failed", "cancelled", "waiting_approval"})
                assert ai["status"] == "completed" and "Dynamic provider" in ai["text"]
                persisted_ai = (root / "ai-runs" / f"{started_ai['runId']}.json").read_text("utf-8")
                assert "dynamic-key" not in persisted_ai and "provider-api-key" not in persisted_ai
                mark("real_http_ai_provider_execution", runId=started_ai["runId"])

                blockstate = client.get("/api/v1/assets/raw/minecraft/blockstate/stone")
                model = client.get("/api/v1/assets/raw/minecraft/model/stone")
                texture = client.get("/api/v1/assets/raw/minecraft/texture/block/stone")
                assert blockstate.status_code == model.status_code == texture.status_code == 200
                assert texture.content.startswith(b"\x89PNG")
                mark("full_asset_pack_serving")

                old = root / "uploads" / "old-retention-object"
                old.write_bytes(b"remove-me")
                old_time = time.time() - 8 * 86400
                os.utime(old, (old_time, old_time))
                retained = require(client.post("/api/v1/admin/retention/run"))
                assert retained["deleted"] >= 1 and not old.exists()
                mark("retention_cleanup", deleted=retained["deleted"])

                metrics = client.get("/metrics")
                assert metrics.status_code == 200 and "mbi_http_requests_total" in metrics.text
                openapi = require(client.get("/openapi.json"))
                assert "/api/v1/builds/{build_id}/presentation-snapshots" in openapi["paths"]
                mark("metrics_and_openapi")

            api.stop()
            api.start()
            with httpx.Client(base_url=f"http://127.0.0.1:{api_port}", headers=headers, timeout=30) as client:
                persisted_build = require(client.get(f"/api/v1/builds/{build_id}"))
                persisted_job = require(client.get(f"/api/v1/jobs/{imported['job_id']}"))
                persisted_ai_record = require(client.get(f"/api/v1/ai-runs/{started_ai['runId']}"))
                assert persisted_build["activeVersionId"] == committed["versionId"]
                assert persisted_job["status"] == "completed"
                assert persisted_ai_record["status"] == "completed"
                mark("second_restart_persistence")
        finally:
            api.stop()

    report = {
        "schemaVersion": 1,
        "startedAtUnix": started,
        "durationSeconds": round(time.time() - started, 3),
        "temporaryRoot": str(root),
        "passed": all(bool(step["passed"]) for step in steps),
        "stepCount": len(steps),
        "steps": steps,
        "apiLogTail": api.log.read_text("utf-8")[-4000:] if api.log.exists() else "",
    }
    report_path = REPO / "var/reports/dynamic-e2e.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")
    shutil.rmtree(root, ignore_errors=True)
    print(json.dumps(report, indent=2, sort_keys=True))
    return report


if __name__ == "__main__":
    result = run()
    raise SystemExit(0 if result["passed"] else 1)
