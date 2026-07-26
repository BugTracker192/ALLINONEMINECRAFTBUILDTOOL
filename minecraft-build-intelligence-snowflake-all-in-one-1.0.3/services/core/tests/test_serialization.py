from __future__ import annotations

import gzip
import json

import pytest

from mbi.errors import MBIError
from mbi.serialization import deserialize_document, document_to_payload, serialize_document


def test_document_serialization_round_trip(sample_document) -> None:
    sample_document.extension_data["raw"] = b"\x00\xff"
    encoded = serialize_document(sample_document)
    restored = deserialize_document(encoded)
    assert restored.content_hash == sample_document.content_hash
    assert restored.blocks == sample_document.blocks
    assert restored.palette == sample_document.palette
    assert restored.extension_data["raw"] == b"\x00\xff"


def test_document_serialization_is_deterministic(sample_document) -> None:
    assert serialize_document(sample_document) == serialize_document(sample_document)


def test_document_serialization_rejects_tampered_hash(sample_document) -> None:
    payload = document_to_payload(sample_document)
    payload["blocks"][0][3] = 2
    data = gzip.compress(json.dumps(payload).encode("utf-8"), mtime=0)
    with pytest.raises(MBIError) as error:
        deserialize_document(data)
    assert error.value.code == "DOCUMENT_CONTENT_HASH_MISMATCH"


def test_document_serialization_enforces_decompressed_limit(sample_document) -> None:
    data = serialize_document(sample_document)
    with pytest.raises(MBIError) as error:
        deserialize_document(data, max_decompressed_bytes=10)
    assert error.value.code == "DOCUMENT_DECOMPRESSED_SIZE_LIMIT"
