"""Projects as folders: layout, rename, delete, moving the old layout in, and saving exports there."""
import hashlib
import json
import shutil
from pathlib import Path

import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.pdf_store import PdfStore
from openx_workbench.project_store import DATA, PDF_FOLDER, ProjectStore, folder_name


def _pdf(text: str = "7.4.1 Cut-in scenario\nTarget vehicle cuts in. TTC = 3.0 s.") -> bytes:
    pymupdf = pytest.importorskip("pymupdf")
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), text)
    data = document.tobytes()
    document.close()
    return data


def test_folder_names_are_valid_on_windows():
    assert folder_name('AEB: "城市" <v2>?') == "AEB_ _城市_ _v2__"
    assert folder_name("  ..  ") == "project"
    assert folder_name("con") == "_con"
    assert folder_name("Report.") == "Report"


def test_a_project_is_a_folder_holding_its_pdfs(tmp_path):
    assets = AssetStore(tmp_path)
    projects = ProjectStore(assets)
    project = projects.create("IVISTA 城市 NOA")
    folder = Path(project.folder)
    assert folder == tmp_path / "projects" / "IVISTA 城市 NOA"
    assert json.loads((folder / DATA / "project.json").read_text(encoding="utf-8"))["name"] == "IVISTA 城市 NOA"
    assert projects.create("IVISTA 城市 NOA").folder.endswith("IVISTA 城市 NOA (2)")
    data = _pdf()
    document = PdfStore(assets).import_pdf(project.project_id, "protocol.pdf", data, "Test", engine="legacy")
    assert (folder / PDF_FOLDER / "protocol.pdf").read_bytes() == data
    assert (folder / DATA / "documents" / document.document_id / "document.json").is_file()
    assert projects.last().project_id != project.project_id  # the second project was created last


def test_rename_moves_the_folder_and_keeps_the_project(tmp_path):
    assets = AssetStore(tmp_path)
    projects = ProjectStore(assets)
    project = projects.create("Old name")
    document = PdfStore(assets).import_pdf(project.project_id, "rules.pdf", _pdf(), "Test", engine="legacy")
    renamed = projects.rename(project.project_id, "New name")
    assert renamed.project_id == project.project_id and Path(renamed.folder).name == "New name"
    assert not Path(project.folder).exists()
    assert [item.name for item in projects.projects()] == ["New name"]
    assert PdfStore(assets).scenes(project.project_id, document.document_id)


def test_delete_moves_the_folder_away_and_releases_its_reports(tmp_path):
    assets = AssetStore(tmp_path)
    projects = ProjectStore(assets)
    keep, gone = projects.create("Keep"), projects.create("Gone")
    (Path(gone.folder) / DATA / "reports").mkdir(parents=True)
    (Path(gone.folder) / DATA / "reports" / "r1.json").write_text("{}", encoding="utf-8")
    (tmp_path / "version_references.json").write_text(json.dumps({"a:v": ["report:r1", "binding:x"], "b:v": ["report:r1"]}),
                                                      encoding="utf-8")
    projects.delete(gone.project_id)
    assert [item.project_id for item in projects.projects()] == [keep.project_id]
    assert not Path(gone.folder).exists() and (tmp_path / "trash" / "Gone" / DATA / "project.json").is_file()
    assert json.loads((tmp_path / "version_references.json").read_text(encoding="utf-8")) == {"a:v": ["binding:x"]}
    assert projects.last() is None  # the deleted project was the last one opened


def test_a_folder_moved_by_hand_is_missing_until_it_is_added_again(tmp_path):
    assets = AssetStore(tmp_path)
    projects = ProjectStore(assets)
    project = projects.create("Moved")
    moved = tmp_path / "elsewhere" / "Moved"
    moved.parent.mkdir()
    shutil.move(project.folder, moved)
    assert projects.projects() == [] and projects.missing()[0]["project_id"] == project.project_id
    assert projects.add(moved).project_id == project.project_id
    assert projects.folder(project.project_id) == moved and projects.missing() == []
    with pytest.raises(ValueError, match="OpenX"):
        projects.add(tmp_path / "elsewhere")
    shutil.rmtree(moved)
    projects.delete(project.project_id)  # its folder is gone: only removed from the list
    assert projects.missing() == []


def test_projects_of_the_old_layout_move_into_folders(tmp_path):
    assets = AssetStore(tmp_path)
    data = _pdf()
    # The layout before projects were folders: <data>/projects/<id>/..., PDFs only in pdf_blobs.
    legacy = tmp_path / "projects" / "0123456789abcdef0123456789abcdef"
    (legacy / "reports").mkdir(parents=True)
    (legacy / "project.json").write_text(json.dumps({"project_id": legacy.name, "name": "CICAP NOA",
                                                     "created_at": "2026-10-06T14:21:11+00:00"}), encoding="utf-8")
    (legacy / "reports" / "r1.json").write_text("{}", encoding="utf-8")
    digest = hashlib.sha256(data).hexdigest()
    (tmp_path / "pdf_blobs").mkdir()
    (tmp_path / "pdf_blobs" / digest).write_bytes(data)
    manifest = legacy / "documents" / "0123456789abcdef0123" / "document.json"
    manifest.parent.mkdir(parents=True)
    manifest.write_text(json.dumps({"document_id": "0123456789abcdef0123", "project_id": legacy.name,
                                    "filename": "CICAP.pdf", "source_standard": "", "sha256": digest,
                                    "imported_at": "2026-10-06T14:22:00+00:00", "page_count": 1, "scene_count": 0}),
                        encoding="utf-8")
    (tmp_path / "projects" / "last_project.json").write_text(json.dumps({"project_id": legacy.name}), encoding="utf-8")

    projects = ProjectStore(assets)
    projects.refresh()
    folder = tmp_path / "projects" / "CICAP NOA"
    assert projects.folder(legacy.name) == folder and projects.last().project_id == legacy.name
    assert (folder / PDF_FOLDER / "CICAP.pdf").read_bytes() == data
    assert (folder / DATA / "reports" / "r1.json").is_file()
    assert [item.filename for item in PdfStore(assets).documents(legacy.name)] == ["CICAP.pdf"]
    assert not legacy.exists() and (tmp_path / "projects-before-folders" / legacy.name / "project.json").is_file()
    projects.refresh()  # nothing left to move
    assert len(projects.projects()) == 1


def test_project_routes(workbench, monkeypatch):
    client, base, _ = workbench
    listed = client.get("/api/projects").json()
    project = next(item for item in listed["projects"] if item["project_id"] == base["project_id"])
    assert project["pdf_count"] == 1 and listed["missing"] == [] and listed["location"].endswith("projects")
    renamed = client.patch(f"/api/projects/{base['project_id']}", json={"name": "Renamed"}).json()
    assert renamed["name"] == "Renamed" and Path(renamed["folder"]).name == "Renamed"

    from openx_workbench import jobs
    with monkeypatch.context() as patched:  # never monkeypatch.undo(): it would drop the fixture's data folder
        patched.setattr(jobs, "busy", lambda project: project == base["project_id"])
        refused = client.delete(f"/api/projects/{base['project_id']}")
    assert refused.status_code == 400 and "任务" in refused.json()["detail"]

    saved = client.post(f"/api/projects/{base['project_id']}/bindings/export",
                        json={"document_ids": [base["document_id"]], "format": "csv", "lang": "zh"}).json()
    path = Path(saved["path"])
    assert path.parent == Path(renamed["folder"]) / "导出" and "复用评估表" in saved["filename"]
    assert path.read_bytes().startswith("﻿".encode("utf-8"))

    opened = []
    monkeypatch.setattr("openx_workbench.api_projects.open_folder", opened.append)
    client.post(f"/api/projects/{base['project_id']}/open-folder", json={"target": "exports"})
    assert opened == [path.parent]

    assert client.delete(f"/api/projects/{base['project_id']}").json() == {"deleted": base["project_id"]}
    assert client.get("/api/projects").json()["projects"] == []


def test_library_status_answers_while_loading(workbench):
    client, _, _ = workbench
    client.get("/api/library")
    status = client.get("/api/library/status").json()
    assert status["catalog"]["state"] == "ready" and status["catalog"]["total"] == status["catalog"]["done"]
    assert status["encoder"]["state"] in {"idle", "loading", "ready"}
