from __future__ import annotations

import hashlib
import io
from dataclasses import asdict, dataclass

from PIL import Image

from ..canonical import BuildDocument, IntVector3


@dataclass(frozen=True, slots=True)
class LayerManifest:
    snapshot_id: str
    build_version_hash: str
    y: int
    resolution: tuple[int, int]
    visible_min: tuple[int, int, int]
    visible_max: tuple[int, int, int]
    pixels_per_block: int
    x_axis: str
    z_axis: str
    content_hash: str


def palette_color(palette_id: int) -> tuple[int, int, int, int]:
    digest = hashlib.blake2s(str(palette_id).encode(), digest_size=3).digest()
    return digest[0], digest[1], digest[2], 255


def render_palette_layer(document: BuildDocument, y: int, *, pixels_per_block: int = 4) -> tuple[bytes, LayerManifest]:
    if not document.bounds.min.y <= y <= document.bounds.max.y:
        raise ValueError("layer is outside build bounds")
    width = document.bounds.dimensions.x
    length = document.bounds.dimensions.z
    image = Image.new("RGBA", (width * pixels_per_block, length * pixels_per_block), (0, 0, 0, 0))
    pixels = image.load()
    for z in range(length):
        for x in range(width):
            position = IntVector3(document.bounds.min.x + x, y, document.bounds.min.z + z)
            palette_id = document.blocks.get(position)
            if palette_id is None:
                continue
            color = palette_color(palette_id)
            for py in range(z * pixels_per_block, (z + 1) * pixels_per_block):
                for px in range(x * pixels_per_block, (x + 1) * pixels_per_block):
                    pixels[px, py] = color
    out = io.BytesIO()
    image.save(out, format="PNG", optimize=False, compress_level=9)
    data = out.getvalue()
    content_hash = hashlib.sha256(data).hexdigest()
    manifest = LayerManifest(
        snapshot_id="snap_" + content_hash[:20],
        build_version_hash=document.content_hash,
        y=y,
        resolution=image.size,
        visible_min=document.bounds.min.as_tuple(),
        visible_max=document.bounds.max.as_tuple(),
        pixels_per_block=pixels_per_block,
        x_axis="left_to_right:+X",
        z_axis="top_to_bottom:+Z",
        content_hash=content_hash,
    )
    return data, manifest


def block_to_pixel(manifest: LayerManifest, position: IntVector3) -> tuple[int, int]:
    x = (position.x - manifest.visible_min[0]) * manifest.pixels_per_block
    y = (position.z - manifest.visible_min[2]) * manifest.pixels_per_block
    return x, y


def pixel_to_block(manifest: LayerManifest, px: int, py: int) -> IntVector3:
    return IntVector3(
        manifest.visible_min[0] + px // manifest.pixels_per_block,
        manifest.y,
        manifest.visible_min[2] + py // manifest.pixels_per_block,
    )
