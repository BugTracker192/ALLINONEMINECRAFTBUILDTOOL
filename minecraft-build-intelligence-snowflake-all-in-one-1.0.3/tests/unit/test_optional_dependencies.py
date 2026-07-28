from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path


def test_offline_import_does_not_require_httpx_or_cryptography() -> None:
    repository = Path(__file__).resolve().parents[2]
    code = r'''
import sys
class BlockOptional:
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'httpx', 'cryptography'}:
            raise ModuleNotFoundError(f'blocked optional dependency: {fullname}', name=fullname.split('.')[0])
        return None
sys.meta_path.insert(0, BlockOptional())
import app.cli
from mbi.ai import BuildToolExecutor
print('offline-import-ok')
'''
    completed = subprocess.run(
        [sys.executable, "-c", code], cwd=repository, text=True, capture_output=True, check=False,
        env={
            **os.environ,
            "PYTHONPATH": os.pathsep.join(
                (str(repository), str(repository / "services/core/src"))
            ),
        },
    )
    assert completed.returncode == 0, completed.stderr
    assert completed.stdout.strip() == "offline-import-ok"
