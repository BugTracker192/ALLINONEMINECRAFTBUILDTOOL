from __future__ import annotations

import json
import struct
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from app.storage import atomic_write_bytes, atomic_write_json


NO_COORDINATE = np.iinfo(np.int32).min
NO_PALETTE = np.iinfo(np.uint32).max
NO_REGION = np.iinfo(np.uint16).max


@dataclass(slots=True)
class SemanticBuffers:
    palette: np.ndarray
    coordinates: np.ndarray
    depth: np.ndarray
    normals: np.ndarray
    regions: np.ndarray
    occupancy: np.ndarray
    changed: np.ndarray
    issues: np.ndarray

    @classmethod
    def create(cls, width: int, height: int) -> "SemanticBuffers":
        return cls(
            np.full((height, width), NO_PALETTE, dtype="<u4"),
            np.full((height, width, 3), NO_COORDINATE, dtype="<i4"),
            np.full((height, width), np.inf, dtype="<f4"),
            np.zeros((height, width, 3), dtype="i1"),
            np.full((height, width), NO_REGION, dtype="<u2"),
            np.zeros((height, width), dtype="u1"),
            np.zeros((height, width), dtype="u1"),
            np.zeros((height, width), dtype="u1"),
        )

    def write(self, root: Path, snapshot_id: str) -> dict[str, str]:
        root.mkdir(parents=True, exist_ok=True)
        arrays = {
            "palette": self.palette,
            "coordinate": self.coordinates,
            "depth": self.depth,
            "normal": self.normals,
            "region": self.regions,
            "occupancy": self.occupancy,
            "changed": self.changed,
            "issue": self.issues,
        }
        result: dict[str, str] = {}
        metadata: dict[str, Any] = {"schema": "mbi.semantic-maps.v1", "arrays": {}}
        for name, array in arrays.items():
            filename = f"{snapshot_id}.{name}.bin"
            atomic_write_bytes(root / filename, array.tobytes(order="C"))
            result[name] = filename
            metadata["arrays"][name] = {
                "path": filename,
                "dtype": array.dtype.str,
                "shape": list(array.shape),
                "order": "C",
                "endianness": "little",
            }
        rgba = np.zeros((*self.palette.shape, 4), dtype=np.uint8)
        occupied = self.palette != NO_PALETTE
        rgba[..., 0] = ((self.palette >> 16) & 0xFF).astype(np.uint8)
        rgba[..., 1] = ((self.palette >> 8) & 0xFF).astype(np.uint8)
        rgba[..., 2] = (self.palette & 0xFF).astype(np.uint8)
        rgba[..., 3] = occupied.astype(np.uint8) * 255
        palette_png = f"{snapshot_id}.palette.png"
        Image.fromarray(rgba, "RGBA").save(root / palette_png, format="PNG", compress_level=9, optimize=False)
        result["palette_png"] = palette_png
        atomic_write_json(root / f"{snapshot_id}.metadata.json", metadata)
        result["metadata"] = f"{snapshot_id}.metadata.json"
        return result


def load_map(metadata_path: Path, name: str) -> np.ndarray:
    metadata = json.loads(metadata_path.read_text("utf-8"))
    item = metadata["arrays"][name]
    raw = (metadata_path.parent / item["path"]).read_bytes()
    return np.frombuffer(raw, dtype=np.dtype(item["dtype"])).reshape(item["shape"])
