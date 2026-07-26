from __future__ import annotations

import hashlib
import json
import threading
from pathlib import Path
from typing import Any, Callable, TypeVar

from fastapi import HTTPException

T = TypeVar("T")


class IdempotencyStore:
    """Small deterministic disk-backed idempotency registry.

    Keys are scoped per operation. A repeated key with an identical request
    fingerprint returns the original JSON result; reusing a key for a different
    request is rejected. Writes are atomic and safe across API process restarts.
    """

    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @staticmethod
    def _fingerprint(payload: Any) -> str:
        encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def _path(self, scope: str, key: str) -> Path:
        digest = hashlib.sha256(f"{scope}\0{key}".encode("utf-8")).hexdigest()
        return self.root / f"{digest}.json"

    def execute(self, *, scope: str, key: str | None, payload: Any, producer: Callable[[], T]) -> tuple[T, bool]:
        if not key:
            return producer(), False
        if len(key) > 255 or any(ord(char) < 32 for char in key):
            raise HTTPException(422, detail={"code": "IDEMPOTENCY_KEY_INVALID"})
        fingerprint = self._fingerprint(payload)
        path = self._path(scope, key)
        with self._lock:
            if path.is_file():
                record = json.loads(path.read_text("utf-8"))
                if record.get("fingerprint") != fingerprint:
                    raise HTTPException(
                        409,
                        detail={
                            "code": "IDEMPOTENCY_KEY_REUSED",
                            "message": "The idempotency key was already used with a different request.",
                        },
                    )
                return record["response"], True  # type: ignore[return-value]
            result = producer()
            temporary = path.with_suffix(".writing")
            temporary.write_text(
                json.dumps({"scope": scope, "fingerprint": fingerprint, "response": result}, sort_keys=True, separators=(",", ":"), default=str),
                "utf-8",
            )
            temporary.replace(path)
            return result, False
