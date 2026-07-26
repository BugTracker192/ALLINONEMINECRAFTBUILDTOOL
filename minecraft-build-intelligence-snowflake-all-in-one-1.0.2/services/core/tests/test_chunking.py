from __future__ import annotations

from mbi.chunking import CHUNK_VOLUME, ChunkEncoding, build_chunks, encode_chunk


def test_single_chunk_encoding() -> None:
    encoding, data = encode_chunk([3] * CHUNK_VOLUME, {0})
    assert encoding is ChunkEncoding.SINGLE
    assert len(data) == 4


def test_document_chunking_is_deterministic(sample_document) -> None:
    first = build_chunks(sample_document)
    second = build_chunks(sample_document)
    assert [item.content_hash for item in first] == [item.content_hash for item in second]
