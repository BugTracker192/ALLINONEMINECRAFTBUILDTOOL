from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class MBIError(Exception):
    code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    recoverable: bool = False

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class NBTError(MBIError):
    pass


class FormatError(MBIError):
    pass


class PatchError(MBIError):
    pass
