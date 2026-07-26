#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def main() -> int:
    root = Path(tempfile.mkdtemp(prefix="mbi-worker-dynamic-", dir="/mnt/data"))
    try:
        os.environ["MBI_OBJECT_STORE_ROOT"] = str(root)
        os.environ["MBI_ENV"] = "development"
        from mbi_worker.tasks import (
            autonomous_construct_task,
            export_build_task,
            import_build_task,
            render_global_snapshot_task,
            render_layer_task,
        )

        source = REPO / "packages/test-fixtures/generated/asymmetric-corners.litematic"
        upload = root / "uploads" / source.name
        upload.parent.mkdir(parents=True)
        shutil.copy2(source, upload)
        imported = import_build_task(f"uploads/{source.name}", source.name)
        build_id = imported["buildId"]
        assert (root / "builds" / build_id / "graph.json").is_file()
        assert (root / "builds" / build_id / "analysis.json").is_file()

        layer_y = int(imported["summary"]["bounds"]["min"]["y"])
        layer = render_layer_task(build_id, layer_y, 2)
        assert (root / "snapshots" / layer["snapshotId"] / "color.png").is_file()
        global_snapshot = render_global_snapshot_task(build_id, "north", 2)
        snapshot_root = root / "snapshots" / global_snapshot["snapshotId"]
        assert all((snapshot_root / name).is_file() for name in ("color.png", "palette.png", "depth.png", "normal.png", "coordinates.bin.gz", "manifest.json"))

        schem = export_build_task(build_id, "schem", True)
        litematic = export_build_task(build_id, "litematic", True)
        assert schem["roundTrip"]["valid"] is True
        assert litematic["roundTrip"]["valid"] is True
        assert (root / "exports" / schem["exportKey"]).is_file()
        assert (root / "exports" / litematic["exportKey"]).is_file()

        generated = autonomous_construct_task(
            {
                "name": "Worker Hall",
                "build_type": "hall",
                "style": "gothic",
                "dimensions": [12, 10, 12],
                "floors": 1,
                "interior_required": True,
            },
            1,
        )
        assert generated["summary"]["nonAirCount"] > 0
        assert (root / "builds" / generated["buildId"] / "construction-run.json").is_file()

        # The development shim must never be silently used in production.
        env = os.environ.copy()
        env["MBI_ENV"] = "production"
        probe = subprocess.run(
            [sys.executable, "-c", "import mbi_worker.app"],
            cwd=REPO,
            env=env,
            capture_output=True,
            text=True,
        )
        assert probe.returncode != 0
        assert "Celery is required in production" in probe.stderr

        report = {
            "schemaVersion": 1,
            "passed": True,
            "buildId": build_id,
            "import": imported,
            "layerSnapshotId": layer["snapshotId"],
            "globalSnapshotId": global_snapshot["snapshotId"],
            "exports": {"schem": schem, "litematic": litematic},
            "autonomousBuildId": generated["buildId"],
            "productionFallbackRejected": True,
        }
        output = REPO / "var/reports/dynamic-worker.json"
        output.write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    finally:
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
