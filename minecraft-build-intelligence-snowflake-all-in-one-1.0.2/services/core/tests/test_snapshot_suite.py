from __future__ import annotations

import gzip
import struct

from PIL import Image
import io

from mbi.snapshot import decode_palette_rgb, render_global_snapshot, render_snapshot_suite


def test_snapshot_suite_is_deterministic_and_semantic(sample_document) -> None:
    first = render_snapshot_suite(sample_document, pixels_per_block=2)
    second = render_snapshot_suite(sample_document, pixels_per_block=2)
    assert set(first) == {"north", "south", "east", "west", "top", "bottom", "isometric_ne", "isometric_nw", "isometric_se", "isometric_sw"}
    for direction in first:
        assert first[direction].manifest.content_hash == second[direction].manifest.content_hash
        assert first[direction].color_png == second[direction].color_png
        assert first[direction].manifest.resolution[0] > 0
        assert first[direction].manifest.resolution[1] > 0

    top = first["top"]
    palette_image = Image.open(io.BytesIO(top.palette_png)).convert("RGBA")
    occupied = [pixel for pixel in palette_image.get_flattened_data() if pixel[3] != 0]
    assert occupied
    assert all(decode_palette_rgb(pixel) in {1, 2, 3} for pixel in occupied)
    raw = gzip.decompress(top.coordinate_map_gzip)
    assert raw.startswith(b"MBICMAP1")
    width, height, ppb, count = struct.unpack(">IIII", raw[8:24])
    assert count == width * height
    assert ppb == 2


def test_hidden_palette_changes_snapshot(sample_document) -> None:
    visible = render_global_snapshot(sample_document, "north", pixels_per_block=1)
    hidden = render_global_snapshot(sample_document, "north", pixels_per_block=1, hidden_palette_ids=frozenset({1}))
    assert visible.manifest.content_hash != hidden.manifest.content_hash
