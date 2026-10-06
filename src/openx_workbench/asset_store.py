"""Machine-local, project-independent, immutable OpenX asset versions."""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

from .atomic_write import write_bytes, write_json
from .catalog import AssetFile, OpenXAsset, build_catalog, case_metadata_name
from .dependency_package import package_files
from .sim_archive import expand_sim_archives
from .store_lock import serialized


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

    @property
    def road_missing(self) -> bool:
        """The scenario's road is a simulator built-in map that was not imported: no preview or export."""
        return not any(record["role"] == "road" for record in self.files)


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
        road = next((item for item in reversed(expanded) if item.name == asset.xodr_name), None) if asset.xodr_name else None
        case = next((item for item in expanded if item.name == case_metadata_name(asset.xosc_name)), None)
        logical = f"{source.name.casefold()}\0{asset.xosc_name.casefold()}".encode("utf-8")
        asset_id = _digest(logical)[:20]
        content_hash = _digest(source.data + b"\0" + scenario.data + b"\0" + (road.data if road else b""))
        version_id = content_hash[:20]
        old = next((v for v in existing if v.asset_id == asset_id and v.version_id == version_id), None)
        if old:
            return self._backfill_case(old, case, existing)
        number = 1 + max((v.version_number for v in existing if v.asset_id == asset_id), default=0)
        folder = self._manifest_path(asset_id, version_id).parent
        folder.mkdir(parents=True, exist_ok=True)
        payloads = (("source", source), ("scenario", scenario), ("road", road), ("case", case))
        records = []
        for role, item in ((role, item) for role, item in payloads if item is not None):
            suffix = PurePosixPath(item.name.replace("\\", "/")).suffix.lower()
            filename = f"{role}{suffix}"
            checksum = _digest(item.data)
            if role == "source":
                blob = self.root / "blobs" / checksum
                blob.parent.mkdir(parents=True, exist_ok=True)
                if not blob.exists():
                    write_bytes(blob, item.data, prefix="blob-", suffix=".tmp")
                records.append({"role": role, "original_name": item.name,
                                "blob_sha256": checksum, "sha256": checksum})
            else:
                (folder / filename).write_bytes(item.data)
                records.append({"role": role, "original_name": item.name,
                                "stored_name": filename, "sha256": checksum})
        if source.name.casefold().endswith(".zip"):
            for item in expanded:
                if item.name in {scenario.name, road.name if road else None}:
                    continue
                records.append({"role": "dependency", "original_name": item.name,
                                "archive_member": item.name, "sha256": _digest(item.data)})
        version = AssetVersion(asset_id, version_id, number, asset.title, source.name,
                               asset.xosc_name, asset.xodr_name,
                               datetime.now(timezone.utc).isoformat(), content_hash,
                               _digest(source.data), tuple(records),
                               compatibility="road_missing" if road is None else "not_tested")
        self._write_manifest(version)
        existing.append(version)
        return version

    def _backfill_case(self, version: AssetVersion, case: AssetFile | None,
                       existing: list[AssetVersion]) -> AssetVersion:
        """Add SIM case metadata to a version imported before it was kept, or refresh it.

        The metadata is derived from the version's own source archive, so the
        version's content identity is unchanged; a newer import reads more of it.
        """
        stored = [record for record in version.files if record["role"] == "case"]
        if case is None or any(record["sha256"] == _digest(case.data) for record in stored):
            return version
        from dataclasses import replace
        folder = self._manifest_path(version.asset_id, version.version_id).parent
        write_bytes(folder / "case.json", case.data, prefix="case-", suffix=".tmp")
        record = {"role": "case", "original_name": case.name, "stored_name": "case.json",
                  "sha256": _digest(case.data)}
        updated = replace(version, files=(*(item for item in version.files if item["role"] != "case"), record))
        self._write_manifest(updated)
        existing[existing.index(version)] = updated
        return updated

    def _write_manifest(self, version: AssetVersion) -> None:
        from dataclasses import asdict
        path = self._manifest_path(version.asset_id, version.version_id)
        write_json(path, asdict(version), ensure_ascii=False, indent=2, prefix="manifest-", suffix=".tmp")

    def file_bytes(self, version: AssetVersion, role: str,
                   original_name: str | None = None) -> bytes:
        record = next((record for record in version.files
                       if record["role"] == role and
                       (original_name is None or record["original_name"] == original_name)), None)
        if record is None:
            if role == "road":
                raise FileNotFoundError("道路文件缺失：该场景引用的仿真软件内置道路未导入 / "
                                        "Road file missing: the simulator's built-in road was not imported.")
            raise KeyError(f"No {role} file in this version.")
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
        files = [AssetFile(version.xosc_name, self.file_bytes(version, "scenario"))]
        if not version.road_missing:
            files.append(AssetFile(version.xodr_name, self.file_bytes(version, "road")))
        if any(record["role"] == "case" for record in version.files):
            files.append(AssetFile(case_metadata_name(version.xosc_name), self.file_bytes(version, "case")))
        asset = build_catalog(files)[0]
        asset.asset_id = f"{version.asset_id}:{version.version_id}"
        from .classification import read_classification
        record = read_classification(self, version)
        # Preserve accepted labels even if a later model retry failed. Pending
        # rule/model suggestions do not certify a tested function.
        if record.get("final_accepted", record.get("status") in {"classified", "manual_confirmed"} and not record.get("needs_review", True)):
            asset.classification = record.get("final", {})
        return asset

    def set_compatibility(self, version: AssetVersion, status: str, detail: str = "") -> None:
        if status not in {"not_tested", "playable", "warning", "unsupported", "failed", "timeout", "road_missing"}:
            raise ValueError("Unknown compatibility status")
        from dataclasses import replace
        self._write_manifest(replace(version, compatibility=status, compatibility_detail=detail))

    @serialized
    def pin_version(self, project_id: str, version: AssetVersion) -> None:
        """Record a project/report dependency on an exact immutable asset version."""
        if not project_id.strip():
            raise ValueError("Project or report ID is required.")
        if not self._manifest_path(version.asset_id, version.version_id).is_file():
            raise ValueError("Cannot reference a missing asset version.")
        self._update_reference(project_id, version, add=True)

    @serialized
    def release_reference(self, reference_id: str, version: AssetVersion) -> None:
        """Release only the caller's reference after a failed report write."""
        self._update_reference(reference_id, version, add=False)

    def _update_reference(self, reference_id: str, version: AssetVersion, *, add: bool) -> None:
        path = self.root / "version_references.json"
        references = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        key = f"{version.asset_id}:{version.version_id}"
        refs = set(references.get(key, []))
        if add:
            refs.add(reference_id)
        else:
            refs.discard(reference_id)
        if refs:
            references[key] = sorted(refs)
        else:
            references.pop(key, None)
        write_json(path, references, ensure_ascii=False, indent=2, prefix="references-", suffix=".tmp")

    @serialized
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

    @serialized
    def references(self, version: AssetVersion) -> tuple[str, ...]:
        path = self.root / "version_references.json"
        references = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
        return tuple(references.get(f"{version.asset_id}:{version.version_id}", []))
