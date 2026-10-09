"""Projects as folders the user owns, and version-pinned reuse decisions.

A project is a folder, by default `Documents\\OpenX 项目\\<name>`:

    <name>\\PDF\\        the imported PDFs, as the user gave them
    <name>\\导出\\       exported reuse assessments (`Exports` when created in English)
    <name>\\.openx\\     the workbench's own records: project.json, extracted scenes, saved reports

The data folder keeps a registry (`projects.json`) of where each project's folder is, and which
project was open last. The project ID never changes, so bindings, reports and requirements that
name a project keep finding it after a rename or a move. A data folder other than this machine's
own (a demo, a test) keeps its projects inside itself, under `projects`.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .atomic_write import write_bytes, write_json
from .asset_store import AssetStore, AssetVersion, default_store_root
from .store_lock import serialized, store_transaction

REGISTRY = "projects.json"
DATA = ".openx"
PDF_FOLDER = "PDF"
EXPORT_FOLDERS = {"zh": "导出", "en": "Exports"}
DEFAULT_PARENT = "OpenX 项目"
LEGACY = "projects"  # where projects lived before they were folders: <data>/projects/<id>/project.json
LEGACY_BACKUP = "projects-before-folders"
_INVALID = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{n}" for n in range(1, 10)), *(f"LPT{n}" for n in range(1, 10))}


@dataclass(frozen=True, slots=True)
class Project:
    project_id: str
    name: str
    created_at: str
    folder: str = ""


def folder_name(name: str) -> str:
    """A folder name Windows accepts, as close to the project's name as it allows."""
    text = _INVALID.sub("_", name).strip().rstrip(". ")[:80].rstrip(". ") or "project"
    return "_" + text if text.split(".")[0].upper() in _RESERVED else text


def _unique(parent: Path, base: str, keep: Path | None = None) -> Path:
    candidate, number = parent / base, 2
    while candidate.exists() and not (keep is not None and _same(candidate, keep)):
        candidate, number = parent / f"{base} ({number})", number + 1
    return candidate


def _same(a: Path, b: Path) -> bool:
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def _check_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise ValueError("Enter a project name.")
    if len(name) > 120:
        raise ValueError("Project name is too long.")
    return name


class ProjectStore:
    def __init__(self, assets: AssetStore | None = None):
        self.assets = assets or AssetStore()
        self.root = self.assets.root
        # This machine's own data folder: projects go to Documents, deleted ones to the Recycle Bin.
        self.own = _same(self.root, default_store_root()) and not os.environ.get("OPENX_DATA_DIR")

    # ---------- where projects are ----------

    def location(self) -> Path:
        """The folder new projects are created in."""
        if _same(self.root, default_store_root()):
            from .preferences import read_preferences
            chosen = read_preferences().get("projects_dir")
            if isinstance(chosen, str) and chosen.strip():
                return Path(chosen)
        if self.own:
            from .local_folders import documents_folder
            return documents_folder() / DEFAULT_PARENT
        return self.root / LEGACY

    def _registry(self) -> dict[str, Any]:
        try:
            value = json.loads((self.root / REGISTRY).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            value = {}
        entries = value.get("projects") if isinstance(value, dict) else None
        return {"projects": [item for item in entries or [] if isinstance(item, dict) and item.get("project_id")],
                "last": value.get("last") if isinstance(value, dict) else None}

    def _save_registry(self, registry: dict[str, Any]) -> None:
        self._write_json(self.root / REGISTRY, registry)

    @staticmethod
    def _read(folder: Path) -> Project | None:
        try:
            record = json.loads((folder / DATA / "project.json").read_text(encoding="utf-8"))
            return Project(record["project_id"], record["name"], record["created_at"], str(folder))
        except (OSError, ValueError, KeyError, TypeError):
            return None

    def _entries(self) -> list[tuple[dict[str, Any], Project | None]]:
        """Each registered project with what its folder holds, or None when the folder is gone."""
        result = []
        for entry in self._registry()["projects"]:
            project = self._read(Path(str(entry.get("folder", ""))))
            result.append((entry, project if project and project.project_id == entry["project_id"] else None))
        return result

    def projects(self) -> list[Project]:
        return sorted((project for _, project in self._entries() if project), key=lambda item: item.created_at)

    def missing(self) -> list[dict[str, str]]:
        """Registered projects whose folder was moved or deleted outside the workbench."""
        return [{"project_id": entry["project_id"], "name": str(entry.get("name", "")), "folder": str(entry.get("folder", ""))}
                for entry, project in self._entries() if project is None]

    def project(self, project_id: str) -> Project:
        found = next((item for item in self.projects() if item.project_id == project_id), None)
        if found is None:
            raise ValueError("Unknown project ID.")
        return found

    def folder(self, project_id: str) -> Path:
        return Path(self.project(project_id).folder)

    def data(self, project_id: str) -> Path:
        """The workbench's own records of a project."""
        return self.folder(project_id) / DATA

    def exports(self, project_id: str, language: str = "zh") -> Path:
        folder = self.folder(project_id)
        existing = next((folder / name for name in EXPORT_FOLDERS.values() if (folder / name).is_dir()), None)
        target = existing or folder / EXPORT_FOLDERS.get(language, EXPORT_FOLDERS["zh"])
        target.mkdir(parents=True, exist_ok=True)
        return target

    def keep_pdf(self, project_id: str, filename: str, data: bytes) -> Path:
        """A copy of an imported PDF in the project's PDF folder, under the name it was imported with."""
        return self._keep(self.folder(project_id), filename, data)

    @staticmethod
    def _keep(folder: Path, filename: str, data: bytes) -> Path:
        target = folder / PDF_FOLDER
        target.mkdir(parents=True, exist_ok=True)
        stem, suffix = os.path.splitext(folder_name(Path(filename).name))
        candidate, number = target / f"{stem}{suffix or '.pdf'}", 2
        while candidate.exists():
            if candidate.read_bytes() == data:
                return candidate
            candidate, number = target / f"{stem} ({number}){suffix or '.pdf'}", number + 1
        write_bytes(candidate, data, prefix="writing-", suffix=".tmp")
        return candidate

    # ---------- changes ----------

    @serialized
    def refresh(self) -> None:
        """Move projects kept in the old layout into folders, and register project folders found in the
        location new projects go to (restored from the Recycle Bin, or moved there by hand)."""
        self._migrate()
        registry = self._registry()
        known = {entry["project_id"] for entry in registry["projects"]}
        location = self.location()
        found = sorted(location.glob(f"*/{DATA}/project.json")) if location.is_dir() else []
        added = False
        for path in found:
            project = self._read(path.parent.parent)
            if project and project.project_id not in known:
                registry["projects"].append({"project_id": project.project_id, "name": project.name, "folder": project.folder})
                known.add(project.project_id)
                added = True
        if added:
            self._save_registry(registry)

    def _migrate(self) -> None:
        legacy = self.root / LEGACY
        old = [path.parent for path in sorted(legacy.glob("*/project.json"))] if legacy.is_dir() else []
        if not old:
            return
        registry = self._registry()
        location = self.location()
        backup = self.root / LEGACY_BACKUP
        for source in old:
            record = json.loads((source / "project.json").read_text(encoding="utf-8"))
            if not any(entry["project_id"] == record["project_id"] for entry in registry["projects"]):
                target = _unique(location, folder_name(record["name"]))
                shutil.copytree(source, target / DATA)
                self._hide(target / DATA)
                for manifest in sorted((target / DATA / "documents").glob("*/document.json")):
                    document = json.loads(manifest.read_text(encoding="utf-8"))
                    blob = self.root / "pdf_blobs" / document.get("sha256", "")
                    if document.get("sha256") and blob.is_file():
                        self._keep(target, document["filename"], blob.read_bytes())
                registry["projects"].append({"project_id": record["project_id"], "name": record["name"], "folder": str(target)})
                self._save_registry(registry)
            backup.mkdir(parents=True, exist_ok=True)
            shutil.move(str(source), str(_unique(backup, source.name)))
        last = legacy / "last_project.json"
        if last.is_file():
            try:
                registry["last"] = registry["last"] or json.loads(last.read_text(encoding="utf-8")).get("project_id")
            except ValueError:
                pass
            self._save_registry(registry)
            backup.mkdir(parents=True, exist_ok=True)
            shutil.move(str(last), str(_unique(backup, last.name)))

    @serialized
    def create(self, name: str) -> Project:
        name = _check_name(name)
        location = self.location()
        location.mkdir(parents=True, exist_ok=True)
        folder = _unique(location, folder_name(name))
        project = Project(uuid.uuid4().hex, name, datetime.now(timezone.utc).isoformat(), str(folder))
        (folder / DATA).mkdir(parents=True)
        self._hide(folder / DATA)
        (folder / PDF_FOLDER).mkdir()
        self._write_record(project)
        registry = self._registry()
        registry["projects"].append({"project_id": project.project_id, "name": name, "folder": str(folder)})
        registry["last"] = project.project_id
        self._save_registry(registry)
        return project

    @serialized
    def add(self, folder: Path) -> Project:
        """Register an existing project folder, such as one moved by hand; the same project moves there."""
        project = self._read(folder)
        if project is None:
            raise ValueError("这不是 OpenX 项目文件夹（缺少 .openx\\project.json）/ "
                             "This is not an OpenX project folder (.openx\\project.json is missing).")
        registry = self._registry()
        registry["projects"] = [entry for entry in registry["projects"] if entry["project_id"] != project.project_id]
        registry["projects"].append({"project_id": project.project_id, "name": project.name, "folder": project.folder})
        registry["last"] = project.project_id
        self._save_registry(registry)
        return project

    @serialized
    def rename(self, project_id: str, name: str) -> Project:
        """Rename a project, and its folder too when nothing holds that folder open."""
        name = _check_name(name)
        current = self.project(project_id)
        folder = Path(current.folder)
        target = _unique(folder.parent, folder_name(name), keep=folder)
        if target.name != folder.name:
            try:
                folder.rename(target)
                folder = target
            except OSError:
                pass  # a file inside is open elsewhere: the folder keeps its name
        project = Project(project_id, name, current.created_at, str(folder))
        self._write_record(project)
        registry = self._registry()
        for entry in registry["projects"]:
            if entry["project_id"] == project_id:
                entry.update(name=name, folder=str(folder))
        self._save_registry(registry)
        return project

    @serialized
    def delete(self, project_id: str) -> None:
        """Move a project's folder to the Recycle Bin and forget it; a project whose folder is already gone
        is only forgotten. Bindings and requirements are shared by every project and stay."""
        registry = self._registry()
        entry = next((item for item in registry["projects"] if item["project_id"] == project_id), None)
        if entry is None:
            raise ValueError("Unknown project ID.")
        present = any(item.project_id == project_id for item in self.projects())
        if present:
            folder = Path(entry["folder"])
            reports = {f"report:{path.stem}" for path in (folder / DATA / "reports").glob("*.json")}
            self._trash(folder)
            self.assets.release_references(reports)
        registry["projects"] = [item for item in registry["projects"] if item["project_id"] != project_id]
        if registry["last"] == project_id:
            registry["last"] = None
        self._save_registry(registry)

    def _trash(self, folder: Path) -> None:
        if self.own:
            from .local_folders import recycle
            try:
                recycle(folder)
            except OSError:
                raise ValueError("无法把项目文件夹移到回收站：里面可能有文件正被其他程序打开。/ "
                                 "Could not move the project folder to the Recycle Bin: a file in it may be open "
                                 "in another program.") from None
        else:
            trash = self.root / "trash"
            trash.mkdir(parents=True, exist_ok=True)
            shutil.move(str(folder), str(_unique(trash, folder.name)))

    def _hide(self, folder: Path) -> None:
        if self.own:
            from .local_folders import hide
            hide(folder)

    def _write_record(self, project: Project) -> None:
        record = {key: value for key, value in asdict(project).items() if key != "folder"}
        self._write_json(Path(project.folder) / DATA / "project.json", record)

    def last(self) -> Project | None:
        project_id = self._registry()["last"]
        return next((item for item in self.projects() if item.project_id == project_id), None)

    @serialized
    def set_last(self, project_id: str) -> None:
        self.project(project_id)
        registry = self._registry()
        registry["last"] = project_id
        self._save_registry(registry)

    # ---------- saved decisions ----------

    def save_decision(self, project_id: str, version: AssetVersion,
                      trace: dict[str, Any]) -> Path:
        if not any(item.project_id == project_id for item in self.projects()):
            raise ValueError("Select an existing project before saving.")
        candidate = trace.get("candidate") or {}
        if candidate.get("asset_id") != version.asset_id or candidate.get("version_id") != version.version_id:
            raise ValueError("Decision and selected asset version differ.")
        self._check_direct(trace, version)
        return self._save_report(project_id, trace, [version],
                                 asset_id=version.asset_id, version_id=version.version_id)

    def _check_direct(self, trace, version):
        if trace.get("reuse", {}).get("level") == "direct":
            from .schema_validation import standard_gate
            trusted = next((v for v in self.assets.versions()
                            if v.asset_id == version.asset_id and v.version_id == version.version_id), None)
            if trusted is None or not standard_gate(self.assets.load_asset(trusted).bundle.validation)["passed"]:
                raise ValueError("文件标准检查未通过或未完成，不能确认直接复用 / Standard checks must pass before confirming direct reuse.")

    def _save_report(self, project_id, trace, versions, **metadata) -> Path:
        report_id = uuid.uuid4().hex
        report = {"report_id": report_id, "project_id": project_id,
                  "saved_at": datetime.now(timezone.utc).isoformat(),
                  **metadata, "trace": trace}
        path = self.data(project_id) / "reports" / f"{report_id}.json"
        json.dumps(report, allow_nan=False)
        pinned = []
        # Pin first under the deletion guard. A crash may conservatively leave
        # an orphan pin, but never a report referring to a deleted version.
        with store_transaction(self.assets.root):
            try:
                for version in versions:
                    self.assets.pin_version(f"report:{report_id}", version)
                    pinned.append(version)
                self._write_json(path, report)
            except Exception:
                if not path.is_file():
                    for version in pinned:
                        self.assets.release_reference(f"report:{report_id}", version)
                raise
        return path

    def reports(self, project_id: str) -> list[dict[str, Any]]:
        folder = self.data(project_id) / "reports"
        return sorted((json.loads(path.read_text(encoding="utf-8")) for path in folder.glob("*.json")),
                      key=lambda item: item["saved_at"], reverse=True)

    def save_batch(self, project_id: str, trace: dict[str, Any]) -> Path:
        if not any(item.project_id == project_id for item in self.projects()):
            raise ValueError("Select an existing project before saving.")
        if trace.get("kind") != "batch_match":
            raise ValueError("Expected a document-wide assessment.")
        with store_transaction(self.assets.root):
            versions = {version.version_id: version for version in self.assets.versions()}
            selected = {}
            for entry in trace.get("entries", []):
                if entry.get("assessment", {}).get("level") == "direct" and not entry.get("candidates"):
                    raise ValueError("Direct reuse requires a checked asset candidate.")
                for index, candidate_trace in enumerate(entry.get("candidates", [])):
                    candidate = candidate_trace["candidate"]
                    version = versions.get(candidate.get("version_id"))
                    if version is None or version.asset_id != candidate.get("asset_id") or version.content_sha256 != candidate.get("content_sha256"):
                        raise ValueError("Batch contains an unavailable or mismatched asset version.")
                    direct = candidate_trace.get("reuse", {}).get("level") == "direct" or (
                        index == 0 and entry.get("assessment", {}).get("level") == "direct")
                    if direct:
                        self._check_direct({"reuse": {"level": "direct"}}, version)
                    selected[version.version_id] = version
            return self._save_report(project_id, trace, list(selected.values()))

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        write_json(path, value, ensure_ascii=False, indent=2, prefix="writing-", suffix=".tmp")
