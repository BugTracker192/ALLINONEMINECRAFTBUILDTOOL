from __future__ import annotations

from mbi.canonical import IntVector3
from mbi.snapshot import block_to_pixel, pixel_to_block, render_palette_layer


def test_layer_pixel_mapping(sample_document) -> None:
    image, manifest = render_palette_layer(sample_document, 0, pixels_per_block=8)
    assert image.startswith(b"\x89PNG")
    position = IntVector3(1, 0, -1)
    pixel = block_to_pixel(manifest, position)
    assert pixel_to_block(manifest, *pixel) == position
