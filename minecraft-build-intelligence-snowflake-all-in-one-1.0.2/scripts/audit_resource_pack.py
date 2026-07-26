from __future__ import annotations

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path


def resource(path: str, fallback: str = "minecraft") -> tuple[str, str]:
    if ":" in path:
        return tuple(path.split(":", 1))  # type: ignore[return-value]
    return fallback, path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = args.root.resolve()
    manifest = json.loads((root / "manifest.json").read_text("utf-8"))
    failures = []
    counts = Counter()
    models: dict[str, dict] = {}
    for relative, expected_hash in manifest["files"].items():
        path = root / relative
        if not path.is_file(): failures.append({"code": "MISSING_FILE", "path": relative}); continue
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected_hash: failures.append({"code": "HASH_MISMATCH", "path": relative})
        counts[path.suffix] += 1
        if path.suffix == ".json":
            try: payload = json.loads(path.read_text("utf-8"))
            except Exception as exc: failures.append({"code": "JSON_INVALID", "path": relative, "error": str(exc)}); continue
            if "/models/block/" in relative:
                namespace = relative.split("/", 1)[0]
                model_path = relative.split("/models/", 1)[1][:-5]
                models[f"{namespace}:{model_path}"] = payload
    for name, model in models.items():
        seen = {name}; current_name = name; current = model
        for _ in range(128):
            parent = current.get("parent")
            if not isinstance(parent, str) or parent.startswith("builtin/"): break
            namespace, path = resource(parent, current_name.split(":", 1)[0])
            if not path.startswith("block/"): path = "block/" + path
            key = f"{namespace}:{path}"
            if key in seen: failures.append({"code": "MODEL_PARENT_CYCLE", "model": name, "at": key}); break
            seen.add(key)
            current = models.get(key)
            if current is None: failures.append({"code": "MODEL_PARENT_MISSING", "model": name, "parent": key}); break
            current_name = key
        else: failures.append({"code": "MODEL_PARENT_DEPTH", "model": name})
    report = {"packHash": manifest["pack_hash"], "fileCount": manifest["file_count"], "counts": dict(counts), "modelCount": len(models), "failureCount": len(failures), "failures": failures[:1000]}
    text = json.dumps(report, indent=2)
    if args.output: args.output.parent.mkdir(parents=True, exist_ok=True); args.output.write_text(text, "utf-8")
    print(text)
    if any(item["code"] in {"MISSING_FILE", "HASH_MISMATCH", "JSON_INVALID", "MODEL_PARENT_CYCLE", "MODEL_PARENT_DEPTH"} for item in failures): raise SystemExit(1)


if __name__ == "__main__": main()
