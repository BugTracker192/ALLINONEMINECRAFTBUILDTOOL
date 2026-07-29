from __future__ import annotations

from app import authoring


def test_anchor_translation_covers_boxes_lines_and_assemblies(
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        authoring,
        "load_anchors",
        lambda _run: {
            "anchors": {
                "east_bay": {
                    "position": [100, 20, -30],
                }
            }
        },
    )
    resolved = authoring.resolve_anchored_operations(
        "unused",
        [
            {
                "type": "fill_box",
                "anchor": "east_bay",
                "anchorOffset": [2, 1, -1],
                "min": [-1, 0, -2],
                "max": [1, 3, 2],
                "state": "minecraft:stone",
            },
            {
                "type": "draw_truss",
                "anchor": "east_bay",
                "origin": [0, 4, 0],
            },
        ],
    )

    assert resolved[0]["min"] == [101, 21, -33]
    assert resolved[0]["max"] == [103, 24, -29]
    assert resolved[1]["origin"] == [100, 24, -30]
    assert resolved[0]["resolvedAnchor"] == "east_bay"
