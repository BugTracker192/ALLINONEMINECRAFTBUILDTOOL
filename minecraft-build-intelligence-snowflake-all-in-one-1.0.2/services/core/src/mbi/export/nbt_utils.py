from __future__ import annotations

from typing import Any

from ..errors import FormatError
from ..nbt import Tag

_BYTE_KEYS = {"keepPacked", "auto", "powered", "conditionMet", "B", "b"}
_LONG_KEYS = {"TimeCreated", "TimeModified", "TotalVolume", "TotalBlocks", "UUIDMost", "UUIDLeast"}
_INT_ARRAY_KEYS = {"Pos", "UUID"}
_LONG_ARRAY_KEYS = {"BlockStates"}


def _integer_tag(value: int, key: str | None) -> Tag:
    if key in _BYTE_KEYS and -128 <= value <= 127:
        return Tag.BYTE
    if key in _LONG_KEYS or value < -(1 << 31) or value >= 1 << 31:
        return Tag.LONG
    return Tag.INT


def infer_tagged(value: Any, *, key: str | None = None) -> tuple[Tag, Any]:
    """Convert the reader's normalized Python values back into typed NBT.

    The parser intentionally exposes ordinary Python values. Primitive width is not
    always recoverable, so this function applies deterministic, format-aware rules and
    preserves every value rather than dropping unknown NBT fields.
    """

    if isinstance(value, bool):
        return Tag.BYTE, int(value)
    if isinstance(value, int):
        return _integer_tag(value, key), value
    if isinstance(value, float):
        return Tag.DOUBLE, value
    if isinstance(value, str):
        return Tag.STRING, value
    if isinstance(value, bytes):
        return Tag.BYTE_ARRAY, value
    if isinstance(value, dict):
        return Tag.COMPOUND, {str(name): infer_tagged(item, key=str(name)) for name, item in value.items() if not str(name).startswith("$")}
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, list):
        if key in _INT_ARRAY_KEYS and all(isinstance(item, int) and not isinstance(item, bool) for item in value):
            return Tag.INT_ARRAY, value
        if key in _LONG_ARRAY_KEYS and all(isinstance(item, int) and not isinstance(item, bool) for item in value):
            return Tag.LONG_ARRAY, value
        if not value:
            # Empty compound lists are the most common unknown list in schematic NBT.
            return Tag.LIST, (Tag.COMPOUND, [])
        tagged = [infer_tagged(item) for item in value]
        child_tags = {tag for tag, _ in tagged}
        if child_tags <= {Tag.BYTE, Tag.INT, Tag.LONG}:
            child_tag = Tag.LONG if Tag.LONG in child_tags else Tag.INT
            return Tag.LIST, (child_tag, [payload for _, payload in tagged])
        if len(child_tags) != 1:
            raise FormatError(
                "NBT_EXPORT_HETEROGENEOUS_LIST",
                "NBT lists must contain one tag type.",
                {"key": key, "types": sorted(int(tag) for tag in child_tags)},
            )
        child_tag = tagged[0][0]
        return Tag.LIST, (child_tag, [payload for _, payload in tagged])
    if value is None:
        return Tag.STRING, ""
    raise FormatError("NBT_EXPORT_TYPE", "Unsupported NBT export value.", {"type": type(value).__name__, "key": key})


def typed_compound(raw: dict[str, Any], *, exclude: set[str] | None = None) -> dict[str, tuple[Tag, Any]]:
    excluded = exclude or set()
    return {
        str(key): infer_tagged(value, key=str(key))
        for key, value in raw.items()
        if str(key) not in excluded and not str(key).startswith("$")
    }
