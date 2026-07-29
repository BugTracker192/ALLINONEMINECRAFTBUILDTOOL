from __future__ import annotations

import hashlib
from typing import Any


def nonsecurity_blake2s(data: bytes = b"", **kwargs: Any) -> Any:
    """Construct BLAKE2s for deterministic display/cache data on FIPS hosts."""
    return hashlib.blake2s(data, usedforsecurity=False, **kwargs)
