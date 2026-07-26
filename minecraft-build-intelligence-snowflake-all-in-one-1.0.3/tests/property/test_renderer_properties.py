from __future__ import annotations

from pathlib import Path

import pytest

from app.render import SoftwareRenderer, pixel_to_block
from mbi.importer import import_build


def _assert_layer_mapping(pixels_per_block: int, reference_schem: Path, tmp_path: Path) -> None:
    document = import_build(reference_schem.read_bytes(), reference_schem.name)
    result = SoftwareRenderer(document).render_slice(
        tmp_path / str(pixels_per_block),
        axis="y",
        minimum=3,
        pixels_per_block=pixels_per_block,
        mode="flat",
    )
    hit = pixel_to_block(result.manifest_path, pixels_per_block // 2, pixels_per_block // 2)
    assert hit is not None
    assert hit["coordinate"] == [-2, 3, 5]


try:
    from hypothesis import given, settings, strategies as st
except ModuleNotFoundError:
    @pytest.mark.parametrize("pixels_per_block", range(1, 17))
    def test_layer_pixel_maps_preserve_y(
        pixels_per_block: int,
        reference_schem: Path,
        tmp_path: Path,
    ) -> None:
        _assert_layer_mapping(pixels_per_block, reference_schem, tmp_path)
else:
    @given(st.integers(min_value=1, max_value=16))
    @settings(max_examples=24, deadline=None)
    def test_layer_pixel_maps_preserve_y(
        pixels_per_block: int,
        reference_schem: Path,
        tmp_path: Path,
    ) -> None:
        _assert_layer_mapping(pixels_per_block, reference_schem, tmp_path)
