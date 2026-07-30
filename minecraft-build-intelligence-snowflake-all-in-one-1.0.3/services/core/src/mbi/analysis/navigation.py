from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass

from ..canonical import BuildDocument, IntBoundingBox, IntVector3
from .block_profiles import block_profile

_HORIZONTAL = ((1, 0), (-1, 0), (0, 1), (0, -1))


@dataclass(frozen=True, slots=True)
class NavigationComponent:
    component_id: int
    node_count: int
    bounds: IntBoundingBox


def _profile_at(document: BuildDocument, position: IntVector3):
    palette_id = document.blocks.get(position)
    if palette_id is None:
        return None
    return block_profile(document.palette_by_id()[palette_id])


def _passable(document: BuildDocument, position: IntVector3) -> bool:
    profile = _profile_at(document, position)
    return profile is None or profile.passable


def _standable(document: BuildDocument, feet: IntVector3) -> bool:
    below = IntVector3(feet.x, feet.y - 1, feet.z)
    support = _profile_at(document, below)
    return bool(
        support
        and support.supports_player
        and _passable(document, feet)
        and _passable(document, IntVector3(feet.x, feet.y + 1, feet.z))
    )


def navigation_graph(
    document: BuildDocument,
    *,
    max_nodes: int = 2_000_000,
    max_drop: int = 3,
    room_volumes=(),
) -> dict[str, object]:
    nodes: set[IntVector3] = set()
    for y in range(document.bounds.min.y, document.bounds.max.y + 2):
        for z in range(document.bounds.min.z, document.bounds.max.z + 1):
            for x in range(document.bounds.min.x, document.bounds.max.x + 1):
                feet = IntVector3(x, y, z)
                if _standable(document, feet):
                    nodes.add(feet)
                    if len(nodes) > max_nodes:
                        return {
                            "analysisSkipped": True,
                            "reason": "node_limit",
                            "limit": max_nodes,
                            "estimatedNodesLowerBound": len(nodes),
                        }
    edges: dict[IntVector3, list[IntVector3]] = {node: [] for node in nodes}
    undirected: dict[IntVector3, set[IntVector3]] = {node: set() for node in nodes}
    blocked_doors = 0
    for node in nodes:
        for dx, dz in _HORIZONTAL:
            candidates = [
                IntVector3(node.x + dx, node.y + 1, node.z + dz),
                IntVector3(node.x + dx, node.y, node.z + dz),
            ]
            candidates.extend(IntVector3(node.x + dx, node.y - drop, node.z + dz) for drop in range(1, max_drop + 1))
            target = next((candidate for candidate in candidates if candidate in nodes), None)
            if target is not None:
                edges[node].append(target)
                undirected[node].add(target)
                undirected[target].add(node)
            else:
                adjacent = IntVector3(node.x + dx, node.y, node.z + dz)
                profile = _profile_at(document, adjacent)
                blocked_doors += int(bool(profile and profile.doorway and not profile.passable))
        current_profile = _profile_at(document, node)
        below_profile = _profile_at(document, IntVector3(node.x, node.y - 1, node.z))
        if (current_profile and current_profile.climbable) or (below_profile and below_profile.climbable):
            for dy in (-1, 1):
                target = IntVector3(node.x, node.y + dy, node.z)
                if target in nodes:
                    edges[node].append(target)
                    undirected[node].add(target)
                    undirected[target].add(node)

    unseen = set(nodes)
    components: list[NavigationComponent] = []
    node_component: dict[IntVector3, int] = {}
    for start in sorted(unseen):
        if start not in unseen:
            continue
        unseen.remove(start)
        queue = deque([start])
        points = []
        component_id = len(components)
        while queue:
            point = queue.popleft()
            points.append(point)
            node_component[point] = component_id
            for neighbor in undirected[point]:
                if neighbor in unseen:
                    unseen.remove(neighbor)
                    queue.append(neighbor)
        bounds = IntBoundingBox(
            IntVector3(min(point.x for point in points), min(point.y for point in points), min(point.z for point in points)),
            IntVector3(max(point.x for point in points), max(point.y for point in points), max(point.z for point in points)),
        )
        components.append(NavigationComponent(component_id, len(points), bounds))

    components.sort(key=lambda item: -item.node_count)
    exterior_component_ids = {
        node_component[node]
        for node in nodes
        if (
            node.x in {document.bounds.min.x, document.bounds.max.x}
            or node.z in {document.bounds.min.z, document.bounds.max.z}
        )
    }
    room_reachability = []
    for volume in room_volumes:
        component_counts: dict[int, int] = {}
        for node, component_id in node_component.items():
            if volume.bounds.contains(node):
                component_counts[component_id] = (
                    component_counts.get(component_id, 0) + 1
                )
        component_ids = sorted(component_counts)
        reachable = bool(set(component_ids) & exterior_component_ids)
        room_reachability.append(
            {
                "roomId": volume.volume_id,
                "standableNodeCount": sum(component_counts.values()),
                "navigationComponentIds": component_ids,
                "exteriorConnected": reachable,
                "sealedFromExterior": not reachable,
                "method": "room-bounds-to-exterior-navigation-component-v1",
            }
        )
    dead_ends = [node for node, outgoing in edges.items() if len(set(outgoing)) <= 1]
    return {
        "analysisSkipped": False,
        "nodeCount": len(nodes),
        "directedEdgeCount": sum(len(values) for values in edges.values()),
        "componentCount": len(components),
        "components": [asdict(item) for item in components],
        "exteriorComponentIds": sorted(exterior_component_ids),
        "roomReachability": room_reachability,
        "deadEndCount": len(dead_ends),
        "deadEndSample": [point.as_tuple() for point in dead_ends[:500]],
        "blockedDoorApproachCount": blocked_doors,
        "maxStepUp": 1,
        "maxDrop": max_drop,
        "shapeModel": "state-aware-voxel-collision-v1",
    }
