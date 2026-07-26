from __future__ import annotations

import io
import struct
from dataclasses import dataclass
from enum import IntEnum
from typing import Any, BinaryIO

from .errors import NBTError
from .limits import NBTLimits


class Tag(IntEnum):
    END = 0
    BYTE = 1
    SHORT = 2
    INT = 3
    LONG = 4
    FLOAT = 5
    DOUBLE = 6
    BYTE_ARRAY = 7
    STRING = 8
    LIST = 9
    COMPOUND = 10
    INT_ARRAY = 11
    LONG_ARRAY = 12


@dataclass(frozen=True, slots=True)
class NBTDocument:
    root_name: str
    root: dict[str, Any]


class NBTReader:
    def __init__(self, data: bytes, limits: NBTLimits | None = None) -> None:
        self.stream = io.BytesIO(data)
        self.limits = limits or NBTLimits()
        self.tags_read = 0

    def read(self) -> NBTDocument:
        tag = self._u8()
        if tag != Tag.COMPOUND:
            raise NBTError("NBT_ROOT_NOT_COMPOUND", "The root NBT tag must be a compound.", {"tag": tag})
        name = self._string()
        value = self._payload(Tag.COMPOUND, 0)
        if not isinstance(value, dict):
            raise AssertionError("compound parser invariant")
        trailing = self.stream.read(1)
        if trailing:
            raise NBTError("NBT_TRAILING_BYTES", "Trailing bytes remain after the root NBT compound.")
        return NBTDocument(name, value)

    def _count_tag(self) -> None:
        self.tags_read += 1
        if self.tags_read > self.limits.max_tags:
            raise NBTError("NBT_TAG_LIMIT", "NBT tag count exceeds the configured limit.")

    def _read_exact(self, n: int) -> bytes:
        if n < 0:
            raise NBTError("NBT_NEGATIVE_LENGTH", "NBT declared a negative byte count.")
        data = self.stream.read(n)
        if len(data) != n:
            raise NBTError("NBT_UNEXPECTED_EOF", "NBT ended before the declared value was complete.", {"expected": n, "actual": len(data)})
        return data

    def _u8(self) -> int:
        return self._read_exact(1)[0]

    def _i8(self) -> int:
        return struct.unpack(">b", self._read_exact(1))[0]

    def _i16(self) -> int:
        return struct.unpack(">h", self._read_exact(2))[0]

    def _u16(self) -> int:
        return struct.unpack(">H", self._read_exact(2))[0]

    def _i32(self) -> int:
        return struct.unpack(">i", self._read_exact(4))[0]

    def _i64(self) -> int:
        return struct.unpack(">q", self._read_exact(8))[0]

    def _string(self) -> str:
        length = self._u16()
        if length > self.limits.max_string_bytes:
            raise NBTError("NBT_STRING_LIMIT", "NBT string exceeds the configured byte limit.", {"length": length})
        try:
            return self._read_exact(length).decode("utf-8", errors="strict")
        except UnicodeDecodeError as exc:
            raise NBTError("NBT_INVALID_UTF8", "NBT string is not valid UTF-8.", {"offset": exc.start}) from exc

    def _length(self, limit: int, kind: str) -> int:
        length = self._i32()
        if length < 0:
            raise NBTError("NBT_NEGATIVE_LENGTH", f"NBT {kind} declared a negative length.", {"length": length})
        if length > limit:
            raise NBTError("NBT_LENGTH_LIMIT", f"NBT {kind} exceeds the configured length limit.", {"length": length, "limit": limit})
        return length

    def _payload(self, tag: Tag | int, depth: int) -> Any:
        self._count_tag()
        if depth > self.limits.max_depth:
            raise NBTError("NBT_DEPTH_LIMIT", "NBT nesting exceeds the configured depth limit.")
        try:
            tag = Tag(tag)
        except ValueError as exc:
            raise NBTError("NBT_UNKNOWN_TAG", "NBT contains an unknown tag type.", {"tag": int(tag)}) from exc
        if tag is Tag.BYTE:
            return self._i8()
        if tag is Tag.SHORT:
            return self._i16()
        if tag is Tag.INT:
            return self._i32()
        if tag is Tag.LONG:
            return self._i64()
        if tag is Tag.FLOAT:
            return struct.unpack(">f", self._read_exact(4))[0]
        if tag is Tag.DOUBLE:
            return struct.unpack(">d", self._read_exact(8))[0]
        if tag is Tag.BYTE_ARRAY:
            length = self._length(self.limits.max_array_length, "byte array")
            return self._read_exact(length)
        if tag is Tag.STRING:
            return self._string()
        if tag is Tag.LIST:
            child_tag = self._u8()
            length = self._length(self.limits.max_list_length, "list")
            if child_tag == Tag.END and length:
                raise NBTError("NBT_INVALID_LIST_TYPE", "A non-empty NBT list cannot have TAG_End element type.")
            return [self._payload(child_tag, depth + 1) for _ in range(length)]
        if tag is Tag.COMPOUND:
            result: dict[str, Any] = {}
            while True:
                child_tag = self._u8()
                if child_tag == Tag.END:
                    return result
                key = self._string()
                if key in result:
                    raise NBTError("NBT_DUPLICATE_COMPOUND_KEY", "NBT compound contains a duplicate key.", {"key": key})
                result[key] = self._payload(child_tag, depth + 1)
        if tag is Tag.INT_ARRAY:
            length = self._length(self.limits.max_array_length, "int array")
            return [self._i32() for _ in range(length)]
        if tag is Tag.LONG_ARRAY:
            length = self._length(self.limits.max_array_length, "long array")
            return [self._i64() for _ in range(length)]
        if tag is Tag.END:
            return None
        raise AssertionError("unhandled NBT tag")


def read_nbt(data: bytes, limits: NBTLimits | None = None) -> NBTDocument:
    return NBTReader(data, limits).read()


class NBTWriter:
    """Small typed NBT writer used by deterministic exporters and fixtures."""

    def __init__(self) -> None:
        self.out = io.BytesIO()

    def root(self, name: str, compound: dict[str, tuple[Tag, Any]]) -> bytes:
        self._u8(Tag.COMPOUND)
        self._string(name)
        self._compound(compound)
        return self.out.getvalue()

    def _write(self, data: bytes) -> None:
        self.out.write(data)

    def _u8(self, value: int) -> None:
        self._write(struct.pack(">B", value))

    def _i8(self, value: int) -> None:
        self._write(struct.pack(">b", value))

    def _i16(self, value: int) -> None:
        self._write(struct.pack(">h", value))

    def _i32(self, value: int) -> None:
        self._write(struct.pack(">i", value))

    def _i64(self, value: int) -> None:
        # Allow unsigned words from bit packing by converting to signed NBT long.
        if value >= 1 << 63:
            value -= 1 << 64
        self._write(struct.pack(">q", value))

    def _string(self, value: str) -> None:
        encoded = value.encode("utf-8")
        if len(encoded) > 0xFFFF:
            raise ValueError("NBT string too long")
        self._write(struct.pack(">H", len(encoded)))
        self._write(encoded)

    def _compound(self, value: dict[str, tuple[Tag, Any]]) -> None:
        for key, (tag, payload) in value.items():
            self._u8(tag)
            self._string(key)
            self._payload(tag, payload)
        self._u8(Tag.END)

    def _payload(self, tag: Tag, value: Any) -> None:
        if tag is Tag.BYTE:
            self._i8(int(value))
        elif tag is Tag.SHORT:
            self._i16(int(value))
        elif tag is Tag.INT:
            self._i32(int(value))
        elif tag is Tag.LONG:
            self._i64(int(value))
        elif tag is Tag.FLOAT:
            self._write(struct.pack(">f", float(value)))
        elif tag is Tag.DOUBLE:
            self._write(struct.pack(">d", float(value)))
        elif tag is Tag.BYTE_ARRAY:
            raw = bytes(value)
            self._i32(len(raw))
            self._write(raw)
        elif tag is Tag.STRING:
            self._string(str(value))
        elif tag is Tag.LIST:
            child_tag, items = value
            self._u8(child_tag)
            self._i32(len(items))
            for item in items:
                self._payload(child_tag, item)
        elif tag is Tag.COMPOUND:
            self._compound(value)
        elif tag is Tag.INT_ARRAY:
            self._i32(len(value))
            for item in value:
                self._i32(item)
        elif tag is Tag.LONG_ARRAY:
            self._i32(len(value))
            for item in value:
                self._i64(item)
        else:
            raise ValueError(f"Unsupported export tag: {tag}")
