from __future__ import annotations

from collections import deque

from ..canonical import BuildDocument, IntVector3
from .block_profiles import block_profile

_NEIGHBORS = ((1, 0, 0), (-1, 0, 0), (0, 1, 0), (0, -1, 0), (0, 0, 1), (0, 0, -1))


def support_report(document: BuildDocument) -> dict[str, object]:
    palette = document.palette_by_id()
    solid = {position for position, pid in document.blocks.items() if block_profile(palette[pid]).supports_player}
    grounded = {position for position in solid if position.y == document.bounds.min.y}
    queue = deque(grounded)
    while queue:
        point = queue.popleft()
        for dx, dy, dz in _NEIGHBORS:
            neighbor = IntVector3(point.x + dx, point.y + dy, point.z + dz)
            if neighbor in solid and neighbor not in grounded:
                grounded.add(neighbor)
                queue.append(neighbor)
    unsupported = sorted(solid - grounded)
    gravity_issues = []
    for position, palette_id in document.blocks.items():
        profile = block_profile(palette[palette_id])
        if not profile.gravity_affected:
            continue
        below = IntVector3(position.x, position.y - 1, position.z)
        below_id = document.blocks.get(below)
        if below_id is None or not block_profile(palette[below_id]).supports_player:
            gravity_issues.append({"position": position.as_tuple(), "state": palette[palette_id].canonical_state})
    thin_cantilevers = []
    for position in unsupported[:5000]:
        horizontal_supports = 0
        for dx, _, dz in _NEIGHBORS[:2] + _NEIGHBORS[4:]:
            horizontal_supports += IntVector3(position.x + dx, position.y, position.z + dz) in solid
        below = IntVector3(position.x, position.y - 1, position.z)
        if below not in solid and horizontal_supports <= 1:
            thin_cantilevers.append(position.as_tuple())
            if len(thin_cantilevers) >= 500:
                break
    return {
        "groundedBlockCount": len(grounded),
        "unsupportedBlockCount": len(unsupported),
        "unsupportedSample": [point.as_tuple() for point in unsupported[:500]],
        "gravityIssueCount": len(gravity_issues),
        "gravityIssues": gravity_issues[:500],
        "thinCantileverCountLowerBound": len(thin_cantilevers),
        "thinCantileverSample": thin_cantilevers,
        "classification": "heuristic",
    }
