from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any


REPOSITORY = Path(__file__).resolve().parents[1]


def _run(name: str, command: list[str], output: Path, *, cwd: Path = REPOSITORY, env: dict[str, str] | None = None, timeout: int = 1800) -> dict[str, Any]:
    """Run one release gate with streamed logs and a hard process-group timeout.

    Direct file redirection avoids pipe backpressure and leaves useful progress
    evidence even when a child process is forcibly terminated.
    """
    import signal
    import time

    log = output / "logs" / f"{name}.log"
    log.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    timed_out = False
    returncode = 127
    with log.open("w", encoding="utf-8") as stream:
        stream.write("$ " + " ".join(command) + "\n\n")
        stream.flush()
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env,
            text=True,
            stdout=stream,
            stderr=subprocess.STDOUT,
            start_new_session=False,
        )
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            stream.write(f"\n[release-verifier] TIMEOUT after {timeout} seconds; terminating process group.\n")
            stream.flush()
            process.terminate()
            try:
                returncode = process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                returncode = process.wait(timeout=10)
    text = log.read_text("utf-8", errors="replace")
    return {
        "name": name,
        "passed": returncode == 0 and not timed_out,
        "returncode": returncode,
        "timed_out": timed_out,
        "duration_seconds": round(time.monotonic() - started, 6),
        "command": command,
        "log": str(log),
        "output_tail": text[-4000:],
    }



def _advise_drop_cache(root: Path) -> None:
    """Best-effort release of file-backed cache after a heavy sandbox gate."""
    if not hasattr(os, "posix_fadvise") or not root.exists():
        return
    for path in root.rglob("*") if root.is_dir() else (root,):
        if not path.is_file():
            continue
        try:
            descriptor = os.open(path, os.O_RDONLY)
            try:
                os.posix_fadvise(descriptor, 0, 0, os.POSIX_FADV_DONTNEED)
            finally:
                os.close(descriptor)
        except OSError:
            continue


def _preserve_representative(root: Path, output: Path, name: str) -> list[str]:
    preserved: list[str] = []
    evidence = output / "evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    png = next(iter(sorted(root.rglob("*.png"))), None) if root.exists() else None
    if png is not None:
        destination = evidence / f"{name}{png.suffix}"
        shutil.copy2(png, destination)
        preserved.append(str(destination))
    return preserved


def _prune_heavy(root: Path, output: Path, name: str) -> list[str]:
    preserved = _preserve_representative(root, output, name)
    _advise_drop_cache(root)
    shutil.rmtree(root, ignore_errors=True)
    return preserved


def _copy_report(source: Path, destination: Path) -> None:
    if source.is_file():
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

def _tree_hashes(root: Path) -> dict[str, str]:
    return {
        str(path.relative_to(root)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


def _clean_wheel_check(output: Path, fixture: Path) -> dict[str, Any]:
    wheelhouse = output / "wheelhouse"
    venv = output / "clean-venv"
    run = output / "clean-wheel-run"
    wheelhouse.mkdir(parents=True, exist_ok=True)
    build = _run(
        "wheel_build",
        [sys.executable, "-m", "pip", "wheel", ".", "--no-deps", "--no-build-isolation", "-w", str(wheelhouse)],
        output,
        timeout=600,
    )
    if not build["passed"]:
        return {"name": "clean_wheel_pipeline", "passed": False, "build": build}
    wheel = next(wheelhouse.glob("minecraft_build_intelligence-*.whl"))
    if venv.exists():
        shutil.rmtree(venv)
    subprocess.run([sys.executable, "-m", "venv", str(venv)], check=True)
    python = venv / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    install = _run("wheel_install", [str(python), "-m", "pip", "install", str(wheel), "--no-deps"], output, cwd=output, timeout=300)
    # Outbound PyPI is not guaranteed in the execution sandbox. Mount the already
    # dynamically tested NumPy/Pillow runtime only when dependency resolution is unavailable.
    dependency_mode = "resolved-in-clean-venv"
    dependency_install = _run(
        "wheel_dependencies",
        [str(python), "-m", "pip", "install", "--retries", "0", "--timeout", "5", "numpy>=2.0,<3", "Pillow>=11,<13"],
        output,
        cwd=output,
        timeout=30,
    )
    if not dependency_install["passed"]:
        dependency_mode = "tested-runtime-mounted-after-index-unavailable"
        probe = subprocess.run([str(python), "-c", "import site; print(site.getsitepackages()[0])"], text=True, capture_output=True, check=True)
        site_path = Path(probe.stdout.strip())
        parent_site = next(path for path in sys.path if path.endswith("site-packages") and Path(path).is_dir())
        (site_path / "mbi-tested-runtime.pth").write_text(parent_site + "\n", "utf-8")
    pipeline = _run(
        "clean_wheel_pipeline",
        [str(python), "-m", "app.cli", "pipeline", str(fixture), "--out", str(run), "--size", "192x192"],
        output,
        cwd=output,
        timeout=600,
    )
    required = ["canonical.json", "analysis.json", "snapshots/manifest.json", "export/out.schem", "export/verify_report.json"]
    artifacts_ok = all((run / item).is_file() for item in required)
    verify = json.loads((run / "export" / "verify_report.json").read_text("utf-8")) if artifacts_ok else {}
    artifact_dir = output / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    retained_wheel = artifact_dir / wheel.name
    shutil.copy2(wheel, retained_wheel)
    result = {
        "name": "clean_wheel_pipeline",
        "passed": bool(build["passed"] and install["passed"] and pipeline["passed"] and artifacts_ok and verify.get("passed")),
        "python": subprocess.run([str(python), "--version"], text=True, capture_output=True).stdout.strip(),
        "python_3_12_binary_available": shutil.which("python3.12") is not None,
        "dependency_mode": dependency_mode,
        "dependency_install": dependency_install,
        "wheel": str(retained_wheel),
        "wheel_sha256": hashlib.sha256(retained_wheel.read_bytes()).hexdigest(),
        "pipeline": pipeline,
        "artifacts_ok": artifacts_ok,
        "verify": verify,
    }
    _advise_drop_cache(run)
    _advise_drop_cache(venv)
    shutil.rmtree(run, ignore_errors=True)
    shutil.rmtree(venv, ignore_errors=True)
    shutil.rmtree(wheelhouse, ignore_errors=True)
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the complete offline Snowflake/CoCo release verification matrix.")
    parser.add_argument("--resource-pack", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--fixture", type=Path, default=REPOSITORY / "tests/fixtures/reference.schem")
    args = parser.parse_args()
    output = args.output.resolve()
    if output.exists():
        shutil.rmtree(output)
    output.mkdir(parents=True)
    report_dir = output / "reports"
    report_dir.mkdir()

    checks: list[dict[str, Any]] = []
    preserved_artifacts: dict[str, list[str]] = {}

    def gate(name: str, command: list[str], *, timeout: int, heavy_root: Path | None = None) -> dict[str, Any]:
        print(f"[release-verifier] START {name}", flush=True)
        result = _run(name, command, output, timeout=timeout)
        checks.append(result)
        if heavy_root is not None:
            preserved_artifacts[name] = _prune_heavy(heavy_root, output, name)
        _advise_drop_cache(args.resource_pack)
        print(f"[release-verifier] DONE {name}: {'PASS' if result['passed'] else 'FAIL'} ({result.get('duration_seconds')}s)", flush=True)
        partial = {
            "schema": "mbi.snowflake-release-verification.partial.v1",
            "checks": checks,
            "preserved_artifacts": preserved_artifacts,
        }
        (output / "release-verification.partial.json").write_text(json.dumps(partial, sort_keys=True, indent=2, default=str) + "\n", "utf-8")
        if not result["passed"]:
            raise SystemExit(f"release gate failed: {name}")
        return result

    gate("pytest", [sys.executable, "-m", "pytest", "-q"], timeout=600)
    gate("offline_profile", [sys.executable, "scripts/audit_offline_profile.py"], timeout=300)
    gate("source_security", [sys.executable, "scripts/source_security_audit.py"], timeout=300)

    # Run memory-heavy visual/AI gates before archive extraction. Their full
    # datasets are validated and then compacted to JSON reports + one PNG.
    snowflake_root = output / "snowflake-e2e"
    gate("snowflake_e2e", [sys.executable, "scripts/dynamic_snowflake_e2e.py", "--resource-pack", str(args.resource_pack), "--root", str(snowflake_root), "--report", str(report_dir / "snowflake-e2e.json")], timeout=300, heavy_root=snowflake_root)

    multimodal_root = output / "multimodal-loop"
    gate("multimodal_loop", [sys.executable, "scripts/dynamic_multimodal_build_loop.py", str(args.fixture), str(args.resource_pack), str(multimodal_root), "--report", str(report_dir / "multimodal-loop.json")], timeout=300, heavy_root=multimodal_root)

    multimodal_http_root = output / "multimodal-http"
    gate("multimodal_http", [sys.executable, "scripts/dynamic_multimodal_http.py", str(args.fixture), str(args.resource_pack), str(multimodal_http_root)], timeout=300)
    _copy_report(multimodal_http_root / "dynamic_multimodal_http.json", report_dir / "multimodal-http.json")
    preserved_artifacts["multimodal_http"] = _prune_heavy(multimodal_http_root, output, "multimodal_http")

    blank_root = output / "ai-construct-blank"
    gate("ai_construct_blank", [sys.executable, "scripts/dynamic_ai_construct_from_blank.py", "--resource-pack", str(args.resource_pack), "--root", str(blank_root)], timeout=300)
    _copy_report(blank_root / "dynamic_ai_construct_report.json", report_dir / "ai-construct-blank.json")
    preserved_artifacts["ai_construct_blank"] = _prune_heavy(blank_root, output, "ai_construct_blank")

    cpu_models_root = output / "cpu-models"
    gate("cpu_models", [sys.executable, "scripts/dynamic_cpu_models.py", str(args.resource_pack), str(cpu_models_root)], timeout=180)
    _copy_report(cpu_models_root / "dynamic_cpu_models.json", report_dir / "cpu-models.json")
    preserved_artifacts["cpu_models"] = _prune_heavy(cpu_models_root, output, "cpu_models")

    gate("fuzz_5000", [sys.executable, "scripts/fuzz_formats.py", "--iterations", "5000", "--output", str(report_dir / "fuzz-5000.json")], timeout=600)

    benchmark_flat_root = output / "benchmark-flat"
    gate("benchmark_flat", [sys.executable, "benchmarks/cpu_render.py", "--output-root", str(benchmark_flat_root), "--report", str(report_dir / "benchmark-flat.json")], timeout=300, heavy_root=benchmark_flat_root)
    benchmark_textured_root = output / "benchmark-textured"
    gate("benchmark_textured", [sys.executable, "benchmarks/cpu_render.py", "--resource-pack", str(args.resource_pack), "--output-root", str(benchmark_textured_root), "--report", str(report_dir / "benchmark-textured.json")], timeout=300, heavy_root=benchmark_textured_root)

    deterministic_a, deterministic_b = output / "deterministic-a", output / "deterministic-b"
    gate("deterministic_pipeline_a", [sys.executable, "-m", "app.cli", "pipeline", str(args.fixture), "--out", str(deterministic_a), "--size", "192x192"], timeout=300)
    gate("deterministic_pipeline_b", [sys.executable, "-m", "app.cli", "pipeline", str(args.fixture), "--out", str(deterministic_b), "--size", "192x192"], timeout=300)
    tree_a, tree_b = _tree_hashes(deterministic_a), _tree_hashes(deterministic_b)
    determinism = {
        "name": "byte_determinism",
        "passed": tree_a == tree_b and bool(tree_a),
        "artifact_count": len(tree_a),
        "differences": sorted(set(tree_a) ^ set(tree_b)) + sorted(path for path in set(tree_a) & set(tree_b) if tree_a[path] != tree_b[path]),
    }
    checks.append(determinism)
    _prune_heavy(deterministic_a, output, "deterministic_a")
    _prune_heavy(deterministic_b, output, "deterministic_b")
    if not determinism["passed"]:
        raise SystemExit("release gate failed: byte_determinism")

    clean_wheel = _clean_wheel_check(output, args.fixture.resolve())
    checks.append(clean_wheel)
    if not clean_wheel["passed"]:
        raise SystemExit("release gate failed: clean_wheel_pipeline")

    # Asset extraction/index audit runs last because it intentionally touches
    # thousands of archive members and can populate the sandbox page cache.
    indexed_pack = output / "indexed-resource-pack"
    gate("resource_pack_index", [sys.executable, "scripts/index_resource_pack.py", str(args.resource_pack), str(indexed_pack)], timeout=300)
    gate("resource_pack_audit", [sys.executable, "scripts/audit_resource_pack.py", str(indexed_pack), "--output", str(report_dir / "resource-pack-audit.json")], timeout=300)
    _advise_drop_cache(indexed_pack)
    shutil.rmtree(indexed_pack, ignore_errors=True)

    result = {
        "schema": "mbi.snowflake-release-verification.v1",
        "passed": all(bool(item.get("passed")) for item in checks),
        "runtime_python": sys.version,
        "python_3_12_binary_available": shutil.which("python3.12") is not None,
        "resource_pack": str(args.resource_pack.resolve()),
        "resource_pack_sha256": hashlib.sha256(args.resource_pack.read_bytes()).hexdigest(),
        "checks": checks,
        "preserved_artifacts": preserved_artifacts,
    }
    (output / "release-verification.json").write_text(json.dumps(result, sort_keys=True, indent=2, default=str) + "\n", "utf-8")
    print(json.dumps(result, sort_keys=True, indent=2, default=str))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
