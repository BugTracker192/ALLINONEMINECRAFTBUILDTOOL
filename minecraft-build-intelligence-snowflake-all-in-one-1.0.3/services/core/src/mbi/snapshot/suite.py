from __future__ import annotations

import gzip
import hashlib
import io
import json
import math
import struct
from dataclasses import asdict, dataclass
from typing import Literal

from PIL import Image

from ..canonical import BuildDocument, IntBoundingBox, IntVector3
from .raster import palette_color

Direction = Literal["top", "bottom", "north", "south", "east", "west", "isometric_ne", "isometric_nw", "isometric_se", "isometric_sw"]


@dataclass(frozen=True, slots=True)
class SnapshotManifest:
    snapshot_id: str
    build_version_hash: str
    type: str
    direction: Direction
    resolution: tuple[int, int]
    coordinate_space: str
    visible_bounds: dict[str, tuple[int, int, int]]
    pixels_per_block: int
    camera_position: tuple[float, float, float]
    camera_target: tuple[float, float, float]
    view_matrix: tuple[float, ...]
    projection_matrix: tuple[float, ...]
    lighting_preset: str
    background: str
    hidden_palette_ids: tuple[int, ...]
    renderer_version: str
    content_hash: str
    map_encodings: dict[str, str]
    limitations: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SnapshotBundle:
    color_png: bytes
    palette_png: bytes
    depth_png: bytes
    normal_png: bytes
    coordinate_map_gzip: bytes
    manifest: SnapshotManifest

    def manifest_json(self) -> bytes:
        return json.dumps(asdict(self.manifest), sort_keys=True, separators=(",", ":")).encode("utf-8")


_FACE_NORMALS: dict[str, tuple[int, int, int]] = {
    "top": (0, 1, 0),
    "bottom": (0, -1, 0),
    "north": (0, 0, -1),
    "south": (0, 0, 1),
    "east": (1, 0, 0),
    "west": (-1, 0, 0),
}


def _identity() -> tuple[float, ...]:
    return (1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0, 0.0, 0.0, 0.0, 0.0, 1.0)


def _camera(bounds: IntBoundingBox, direction: Direction) -> tuple[tuple[float, float, float], tuple[float, float, float]]:
    center = (
        (bounds.min.x + bounds.max.x + 1) / 2,
        (bounds.min.y + bounds.max.y + 1) / 2,
        (bounds.min.z + bounds.max.z + 1) / 2,
    )
    radius = max(bounds.dimensions.as_tuple()) * 2.0 + 2.0
    vectors: dict[Direction, tuple[float, float, float]] = {
        "top": (0, radius, 0), "bottom": (0, -radius, 0),
        "north": (0, 0, -radius), "south": (0, 0, radius),
        "east": (radius, 0, 0), "west": (-radius, 0, 0),
        "isometric_ne": (radius, radius, -radius), "isometric_nw": (-radius, radius, -radius),
        "isometric_se": (radius, radius, radius), "isometric_sw": (-radius, radius, radius),
    }
    vector = vectors[direction]
    return (center[0] + vector[0], center[1] + vector[1], center[2] + vector[2]), center


def _palette_rgb(pid: int) -> tuple[int, int, int, int]:
    # Lossless 24-bit integer encoding; alpha marks occupancy.
    if not 0 <= pid <= 0xFFFFFF:
        raise ValueError("palette id exceeds 24-bit semantic map capacity")
    return ((pid >> 16) & 0xFF, (pid >> 8) & 0xFF, pid & 0xFF, 255)


def decode_palette_rgb(pixel: tuple[int, int, int] | tuple[int, int, int, int]) -> int:
    return (int(pixel[0]) << 16) | (int(pixel[1]) << 8) | int(pixel[2])


def _normal_rgb(normal: tuple[int, int, int]) -> tuple[int, int, int, int]:
    return tuple(int(round((axis * 0.5 + 0.5) * 255)) for axis in normal) + (255,)  # type: ignore[return-value]


def _png(image: Image.Image) -> bytes:
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=False, compress_level=9)
    return out.getvalue()


def _axis_projection(document: BuildDocument, direction: Direction) -> tuple[int, int, list[tuple[int, IntVector3, int] | None], int]:
    b = document.bounds
    if direction in {"top", "bottom"}:
        width, height = b.dimensions.x, b.dimensions.z
        cells: list[tuple[int, IntVector3, int] | None] = []
        ys = range(b.max.y, b.min.y - 1, -1) if direction == "top" else range(b.min.y, b.max.y + 1)
        for z in range(b.min.z, b.max.z + 1):
            for x in range(b.min.x, b.max.x + 1):
                hit = next(((document.blocks[IntVector3(x, y, z)], IntVector3(x, y, z), abs(y - (b.max.y if direction == "top" else b.min.y))) for y in ys if IntVector3(x, y, z) in document.blocks), None)
                cells.append(hit)
        return width, height, cells, b.dimensions.y
    if direction in {"north", "south"}:
        width, height = b.dimensions.x, b.dimensions.y
        cells = []
        zs = range(b.min.z, b.max.z + 1) if direction == "north" else range(b.max.z, b.min.z - 1, -1)
        for y in range(b.max.y, b.min.y - 1, -1):
            for x in range(b.min.x, b.max.x + 1):
                anchor = b.min.z if direction == "north" else b.max.z
                hit = next(((document.blocks[IntVector3(x, y, z)], IntVector3(x, y, z), abs(z - anchor)) for z in zs if IntVector3(x, y, z) in document.blocks), None)
                cells.append(hit)
        return width, height, cells, b.dimensions.z
    if direction in {"west", "east"}:
        width, height = b.dimensions.z, b.dimensions.y
        cells = []
        xs = range(b.min.x, b.max.x + 1) if direction == "west" else range(b.max.x, b.min.x - 1, -1)
        for y in range(b.max.y, b.min.y - 1, -1):
            for z in range(b.min.z, b.max.z + 1):
                anchor = b.min.x if direction == "west" else b.max.x
                hit = next(((document.blocks[IntVector3(x, y, z)], IntVector3(x, y, z), abs(x - anchor)) for x in xs if IntVector3(x, y, z) in document.blocks), None)
                cells.append(hit)
        return width, height, cells, b.dimensions.x
    raise ValueError("axis projection requires an axis-aligned direction")


def _isometric_projection(document: BuildDocument, direction: Direction) -> tuple[int, int, list[tuple[int, IntVector3, int] | None], int]:
    # Deterministic semantic axonometric projection. It intentionally avoids GPU-dependent raster differences.
    b = document.bounds
    sx = -1 if direction in {"isometric_nw", "isometric_sw"} else 1
    sz = -1 if direction in {"isometric_ne", "isometric_nw"} else 1
    projected: dict[tuple[int, int], tuple[float, int, IntVector3]] = {}
    raw_coords: list[tuple[int, int]] = []
    for position, pid in sorted(document.blocks.items(), key=lambda item: item[0].as_tuple()):
        lx, ly, lz = position.x - b.min.x, position.y - b.min.y, position.z - b.min.z
        u = sx * lx - sz * lz
        v = sx * lx + sz * lz - 2 * ly
        raw_coords.append((u, v))
        depth = sx * lx + sz * lz + ly * 0.01
        current = projected.get((u, v))
        if current is None or depth > current[0]:
            projected[(u, v)] = (depth, pid, position)
    if not raw_coords:
        return 1, 1, [None], 1
    min_u, max_u = min(x for x, _ in raw_coords), max(x for x, _ in raw_coords)
    min_v, max_v = min(y for _, y in raw_coords), max(y for _, y in raw_coords)
    width, height = max_u - min_u + 1, max_v - min_v + 1
    cells: list[tuple[int, IntVector3, int] | None] = [None] * (width * height)
    depth_values = [value[0] for value in projected.values()]
    min_depth = min(depth_values, default=0.0)
    for (u, v), (depth, pid, position) in projected.items():
        index = (v - min_v) * width + (u - min_u)
        cells[index] = (pid, position, int(round(depth - min_depth)))
    return width, height, cells, max(1, int(math.ceil(max(depth_values, default=1.0) - min_depth + 1)))


def render_global_snapshot(
    document: BuildDocument,
    direction: Direction,
    *,
    pixels_per_block: int = 4,
    hidden_palette_ids: frozenset[int] = frozenset(),
    renderer_version: str = "cpu-semantic-v2",
) -> SnapshotBundle:
    if pixels_per_block < 1 or pixels_per_block > 64:
        raise ValueError("pixels_per_block must be between 1 and 64")
    if direction.startswith("isometric_"):
        width, height, cells, max_depth = _isometric_projection(document, direction)
        normal = (1, 1, 1)
        limitations = ("CPU isometric output is a semantic axonometric map, not a textured perspective render.",)
    else:
        width, height, cells, max_depth = _axis_projection(document, direction)
        normal = _FACE_NORMALS[direction]
        limitations = ()

    size = (width * pixels_per_block, height * pixels_per_block)
    color = Image.new("RGBA", size, (0, 0, 0, 0))
    palette = Image.new("RGBA", size, (0, 0, 0, 0))
    depth = Image.new("I;16", size, 65535)
    normals = Image.new("RGBA", size, (0, 0, 0, 0))
    coordinate_records = bytearray()
    coordinate_records.extend(b"MBICMAP1")
    coordinate_records.extend(struct.pack(">IIII", width, height, pixels_per_block, len(cells)))

    cpx, ppx, dpx, npx = color.load(), palette.load(), depth.load(), normals.load()
    for index, cell in enumerate(cells):
        if cell is None or cell[0] in hidden_palette_ids:
            coordinate_records.extend(struct.pack(">iiiI", -2147483648, -2147483648, -2147483648, 0xFFFFFFFF))
            continue
        pid, position, depth_blocks = cell
        coordinate_records.extend(struct.pack(">iiiI", position.x, position.y, position.z, pid))
        x, y = index % width, index // width
        semantic_color = palette_color(pid)
        palette_value = _palette_rgb(pid)
        depth_value = min(65534, int(round(depth_blocks / max(1, max_depth - 1) * 65534)))
        normal_value = _normal_rgb(normal)
        for py in range(y * pixels_per_block, (y + 1) * pixels_per_block):
            for px in range(x * pixels_per_block, (x + 1) * pixels_per_block):
                cpx[px, py] = semantic_color
                ppx[px, py] = palette_value
                dpx[px, py] = depth_value
                npx[px, py] = normal_value

    color_bytes, palette_bytes, depth_bytes, normal_bytes = map(_png, (color, palette, depth, normals))
    coordinate_bytes = gzip.compress(bytes(coordinate_records), compresslevel=9, mtime=0)
    aggregate = hashlib.sha256(color_bytes + palette_bytes + depth_bytes + normal_bytes + coordinate_bytes).hexdigest()
    camera_position, camera_target = _camera(document.bounds, direction)
    manifest = SnapshotManifest(
        snapshot_id="snap_" + aggregate[:20],
        build_version_hash=document.content_hash,
        type="orthographic" if not direction.startswith("isometric") else "isometric_semantic",
        direction=direction,
        resolution=size,
        coordinate_space="document",
        visible_bounds={"min": document.bounds.min.as_tuple(), "max": document.bounds.max.as_tuple()},
        pixels_per_block=pixels_per_block,
        camera_position=camera_position,
        camera_target=camera_target,
        view_matrix=_identity(),
        projection_matrix=_identity(),
        lighting_preset="analysis_neutral_v2",
        background="transparent",
        hidden_palette_ids=tuple(sorted(hidden_palette_ids)),
        renderer_version=renderer_version,
        content_hash=aggregate,
        map_encodings={
            "palette": "24-bit RGB integer; alpha=0 means no sample",
            "depth": "16-bit PNG; 0 is nearest, 65534 farthest, 65535 empty",
            "normal": "RGB maps [-1,+1] to [0,255]",
            "coordinate": "gzip MBICMAP1 records: big-endian int32 x,y,z + uint32 palette id per logical pixel",
        },
        limitations=limitations,
    )
    return SnapshotBundle(color_bytes, palette_bytes, depth_bytes, normal_bytes, coordinate_bytes, manifest)


def render_snapshot_suite(document: BuildDocument, *, pixels_per_block: int = 4) -> dict[Direction, SnapshotBundle]:
    directions: tuple[Direction, ...] = (
        "north", "south", "east", "west", "top", "bottom",
        "isometric_ne", "isometric_nw", "isometric_se", "isometric_sw",
    )
    return {direction: render_global_snapshot(document, direction, pixels_per_block=pixels_per_block) for direction in directions}
