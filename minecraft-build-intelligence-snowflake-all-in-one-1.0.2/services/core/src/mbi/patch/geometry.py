from __future__ import annotations

import math
import random
from collections.abc import Iterable

from ..canonical import IntBoundingBox, IntVector3


def normalize_box(a: IntVector3, b: IntVector3) -> IntBoundingBox:
    return IntBoundingBox(
        IntVector3(min(a.x, b.x), min(a.y, b.y), min(a.z, b.z)),
        IntVector3(max(a.x, b.x), max(a.y, b.y), max(a.z, b.z)),
    )


def cuboid(bounds: IntBoundingBox, *, hollow: bool = False) -> set[IntVector3]:
    points = set()
    for point in bounds.iter_points():
        if not hollow or (
            point.x in {bounds.min.x, bounds.max.x}
            or point.y in {bounds.min.y, bounds.max.y}
            or point.z in {bounds.min.z, bounds.max.z}
        ):
            points.add(point)
    return points


def line(a: IntVector3, b: IntVector3) -> list[IntVector3]:
    """Deterministic 3D DDA line including both endpoints."""
    dx, dy, dz = b.x - a.x, b.y - a.y, b.z - a.z
    steps = max(abs(dx), abs(dy), abs(dz))
    if steps == 0:
        return [a]
    result = []
    seen = set()
    for index in range(steps + 1):
        t = index / steps
        point = IntVector3(round(a.x + dx * t), round(a.y + dy * t), round(a.z + dz * t))
        if point not in seen:
            seen.add(point)
            result.append(point)
    return result


def polyline(points: list[IntVector3]) -> set[IntVector3]:
    result: set[IntVector3] = set()
    for a, b in zip(points, points[1:]):
        result.update(line(a, b))
    if len(points) == 1:
        result.add(points[0])
    return result


def ellipse(center: IntVector3, radius_a: int, radius_b: int, *, plane: str = "xz", filled: bool = False) -> set[IntVector3]:
    if radius_a < 0 or radius_b < 0:
        raise ValueError("radii must be non-negative")
    if radius_a == 0 and radius_b == 0:
        return {center}
    result: set[IntVector3] = set()
    samples = max(24, int(2 * math.pi * max(radius_a, radius_b) * 4))
    for index in range(samples):
        angle = 2 * math.pi * index / samples
        a = round(math.cos(angle) * radius_a)
        b = round(math.sin(angle) * radius_b)
        if plane == "xz":
            result.add(IntVector3(center.x + a, center.y, center.z + b))
        elif plane == "xy":
            result.add(IntVector3(center.x + a, center.y + b, center.z))
        elif plane == "yz":
            result.add(IntVector3(center.x, center.y + a, center.z + b))
        else:
            raise ValueError("plane must be xz, xy, or yz")
    if filled:
        if plane == "xz":
            for x in range(center.x - radius_a, center.x + radius_a + 1):
                for z in range(center.z - radius_b, center.z + radius_b + 1):
                    if ((x - center.x) / max(1, radius_a)) ** 2 + ((z - center.z) / max(1, radius_b)) ** 2 <= 1.0:
                        result.add(IntVector3(x, center.y, z))
        elif plane == "xy":
            for x in range(center.x - radius_a, center.x + radius_a + 1):
                for y in range(center.y - radius_b, center.y + radius_b + 1):
                    if ((x - center.x) / max(1, radius_a)) ** 2 + ((y - center.y) / max(1, radius_b)) ** 2 <= 1.0:
                        result.add(IntVector3(x, y, center.z))
        else:
            for y in range(center.y - radius_a, center.y + radius_a + 1):
                for z in range(center.z - radius_b, center.z + radius_b + 1):
                    if ((y - center.y) / max(1, radius_a)) ** 2 + ((z - center.z) / max(1, radius_b)) ** 2 <= 1.0:
                        result.add(IntVector3(center.x, y, z))
    return result


def sphere(center: IntVector3, radius: int, *, hollow: bool = False, dome: bool = False) -> set[IntVector3]:
    result = set()
    inner = max(0, radius - 1)
    for y in range(-radius, radius + 1):
        if dome and y < 0:
            continue
        for z in range(-radius, radius + 1):
            for x in range(-radius, radius + 1):
                distance2 = x * x + y * y + z * z
                if distance2 > radius * radius:
                    continue
                if hollow and distance2 < inner * inner:
                    continue
                result.add(IntVector3(center.x + x, center.y + y, center.z + z))
    return result


def cylinder(center: IntVector3, radius_x: int, radius_z: int, height: int, *, hollow: bool = False) -> set[IntVector3]:
    result = set()
    for y in range(center.y, center.y + height):
        outer = ellipse(IntVector3(center.x, y, center.z), radius_x, radius_z, plane="xz", filled=not hollow)
        result.update(outer)
    return result


def arch(a: IntVector3, b: IntVector3, height: int, *, thickness: int = 1) -> set[IntVector3]:
    if a.y != b.y:
        raise ValueError("arch endpoints must share Y")
    span = line(a, b)
    result = set()
    count = max(1, len(span) - 1)
    for index, base in enumerate(span):
        t = index / count
        y = round(a.y + 4 * height * t * (1 - t))
        for offset in range(thickness):
            result.add(IntVector3(base.x, y + offset, base.z))
    return result


def rotate_y(point: IntVector3, origin: IntVector3, quarter_turns: int) -> IntVector3:
    turns = quarter_turns % 4
    x, z = point.x - origin.x, point.z - origin.z
    for _ in range(turns):
        x, z = -z, x
    return IntVector3(origin.x + x, point.y, origin.z + z)


def mirror(point: IntVector3, origin: IntVector3, axis: str) -> IntVector3:
    if axis == "x":
        return IntVector3(2 * origin.x - point.x, point.y, point.z)
    if axis == "y":
        return IntVector3(point.x, 2 * origin.y - point.y, point.z)
    if axis == "z":
        return IntVector3(point.x, point.y, 2 * origin.z - point.z)
    raise ValueError("mirror axis must be x, y, or z")


def integer_scale(point: IntVector3, origin: IntVector3, factor: IntVector3) -> Iterable[IntVector3]:
    base = IntVector3(
        origin.x + (point.x - origin.x) * factor.x,
        origin.y + (point.y - origin.y) * factor.y,
        origin.z + (point.z - origin.z) * factor.z,
    )
    for dy in range(max(1, factor.y)):
        for dz in range(max(1, factor.z)):
            for dx in range(max(1, factor.x)):
                yield IntVector3(base.x + dx, base.y + dy, base.z + dz)


def deterministic_mask(points: Iterable[IntVector3], *, seed: int, probability: float) -> set[IntVector3]:
    if not 0 <= probability <= 1:
        raise ValueError("probability must be between 0 and 1")
    selected = set()
    for point in points:
        randomizer = random.Random(f"{seed}:{point.x}:{point.y}:{point.z}")
        if randomizer.random() < probability:
            selected.add(point)
    return selected


def bezier(control_points: list[IntVector3], *, samples: int | None = None) -> set[IntVector3]:
    """Rasterize a deterministic quadratic/cubic Bezier curve as connected voxel lines."""
    if len(control_points) not in {3, 4}:
        raise ValueError("Bezier curves require three or four control points")
    if samples is None:
        extent = max(
            max(point.x for point in control_points) - min(point.x for point in control_points),
            max(point.y for point in control_points) - min(point.y for point in control_points),
            max(point.z for point in control_points) - min(point.z for point in control_points),
        )
        samples = max(16, extent * 8)
    samples = max(2, min(100_000, int(samples)))
    evaluated: list[IntVector3] = []
    for index in range(samples + 1):
        t = index / samples
        if len(control_points) == 3:
            a, b, c = control_points
            weights = ((1 - t) ** 2, 2 * (1 - t) * t, t**2)
            values = (a, b, c)
        else:
            a, b, c, d = control_points
            weights = ((1 - t) ** 3, 3 * (1 - t) ** 2 * t, 3 * (1 - t) * t**2, t**3)
            values = (a, b, c, d)
        evaluated.append(
            IntVector3(
                round(sum(weight * point.x for weight, point in zip(weights, values, strict=True))),
                round(sum(weight * point.y for weight, point in zip(weights, values, strict=True))),
                round(sum(weight * point.z for weight, point in zip(weights, values, strict=True))),
            )
        )
    return polyline(evaluated)


def extrude_profile(profile: list[IntVector3], offset: IntVector3, *, steps: int = 1) -> set[IntVector3]:
    if not profile:
        return set()
    steps = max(1, min(100_000, int(steps)))
    result: set[IntVector3] = set()
    for step in range(steps + 1):
        ratio = step / steps
        shifted = [
            IntVector3(
                round(point.x + offset.x * ratio),
                round(point.y + offset.y * ratio),
                round(point.z + offset.z * ratio),
            )
            for point in profile
        ]
        result.update(polyline(shifted + ([shifted[0]] if len(shifted) > 2 else [])))
        if step:
            previous_ratio = (step - 1) / steps
            previous = [
                IntVector3(
                    round(point.x + offset.x * previous_ratio),
                    round(point.y + offset.y * previous_ratio),
                    round(point.z + offset.z * previous_ratio),
                )
                for point in profile
            ]
            for a, b in zip(previous, shifted, strict=True):
                result.update(line(a, b))
    return result


def loft_profiles(profiles: list[list[IntVector3]], *, steps_per_pair: int = 8) -> set[IntVector3]:
    if len(profiles) < 2:
        raise ValueError("Loft requires at least two profiles")
    size = len(profiles[0])
    if size < 2 or any(len(profile) != size for profile in profiles):
        raise ValueError("Loft profiles must contain the same number of points")
    result: set[IntVector3] = set()
    steps_per_pair = max(1, min(4096, int(steps_per_pair)))
    for first, second in zip(profiles, profiles[1:]):
        interpolated_profiles: list[list[IntVector3]] = []
        for step in range(steps_per_pair + 1):
            ratio = step / steps_per_pair
            profile = [
                IntVector3(
                    round(a.x + (b.x - a.x) * ratio),
                    round(a.y + (b.y - a.y) * ratio),
                    round(a.z + (b.z - a.z) * ratio),
                )
                for a, b in zip(first, second, strict=True)
            ]
            interpolated_profiles.append(profile)
            result.update(polyline(profile + [profile[0]]))
        for before, after in zip(interpolated_profiles, interpolated_profiles[1:]):
            for a, b in zip(before, after, strict=True):
                result.update(line(a, b))
    return result
