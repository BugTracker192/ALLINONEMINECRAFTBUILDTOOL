from __future__ import annotations

import base64
import gzip
import io
import json
from pathlib import Path
from typing import Any

from .canonical import (
    BuildDocument,
    BuildRegion,
    BuildSource,
    CanonicalBlockEntity,
    CanonicalEntity,
    ImportDiagnostic,
    IntBoundingBox,
    IntVector3,
    PaletteEntry,
)
from .errors import MBIError
from .voxel import ChunkedVoxelMap, iter_items_sorted

_SERIALIZATION_SCHEMA = "mbi.build-document.v2"
_COMPATIBLE_SCHEMAS = {_SERIALIZATION_SCHEMA, "mbi.build-document.v1"}
_DEFAULT_MAX_DECOMPRESSED_BYTES = 2 * 1024 * 1024 * 1024


class _DeferredBlockRows:
    pass


DEFERRED_BLOCK_ROWS = _DeferredBlockRows()


def _encode_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return {"$type": "bytes", "base64": base64.b64encode(value).decode("ascii")}
    if isinstance(value, tuple):
        return {"$type": "tuple", "items": [_encode_value(item) for item in value]}
    if isinstance(value, list):
        return [_encode_value(item) for item in value]
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise MBIError("DOCUMENT_SERIALIZATION_KEY", "Document dictionaries must use string keys.")
        return {key: _encode_value(item) for key, item in sorted(value.items())}
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise MBIError(
        "DOCUMENT_SERIALIZATION_TYPE",
        "Document contains an unsupported extension-data value.",
        {"type": type(value).__name__},
    )


def _decode_value(value: Any) -> Any:
    if isinstance(value, list):
        return [_decode_value(item) for item in value]
    if isinstance(value, dict):
        marker = value.get("$type")
        if marker == "bytes" and set(value) == {"$type", "base64"}:
            try:
                return base64.b64decode(value["base64"], validate=True)
            except (ValueError, TypeError) as exc:
                raise MBIError("DOCUMENT_SERIALIZATION_BASE64", "Document contains invalid base64 data.") from exc
        if marker == "tuple" and set(value) == {"$type", "items"} and isinstance(value["items"], list):
            return tuple(_decode_value(item) for item in value["items"])
        return {str(key): _decode_value(item) for key, item in value.items()}
    return value


def _vec(value: list[int] | tuple[int, int, int]) -> IntVector3:
    if len(value) != 3 or not all(isinstance(item, int) and not isinstance(item, bool) for item in value):
        raise MBIError("DOCUMENT_VECTOR_INVALID", "Document vector must contain exactly three integers.")
    return IntVector3(*value)


def _block_rows(values: dict[IntVector3, int]) -> list[list[int]]:
    return [
        [position.x, position.y, position.z, palette_id]
        for position, palette_id in iter_items_sorted(values)
    ]


def _read_block_rows(rows: Any) -> dict[IntVector3, int]:
    if not isinstance(rows, list):
        raise MBIError("DOCUMENT_BLOCK_INVALID", "Stored document block rows must be a list.")
    blocks = ChunkedVoxelMap()
    for row in rows:
        if not isinstance(row, list) or len(row) != 4 or not all(isinstance(item, int) for item in row):
            raise MBIError("DOCUMENT_BLOCK_INVALID", "Stored document contains an invalid block record.")
        blocks[IntVector3(row[0], row[1], row[2])] = row[3]
    return blocks


def document_to_payload(
    document: BuildDocument,
    *,
    defer_blocks: bool = False,
) -> dict[str, Any]:
    return {
        "serializationSchema": _SERIALIZATION_SCHEMA,
        "schemaVersion": document.schema_version,
        "buildId": document.build_id,
        "source": {
            "originalFilename": document.source.original_filename,
            "detectedFormat": document.source.detected_format,
            "compression": document.source.compression,
            "sourceSha256": document.source.source_sha256,
            "uploadedSizeBytes": document.source.uploaded_size_bytes,
            "decompressedSizeBytes": document.source.decompressed_size_bytes,
            "sourceDataVersion": document.source.source_data_version,
            "sourceFormatVersion": document.source.source_format_version,
        },
        "metadata": _encode_value(document.metadata),
        "bounds": {"min": list(document.bounds.min.as_tuple()), "max": list(document.bounds.max.as_tuple())},
        "origin": list(document.origin.as_tuple()),
        "palette": [
            {
                "paletteId": entry.palette_id,
                "namespace": entry.namespace,
                "blockName": entry.block_name,
                "properties": entry.properties,
                "canonicalState": entry.canonical_state,
                "isAirLike": entry.is_air_like,
                "isFluid": entry.is_fluid,
                "renderCategory": entry.render_category,
                "sourceLegacyId": entry.source_legacy_id,
                "sourceLegacyData": entry.source_legacy_data,
                "requiredModNamespace": entry.required_mod_namespace,
                "diagnostics": list(entry.diagnostics),
            }
            for entry in document.palette
        ],
        "regions": [
            {
                "name": region.name,
                "sourcePosition": list(region.source_position.as_tuple()),
                "sourceSignedSize": list(region.source_signed_size.as_tuple()),
                "bounds": {"min": list(region.bounds.min.as_tuple()), "max": list(region.bounds.max.as_tuple())},
                "paletteStates": list(region.palette_states),
                "extensionData": _encode_value(region.extension_data),
            }
            for region in document.regions
        ],
        "blocks": DEFERRED_BLOCK_ROWS if defer_blocks else _block_rows(document.blocks),
        "regionBlocks": (
            DEFERRED_BLOCK_ROWS
            if defer_blocks
            else {
                name: _block_rows(values)
                for name, values in sorted(document.region_blocks.items())
            }
        ),
        "blockEntities": [
            {
                "position": list(item.position.as_tuple()),
                "namespacedId": item.namespaced_id,
                "data": _encode_value(item.data),
                "regionName": item.region_name,
            }
            for item in document.block_entities
        ],
        "entities": [
            {
                "namespacedId": item.namespaced_id,
                "position": list(item.position) if item.position is not None else None,
                "data": _encode_value(item.data),
                "regionName": item.region_name,
            }
            for item in document.entities
        ],
        "pendingBlockTicks": _encode_value(document.pending_block_ticks),
        "pendingFluidTicks": _encode_value(document.pending_fluid_ticks),
        "diagnostics": [
            {"code": item.code, "severity": item.severity, "message": item.message, "details": _encode_value(item.details)}
            for item in document.diagnostics
        ],
        "extensionData": _encode_value(document.extension_data),
        "contentHash": document.content_hash,
    }


def document_from_payload(
    payload: dict[str, Any],
    *,
    blocks: Any = None,
    region_blocks: Any = None,
) -> BuildDocument:
    schema = payload.get("serializationSchema")
    if schema not in _COMPATIBLE_SCHEMAS:
        raise MBIError(
            "DOCUMENT_SERIALIZATION_SCHEMA",
            "Unsupported stored document schema.",
            {"schema": schema},
        )
    try:
        source_raw = payload["source"]
        bounds_raw = payload["bounds"]
        palette = [
            PaletteEntry(
                palette_id=item["paletteId"],
                namespace=item["namespace"],
                block_name=item["blockName"],
                properties={str(key): str(value) for key, value in item["properties"].items()},
                canonical_state=item["canonicalState"],
                is_air_like=item["isAirLike"],
                is_fluid=item["isFluid"],
                render_category=item["renderCategory"],
                source_legacy_id=item.get("sourceLegacyId"),
                source_legacy_data=item.get("sourceLegacyData"),
                required_mod_namespace=item.get("requiredModNamespace"),
                diagnostics=tuple(item.get("diagnostics", [])),
            )
            for item in payload["palette"]
        ]
        regions = [
            BuildRegion(
                name=item["name"],
                source_position=_vec(item["sourcePosition"]),
                source_signed_size=_vec(item["sourceSignedSize"]),
                bounds=IntBoundingBox(_vec(item["bounds"]["min"]), _vec(item["bounds"]["max"])),
                palette_states=tuple(item["paletteStates"]),
                extension_data=_decode_value(item.get("extensionData", {})),
            )
            for item in payload["regions"]
        ]
        parsed_blocks = (
            blocks if blocks is not None else _read_block_rows(payload["blocks"])
        )
        if region_blocks is None:
            region_blocks_raw = payload.get("regionBlocks", {})
            if not isinstance(region_blocks_raw, dict):
                raise MBIError("DOCUMENT_REGION_BLOCKS_INVALID", "Stored document regionBlocks must be an object.")
            parsed_region_blocks = {
                str(name): _read_block_rows(rows)
                for name, rows in region_blocks_raw.items()
            }
        else:
            parsed_region_blocks = region_blocks
        block_entities = [
            CanonicalBlockEntity(
                _vec(item["position"]),
                item.get("namespacedId"),
                _decode_value(item.get("data", {})),
                item.get("regionName"),
            )
            for item in payload.get("blockEntities", [])
        ]
        entities = [
            CanonicalEntity(
                item.get("namespacedId"),
                tuple(float(value) for value in item["position"]) if item.get("position") is not None else None,
                _decode_value(item.get("data", {})),
                item.get("regionName"),
            )
            for item in payload.get("entities", [])
        ]
        diagnostics = [
            ImportDiagnostic(item["code"], item["severity"], item["message"], _decode_value(item.get("details", {})))
            for item in payload.get("diagnostics", [])
        ]
        document = BuildDocument(
            schema_version=payload["schemaVersion"],
            build_id=payload["buildId"],
            source=BuildSource(
                original_filename=source_raw["originalFilename"],
                detected_format=source_raw["detectedFormat"],
                compression=source_raw["compression"],
                source_sha256=source_raw["sourceSha256"],
                uploaded_size_bytes=source_raw["uploadedSizeBytes"],
                decompressed_size_bytes=source_raw["decompressedSizeBytes"],
                source_data_version=source_raw.get("sourceDataVersion"),
                source_format_version=source_raw.get("sourceFormatVersion"),
            ),
            metadata=_decode_value(payload.get("metadata", {})),
            bounds=IntBoundingBox(_vec(bounds_raw["min"]), _vec(bounds_raw["max"])),
            origin=_vec(payload["origin"]),
            palette=palette,
            regions=regions,
            blocks=parsed_blocks,
            region_blocks=parsed_region_blocks,
            block_entities=block_entities,
            entities=entities,
            pending_block_ticks=_decode_value(payload.get("pendingBlockTicks", [])),
            pending_fluid_ticks=_decode_value(payload.get("pendingFluidTicks", [])),
            diagnostics=diagnostics,
            extension_data=_decode_value(payload.get("extensionData", {})),
            content_hash=payload.get("contentHash", ""),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise MBIError("DOCUMENT_SERIALIZATION_INVALID", "Stored document payload is invalid.") from exc
    computed = document.compute_content_hash()
    # v1 hashes did not include region voxel fields or entities/ticks. Accept and migrate
    # them once, then all subsequent writes use the stronger v2 hash.
    if schema == "mbi.build-document.v1":
        document.content_hash = computed
    elif document.content_hash != computed:
        raise MBIError(
            "DOCUMENT_CONTENT_HASH_MISMATCH",
            "Stored document content hash does not match its canonical data.",
            {"stored": document.content_hash, "computed": computed},
        )
    return document


def serialize_document(document: BuildDocument) -> bytes:
    document.content_hash = document.compute_content_hash()
    raw = json.dumps(document_to_payload(document), sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    output = io.BytesIO()
    with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as stream:
        stream.write(raw)
    return output.getvalue()


def deserialize_document(data: bytes, *, max_decompressed_bytes: int = _DEFAULT_MAX_DECOMPRESSED_BYTES) -> BuildDocument:
    output = bytearray()
    try:
        with gzip.GzipFile(fileobj=io.BytesIO(data), mode="rb") as stream:
            while chunk := stream.read(1024 * 1024):
                output.extend(chunk)
                if len(output) > max_decompressed_bytes:
                    raise MBIError(
                        "DOCUMENT_DECOMPRESSED_SIZE_LIMIT",
                        "Stored document exceeds the decompressed-size limit.",
                        {"limitBytes": max_decompressed_bytes},
                    )
    except (gzip.BadGzipFile, EOFError, OSError) as exc:
        raise MBIError("DOCUMENT_COMPRESSION_INVALID", "Stored document is not valid gzip data.") from exc
    try:
        payload = json.loads(output)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise MBIError("DOCUMENT_JSON_INVALID", "Stored document JSON is invalid.") from exc
    if not isinstance(payload, dict):
        raise MBIError("DOCUMENT_SERIALIZATION_INVALID", "Stored document root must be an object.")
    return document_from_payload(payload)


def write_document(path: Path, document: BuildDocument) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.writing")
    try:
        temporary.write_bytes(serialize_document(document))
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def read_document(path: Path, *, max_decompressed_bytes: int = _DEFAULT_MAX_DECOMPRESSED_BYTES) -> BuildDocument:
    return deserialize_document(path.read_bytes(), max_decompressed_bytes=max_decompressed_bytes)
