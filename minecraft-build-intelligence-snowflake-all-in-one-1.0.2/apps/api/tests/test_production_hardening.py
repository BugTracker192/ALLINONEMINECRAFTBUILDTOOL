from __future__ import annotations

import json
import os
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from mbi_api.artifacts import ArtifactSigner
from mbi_api.renderer_client import RendererServiceClient, RendererServiceError
from mbi_api.retention import RetentionManager


def test_artifact_signatures_bind_resource_filename_and_expiry() -> None:
    signer = ArtifactSigner("a" * 32, ttl_seconds=60)
    query = signer.create_query("/api/v1/exports/export_abc", "castle.schem", now=1_000)
    values = dict(item.split("=", 1) for item in query.split("&"))
    expires = int(values["expires"])
    signature = values["signature"]
    assert signer.verify("/api/v1/exports/export_abc", "castle.schem", expires, signature, now=1_001)
    assert not signer.verify("/api/v1/exports/export_other", "castle.schem", expires, signature, now=1_001)
    assert not signer.verify("/api/v1/exports/export_abc", "other.schem", expires, signature, now=1_001)
    assert not signer.verify("/api/v1/exports/export_abc", "castle.schem", expires, signature, now=1_061)


def test_retention_deletes_only_expired_entries(tmp_path: Path) -> None:
    uploads = tmp_path / "uploads"
    uploads.mkdir()
    expired = uploads / "expired"
    fresh = uploads / "fresh"
    expired.write_bytes(b"old")
    fresh.write_bytes(b"new")
    now = 2_000_000.0
    os.utime(expired, (now - 3 * 86400, now - 3 * 86400))
    os.utime(fresh, (now, now))
    result = RetentionManager(tmp_path, {"uploads": 1}).run(now=now)
    assert result.deleted == 1
    assert result.bytes_reclaimed == 3
    assert not expired.exists()
    assert fresh.exists()


class _RendererHandler(BaseHTTPRequestHandler):
    response_code = 200

    def do_POST(self) -> None:  # noqa: N802
        body = json.loads(self.rfile.read(int(self.headers.get("content-length", "0"))))
        if self.response_code != 200:
            encoded = b'{"error":{"code":"RENDER_FAILED"}}'
            self.send_response(self.response_code)
        else:
            encoded = json.dumps({"snapshotId": "snap_123", "buildId": body["buildId"]}).encode()
            self.send_response(200)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, *_: object) -> None:
        return


def test_renderer_client_validates_live_service_response() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), _RendererHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        client = RendererServiceClient(f"http://127.0.0.1:{server.server_port}", 5)
        result = client.render({"buildId": "build_test"})
        assert result["snapshotId"] == "snap_123"
        _RendererHandler.response_code = 503
        with pytest.raises(RendererServiceError):
            client.render({"buildId": "build_test"})
    finally:
        _RendererHandler.response_code = 200
        server.shutdown()
        server.server_close()
