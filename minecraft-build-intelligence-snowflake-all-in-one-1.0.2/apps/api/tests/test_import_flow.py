from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from mbi_api.main import app


def test_upload_import_and_block_query() -> None:
    client = TestClient(app)
    fixture = Path(__file__).parents[3] / "packages" / "test-fixtures" / "generated" / "one-block.schem"
    with fixture.open("rb") as stream:
        response = client.post("/api/v1/uploads", files={"file": ("one-block.schem", stream, "application/octet-stream")})
    assert response.status_code == 202
    upload = response.json()
    started = client.post("/api/v1/builds/import", json={"uploadId": upload["uploadId"], "filename": "one-block.schem"})
    assert started.status_code == 202
    job_id = started.json()["job_id"]
    for _ in range(100):
        job = client.get(f"/api/v1/jobs/{job_id}").json()
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)
    assert job["status"] == "completed", job
    build_id = job["result"]["buildId"]
    build = client.get(f"/api/v1/builds/{build_id}")
    assert build.status_code == 200
    assert build.json()["nonAirCount"] == 1
    blocks = client.get(f"/api/v1/builds/{build_id}/blocks")
    assert blocks.status_code == 200
    assert blocks.json()["total"] == 1
