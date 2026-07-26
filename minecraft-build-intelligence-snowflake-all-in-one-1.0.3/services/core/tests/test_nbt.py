from __future__ import annotations

import pytest

from mbi.errors import NBTError
from mbi.nbt import NBTWriter, Tag, read_nbt


def test_nbt_writer_reader_round_trip() -> None:
    raw = NBTWriter().root("root", {
        "byte": (Tag.BYTE, -4),
        "short": (Tag.SHORT, 123),
        "int": (Tag.INT, 123456),
        "long": (Tag.LONG, 2**40),
        "text": (Tag.STRING, "hello"),
        "bytes": (Tag.BYTE_ARRAY, b"\x00\xff"),
        "ints": (Tag.INT_ARRAY, [1, 2, 3]),
        "longs": (Tag.LONG_ARRAY, [0, -1, 2**62]),
        "list": (Tag.LIST, (Tag.STRING, ["a", "b"])),
        "compound": (Tag.COMPOUND, {"x": (Tag.INT, 1)}),
    })
    document = read_nbt(raw)
    assert document.root_name == "root"
    assert document.root["bytes"] == b"\x00\xff"
    assert document.root["compound"] == {"x": 1}


def test_nbt_rejects_trailing_bytes() -> None:
    raw = NBTWriter().root("", {}) + b"extra"
    with pytest.raises(NBTError) as error:
        read_nbt(raw)
    assert error.value.code == "NBT_TRAILING_BYTES"
