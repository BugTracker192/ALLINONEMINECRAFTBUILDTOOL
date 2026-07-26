from __future__ import annotations

import time
from pathlib import Path

from fastapi.testclient import TestClient

from mbi_api.main import app


def _import_fixture(client: TestClient) -> tuple[str, str]:
    fixture = Path(__file__).parents[3] / "packages" / "test-fixtures" / "generated" / "asymmetric-corners.litematic"
    with fixture.open("rb") as stream:
        upload = client.post("/api/v1/uploads", files={"file": (fixture.name, stream, "application/octet-stream")}).json()
    started = client.post("/api/v1/builds/import", json={"uploadId": upload["uploadId"], "filename": fixture.name}).json()
    for _ in range(200):
        job = client.get(f"/api/v1/jobs/{started['job_id']}").json()
        if job["status"] in {"completed", "failed"}:
            break
        time.sleep(0.01)
    assert job["status"] == "completed", job
    build_id = job["result"]["buildId"]
    version_id = client.get(f"/api/v1/builds/{build_id}").json()["activeVersionId"]
    return build_id, version_id


def test_patch_snapshot_version_and_export_flow() -> None:
    client = TestClient(app)
    build_id, version_id = _import_fixture(client)
    snapshot = client.post(f"/api/v1/builds/{build_id}/snapshots", json={"type": "global", "direction": "north", "pixelsPerBlock": 1})
    assert snapshot.status_code == 200, snapshot.text
    snapshot_id = snapshot.json()["snapshotId"]
    assert client.get(f"/api/v1/snapshots/{snapshot_id}/artifacts/depth").status_code == 200

    summary = client.get(f"/api/v1/builds/{build_id}").json()
    bounds = summary["bounds"]
    position = bounds["min"]
    patch_payload = {
        "buildVersionId": version_id,
        "bounds": {"min": position, "max": position},
        "maxAffectedBlocks": 1,
        "operations": [{"type": "set_block", "position": [position["x"], position["y"], position["z"]], "state": "minecraft:diamond_block"}],
        "reason": "integration",
        "author": "test",
    }
    created = client.post(f"/api/v1/builds/{build_id}/patches", json=patch_payload)
    assert created.status_code == 200, created.text
    patch_id = created.json()["patchId"]
    assert client.post(f"/api/v1/patches/{patch_id}/preview").status_code == 200
    committed = client.post(f"/api/v1/patches/{patch_id}/commit")
    assert committed.status_code == 200, committed.text
    assert len(client.get(f"/api/v1/builds/{build_id}/versions").json()) >= 2
    exported = client.post(f"/api/v1/builds/{build_id}/exports", json={"format": "litematic", "preserveRegions": True})
    assert exported.status_code == 200, exported.text
    assert exported.json()["roundTrip"]["valid"] is True
    assert client.post(f"/api/v1/patches/{patch_id}/rollback").status_code == 200


def test_autonomous_generation_endpoint() -> None:
    response = TestClient(app).post("/api/v1/builds/generate", json={"name": "API Hall", "dimensions": [12, 10, 12], "floors": 1, "critiqueIterations": 0})
    assert response.status_code == 201, response.text
    assert response.json()["summary"]["nonAirCount"] > 0
