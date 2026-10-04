from pathlib import Path

import pymupdf
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from openx_workbench import api
from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile
from openx_workbench.pdf_store import PdfStore
from openx_workbench.project_store import ProjectStore


def _pdf(title: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), f"7.4.1 {title} scenario\nTarget vehicle cuts in on a straight road. TTC = 3.0 s.")
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    api._cache.clear()
    assets = AssetStore()
    fixtures = Path(__file__).parent / "fixtures"
    version = assets.import_files([AssetFile(name, (fixtures / name).read_bytes())
                                   for name in ("minimal.xosc", "minimal.xodr")])[0]
    project = ProjectStore(assets).create("API")
    document = PdfStore(assets).import_pdf(project.project_id, "rules.pdf", _pdf("Cut-in"), "Test", engine="legacy")
    scene = PdfStore(assets).scenes(project.project_id, document.document_id)[0]
    base = {"project_id": project.project_id, "document_id": document.document_id,
            "scene_id": scene.scene_id, "encoder": "hashing"}
    yield TestClient(api.app, base_url="http://127.0.0.1"), base, version
    api._cache.clear()


def test_lists_projects_documents_and_scenes(workbench):
    client, base, _ = workbench
    projects = client.get("/api/projects").json()
    assert projects["last_project_id"] == base["project_id"]
    documents = client.get(f"/api/projects/{base['project_id']}/documents").json()
    assert documents[0]["filename"] == "rules.pdf" and documents[0]["size_bytes"] > 0
    scenes = client.get(f"/api/projects/{base['project_id']}/documents/{base['document_id']}/scenes").json()
    assert scenes[0]["scene_id"] == base["scene_id"] and scenes[0]["pages"] == [1, 1]
    page = client.get(f"/api/projects/{base['project_id']}/documents/{base['document_id']}/pages/1?width=200")
    assert page.headers["content-type"] == "image/png"
    clipped = client.get(f"/api/projects/{base['project_id']}/documents/{base['document_id']}/pages/1?width=100&clip=0,0,300,100")
    assert clipped.status_code == 200
    assert client.get(f"/api/projects/{base['project_id']}/documents/{base['document_id']}/pages/1?clip=1,2").status_code == 400


def test_search_returns_bare_ids_that_resolve_files_and_traces(workbench):
    client, base, version = workbench
    result = client.post("/api/search", json=base).json()
    candidate = result["results"][0]
    assert result["encoder"] == "hashing" and result["total"] == 1
    assert (candidate["asset_id"], candidate["version_id"]) == (version.asset_id, version.version_id)
    assert candidate["level"] in {"direct", "modify", "review", "new_build"}
    xosc = client.get(f"/api/assets/{version.asset_id}/versions/{version.version_id}/files/scenario")
    assert b"OpenSCENARIO" in xosc.content
    assert client.get(f"/api/assets/{version.asset_id}/versions/{version.version_id}/frame").status_code == 404
    trace = client.post("/api/trace", json={**base, "asset_id": version.asset_id, "version_id": version.version_id}).json()
    assert trace["candidate"]["version_id"] == version.version_id
    assert trace["source"]["scene_id"] == base["scene_id"]


def test_filters_and_validation(workbench):
    client, base, _ = workbench
    assert client.post("/api/search", json={**base, "filters": {"function_type": "nothing"}}).json()["total"] == 0
    assert client.post("/api/search", json={**base, "filters": {"colour": "red"}}).status_code == 400
    empty = client.post("/api/search", json={"project_id": base["project_id"], "encoder": "hashing"})
    assert empty.status_code == 400 and "Select a scene" in empty.json()["detail"]


def test_decisions_are_recomputed_and_guarded(workbench):
    client, base, version = workbench
    request = {**base, "asset_id": version.asset_id, "version_id": version.version_id}
    level = client.post("/api/search", json=base).json()["results"][0]["level"]
    saved = client.post("/api/decisions", json=request)
    if level == "review":
        assert saved.status_code == 400
    else:
        assert saved.status_code == 200
        reports = client.get(f"/api/projects/{base['project_id']}/reports").json()
        assert reports[0]["report_id"] == saved.json()["report_id"]
    stale = client.post("/api/decisions", json={**request, "version_id": "0" * 20})
    assert stale.status_code == 400 and "no longer the latest" in stale.json()["detail"]
    no_scene = {key: value for key, value in request.items() if key != "scene_id"}
    assert client.post("/api/decisions", json={**no_scene, "text": "cut in"}).status_code == 400
