"""Machine-local, project-independent, immutable OpenX asset versions."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .catalog import AssetFile, OpenXAsset, build_catalog
from .dependency_package import package_files
from .sim_archive import expand_sim_archives


def default_store_root() -> Path:
    base = os.environ.get("OPENX_DATA_DIR")
    if base:
        return Path(base).expanduser().resolve()
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "OpenXScenarioWorkbench"


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True, slots=True)
class AssetVersion:
    asset_id: str
    version_id: str
    version_number: int
    title: str
    source_name: str
    xosc_name: str
    xodr_name: str
    created_at: str
    content_sha256: str
    source_sha256: str
    files: tuple[dict[str, str], ...]
    compatibility: str = "not_tested"
    compatibility_detail: str = ""


class AssetStore:
    def __init__(self, root: Path | None = None):
        self.root = root or default_store_root()
        self.root.mkdir(parents=True, exist_ok=True)

    def _manifest_path(self, asset_id: str, version_id: str) -> Path:
        return self.root / "assets" / asset_id / version_id / "manifest.json"

    def versions(self) -> list[AssetVersion]:
        result = []
        for path in (self.root / "assets").glob("*/*/manifest.json"):
            payload = json.loads(path.read_text(encoding="utf-8"))
            payload["files"] = tuple(payload["files"])
            result.append(AssetVersion(**payload))
        return sorted(result, key=lambda item: (item.asset_id, item.version_number))

    def latest(self) -> list[AssetVersion]:
        by_id: dict[str, AssetVersion] = {}
        for version in self.versions():
            by_id[version.asset_id] = version
        return list(by_id.values())

    def import_files(self, files: list[AssetFile], *, progress=None, cancelled=None, report_sink=None) -> list[AssetVersion]:
        """Import each SIM independently and pair standalone files in one batch."""
        if not files:
            raise ValueError("Select at least one asset file.")
        existing = self.versions()
        imported: list[AssetVersion] = []
        def report(stage, current, done=0, total=0):
            if progress:
                progress(stage=stage, current=current, done=done, total=total, saved=len(imported))
            if cancelled and cancelled():
                raise InterruptedError("Import stopped; saved assets are retained.")

        def save_batch(expanded, source=None):
            report("parsing", source.name if source else "XOSC / XODR")
            assets = build_catalog(expanded)
            for index, asset in enumerate(assets):
                report("saving", asset.xosc_name, index, len(assets))
                original = source or next(item for item in expanded if item.name == asset.xosc_name)
                imported.append(self._save(asset, expanded, original, existing))
                report("saving", asset.xosc_name, index + 1, len(assets))

        standalone = [item for item in files if not item.name.casefold().endswith(".sim")]
        for sim in (item for item in files if item.name.casefold().endswith(".sim")):
            report("expanding", sim.name)
            expanded, reports = expand_sim_archives([sim, *[item for item in standalone if item.name.casefold().endswith(".xodr")]])
            if report_sink:
                for item in reports:
                    report_sink(item)
            save_batch(expanded, sim)
        for package in (item for item in files if item.name.casefold().endswith(".zip")):
            report("expanding", package.name)
            expanded = package_files(package.data)
            save_batch(expanded, package)
        if any(item.name.casefold().endswith(".xosc") for item in standalone):
            save_batch(standalone)
        if not imported:
            raise ValueError("No pairable XOSC/XODR scenario was found.")
        return imported

    def _save(self, asset: OpenXAsset, expanded: list[AssetFile], source: AssetFile,
              existing: list[AssetVersion]) -> AssetVersion:
        scenario = next(item for item in expanded if item.name == asset.xosc_name)
        road = next(item for item in reversed(expanded) if item.name == asset.xodr_name)
        logical = f"{source.name.casefold()}\0{asset.xosc_name.casefold()}".encode("utf-8")
        asset_id = _digest(logical)[:20]
        content_hash = _digest(source.data + b"\0" + scenario.data + b"\0" + road.data)
        version_id = content_hash[:20]
        old = next((v for v in existing if v.asset_id == asset_id and v.version_id == version_id), None)
        if old:
            return old
        number = 1 + max((v.version_number for v in existing if v.asset_id == asset_id), default=0)
        folder = self._manifest_path(asset_id, version_id).parent
        folder.mkdir(parents=True, exist_ok=True)
        payloads = (("source", source), ("scenario", scenario), ("road", road))
        records = []
        for role, item in payloads:
            suffix = PurePosixPath(item.name.replace("\\", "/")).suffix.lower()
            filename = f"{role}{suffix}"
            checksum = _digest(item.data)
            if role == "source":
                blob = self.root / "blobs" / checksum
                blob.parent.mkdir(parents=True, exist_ok=True)
                if not blob.exists():
                    with tempfile.NamedTemporaryFile("wb", dir=blob.parent, prefix="blob-",
                                                     suffix=".tmp", delete=False) as handle:
                        handle.write(item.data)
                        temporary = Path(handle.name)
                    temporary.replace(blob)
                records.append({"role": role, "original_name": item.name,
                                "blob_sha256": checksum, "sha256": checksum})
            else:
                (folder / filename).write_bytes(item.data)
                records.append({"role": role, "original_name": item.name,
                                "stored_name": filename, "sha256": checksum})
        if source.name.casefold().endswith(".zip"):
            for item in expanded:
                if item.name in {scenario.name, road.name}:
                    continue
                records.append({"role": "dependency", "original_name": item.name,
                                "archive_member": item.name, "sha256": _digest(item.data)})
        version = AssetVersion(asset_id, version_id, number, asset.title, source.name,
                               asset.xosc_name, asset.xodr_name,
                               datetime.now(timezone.utc).isoformat(), content_hash,
                               _digest(source.data), tuple(records))
        self._write_manifest(version)
        existing.append(version)
        return version

    def _write_manifest(self, version: AssetVersion) -> None:
        from dataclasses import asdict
        path = self._manifest_path(version.asset_id, version.version_id)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix="manifest-", suffix=".tmp", delete=False) as handle:
            json.dump(asdict(version), handle, ensure_ascii=False, indent=2)
            temporary = Path(handle.name)
        temporary.replace(path)

    def file_bytes(self, version: AssetVersion, role: str,
                   original_name: str | None = None) -> bytes:
        record = next(record for record in version.files
                      if record["role"] == role and
                      (original_name is None or record["original_name"] == original_name))
        if "archive_member" in record:
            with zipfile.ZipFile(io.BytesIO(self.file_bytes(version, "source"))) as archive:
                data = archive.read(record["archive_member"])
        elif "blob_sha256" in record:
            path = self.root / "blobs" / record["blob_sha256"]
            data = path.read_bytes()
        else:
            path = self._manifest_path(version.asset_id, version.version_id).parent / record["stored_name"]
            data = path.read_bytes()
        if _digest(data) != record["sha256"]:
            raise ValueError(f"Stored {role} file failed integrity check.")
        return data

    def catalog(self, *, latest_only: bool = True) -> tuple[list[OpenXAsset], dict[str, AssetVersion]]:
        assets: list[OpenXAsset] = []
        mapping: dict[str, AssetVersion] = {}
        for version in self.latest() if latest_only else self.versions():
            asset = self.load_asset(version)
            assets.append(asset)
            mapping[asset.asset_id] = version
        return assets, mapping

    def load_asset(self, version: AssetVersion) -> OpenXAsset:
        pair = [AssetFile(version.xosc_name, self.file_bytes(version, "scenario")),
                AssetFile(version.xodr_name, self.file_bytes(version, "road"))]
        asset = build_catalog(pair)[0]
        asset.asset_id = f"{version.asset_id}:{version.version_id}"
        return asset

    def set_compatibility(self, version: AssetVersion, status: str, detail: str = "") -> None:
        if status not in {"not_tested", "playable", "warning", "unsupported", "failed", "timeout"}:
            raise ValueError("Unknown compatibility status")
        from dataclasses import replace
        self._write_manifest(replace(version, compatibility=status, compatibility_detail=detail))

    def pin_version(self, project_id: str, version: AssetVersion) -> None:
        """Record a project/report dependency on an exact immutable asset version."""
        if not project_id.strip():
            raise ValueError("Project or report ID is required.")
        path = self.root / "version_references.json"
        references = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        key = f"{version.asset_id}:{version.version_id}"
        refs = set(references.get(key, []))
        refs.add(project_id)
        references[key] = sorted(refs)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.root,
                                         prefix="references-", suffix=".tmp", delete=False) as handle:
            json.dump(references, handle, ensure_ascii=False, indent=2)
            temporary = Path(handle.name)
        temporary.replace(path)

    def delete_version(self, version: AssetVersion) -> None:
        path = self.root / "version_references.json"
        references = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        if references.get(f"{version.asset_id}:{version.version_id}"):
            raise ValueError("This version is referenced by a saved project or report.")
        folder = self._manifest_path(version.asset_id, version.version_id).parent.resolve()
        assets_root = (self.root / "assets").resolve()
        if assets_root not in folder.parents or not (folder / "manifest.json").is_file():
            raise ValueError("Version directory is invalid or missing.")
        source_blobs = {item["blob_sha256"] for item in version.files if "blob_sha256" in item}
        shutil.rmtree(folder)
        still_used = {item["blob_sha256"] for remaining in self.versions()
                      for item in remaining.files if "blob_sha256" in item}
        blobs_root = (self.root / "blobs").resolve()
        for checksum in source_blobs - still_used:
            blob = (blobs_root / checksum).resolve()
            if blob.parent == blobs_root and blob.is_file():
                blob.unlink()

    def references(self, version: AssetVersion) -> tuple[str, ...]:
        path = self.root / "version_references.json"
        references = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return tuple(references.get(f"{version.asset_id}:{version.version_id}", []))
