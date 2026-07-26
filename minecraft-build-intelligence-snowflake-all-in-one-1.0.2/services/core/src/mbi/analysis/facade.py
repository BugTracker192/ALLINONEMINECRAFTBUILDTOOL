from __future__ import annotations

from collections import Counter, defaultdict

from ..canonical import BuildDocument, IntVector3
from .block_profiles import block_profile

_FACES = {
    "north": (0, 0, -1),
    "south": (0, 0, 1),
    "west": (-1, 0, 0),
    "east": (1, 0, 0),
}


def facade_report(document: BuildDocument) -> dict[str, object]:
    palette = document.palette_by_id()
    per_face: dict[str, dict[str, object]] = {}
    all_flat_regions: list[dict[str, object]] = []
    for direction, (dx, _, dz) in _FACES.items():
        exposed: dict[tuple[int, int], tuple[int, str]] = {}
        depth_axis = "z" if dz else "x"
        for position, palette_id in document.blocks.items():
            entry = palette[palette_id]
            neighbor = IntVector3(position.x + dx, position.y, position.z + dz)
            neighbor_id = document.blocks.get(neighbor)
            if neighbor_id is not None and not block_profile(palette[neighbor_id]).transparent:
                continue
            u = position.x if dz else position.z
            depth = position.z if dz else position.x
            key = (u, position.y)
            current = exposed.get(key)
            # Keep the outermost depth for the selected direction.
            if current is None or (direction in {"north", "west"} and depth < current[0]) or (direction in {"south", "east"} and depth > current[0]):
                exposed[key] = (depth, entry.canonical_state)
        depth_counts = Counter(depth for depth, _ in exposed.values())
        material_counts = Counter(state for _, state in exposed.values())
        transitions = 0
        windows = []
        for (u, y), (depth, state) in exposed.items():
            for neighbor_key in ((u + 1, y), (u, y + 1)):
                neighbor = exposed.get(neighbor_key)
                if neighbor and neighbor[1] != state:
                    transitions += 1
            if "glass" in state:
                windows.append((u, y, depth))

        # Flood-fill same-depth, same-state facade patches in 2D.
        unseen = set(exposed)
        patches = []
        while unseen:
            start = min(unseen)
            unseen.remove(start)
            stack = [start]
            points = []
            signature = exposed[start]
            while stack:
                point = stack.pop()
                points.append(point)
                for candidate in ((point[0] + 1, point[1]), (point[0] - 1, point[1]), (point[0], point[1] + 1), (point[0], point[1] - 1)):
                    if candidate in unseen and exposed[candidate] == signature:
                        unseen.remove(candidate)
                        stack.append(candidate)
            if len(points) >= 16:
                patch = {
                    "direction": direction,
                    "area": len(points),
                    "uMin": min(point[0] for point in points),
                    "uMax": max(point[0] for point in points),
                    "yMin": min(point[1] for point in points),
                    "yMax": max(point[1] for point in points),
                    "depth": signature[0],
                    "state": signature[1],
                }
                patches.append(patch)
                all_flat_regions.append(patch)
        window_rows: dict[int, list[int]] = defaultdict(list)
        for u, y, _ in windows:
            window_rows[y].append(u)
        spacing = []
        for values in window_rows.values():
            values.sort()
            spacing.extend(b - a for a, b in zip(values, values[1:]))
        per_face[direction] = {
            "surfaceCells": len(exposed),
            "depthAxis": depth_axis,
            "uniqueDepths": len(depth_counts),
            "depthHistogram": dict(sorted(depth_counts.items())),
            "materialTransitions": transitions,
            "materialHistogram": dict(material_counts.most_common()),
            "windowCellCount": len(windows),
            "windowSpacing": spacing[:500],
            "largeFlatPatches": sorted(patches, key=lambda item: -int(item["area"]))[:100],
        }
    return {
        "faces": per_face,
        "largestFlatPatches": sorted(all_flat_regions, key=lambda item: -int(item["area"]))[:100],
        "largeFlatPatchCount": len(all_flat_regions),
    }
