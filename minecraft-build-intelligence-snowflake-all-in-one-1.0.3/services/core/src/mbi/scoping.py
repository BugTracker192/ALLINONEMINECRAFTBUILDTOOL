from __future__ import annotations

import copy
from dataclasses import replace

from .canonical import BuildDocument, BuildRegion, IntBoundingBox
from .voxel import ChunkedVoxelMap, iter_items_sorted


def scoped_document(document: BuildDocument, bounds: IntBoundingBox) -> BuildDocument:
    """Return an independent canonical view clipped to inclusive world bounds."""
    intersection = document.bounds.intersection(bounds)
    if intersection is None:
        raise ValueError("analysis bounds do not intersect the document")
    blocks = ChunkedVoxelMap()
    for position, palette_id in iter_items_sorted(document.blocks):
        if intersection.contains(position):
            blocks[position] = palette_id
    region_blocks = {}
    for name, values in document.region_blocks.items():
        selected = ChunkedVoxelMap()
        for position, palette_id in iter_items_sorted(values):
            if intersection.contains(position):
                selected[position] = palette_id
        if selected:
            region_blocks[name] = selected
    regions: list[BuildRegion] = []
    for region in document.regions:
        clipped = region.bounds.intersection(intersection)
        if clipped is not None:
            regions.append(
                replace(
                    region,
                    source_position=clipped.min,
                    source_signed_size=clipped.dimensions,
                    bounds=clipped,
                )
            )
    block_entities = [
        entity for entity in document.block_entities if intersection.contains(entity.position)
    ]
    entities = [
        entity
        for entity in document.entities
        if entity.position is not None
        and intersection.contains(
            type(intersection.min)(
                int(entity.position[0]),
                int(entity.position[1]),
                int(entity.position[2]),
            )
        )
    ]
    metadata = {
        **document.metadata,
        "scope": {
            "type": "bounds",
            "min": intersection.min.as_tuple(),
            "max": intersection.max.as_tuple(),
            "parent_content_hash": document.content_hash,
        },
    }
    return BuildDocument(
        schema_version=document.schema_version,
        build_id=document.build_id,
        source=document.source,
        metadata=copy.deepcopy(metadata),
        bounds=intersection,
        origin=intersection.min,
        palette=list(document.palette),
        regions=regions,
        blocks=blocks,
        region_blocks=region_blocks,
        block_entities=copy.deepcopy(block_entities),
        entities=copy.deepcopy(entities),
        pending_block_ticks=copy.deepcopy(document.pending_block_ticks),
        pending_fluid_ticks=copy.deepcopy(document.pending_fluid_ticks),
        diagnostics=list(document.diagnostics),
        extension_data=copy.deepcopy(document.extension_data),
    )
