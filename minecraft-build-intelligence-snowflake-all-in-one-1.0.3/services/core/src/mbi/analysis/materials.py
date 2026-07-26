from __future__ import annotations

from collections import Counter, defaultdict

from ..canonical import BuildDocument


def material_report(document: BuildDocument) -> dict[str, object]:
    palette = document.palette_by_id()
    state_counts: Counter[str] = Counter()
    base_counts: Counter[str] = Counter()
    layer_counts: dict[int, Counter[str]] = defaultdict(Counter)
    for position, palette_id in document.blocks.items():
        entry = palette[palette_id]
        if entry.is_air_like:
            continue
        state_counts[entry.canonical_state] += 1
        base = f"{entry.namespace}:{entry.block_name}"
        base_counts[base] += 1
        layer_counts[position.y][entry.canonical_state] += 1
    total = sum(state_counts.values())
    return {
        "totalNonAir": total,
        "states": dict(state_counts.most_common()),
        "baseBlocks": dict(base_counts.most_common()),
        "layers": {str(y): dict(counter.most_common()) for y, counter in sorted(layer_counts.items())},
        "percentages": {state: count / total if total else 0.0 for state, count in state_counts.items()},
    }
