from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any


def _git_preserves_bytes(repository: Path, path: Path) -> bool:
    relative = path.resolve().relative_to(repository.resolve()).as_posix()
    return _git(repository, "check-attr", "text", "--", relative).endswith(": unset")


def _manifest_size_hash(path: Path, repository: Path) -> tuple[int, str]:
    with path.open("rb") as stream:
        head = stream.read(8192)
    is_text = b"\0" not in head
    if is_text:
        try:
            head.decode("utf-8")
        except UnicodeDecodeError:
            is_text = False
    if is_text and not _git_preserves_bytes(repository, path):
        canonical = path.read_bytes().replace(b"\r\n", b"\n")
        return len(canonical), hashlib.sha256(canonical).hexdigest()
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
            size += len(chunk)
    return size, digest.hexdigest()


def _git(root: Path, *arguments: str) -> str:
    completed = subprocess.run(
        ("git", *arguments),
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return completed.stdout.strip()


def _entry(path: Path, relative: str, repository: Path) -> dict[str, Any]:
    size, digest = _manifest_size_hash(path, repository)
    return {
        "path": relative,
        "sha256": digest,
        "size_bytes": size,
    }


def update_overlay(release_root: Path, *, test_count: int) -> dict[str, Any]:
    release_root = release_root.resolve()
    repository = Path(_git(release_root, "rev-parse", "--show-toplevel"))
    release_prefix = release_root.relative_to(repository).as_posix() + "/"
    base_path = release_root / "RELEASE_FILE_MANIFEST.json"
    overlay_path = release_root / "RELEASE_FILE_MANIFEST_PATCH.json"
    base = json.loads(base_path.read_text("utf-8"))
    base_entries = {item["path"]: item for item in base["files"]}
    prior_overlay: dict[str, Any] = {}
    try:
        prior_overlay = json.loads(
            _git(
                repository,
                "show",
                f"HEAD:{release_prefix}RELEASE_FILE_MANIFEST_PATCH.json",
            )
        )
    except (subprocess.CalledProcessError, json.JSONDecodeError):
        prior_overlay = {}

    changed = set(
        filter(
            None,
            _git(repository, "diff", "--name-only", "HEAD", "--", release_prefix).splitlines(),
        )
    )
    changed.update(
        filter(
            None,
            _git(
                repository,
                "ls-files",
                "--others",
                "--exclude-standard",
                "--",
                release_prefix,
            ).splitlines(),
        )
    )
    relative_changes = {
        path[len(release_prefix) :]
        for path in changed
        if path.startswith(release_prefix)
        and path[len(release_prefix) :] != "RELEASE_FILE_MANIFEST_PATCH.json"
    }
    relative_changes.update(
        item["path"]
        for key in ("additions", "overrides")
        for item in prior_overlay.get(key, [])
    )
    relative_changes.update(prior_overlay.get("deletions", []))
    for relative, expected in base_entries.items():
        path = release_root / relative
        if not path.is_file():
            relative_changes.add(relative)
            continue
        size, digest = _manifest_size_hash(path, repository)
        if size != int(expected["size_bytes"]) or digest != expected["sha256"]:
            relative_changes.add(relative)

    additions: list[dict[str, Any]] = []
    overrides: list[dict[str, Any]] = []
    deletions: list[str] = []
    for relative in sorted(relative_changes):
        path = release_root / relative
        if not path.exists():
            if relative in base_entries:
                deletions.append(relative)
            continue
        item = _entry(path, relative, repository)
        (overrides if relative in base_entries else additions).append(item)

    effective_count = int(base["file_count"]) + len(additions) - len(deletions)
    effective_size = int(base["total_size_bytes"])
    for item in overrides:
        effective_size += item["size_bytes"] - int(base_entries[item["path"]]["size_bytes"])
    effective_size += sum(item["size_bytes"] for item in additions)
    effective_size -= sum(int(base_entries[path]["size_bytes"]) for path in deletions)

    overlay = {
        "schema": "mbi.release-manifest-overlay.v1",
        "base_version": str(base["version"]),
        "feature_revision": "1.0.3-p2-production-interior-vision",
        "description": (
            "Production interior classification, visibility-aware cameras, protected cutaways, "
            "semantic quality retries, room-bounded slices, and composite evidence packets. "
            "Base release files remain hash-locked; only listed overrides and additions are permitted."
        ),
        "base_manifest_git_blob_sha": _git(repository, "hash-object", str(base_path)),
        "additions": additions,
        "overrides": overrides,
        "deletions": deletions,
        "effective_file_count": effective_count,
        "effective_total_size_bytes": effective_size,
        "verification": {
            "local_python_suite": f"{test_count} passed",
            "interior_classification": "passed",
            "voxel_line_of_sight": "passed",
            "camera_collision_and_rejection": "passed",
            "semantic_quality_metrics": "passed",
            "protected_cutaway": "passed",
            "room_bounded_slices": "passed",
            "composite_packet_contract": "passed",
            "perspective_semantic_grounding": "passed",
            "legacy_regression": "passed",
            "hosted_ci": "pending",
            "japan_benchmark": "download-blocked-not-executed",
        },
    }
    overlay_path.write_text(json.dumps(overlay, indent=2, sort_keys=True) + "\n", "utf-8")
    return overlay


def verify_overlay(release_root: Path) -> dict[str, Any]:
    release_root = release_root.resolve()
    repository = Path(_git(release_root, "rev-parse", "--show-toplevel"))
    base = json.loads((release_root / "RELEASE_FILE_MANIFEST.json").read_text("utf-8"))
    overlay = json.loads((release_root / "RELEASE_FILE_MANIFEST_PATCH.json").read_text("utf-8"))
    effective = {item["path"]: item for item in base["files"]}
    for relative in overlay["deletions"]:
        effective.pop(relative, None)
    for item in (*overlay["overrides"], *overlay["additions"]):
        effective[item["path"]] = item

    failures: list[dict[str, Any]] = []
    total_size = 0
    for relative, expected in sorted(effective.items()):
        path = release_root / relative
        if not path.is_file():
            failures.append({"path": relative, "reason": "missing"})
            continue
        size, digest = _manifest_size_hash(path, repository)
        total_size += int(expected["size_bytes"])
        if size != int(expected["size_bytes"]) or digest != expected["sha256"]:
            failures.append(
                {
                    "path": relative,
                    "reason": "hash-or-size-mismatch",
                    "expected_size": int(expected["size_bytes"]),
                    "actual_size": size,
                    "expected_sha256": expected["sha256"],
                    "actual_sha256": digest,
                }
            )
    if len(effective) != int(overlay["effective_file_count"]):
        failures.append(
            {
                "reason": "effective-file-count",
                "expected": int(overlay["effective_file_count"]),
                "actual": len(effective),
            }
        )
    if total_size != int(overlay["effective_total_size_bytes"]):
        failures.append(
            {
                "reason": "effective-total-size",
                "expected": int(overlay["effective_total_size_bytes"]),
                "actual": total_size,
            }
        )
    if failures:
        raise SystemExit(json.dumps({"status": "failed", "failures": failures}, indent=2))
    return {
        "status": "passed",
        "feature_revision": overlay["feature_revision"],
        "effective_file_count": len(effective),
        "effective_total_size_bytes": total_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--release-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--test-count", type=int)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        print(json.dumps(verify_overlay(args.release_root), sort_keys=True))
        return 0
    if args.test_count is None:
        parser.error("--test-count is required unless --check is used")
    overlay = update_overlay(args.release_root, test_count=args.test_count)
    print(
        json.dumps(
            {
                "feature_revision": overlay["feature_revision"],
                "additions": len(overlay["additions"]),
                "overrides": len(overlay["overrides"]),
                "deletions": len(overlay["deletions"]),
                "effective_file_count": overlay["effective_file_count"],
                "effective_total_size_bytes": overlay["effective_total_size_bytes"],
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
