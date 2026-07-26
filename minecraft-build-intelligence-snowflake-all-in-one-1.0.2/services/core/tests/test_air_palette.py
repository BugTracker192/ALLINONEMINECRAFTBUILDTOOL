from __future__ import annotations

from mbi.canonical import IntVector3
from mbi.importer import import_build
from mbi.nbt import NBTWriter, Tag


def _sponge(*, palette: dict[str, int], data: bytes, width: int) -> bytes:
    return NBTWriter().root(
        "",
        {
            "Schematic": (
                Tag.COMPOUND,
                {
                    "Version": (Tag.INT, 3),
                    "DataVersion": (Tag.INT, 3953),
                    "Width": (Tag.SHORT, width),
                    "Height": (Tag.SHORT, 1),
                    "Length": (Tag.SHORT, 1),
                    "Offset": (Tag.INT_ARRAY, [0, 0, 0]),
                    "Blocks": (
                        Tag.COMPOUND,
                        {
                            "Palette": (Tag.COMPOUND, {state: (Tag.INT, index) for state, index in palette.items()}),
                            "Data": (Tag.BYTE_ARRAY, data),
                            "BlockEntities": (Tag.LIST, (Tag.COMPOUND, [])),
                        },
                    ),
                    "Entities": (Tag.LIST, (Tag.COMPOUND, [])),
                },
            )
        },
    )


def test_sponge_does_not_assume_air_is_palette_zero() -> None:
    document = import_build(
        _sponge(palette={"minecraft:stone": 0, "minecraft:air": 1}, data=b"\x00\x01", width=2),
        "air-not-zero.schem",
    )
    assert document.state_at(IntVector3(0, 0, 0)).canonical_state == "minecraft:stone"
    assert document.state_at(IntVector3(1, 0, 0)).canonical_state == "minecraft:air"
    assert document.blocks == {IntVector3(0, 0, 0): 0}


def test_sponge_appends_missing_air_without_remapping_source_indexes() -> None:
    document = import_build(
        _sponge(palette={"minecraft:stone": 0}, data=b"\x00", width=1),
        "missing-air.schem",
    )
    assert document.state_at(IntVector3(0, 0, 0)).canonical_state == "minecraft:stone"
    air = [entry for entry in document.palette if entry.is_air_like]
    assert len(air) == 1
    assert air[0].palette_id == 1
