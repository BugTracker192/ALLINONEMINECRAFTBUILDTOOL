"""Self-contained PEP 517 backend for the mandatory offline Snowflake profile.

The project deliberately avoids downloading setuptools/hatchling merely to build
its pure-Python wheel. Runtime dependencies remain declared in METADATA and are
installed normally by pip.
"""
from __future__ import annotations

import base64
import csv
import hashlib
import io
import os
import tarfile
import tomllib
import zipfile
from pathlib import Path
from typing import Iterable

NAME = "minecraft-build-intelligence"
DIST = "minecraft_build_intelligence"
ROOT = Path(__file__).resolve().parent
VERSION = str(tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]["version"])
DIST_INFO = f"{DIST}-{VERSION}.dist-info"
WHEEL_NAME = f"{DIST}-{VERSION}-py3-none-any.whl"


def get_requires_for_build_wheel(config_settings=None) -> list[str]:
    return []


def get_requires_for_build_sdist(config_settings=None) -> list[str]:
    return []


def _metadata() -> bytes:
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    text = f"""Metadata-Version: 2.3
Name: {NAME}
Version: {VERSION}
Summary: Offline Minecraft Java build intelligence, CPU rendering, AI tooling, editing, and verified export platform
Requires-Python: >=3.12
License-File: LICENSE
Requires-Dist: numpy<3,>=2.0
Requires-Dist: Pillow<13,>=12.3
Provides-Extra: ai
Requires-Dist: httpx<1,>=0.27; extra == 'ai'
Provides-Extra: security
Requires-Dist: cryptography<47,>=42; extra == 'security'
Provides-Extra: test
Requires-Dist: pytest<10,>=8; extra == 'test'
Requires-Dist: hypothesis<7,>=6.100; extra == 'test'
Description-Content-Type: text/markdown

{readme}
"""
    return text.encode("utf-8")


def _wheel() -> bytes:
    return b"Wheel-Version: 1.0\nGenerator: mbi-stdlib-backend 1\nRoot-Is-Purelib: true\nTag: py3-none-any\n"


def _entry_points() -> bytes:
    return b"[console_scripts]\nmbi = app.cli:main\n"


def _package_files() -> Iterable[tuple[str, Path]]:
    roots = ((ROOT / "app", "app"), (ROOT / "services" / "core" / "src" / "mbi", "mbi"))
    for source_root, wheel_root in roots:
        for path in sorted(source_root.rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(source_root).as_posix()
            include = path.suffix in {".py", ".pyi"} or relative.startswith("bundled_assets/")
            if not include:
                continue
            yield f"{wheel_root}/{relative}", path


def _hash(data: bytes) -> str:
    digest = base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode("ascii")
    return f"sha256={digest}"


def _zip_write(archive: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
    already_compressed = name.lower().endswith((".zip", ".jar", ".png", ".whl", ".gz", ".zst"))
    info.compress_type = zipfile.ZIP_STORED if already_compressed else zipfile.ZIP_DEFLATED
    info.external_attr = 0o644 << 16
    if already_compressed:
        archive.writestr(info, data)
    else:
        archive.writestr(info, data, compresslevel=9)


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None) -> str:
    target = Path(metadata_directory) / DIST_INFO
    target.mkdir(parents=True, exist_ok=True)
    (target / "METADATA").write_bytes(_metadata())
    (target / "WHEEL").write_bytes(_wheel())
    (target / "entry_points.txt").write_bytes(_entry_points())
    (target / "top_level.txt").write_text("app\nmbi\n", encoding="utf-8")
    return DIST_INFO


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None) -> str:
    destination = Path(wheel_directory)
    destination.mkdir(parents=True, exist_ok=True)
    output = destination / WHEEL_NAME
    records: list[tuple[str, str, str]] = []
    with zipfile.ZipFile(output, "w") as archive:
        for name, path in _package_files():
            data = path.read_bytes()
            _zip_write(archive, name, data)
            records.append((name, _hash(data), str(len(data))))
        fixed = {
            f"{DIST_INFO}/METADATA": _metadata(),
            f"{DIST_INFO}/WHEEL": _wheel(),
            f"{DIST_INFO}/entry_points.txt": _entry_points(),
            f"{DIST_INFO}/top_level.txt": b"app\nmbi\n",
            f"{DIST_INFO}/licenses/LICENSE": (ROOT / "LICENSE").read_bytes(),
            f"{DIST_INFO}/AUTONOMOUS_LLM_AGENT_GUIDE.md": (ROOT / "SNOWFLAKE_COCO_AUTONOMOUS_LLM_AGENT_GUIDE.md").read_bytes(),
            f"{DIST_INFO}/FINAL_SNOWFLAKE_COMPLIANCE_AUDIT.md": (ROOT / "FINAL_SNOWFLAKE_COMPLIANCE_AUDIT.md").read_bytes(),
        }
        for name, data in fixed.items():
            _zip_write(archive, name, data)
            records.append((name, _hash(data), str(len(data))))
        record_name = f"{DIST_INFO}/RECORD"
        buffer = io.StringIO(newline="")
        writer = csv.writer(buffer, lineterminator="\n")
        writer.writerows(records)
        writer.writerow((record_name, "", ""))
        _zip_write(archive, record_name, buffer.getvalue().encode("utf-8"))
    return output.name


def build_sdist(sdist_directory, config_settings=None) -> str:
    destination = Path(sdist_directory)
    destination.mkdir(parents=True, exist_ok=True)
    filename = f"{DIST}-{VERSION}.tar.gz"
    output = destination / filename
    prefix = f"{DIST}-{VERSION}"
    include = [
        "app",
        "services/core/src/mbi",
        "README.md",
        "LICENSE",
        "pyproject.toml",
        "build_backend.py",
        "constraints.txt",
        "SNOWFLAKE_COCO_AUTONOMOUS_LLM_AGENT_GUIDE.md",
        "FINAL_SNOWFLAKE_COMPLIANCE_AUDIT.md",
        "FINAL_SNOWFLAKE_COMPLIANCE_AUDIT.json",
    ]
    with output.open("wb") as raw:
        import gzip
        with gzip.GzipFile(fileobj=raw, mode="wb", mtime=0, filename="") as gz:
            with tarfile.open(fileobj=gz, mode="w") as tar:
                for item in include:
                    path = ROOT / item
                    paths = [path] if path.is_file() else sorted(p for p in path.rglob("*") if p.is_file())
                    for child in paths:
                        rel = child.relative_to(ROOT)
                        info = tar.gettarinfo(str(child), arcname=f"{prefix}/{rel.as_posix()}")
                        info.mtime = 0
                        info.uid = info.gid = 0
                        info.uname = info.gname = ""
                        with child.open("rb") as stream:
                            tar.addfile(info, stream)
    return filename
