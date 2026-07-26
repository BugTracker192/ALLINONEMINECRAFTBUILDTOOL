#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "var/reports/source-security-audit.json"
EXCLUDED_DIRS = {".git", ".pytest_cache", "node_modules", "dist", "build", "__pycache__", "var"}
TEXT_SUFFIXES = {".py", ".ts", ".tsx", ".js", ".mjs", ".json", ".yaml", ".yml", ".toml", ".md", ".txt", ".html", ".css", ".sh", ".env"}
SECRET_PATTERNS = {
    "private_key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "openai_key": re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    "github_token": re.compile(r"\bgh[pousr]_[A-Za-z0-9]{30,}\b"),
    "aws_access_key": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
}
DANGEROUS_PATTERNS = {
    "pickle_deserialization": re.compile(r"\bpickle\.(?:loads?|Unpickler)\b"),
    "python_eval": re.compile(r"(?<![A-Za-z0-9_])eval\s*\("),
    "python_exec": re.compile(r"(?<![A-Za-z0-9_])exec\s*\("),
    "shell_true": re.compile(r"shell\s*=\s*True"),
    "unsafe_yaml": re.compile(r"yaml\.load\s*\([^\n]*(?!Loader\s*=)"),
}
BINARY_DENY = {".zip", ".jar", ".exe", ".dll", ".so", ".dylib", ".class"}


def files() -> list[Path]:
    output = []
    for path in ROOT.rglob("*"):
        if not path.is_file() or any(part in EXCLUDED_DIRS for part in path.parts):
            continue
        output.append(path)
    return sorted(output)


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    failures: list[dict[str, object]] = []
    warnings: list[dict[str, object]] = []
    scanned = 0
    for path in files():
        rel = path.relative_to(ROOT).as_posix()
        stat = path.stat()
        if stat.st_mode & 0o002:
            failures.append({"code": "WORLD_WRITABLE", "path": rel})
        if path.is_symlink():
            failures.append({"code": "SYMLINK_IN_SOURCE", "path": rel})
        if path.suffix.lower() in BINARY_DENY:
            failures.append({"code": "BINARY_ARTIFACT", "path": rel})
        if stat.st_size > 5 * 1024 * 1024:
            failures.append({"code": "OVERSIZED_SOURCE_FILE", "path": rel, "size": stat.st_size})
        if path.suffix.lower() not in TEXT_SUFFIXES and path.name not in {"Dockerfile", "Makefile", ".gitignore", ".npmrc"}:
            continue
        scanned += 1
        try:
            text = path.read_text("utf-8")
        except UnicodeDecodeError:
            warnings.append({"code": "NON_UTF8_TEXT", "path": rel})
            continue
        for name, pattern in SECRET_PATTERNS.items():
            if pattern.search(text):
                failures.append({"code": "SECRET_PATTERN", "kind": name, "path": rel})
        if path.suffix == ".py" and "/tests/" not in f"/{rel}":
            for name, pattern in DANGEROUS_PATTERNS.items():
                if pattern.search(text):
                    failures.append({"code": "DANGEROUS_PYTHON", "kind": name, "path": rel})
        if "TODO" in text or "FIXME" in text:
            warnings.append({"code": "UNRESOLVED_MARKER", "path": rel})

    for dockerfile in sorted((ROOT / "infrastructure/docker").glob("*.Dockerfile")):
        text = dockerfile.read_text("utf-8")
        if not re.search(r"^USER\s+[^\s]+", text, re.MULTILINE):
            failures.append({"code": "DOCKERFILE_ROOT_USER", "path": dockerfile.relative_to(ROOT).as_posix()})

    report = {
        "schemaVersion": 1,
        "passed": not failures,
        "filesScanned": scanned,
        "failures": failures,
        "warnings": warnings,
    }
    output = args.output or REPORT
    if not output.is_absolute():
        output = ROOT / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
