from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

FORBIDDEN = {
    "OpenGL", "moderngl", "pyrender", "pygame", "playwright", "selenium", "chromium",
    "docker", "redis", "celery", "sqlalchemy", "psycopg", "boto3", "three", "nodejs",
}
OPTIONAL_ALLOWED = {
    "services/core/src/mbi/ai/providers.py": {"httpx"},
    "services/core/src/mbi/ai/key_vault.py": {"cryptography"},
}


def imported_roots(path: Path) -> set[str]:
    tree = ast.parse(path.read_text("utf-8"), filename=str(path), feature_version=(3, 12))
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".", 1)[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".", 1)[0])
    return roots


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    findings = []
    parsed = 0
    for base in (root / "app", root / "services/core/src/mbi"):
        for path in sorted(base.rglob("*.py")):
            relative = path.relative_to(root).as_posix()
            imports = imported_roots(path)
            parsed += 1
            allowed = OPTIONAL_ALLOWED.get(relative, set())
            for name in sorted(imports & FORBIDDEN):
                if name not in allowed:
                    findings.append({"path": relative, "forbidden_import": name})
    code = r'''
import sys
class BlockOptional:
    def find_spec(self, fullname, path=None, target=None):
        root = fullname.split('.')[0]
        if root in {'httpx','cryptography','OpenGL','moderngl','playwright','docker','redis','celery','sqlalchemy','psycopg','boto3'}:
            raise ModuleNotFoundError(f'blocked optional/forbidden dependency: {fullname}', name=root)
        return None
sys.meta_path.insert(0, BlockOptional())
import app.cli
import app.render
from mbi.ai import BuildToolExecutor
print('mandatory-import-closure-ok')
'''
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=root, text=True, capture_output=True, check=False,
        env={"PYTHONPATH": f"{root}:{root / 'services/core/src'}"},
    )
    report = {
        "passed": not findings and completed.returncode == 0,
        "python_files_parsed_as_3_12": parsed,
        "forbidden_import_findings": findings,
        "blocked_optional_import_smoke": {
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        },
        "mandatory_external_dependencies": ["numpy", "Pillow"],
        "optional_dependencies": ["httpx", "cryptography", "pytest", "hypothesis"],
        "requires_gl_context": False,
        "requires_external_executable": False,
    }
    output = args.output or (root / "var/reports/offline-profile-audit.json")
    if not output.is_absolute():
        output = root / output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, sort_keys=True, separators=(",", ":")) + "\n", "utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
