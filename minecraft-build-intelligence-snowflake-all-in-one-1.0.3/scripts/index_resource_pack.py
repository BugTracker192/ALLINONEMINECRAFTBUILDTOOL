#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

from mbi.assets import safe_index_resource_zip


def main() -> None:
    parser = argparse.ArgumentParser(description="Safely extract the render-relevant subset of a Minecraft asset ZIP.")
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    manifest = safe_index_resource_zip(args.source, args.destination)
    print(f"Indexed {manifest.file_count} render assets; pack SHA-256 {manifest.pack_hash}")


if __name__ == "__main__":
    main()
