from __future__ import annotations

import json
import random
import tracemalloc
from types import GeneratorType

import pytest
from mbi.canonical import BuildDocument, IntBoundingBox, IntVector3
from mbi.canonical_reader import read_canonical_payload
from mbi.errors import FormatError, MBIError
from mbi.formats.sponge import parse_sponge
from mbi.formats.varint import (
    decode_unsigned_varints,
    encode_unsigned_varints,
    iter_unsigned_varints,
)
from mbi.importer import import_build
from mbi.limits import NBTLimits
from mbi.serialization import document_to_payload
from mbi.voxel import ChunkedVoxelMap

from app.project import load_document, save_document
from app.storage.filesystem import deterministic_json_bytes


def _legacy_hash(document: BuildDocument) -> str:
    import hashlib

    palette = [
        {"id": item.palette_id, "state": item.canonical_state}
        for item in sorted(document.palette, key=lambda item: item.palette_id)
    ]
    blocks = [
        [point.x, point.y, point.z, palette_id]
        for point, palette_id in sorted(document.blocks.items())
    ]
    regions = {
        name: [
            [point.x, point.y, point.z, palette_id]
            for point, palette_id in sorted(values.items())
        ]
        for name, values in sorted(document.region_blocks.items())
    }
    block_entities = [
        {
            "pos": item.position.as_tuple(),
            "id": item.namespaced_id,
            "region": item.region_name,
            "data": item.data,
        }
        for item in sorted(
            document.block_entities,
            key=lambda item: (item.region_name or "", item.position),
        )
    ]
    entities = [
        {
            "pos": item.position,
            "id": item.namespaced_id,
            "region": item.region_name,
            "data": item.data,
        }
        for item in sorted(
            document.entities,
            key=lambda item: (
                item.region_name or "",
                item.position or (0, 0, 0),
            ),
        )
    ]
    encoded = json.dumps(
        {
            "palette": palette,
            "blocks": blocks,
            "regions": regions,
            "blockEntities": block_entities,
            "entities": entities,
            "pendingBlockTicks": document.pending_block_ticks,
            "pendingFluidTicks": document.pending_fluid_ticks,
        },
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


def test_streamed_varints_match_list_and_preserve_all_errors() -> None:
    rng = random.Random(90125)
    for _ in range(100):
        values = [rng.randrange(2**31) for _ in range(rng.randrange(200))]
        encoded = encode_unsigned_varints(values)
        iterator = iter_unsigned_varints(encoded, expected_count=len(values))
        assert isinstance(iterator, GeneratorType)
        assert list(iterator) == decode_unsigned_varints(
            encoded,
            expected_count=len(values),
        )

    cases = (
        (b"\x00\x00", 1, "SPONGE_BLOCK_DATA_EXCESS"),
        (b"\x80\x80\x80\x80\x80", None, "SPONGE_VARINT_OVERFLOW"),
        (b"\x80", None, "SPONGE_VARINT_UNTERMINATED"),
        (b"\x00", 2, "SPONGE_BLOCK_DATA_LENGTH"),
    )
    for data, expected, code in cases:
        with pytest.raises(FormatError) as caught:
            list(iter_unsigned_varints(data, expected_count=expected))
        assert caught.value.code == code


def test_declared_limits_match_the_tested_large_schematic_envelope() -> None:
    limits = NBTLimits()
    assert limits.max_volume == 100_000_000
    assert limits.max_palette_size == 65_536


def test_anvil_region_input_fails_with_explicit_scope_error() -> None:
    with pytest.raises(FormatError) as caught:
        import_build(b"not-an-anvil-region", "r.0.0.mca")
    assert caught.value.code == "ANVIL_WORLD_UNSUPPORTED"
    assert caught.value.details["scopeDecision"] == "schematic-files-only"


def test_sponge_stream_rejects_first_unknown_palette_index() -> None:
    root = {
        "Version": 2,
        "Width": 1,
        "Height": 1,
        "Length": 2,
        "Palette": {"minecraft:air": 0},
        "BlockData": encode_unsigned_varints([1, 2]),
    }
    with pytest.raises(FormatError) as caught:
        parse_sponge(
            root,
            filename="bad.schem",
            compressed=b"",
            decompressed=b"",
            compression="none",
            limits=NBTLimits(),
        )
    assert caught.value.code == "PALETTE_INDEX_OUT_OF_RANGE"
    assert caught.value.details["index"] == 1


def test_streamed_content_hash_is_legacy_exact(
    sample_document: BuildDocument,
) -> None:
    assert sample_document.compute_content_hash() == _legacy_hash(sample_document)
    sample_document.region_blocks = {}
    sample_document.block_entities = []
    assert sample_document.compute_content_hash() == _legacy_hash(sample_document)
    sample_document.blocks.clear()
    assert sample_document.compute_content_hash() == _legacy_hash(sample_document)


def test_streaming_reader_matches_json_and_handles_negative_and_decoy(
    sample_document: BuildDocument,
    tmp_path,
) -> None:
    sample_document.extension_data["decoy"] = {
        "blocks": [[999, 999, 999, 999]],
        "text": 'brackets [{"] survive',
    }
    payload = document_to_payload(sample_document)
    path = tmp_path / "canonical.json"
    path.write_bytes(deterministic_json_bytes(payload))
    metadata, blocks, regions = read_canonical_payload(path)
    materialized = json.loads(path.read_text("utf-8"))
    assert metadata == {
        key: value
        for key, value in materialized.items()
        if key not in {"blocks", "regionBlocks"}
    }
    assert blocks == sample_document.blocks
    assert all(point.x < 0 or point.z < 0 for point in blocks if point.x < 0 or point.z < 0)
    assert regions == sample_document.region_blocks
    assert metadata["extensionData"]["decoy"]["blocks"] == [[999, 999, 999, 999]]


def test_streaming_writer_is_byte_identical_and_hash_tampering_is_rejected(
    sample_document: BuildDocument,
    tmp_path,
) -> None:
    run = tmp_path / "run"
    save_document(run, sample_document)
    expected = document_to_payload(sample_document)
    expected["offlineRunSchema"] = "mbi.offline-run.v1"
    expected["chunkManifest"] = "chunks/manifest.json"
    assert (run / "canonical.json").read_bytes() == deterministic_json_bytes(expected)
    version = next((run / "versions").glob("ver_*.json"))
    assert version.read_bytes() == (run / "canonical.json").read_bytes()

    payload = json.loads((run / "canonical.json").read_text("utf-8"))
    payload["blocks"][0][3] = 999
    (run / "canonical.json").write_bytes(deterministic_json_bytes(payload))
    with pytest.raises(MBIError) as caught:
        load_document(run)
    assert caught.value.code == "DOCUMENT_CONTENT_HASH_MISMATCH"


def test_streaming_varint_peak_does_not_scale_per_cell() -> None:
    encoded = b"\x00" * 2_000_000
    tracemalloc.start()
    count = sum(
        1
        for _ in iter_unsigned_varints(
            encoded,
            expected_count=2_000_000,
        )
    )
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert count == 2_000_000
    assert peak < 2_000_000


def test_chunked_voxels_are_dense_in_memory_and_negative_safe() -> None:
    values = ChunkedVoxelMap()
    for x in range(-16, 16):
        for y in range(-8, 8):
            for z in range(-16, 16):
                values[IntVector3(x, y, z)] = 7
    assert len(values) == 16_384
    assert values[IntVector3(-16, -8, -16)] == 7
    assert values.storage_bytes <= 16 * 16**3 * 4
    assert list(values) == sorted(values)


def test_bounded_reader_skips_outside_voxel_rows(
    sample_document: BuildDocument,
    tmp_path,
) -> None:
    path = tmp_path / "canonical.json"
    path.write_bytes(deterministic_json_bytes(document_to_payload(sample_document)))
    scope = IntBoundingBox(IntVector3(0, 0, 0), IntVector3(0, 2, 0))
    _, blocks, regions = read_canonical_payload(path, bounds=scope)
    assert all(scope.contains(point) for point in blocks)
    assert all(
        scope.contains(point)
        for values in regions.values()
        for point in values
    )
