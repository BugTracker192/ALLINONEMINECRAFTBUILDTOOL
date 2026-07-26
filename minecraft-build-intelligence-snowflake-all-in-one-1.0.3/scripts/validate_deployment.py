#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "var/reports/deployment-validation.json"


def load_documents(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as handle:
        return [doc for doc in yaml.safe_load_all(handle) if isinstance(doc, dict)]


def main() -> int:
    files = sorted((ROOT / "infrastructure/kubernetes").glob("*.yaml")) + [ROOT / "docker-compose.yml"]
    failures: list[str] = []
    warnings: list[str] = []
    documents = 0
    workloads = 0
    images: list[str] = []

    for path in files:
        try:
            docs = load_documents(path)
        except Exception as exc:  # pragma: no cover - command-line report path
            failures.append(f"{path.relative_to(ROOT)}: YAML parse failed: {exc}")
            continue
        documents += len(docs)
        for doc in docs:
            kind = str(doc.get("kind", ""))
            if kind not in {"Deployment", "StatefulSet", "DaemonSet", "Job", "CronJob"}:
                continue
            workloads += 1
            template = doc.get("spec", {}).get("template", {})
            pod_spec = template.get("spec", {})
            if pod_spec.get("automountServiceAccountToken") is not False:
                failures.append(f"{path.name}:{doc.get('metadata', {}).get('name')}: service-account token not disabled")
            pod_security = pod_spec.get("securityContext", {})
            if pod_security.get("runAsNonRoot") is not True:
                failures.append(f"{path.name}:{doc.get('metadata', {}).get('name')}: runAsNonRoot missing")
            for container in pod_spec.get("containers", []):
                image = str(container.get("image", ""))
                images.append(image)
                if not image or image.endswith(":latest") or ":" not in image.rsplit("/", 1)[-1]:
                    failures.append(f"{path.name}:{container.get('name')}: unpinned image {image!r}")
                security = container.get("securityContext", {})
                if security.get("allowPrivilegeEscalation") is not False:
                    failures.append(f"{path.name}:{container.get('name')}: privilege escalation not disabled")
                if security.get("readOnlyRootFilesystem") is not True:
                    failures.append(f"{path.name}:{container.get('name')}: read-only root filesystem missing")
                dropped = security.get("capabilities", {}).get("drop", [])
                if "ALL" not in dropped:
                    failures.append(f"{path.name}:{container.get('name')}: Linux capabilities not fully dropped")
                resources = container.get("resources", {})
                if not resources.get("requests") or not resources.get("limits"):
                    failures.append(f"{path.name}:{container.get('name')}: resource requests/limits missing")

    compose = yaml.safe_load((ROOT / "docker-compose.yml").read_text("utf-8"))
    for name, service in compose.get("services", {}).items():
        image = service.get("image")
        if image:
            images.append(str(image))
            if str(image).endswith(":latest"):
                failures.append(f"docker-compose:{name}: unpinned image {image}")
        if name in {"api", "worker", "web", "renderer-service"}:
            if service.get("read_only") is not True:
                failures.append(f"docker-compose:{name}: read_only not enabled")
            if "no-new-privileges:true" not in service.get("security_opt", []):
                failures.append(f"docker-compose:{name}: no-new-privileges missing")

    secret_example = ROOT / "infrastructure/kubernetes/secrets.example.yaml"
    secret_text = secret_example.read_text("utf-8")
    forbidden_realistic_markers = ("sk-", "AKIA", "ghp_", "postgresql://mbi:")
    if any(marker in secret_text for marker in forbidden_realistic_markers):
        failures.append("secrets.example.yaml appears to contain a real credential")
    if "CHANGE_ME" not in secret_text:
        failures.append("secrets.example.yaml does not use explicit placeholders")

    report = {
        "schemaVersion": 1,
        "passed": not failures,
        "yamlFiles": [str(path.relative_to(ROOT)) for path in files],
        "documentsParsed": documents,
        "workloadsValidated": workloads,
        "images": sorted(set(images)),
        "failures": failures,
        "warnings": warnings,
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2, sort_keys=True), "utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
