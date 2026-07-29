from __future__ import annotations

from ..canonical import BuildDocument, IntVector3


def reflection_symmetry(document: BuildDocument) -> dict[str, object]:
    palette = document.palette_by_id()
    state_at = {position: palette[pid].canonical_state for position, pid in document.blocks.items()}
    results: dict[str, object] = {}
    for axis in ("x", "z"):
        minimum = getattr(document.bounds.min, axis)
        maximum = getattr(document.bounds.max, axis)
        mismatches: list[tuple[tuple[int, int, int], tuple[int, int, int]]] = []
        mismatch_count = 0
        checked = set()
        for position in state_at:
            coords = [position.x, position.y, position.z]
            index = 0 if axis == "x" else 2
            coords[index] = minimum + maximum - coords[index]
            mirror = IntVector3(*coords)
            pair = tuple(sorted((position, mirror)))
            if pair in checked:
                continue
            checked.add(pair)
            if state_at.get(position, "minecraft:air") != state_at.get(mirror, "minecraft:air"):
                mismatch_count += 1
                if len(mismatches) < 200:
                    mismatches.append((position.as_tuple(), mirror.as_tuple()))
        score = 1.0 - (mismatch_count / max(1, len(checked)))
        results[axis] = {
            "exactScore": max(0.0, score),
            "scoreLowerBound": max(0.0, score),
            "checkedPairCount": len(checked),
            "mismatchCount": mismatch_count,
            "sampleMismatches": mismatches,
            "sampleCapped": mismatch_count > len(mismatches),
            "exactPass": True,
        }
    return results
