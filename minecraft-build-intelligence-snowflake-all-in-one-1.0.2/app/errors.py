from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class AppError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    exit_code: int = 1

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


EXIT_CODES = {
    "usage": 2,
    "format": 10,
    "nbt": 11,
    "limit": 12,
    "canonical": 20,
    "render": 30,
    "texture": 31,
    "patch": 40,
    "stale": 41,
    "export": 50,
    "verify": 51,
    "provider": 60,
}
