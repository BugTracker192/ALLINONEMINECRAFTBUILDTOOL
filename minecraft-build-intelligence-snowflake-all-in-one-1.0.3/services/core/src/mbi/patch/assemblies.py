from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from ..canonical import IntVector3
from ..errors import PatchError
from .geometry import arch, line


def _vector(raw: object, name: str) -> IntVector3:
    if (
        not isinstance(raw, (list, tuple))
        or len(raw) != 3
        or not all(isinstance(value, int) for value in raw)
    ):
        raise PatchError("ASSEMBLY_VECTOR", f"{name} must be a three-integer vector.")
    return IntVector3(*raw)


def _thicken(points: Iterable[IntVector3], thickness: int) -> set[IntVector3]:
    radius = max(0, thickness - 1)
    return {
        IntVector3(point.x + dx, point.y + dy, point.z + dz)
        for point in points
        for dx in range(-radius, radius + 1)
        for dy in range(-radius, radius + 1)
        for dz in range(-radius, radius + 1)
        if abs(dx) + abs(dy) + abs(dz) <= radius
    }


def draw_truss(operation: dict[str, object]) -> dict[IntVector3, str]:
    origin = _vector(operation.get("origin"), "origin")
    width = max(3, int(operation.get("width", 7)))
    height = max(2, int(operation.get("height", 4)))
    axis = str(operation.get("axis", "x"))
    state = str(operation.get("state", "minecraft:oak_log"))
    accent = str(operation.get("accentState", state))
    thickness = max(1, int(operation.get("thickness", 1)))

    def point(horizontal: int, vertical: int) -> IntVector3:
        return (
            IntVector3(origin.x + horizontal, origin.y + vertical, origin.z)
            if axis == "x"
            else IntVector3(origin.x, origin.y + vertical, origin.z + horizontal)
        )

    left = point(0, 0)
    right = point(width - 1, 0)
    apex = point((width - 1) // 2, height)
    primary = _thicken(
        list(line(left, right)) + list(line(left, apex)) + list(line(apex, right)),
        thickness,
    )
    king_post = _thicken(
        line(point((width - 1) // 2, 0), apex),
        thickness,
    )
    braces = _thicken(
        list(line(point(1, 0), point((width - 1) // 2, max(1, height // 2))))
        + list(
            line(
                point(width - 2, 0),
                point((width - 1) // 2, max(1, height // 2)),
            )
        ),
        thickness,
    )
    return {
        **{point: state for point in primary},
        **{point: accent for point in king_post | braces},
    }


def draw_dormer(operation: dict[str, object]) -> dict[IntVector3, str]:
    origin = _vector(operation.get("origin"), "origin")
    width = max(3, int(operation.get("width", 5)))
    depth = max(2, int(operation.get("depth", 3)))
    height = max(2, int(operation.get("height", 3)))
    axis = str(operation.get("axis", "x"))
    wall_state = str(operation.get("state", "minecraft:oak_planks"))
    roof_state = str(operation.get("roofState", "minecraft:oak_stairs"))
    trim_state = str(operation.get("trimState", wall_state))
    result: dict[IntVector3, str] = {}
    for u in range(width):
        for v in range(depth):
            for y in range(height):
                if u in {0, width - 1} or v in {0, depth - 1}:
                    point = (
                        IntVector3(origin.x + u, origin.y + y, origin.z + v)
                        if axis == "x"
                        else IntVector3(origin.x + v, origin.y + y, origin.z + u)
                    )
                    result[point] = wall_state
    middle = (width - 1) / 2.0
    for u in range(width):
        roof_y = (
            origin.y
            + height
            + round(middle - abs(u - middle))
        )
        for v in range(depth):
            point = (
                IntVector3(origin.x + u, roof_y, origin.z + v)
                if axis == "x"
                else IntVector3(origin.x + v, roof_y, origin.z + u)
            )
            result[point] = roof_state
    for u in (0, width - 1):
        for y in range(height + 1):
            point = (
                IntVector3(origin.x + u, origin.y + y, origin.z)
                if axis == "x"
                else IntVector3(origin.x, origin.y + y, origin.z + u)
            )
            result[point] = trim_state
    return result


def draw_arcade(operation: dict[str, object]) -> dict[IntVector3, str]:
    origin = _vector(operation.get("origin"), "origin")
    bay_count = max(1, int(operation.get("bayCount", 3)))
    bay_width = max(3, int(operation.get("bayWidth", 5)))
    height = max(2, int(operation.get("height", 5)))
    axis = str(operation.get("axis", "x"))
    state = str(operation.get("state", "minecraft:stone_bricks"))
    thickness = max(1, int(operation.get("thickness", 1)))
    points: set[IntVector3] = set()
    for bay in range(bay_count):
        offset = bay * (bay_width - 1)
        start = (
            IntVector3(origin.x + offset, origin.y, origin.z)
            if axis == "x"
            else IntVector3(origin.x, origin.y, origin.z + offset)
        )
        end = (
            IntVector3(origin.x + offset + bay_width - 1, origin.y, origin.z)
            if axis == "x"
            else IntVector3(origin.x, origin.y, origin.z + offset + bay_width - 1)
        )
        points.update(arch(start, end, height, thickness=thickness))
    return {point: state for point in points}


def draw_bellcast_eave(operation: dict[str, object]) -> dict[IntVector3, str]:
    origin = _vector(operation.get("origin"), "origin")
    length = max(1, int(operation.get("length", 8)))
    overhang = max(1, int(operation.get("overhang", 3)))
    drop = max(1, int(operation.get("drop", 2)))
    axis = str(operation.get("axis", "x"))
    state = str(operation.get("state", "minecraft:oak_stairs"))
    trim_state = str(operation.get("trimState", state))
    result: dict[IntVector3, str] = {}
    for along in range(length):
        for outward in range(overhang + 1):
            vertical = -round((outward / max(1, overhang)) ** 2 * drop)
            point = (
                IntVector3(
                    origin.x + along,
                    origin.y + vertical,
                    origin.z + outward,
                )
                if axis == "x"
                else IntVector3(
                    origin.x + outward,
                    origin.y + vertical,
                    origin.z + along,
                )
            )
            result[point] = trim_state if outward == overhang else state
    return result


def place_fixture(operation: dict[str, object]) -> dict[IntVector3, str]:
    origin = _vector(operation.get("origin"), "origin")
    fixture = str(operation.get("fixture", "bench"))
    primary = str(operation.get("state", "minecraft:oak_planks"))
    accent = str(operation.get("accentState", "minecraft:oak_fence"))
    facing = str(operation.get("facing", "east"))
    length = max(2, int(operation.get("length", 3)))
    result: dict[IntVector3, str] = {}

    def offset(x: int, y: int, z: int) -> IntVector3:
        rotations = {
            "east": (x, z),
            "west": (-x, -z),
            "south": (-z, x),
            "north": (z, -x),
        }
        dx, dz = rotations.get(facing, rotations["east"])
        return IntVector3(origin.x + dx, origin.y + y, origin.z + dz)

    if fixture == "bench":
        for index in range(length):
            result[offset(index, 1, 0)] = primary
        for index in (0, length - 1):
            result[offset(index, 0, 0)] = accent
            result[offset(index, 2, 1)] = accent
    elif fixture == "table":
        for x in range(length):
            for z in range(2):
                result[offset(x, 2, z)] = primary
        for x, z in ((0, 0), (0, 1), (length - 1, 0), (length - 1, 1)):
            result[offset(x, 1, z)] = accent
    elif fixture == "hearth":
        fire = str(operation.get("fireState", "minecraft:campfire"))
        for x in range(3):
            result[offset(x, 0, 0)] = primary
            result[offset(x, 0, 2)] = primary
        for z in range(3):
            result[offset(0, 0, z)] = primary
            result[offset(2, 0, z)] = primary
        result[offset(1, 0, 1)] = fire
    elif fixture == "brazier":
        fire = str(operation.get("fireState", "minecraft:soul_campfire"))
        result[offset(0, 0, 0)] = accent
        result[offset(0, 1, 0)] = primary
        result[offset(0, 2, 0)] = fire
    elif fixture == "banner_arrangement":
        default_facing = {
            "east": "west",
            "west": "east",
            "south": "north",
            "north": "south",
        }.get(facing, "north")
        banner = str(
            operation.get(
                "bannerState",
                f"minecraft:red_wall_banner[facing={default_facing}]",
            )
        )
        for index in range(length):
            result[offset(index * 2, 2, 0)] = banner
    else:
        raise PatchError(
            "FIXTURE_UNKNOWN",
            "Unknown fixture kit part.",
            {"fixture": fixture},
        )
    return result


ASSEMBLIES = {
    "draw_truss": draw_truss,
    "draw_dormer": draw_dormer,
    "draw_arcade": draw_arcade,
    "draw_bellcast_eave": draw_bellcast_eave,
    "place_fixture": place_fixture,
}


def assembly_changes(operation: dict[str, object]) -> dict[IntVector3, str]:
    function = ASSEMBLIES.get(str(operation.get("type")))
    if function is None:
        raise PatchError(
            "ASSEMBLY_UNKNOWN",
            "Unknown compound assembly.",
            {"type": operation.get("type")},
        )
    return function(operation)


def fixture_catalog() -> dict[str, Any]:
    return {
        "schema": "mbi.fixture-catalog.v1",
        "fixtures": {
            "bench": ["origin", "length", "facing", "state", "accentState"],
            "table": ["origin", "length", "facing", "state", "accentState"],
            "hearth": ["origin", "facing", "state", "fireState"],
            "brazier": ["origin", "facing", "state", "accentState", "fireState"],
            "banner_arrangement": [
                "origin",
                "length",
                "facing",
                "bannerState",
            ],
        },
        "assemblies": {
            "draw_truss": ["origin", "width", "height", "axis", "state"],
            "draw_dormer": [
                "origin",
                "width",
                "depth",
                "height",
                "axis",
                "state",
                "roofState",
            ],
            "draw_arcade": [
                "origin",
                "bayCount",
                "bayWidth",
                "height",
                "axis",
                "state",
            ],
            "draw_bellcast_eave": [
                "origin",
                "length",
                "overhang",
                "drop",
                "axis",
                "state",
            ],
        },
    }
