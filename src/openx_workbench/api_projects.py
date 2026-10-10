"""Project routes: list, create, rename, delete, and the project's folder on this computer.

Paths never come from the client: folders are chosen in the native folder dialog on this machine,
and only the folders of known projects are opened.
"""

from __future__ import annotations

from pathlib import Path
from subprocess import TimeoutExpired
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import jobs
from .api_common import _store
from .api_schemas import (DeletedProject, OpenedFolder, OpenedProject, Project, ProjectList, ProjectLocation,
                          SelectedProject, documented)
from .local_folders import choose_folder, open_folder
from .preferences import interface_language, save_preferences
from .project_store import DATA, ProjectStore

router = APIRouter(prefix="/api/projects", tags=["projects"])

BUSY = ("该项目有任务正在进行（导入 PDF 或生成复用建议），请等它结束后再试。/ "
        "A job is running in this project (a PDF import or reuse suggestions); try again when it has finished.")
NO_DIALOG = ("无法打开文件夹选择窗口，请在本机桌面使用工作台。/ "
             "Could not open the folder browser. Use the workbench on this computer's desktop.")


def _json(project) -> dict[str, Any]:
    documents = Path(project.folder) / DATA / "documents"
    return {"project_id": project.project_id, "name": project.name, "created_at": project.created_at,
            "folder": project.folder, "pdf_count": sum(1 for _ in documents.glob("*/document.json"))}


def _idle(project_id: str) -> None:
    if jobs.busy(project_id):
        raise ValueError(BUSY)


def _choose(title: str, initial: Path) -> Path | None:
    try:
        return choose_folder(title, initial if initial.is_dir() else Path.home())
    except (OSError, ValueError, TimeoutExpired):
        raise ValueError(NO_DIALOG) from None


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class FolderRequest(BaseModel):
    target: Literal["project", "exports"] = "project"


@router.get("", **documented(ProjectList))
def projects() -> dict[str, Any]:
    store = ProjectStore(_store())
    store.refresh()
    last = store.last()
    return {"projects": [_json(item) for item in store.projects()], "missing": store.missing(),
            "last_project_id": last.project_id if last else None, "location": str(store.location())}


@router.post("", **documented(Project))
def create_project(request: ProjectRequest) -> dict[str, Any]:
    return _json(ProjectStore(_store()).create(request.name))


@router.post("/location", **documented(ProjectLocation))
def choose_location() -> dict[str, Any]:
    """Choose the folder new projects go to, in the native folder dialog."""
    store = ProjectStore(_store())
    folder = _choose("选择新项目的保存位置 / Choose where new projects are saved", store.location())
    if folder is not None:
        save_preferences(projects_dir=str(folder))
    return {"location": str(store.location()), "cancelled": folder is None}


@router.post("/open", **documented(OpenedProject))
def open_project() -> dict[str, Any]:
    """Add an existing project folder (moved by hand, or restored from the Recycle Bin) in the native dialog."""
    store = ProjectStore(_store())
    folder = _choose("选择 OpenX 项目文件夹 / Choose an OpenX project folder", store.location())
    return {"project": None if folder is None else _json(store.add(folder))}


@router.patch("/{project_id}", **documented(Project))
def rename_project(project_id: str, request: ProjectRequest) -> dict[str, Any]:
    _idle(project_id)
    return _json(ProjectStore(_store()).rename(project_id, request.name))


@router.delete("/{project_id}", **documented(DeletedProject))
def delete_project(project_id: str) -> dict[str, str]:
    """Move the project's folder to the Recycle Bin; one whose folder is already gone is only removed from the list."""
    _idle(project_id)
    ProjectStore(_store()).delete(project_id)
    return {"deleted": project_id}


@router.post("/{project_id}/select", **documented(SelectedProject))
def select_project(project_id: str) -> dict[str, str]:
    ProjectStore(_store()).set_last(project_id)
    return {"project_id": project_id}


@router.post("/{project_id}/open-folder", **documented(OpenedFolder))
def open_project_folder(project_id: str, request: FolderRequest) -> dict[str, str]:
    store = ProjectStore(_store())
    language = interface_language()
    path = store.folder(project_id) if request.target == "project" else store.exports(project_id, language)
    try:
        open_folder(path)
    except OSError:
        raise ValueError("无法打开此文件夹，请检查它是否仍然存在。/ Could not open this folder. Check that it still exists.") from None
    return {"opened": str(path)}
