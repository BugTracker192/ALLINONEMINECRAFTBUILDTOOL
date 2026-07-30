from __future__ import annotations

from pathlib import Path

from .canonical import BuildDocument
from .compression import decompress_nbt
from .errors import FormatError
from .formats.legacy import parse_legacy
from .formats.litematic import parse_litematic
from .formats.sponge import parse_sponge
from .limits import NBTLimits
from .nbt import read_nbt


def detect_format(root_name: str, root: dict[str, object], filename: str) -> str:
    suffix = Path(filename).suffix.lower()
    if "Regions" in root and isinstance(root.get("Regions"), dict):
        return "litematic"
    schematic = root.get("Schematic") if isinstance(root.get("Schematic"), dict) else root
    if isinstance(schematic, dict) and "Version" in schematic and ("Blocks" in schematic or "BlockData" in schematic):
        return "sponge"
    if isinstance(schematic, dict) and all(key in schematic for key in ("Blocks", "Data", "Width", "Height", "Length")):
        return "legacy"
    if suffix == ".litematic":
        raise FormatError("LITEMATIC_STRUCTURE_MISSING", "File extension suggests Litematic, but the expected Regions compound is absent.")
    raise FormatError("UNKNOWN_STRUCTURE_FORMAT", "Could not detect a supported Minecraft structure format.", {"rootName": root_name, "suffix": suffix})


def import_build(data: bytes, filename: str = "upload.nbt", limits: NBTLimits | None = None) -> BuildDocument:
    suffix = Path(filename).suffix.lower()
    if suffix == ".mca":
        raise FormatError(
            "ANVIL_WORLD_UNSUPPORTED",
            "Anvil region/world saves are not supported; import a Sponge .schem, "
            "Litematic .litematic, or legacy .schematic file.",
            {
                "filename": filename,
                "supportedInputs": [".schem", ".litematic", ".schematic"],
                "scopeDecision": "schematic-files-only",
            },
        )
    limits = limits or NBTLimits()
    compression, decompressed = decompress_nbt(data, limits)
    document = read_nbt(decompressed, limits)
    detected = detect_format(document.root_name, document.root, filename)
    kwargs = {
        "filename": filename,
        "compressed": data,
        "decompressed": decompressed,
        "compression": compression,
        "limits": limits,
    }
    if detected == "sponge":
        return parse_sponge(document.root, **kwargs)
    if detected == "litematic":
        return parse_litematic(document.root, **kwargs)
    if detected == "legacy":
        return parse_legacy(document.root, **kwargs)
    raise AssertionError("unreachable format detector")
