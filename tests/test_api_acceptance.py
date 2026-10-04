"""Workflow acceptance through the HTTP API (ported from the retired Streamlit AppTest suite)."""
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
from openx_workbench.report_html import render_report

FIXTURES = Path(__file__).parent / "fixtures"
SCENARIO = (FIXTURES / "minimal.xosc").read_bytes()
ROAD = (FIXTURES / "minimal.xodr").read_bytes()


@pytest.fixture
def space(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    api._cache.clear()
    assets = AssetStore()
    version = assets.import_files([AssetFile("minimal.xosc", SCENARIO), AssetFile("minimal.xodr", ROAD)])[0]
    project = ProjectStore(assets).create("Acceptance")
    yield TestClient(api.app, base_url="http://127.0.0.1"), assets, project.project_id, version
    api._cache.clear()


def _document(assets, project_id, *pages):
    with pymupdf.open() as document:
        for text in pages:
            document.new_page().insert_text((72, 72), text)
        return PdfStore(assets).import_pdf(project_id, "authored-acceptance.pdf", document.tobytes(), engine="legacy")


def test_saved_decision_is_a_snapshot_of_revision_version_and_explanation(space):
    client, assets, project_id, version = space
    record = _document(assets, project_id, "7.4.1 Cut-in scenario\nTarget vehicle cuts in on a straight road.",
                       "Test vehicle approaches the target vehicle. TTC = 3.0 s.")
    original = PdfStore(assets).scenes(project_id, record.document_id)[0].package.evidence
    scene_url = f"/api/projects/{project_id}/documents/{record.document_id}/scenes/scene-0001"
    assert client.post(scene_url + "/revisions", json={"edits": {"title": "Reviewed cut-in"}}).json()["revision"] == 2

    request = {"project_id": project_id, "document_id": record.document_id, "scene_id": "scene-0001",
               "encoder": "hashing", "asset_id": version.asset_id, "version_id": version.version_id}
    explanation = client.post("/api/explanation", json={**request, "mode": "structural"}).json()
    level = client.post("/api/search", json=request).json()["results"][0]["level"]
    assert level != "review"
    saved = client.post("/api/decisions", json={**request, "explanation_id": explanation["explanation_id"]})
    assert saved.status_code == 200
    report = ProjectStore(assets).reports(project_id)[0]
    trace = report["trace"]
    assert (trace["source"]["revision"], trace["source"]["title"]) == (2, "Reviewed cut-in")
    assert trace["source"]["evidence"][0]["page_end"] == 2
    assert trace["candidate"]["version_id"] == version.version_id
    assert trace["explanation"]["method"] == "structural"
    assert "authored-acceptance.pdf" in render_report(trace)
    queue = client.get(f"/api/projects/{project_id}/documents/{record.document_id}/scenes").json()
    assert queue[0]["queue_status"] == "assessed"

    # Later facts and a newer asset version leave the saved report and its pinned version untouched.
    newer = assets.import_files([AssetFile("minimal.xosc", SCENARIO.replace(b"Minimal cut-in", b"Updated cut-in")),
                                 AssetFile("minimal.xodr", ROAD)])[0]
    client.post(scene_url + "/revisions", json={"edits": {"title": "Later revision"}})
    assert newer.version_id != version.version_id
    assert ProjectStore(assets).reports(project_id)[0] == report
    assert assets.references(version)
    detail = client.get(f"/api/projects/{project_id}/reports/{report['report_id']}").json()
    assert detail["reopenable"] == [{"document_id": record.document_id, "scene_id": "scene-0001"}]
    latest = client.get(f"/api/projects/{project_id}/documents/{record.document_id}/scenes").json()[0]
    assert (latest["revision"], latest["title"], latest["queue_status"]) == (3, "Later revision", "pending")
    assert PdfStore(assets).scenes(project_id, record.document_id)[0].package.evidence == original


def test_typed_structure_edit_changes_the_live_assessment_and_the_saved_snapshot(space):
    client, assets, project_id, _ = space
    record = _document(assets, project_id, "7.4.1 Cut-in scenario\nTarget vehicle cuts in on a straight road.")
    scene_url = f"/api/projects/{project_id}/documents/{record.document_id}/scenes/scene-0001"
    revised = client.post(scene_url + "/revisions", json={"edits": {"structure": {"road_class": "直道"}}}).json()
    request = {"project_id": project_id, "document_id": record.document_id, "scene_id": "scene-0001", "encoder": "hashing"}
    first = client.post("/api/search", json=request).json()["results"][0]
    assert (first["structural_level"], first["level"], first["review_kind"]) == ("direct", "review", "standards")
    refused = client.post("/api/decisions", json={**request, "asset_id": first["asset_id"], "version_id": first["version_id"]})
    assert refused.status_code == 400

    structure = {**revised["structure"], "road_class": "交叉口"}
    assert client.post(scene_url + "/revisions", json={"edits": {"structure": structure}}).json()["revision"] == revised["revision"] + 1
    changed = client.post("/api/search", json=request).json()["results"][0]
    assert changed["structural_level"] == "modify"
    assert client.post("/api/decisions", json={**request, "asset_id": changed["asset_id"], "version_id": changed["version_id"]}).status_code == 200
    trace = ProjectStore(assets).reports(project_id)[0]["trace"]
    assert trace["source"]["structure"]["road_class"] == "交叉口"
    assert trace["source"]["revision"] == revised["revision"] + 1
    assert trace["candidate"]["parsed_facts"]["road"]["geometry_types"] == {"line": 1}
    legacy = client.post(scene_url + "/revisions", json={"edits": {"parameters": {"ego_speed_kph": 80}}})
    assert legacy.status_code == 400 and "typed structure" in legacy.json()["detail"]


def test_typed_fact_edit_keeps_evidence_topology_and_zero(space):
    from test_pdf_v2_migration import authored_pdf, fake_client

    client, assets, project_id, _ = space
    model, _ = fake_client()
    record = PdfStore(assets).import_pdf(project_id, "authored.pdf", authored_pdf(), client=model)
    original = PdfStore(assets).scenes(project_id, record.document_id)[0]
    scene_url = f"/api/projects/{project_id}/documents/{record.document_id}/scenes/{original.scene_id}"

    def edit_speed(speed):
        # What the editor sends: the saved structure with one changed value.
        current = client.get(f"/api/projects/{project_id}/documents/{record.document_id}/scenes").json()[0]
        structure = {**current["structure"], "params": {**current["structure"]["params"], "ego_speed_kph": speed}}
        return client.post(scene_url + "/revisions", json={"edits": {"structure": structure}}).json()

    revised = edit_speed(50)
    assert revised["revision"] == original.revision + 1
    assert revised["parameters"]["ego_speed_kph"] == 50 and revised["structure"]["params"]["ego_speed_kph"] == 50
    assert revised["structure"]["participants"] == original.package.structure["participants"]
    stored = PdfStore(assets).scenes(project_id, record.document_id)[0]
    assert stored.package.evidence == original.package.evidence
    assert edit_speed(0)["structure"]["params"]["ego_speed_kph"] == 0
    assert client.post(scene_url + "/publish", json={"revision": original.revision + 2}).status_code == 200
    published = client.get(f"/api/projects/{project_id}/documents/{record.document_id}/scenes").json()[0]
    assert published["published"] is True and published["queue_status"] == "confirmed"
