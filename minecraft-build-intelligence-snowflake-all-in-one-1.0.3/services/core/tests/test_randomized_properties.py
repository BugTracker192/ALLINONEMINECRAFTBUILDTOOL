from __future__ import annotations

import hashlib
import random

from mbi.canonical import BuildDocument, BuildRegion, BuildSource, IntBoundingBox, IntVector3, PaletteEntry
from mbi.export.litematic import export_litematic
from mbi.export.sponge import export_sponge_v3
from mbi.export.verify import verify_round_trip
from mbi.formats.litematic import bits_per_entry, pack_block_states, unpack_block_states
from mbi.patch import PatchEngine


def test_random_bit_packing_and_export_properties() -> None:
    randomizer = random.Random(91337)
    for palette_size in [1, 2, 3, 4, 5, 8, 9, 16, 17, 31, 32, 33, 255, 256, 257]:
        bits = bits_per_entry(palette_size)
        values = [randomizer.randrange(palette_size) for _ in range(173)]
        assert unpack_block_states(pack_block_states(values, bits), len(values), bits) == values

    for case in range(12):
        size = IntVector3(randomizer.randint(2, 7), randomizer.randint(2, 5), randomizer.randint(2, 7))
        bounds = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(size.x - 1, size.y - 1, size.z - 1))
        palette = [PaletteEntry.from_state(0, "minecraft:air"), PaletteEntry.from_state(1, "minecraft:stone"), PaletteEntry.from_state(2, "minecraft:glass")]
        blocks = {point: randomizer.choice((1, 2)) for point in bounds.iter_points() if randomizer.random() < 0.35}
        source = BuildSource("random", "generated", "raw_nbt", hashlib.sha256(f"random-{case}".encode()).hexdigest(), 0, 0, 3953, 1)
        region = BuildRegion("Main", bounds.min, size, bounds, tuple(p.canonical_state for p in palette))
        document = BuildDocument("1.1.0", f"random_{case}", source, {}, bounds, bounds.min, palette, [region], blocks, region_blocks={"Main": dict(blocks)})
        for data, filename in ((export_sponge_v3(document), "x.schem"), (export_litematic(document), "x.litematic")):
            report = verify_round_trip(document, data, filename)
            assert report.valid, report.messages


def test_random_patch_rollback_restores_hash(sample_document) -> None:
    randomizer = random.Random(77)
    for _ in range(20):
        engine = PatchEngine(sample_document)
        point = randomizer.choice(list(sample_document.bounds.iter_points()))
        patch = engine.create_patch(
            "random", "property", IntBoundingBox(point, point), 1,
            [{"type": "set_block", "position": list(point.as_tuple()), "state": randomizer.choice(["minecraft:diamond_block", "minecraft:air", "minecraft:redstone_block"])}],
            expected_parent_hash=sample_document.content_hash,
        )
        engine.validate(patch)
        engine.preview(patch)
        engine.commit(patch)
        assert engine.undo().document.content_hash == sample_document.content_hash
