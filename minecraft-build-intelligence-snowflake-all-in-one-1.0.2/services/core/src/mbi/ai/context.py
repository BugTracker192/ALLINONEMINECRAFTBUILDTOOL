from __future__ import annotations

from dataclasses import dataclass

from ..analysis import analyze_document
from ..canonical import BuildDocument


@dataclass(frozen=True, slots=True)
class ContextBudget:
    max_text_tokens: int
    max_images: int
    max_image_pixels: int
    reserve_output_tokens: int


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    kind: str
    payload: dict[str, object]
    estimated_tokens: int


def build_project_synopsis(document: BuildDocument) -> EvidenceItem:
    analysis = analyze_document(document)
    payload = {
        "summary": document.to_summary(),
        "majorMaterials": list(analysis["materials"]["states"].items())[:20],
        "componentCount": analysis["components"]["count"],
        "roomCount": analysis["rooms"]["interiorVolumeCount"],
        "diagnostics": [item.code for item in document.diagnostics],
    }
    return EvidenceItem(f"build:summary:{document.content_hash[:12]}", "project_synopsis", payload, 1000)


def run_length_slice(document: BuildDocument, y: int) -> EvidenceItem:
    palette = document.palette_by_id()
    rows: list[str] = []
    for z in range(document.bounds.min.z, document.bounds.max.z + 1):
        runs: list[str] = []
        start_x = document.bounds.min.x
        last_state = None
        for x in range(document.bounds.min.x, document.bounds.max.x + 2):
            if x <= document.bounds.max.x:
                pid = document.blocks.get(__import__("mbi.canonical", fromlist=["IntVector3"]).IntVector3(x, y, z))
                state = palette[pid].canonical_state if pid is not None else "minecraft:air"
            else:
                state = None
            if last_state is None:
                last_state = state
                start_x = x
            elif state != last_state:
                runs.append(f"X{start_x}-{x-1}={last_state}")
                last_state = state
                start_x = x
        rows.append(f"Y{y} Z{z}: " + " ".join(runs))
    payload = {"coordinateSpace": "document", "rows": rows}
    return EvidenceItem(f"slice:y:{y}:{document.content_hash[:12]}", "exact_slice", payload, max(100, len("\n".join(rows)) // 4))


def choose_context(document: BuildDocument, budget: ContextBudget, requested_y: int | None = None) -> list[EvidenceItem]:
    items = [build_project_synopsis(document)]
    if requested_y is not None:
        slice_item = run_length_slice(document, requested_y)
        if sum(item.estimated_tokens for item in items) + slice_item.estimated_tokens <= budget.max_text_tokens:
            items.append(slice_item)
    return items
