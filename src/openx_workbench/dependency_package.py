"""Validate and stage a portable XOSC dependency ZIP without unsafe extraction."""

from __future__ import annotations

import io
import hashlib
import json
import stat
import zipfile
from pathlib import Path, PurePosixPath

from .catalog import AssetFile

MAX_FILES = 5000
MAX_TOTAL_BYTES = 500 * 1024 * 1024


def package_files(data: bytes) -> list[AssetFile]:
    files: list[AssetFile] = []
    total = 0
    seen: set[str] = set()
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        members = [member for member in archive.infolist() if not member.is_dir()]
        if len(members) > MAX_FILES:
            raise ValueError("Dependency package contains too many files.")
        for member in members:
            name = member.filename.replace("\\", "/")
            if (not name or name.startswith("/") or ":" in name or
                    any(part in {"", ".", ".."} for part in name.split("/")) or
                    stat.S_IFMT(member.external_attr >> 16) == stat.S_IFLNK):
                raise ValueError(f"Unsafe dependency package path: {name}")
            key = name.casefold()
            if key in seen:
                raise ValueError(f"Duplicate dependency package path: {name}")
            seen.add(key)
            total += member.file_size
            if total > MAX_TOTAL_BYTES:
                raise ValueError("Dependency package exceeds the size limit.")
            content = archive.read(member)
            if len(content) != member.file_size:
                raise ValueError(f"Incomplete dependency package file: {name}")
            files.append(AssetFile(name, content))
    if not any(file.name.casefold().endswith(".xosc") for file in files):
        raise ValueError("Dependency package contains no XOSC scenario.")
    audit_file = next((file for file in files if file.name == "audit.json"), None)
    if audit_file:
        try:
            audit = json.loads(audit_file.data)
        except (ValueError, UnicodeDecodeError):
            audit = {}
        if isinstance(audit, dict) and str(audit.get("export_version", "")).startswith("sim-standard-copy-"):
            from .standard_export import EXPORT_VERSION
            if audit["export_version"] != EXPORT_VERSION:
                raise ValueError("Standard export format is not supported.")
            if audit.get("ready") is not True:
                raise ValueError("诊断包不能作为标准副本导入 / Diagnostic package is not a standard copy.")
            selected = [audit_file]
            for role, name in (("scenario", "standard/scenario.xosc"), ("road", "standard/road.xodr")):
                item = next((file for file in files if file.name == name), None)
                hashes = audit.get("export_sha256") or {}
                if item is None or not isinstance(hashes, dict) or hashlib.sha256(item.data).hexdigest() != hashes.get(role):
                    raise ValueError("Standard export is incomplete or failed integrity verification.")
                selected.append(item)
            # The ZIP source blob retains every original byte. Only the checked
            # pair enters the catalog/staging, preventing original-road aliases
            # from being paired with the standard copy.
            return selected
    return files


def stage_package(data: bytes, root: Path) -> None:
    for item in package_files(data):
        target = root.joinpath(*PurePosixPath(item.name).parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(item.data)
