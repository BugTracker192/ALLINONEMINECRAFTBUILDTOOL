from __future__ import annotations

import os
import shutil
import time
from dataclasses import dataclass, asdict
from pathlib import Path


@dataclass(frozen=True, slots=True)
class RetentionResult:
    scanned: int
    deleted: int
    bytes_reclaimed: int
    errors: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class RetentionManager:
    def __init__(self, root: Path, policies: dict[str, int]) -> None:
        self.root = root.resolve()
        self.policies = {name: max(0, int(days)) for name, days in policies.items()}

    @staticmethod
    def _size(path: Path) -> int:
        if path.is_file():
            return path.stat().st_size
        return sum(item.stat().st_size for item in path.rglob("*") if item.is_file() and not item.is_symlink())

    def run(self, now: float | None = None) -> RetentionResult:
        current = time.time() if now is None else now
        scanned = deleted = reclaimed = 0
        errors: list[str] = []
        for bucket, days in self.policies.items():
            bucket_path = (self.root / bucket).resolve()
            if self.root not in bucket_path.parents or not bucket_path.exists():
                continue
            cutoff = current - days * 86400
            for path in list(bucket_path.iterdir()):
                if path.name == ".gitkeep" or path.is_symlink():
                    continue
                scanned += 1
                try:
                    if path.stat().st_mtime >= cutoff:
                        continue
                    size = self._size(path)
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                    deleted += 1
                    reclaimed += size
                except OSError as exc:
                    errors.append(f"{path.name}: {exc}")
        return RetentionResult(scanned, deleted, reclaimed, tuple(errors))
