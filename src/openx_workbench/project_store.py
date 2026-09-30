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
        report_id = uuid.uuid4().hex
        report = {"report_id": report_id, "project_id": project_id,
                  "saved_at": datetime.now(timezone.utc).isoformat(),
                  "asset_id": version.asset_id, "version_id": version.version_id,
                  "trace": trace}
        self.assets.pin_version(f"report:{report_id}", version)
        path = self.root / project_id / "reports" / f"{report_id}.json"
        self._write_json(path, report)
        return path

    def reports(self, project_id: str) -> list[dict[str, Any]]:
        folder = self.root / project_id / "reports"
        if not any(item.project_id == project_id for item in self.projects()):
            raise ValueError("Unknown project ID.")
        return sorted((json.loads(path.read_text(encoding="utf-8")) for path in folder.glob("*.json")),
                      key=lambda item: item["saved_at"], reverse=True)

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix="writing-", suffix=".tmp", delete=False) as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2)
            temporary = Path(handle.name)
        temporary.replace(path)
