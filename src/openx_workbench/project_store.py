"""Machine-local projects and version-pinned reuse decisions."""

from __future__ import annotations

import json
import tempfile
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .asset_store import AssetStore, AssetVersion
from .store_lock import store_transaction


@dataclass(frozen=True, slots=True)
class Project:
    project_id: str
    name: str
    created_at: str


class ProjectStore:
    def __init__(self, assets: AssetStore | None = None):
        self.assets = assets or AssetStore()
        self.root = self.assets.root / "projects"
        self.root.mkdir(parents=True, exist_ok=True)

    def projects(self) -> list[Project]:
        result = []
        for path in self.root.glob("*/project.json"):
            result.append(Project(**json.loads(path.read_text(encoding="utf-8"))))
        return sorted(result, key=lambda item: item.created_at)

    def create(self, name: str) -> Project:
        name = name.strip()
        if not name:
            raise ValueError("Enter a project name.")
        if len(name) > 120:
            raise ValueError("Project name is too long.")
        project = Project(uuid.uuid4().hex, name, datetime.now(timezone.utc).isoformat())
        folder = self.root / project.project_id
        folder.mkdir()
        self._write_json(folder / "project.json", asdict(project))
        self.set_last(project.project_id)
        return project

    def last(self) -> Project | None:
        path = self.root / "last_project.json"
        if not path.exists():
            return None
        project_id = json.loads(path.read_text(encoding="utf-8")).get("project_id")
        return next((item for item in self.projects() if item.project_id == project_id), None)

    def set_last(self, project_id: str) -> None:
        if not any(item.project_id == project_id for item in self.projects()):
            raise ValueError("Unknown project ID.")
        self._write_json(self.root / "last_project.json", {"project_id": project_id})

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
        path = self.root / project_id / "reports" / f"{report_id}.json"
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
        folder = self.root / project_id / "reports"
        if not any(item.project_id == project_id for item in self.projects()):
            raise ValueError("Unknown project ID.")
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
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix="writing-", suffix=".tmp", delete=False) as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            temporary = Path(handle.name)
        temporary.replace(path)
