from __future__ import annotations

import copy
from dataclasses import replace

from .canonical import BuildDocument, BuildRegion, IntBoundingBox


def scoped_document(document: BuildDocument, bounds: IntBoundingBox) -> BuildDocument:
    """Return an independent canonical view clipped to inclusive world bounds."""
    intersection = document.bounds.intersection(bounds)
    if intersection is None:
        raise ValueError("analysis bounds do not intersect the document")
    scoped = copy.deepcopy(document)
    scoped.bounds = intersection
    scoped.blocks = {
        position: palette_id
        for position, palette_id in document.blocks.items()
        if intersection.contains(position)
    }
    scoped.region_blocks = {
        name: {
            position: palette_id
            for position, palette_id in blocks.items()
            if intersection.contains(position)
        }
        for name, blocks in document.region_blocks.items()
    }
    scoped.region_blocks = {name: blocks for name, blocks in scoped.region_blocks.items() if blocks}
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
    scoped.regions = regions
    scoped.block_entities = [
        entity for entity in document.block_entities if intersection.contains(entity.position)
    ]
    scoped.entities = [
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
    scoped.metadata = {
        **document.metadata,
        "scope": {
            "type": "bounds",
            "min": intersection.min.as_tuple(),
            "max": intersection.max.as_tuple(),
            "parent_content_hash": document.content_hash,
        },
    }
    scoped.content_hash = scoped.compute_content_hash()
    return scoped
