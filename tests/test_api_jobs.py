import json
from pathlib import Path
from threading import Event
import time

import pymupdf
import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from openx_workbench import api, import_jobs
from openx_workbench.asset_store import AssetStore
from openx_workbench.import_jobs import ImportJob
from openx_workbench.llm_service import ModelConfig
from openx_workbench.pdf_store import PdfStore
from openx_workbench.project_store import ProjectStore

FIXTURES = Path(__file__).parent / "fixtures"


def _pdf(title: str) -> bytes:
    document = pymupdf.open()
    document.new_page().insert_text((72, 72), f"7.4.1 {title} scenario\nTarget vehicle cuts in on a straight road.")
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    api._cache.clear()
    yield TestClient(api.app, base_url="http://127.0.0.1")
    api._cache.clear()


@pytest.fixture
def project(client):
    return ProjectStore(AssetStore()).create("Jobs").project_id


@pytest.fixture
def legacy_extraction(monkeypatch):
    """Extract with the offline rule engine; the real path calls the configured model."""
    original = PdfStore.import_pdf
    gates = {}

    def import_pdf(self, project_id, filename, data, standard="", *, progress=None, **_):
        progress(f"authored step for {filename}")
        if filename in gates:
            gates[filename][0].set()
            assert gates[filename][1].wait(5)
        return original(self, project_id, filename, data, standard, engine="legacy")

    monkeypatch.setattr(PdfStore, "import_pdf", import_pdf)
    return gates


def finished(client, job):
    until = time.monotonic() + 10
    while job["status"] == "running" and time.monotonic() < until:
        time.sleep(.02)
        job = client.get(f"/api/jobs/{job['id']}").json()
    assert job["status"] != "running"
    return job


def pdfs(*names):
    return [("files", (name, _pdf(name), "application/pdf")) for name in names]


def test_pdf_import_reports_progress_and_lists_documents(client, project, legacy_extraction):
    started = client.post(f"/api/projects/{project}/documents", files=pdfs("a.pdf", "b.pdf"), data={"standard": " Std "})
    assert started.status_code == 200 and started.json()["kind"] == "pdf_import"
    job = finished(client, started.json())
    assert job["status"] == "completed" and (job["done"], job["total"]) == (2, 2)
    assert "authored step for b.pdf" in job["messages"]
    documents = client.get(f"/api/projects/{project}/documents").json()
    assert sorted(job["result"]["document_ids"]) == sorted(item["document_id"] for item in documents)
    assert {item["source_standard"] for item in documents} == {"Std"}
    assert client.get("/api/jobs", params={"kind": "pdf_import"}).json()[0]["id"] == job["id"]


def test_pdf_import_rejects_bad_input_before_starting(client, project, legacy_extraction):
    assert client.post(f"/api/projects/{project}/documents",
                       files=[("files", ("notes.txt", b"text", "text/plain"))]).status_code == 400
    assert client.post("/api/projects/unknown/documents", files=pdfs("a.pdf")).status_code == 400
    assert client.get("/api/jobs").json() == []


def test_cancel_stops_after_the_current_pdf_and_blocks_a_second_run(client, project, legacy_extraction):
    entered, release = Event(), Event()
    legacy_extraction["first.pdf"] = (entered, release)
    job = client.post(f"/api/projects/{project}/documents", files=pdfs("first.pdf", "second.pdf")).json()
    try:
        assert entered.wait(5)
        assert client.post(f"/api/projects/{project}/documents", files=pdfs("other.pdf")).status_code == 400
        assert client.post(f"/api/jobs/{job['id']}/cancel").json()["cancelling"] is True
    finally:
        release.set()
    job = finished(client, job)
    assert job["status"] == "stopped" and len(job["result"]["document_ids"]) == 1
    assert [item["filename"] for item in client.get(f"/api/projects/{project}/documents").json()] == ["first.pdf"]


def test_reextract_runs_as_a_job_for_the_stored_pdf(client, project, legacy_extraction):
    finished(client, client.post(f"/api/projects/{project}/documents", files=pdfs("rules.pdf")).json())
    document = client.get(f"/api/projects/{project}/documents").json()[0]
    job = finished(client, client.post(f"/api/projects/{project}/documents/{document['document_id']}/reextract").json())
    assert job["status"] == "completed" and job["result"]["document_ids"] == [document["document_id"]]
    assert client.post(f"/api/projects/{project}/documents/{'0' * 20}/reextract").status_code == 404


def assets():
    return [("files", (name, (FIXTURES / name).read_bytes(), "application/xml")) for name in ("minimal.xosc", "minimal.xodr")]


def test_asset_import_job_and_its_status_after_a_restart(client, tmp_path, monkeypatch):
    assert client.post("/api/assets/import", files=[("files", ("a.txt", b"x", "text/plain"))]).status_code == 400
    job = finished(client, client.post("/api/assets/import", files=assets()).json())
    assert job["status"] == "completed" and job["saved"] == 1
    assert client.get("/api/library").json()["asset_count"] == 1
    assert client.get("/api/jobs", params={"kind": "asset_import"}).json()[0]["id"] == job["id"]

    # A data folder whose import was cut off by a service restart: only its status file remains.
    other = tmp_path / "restarted"
    ImportJob(AssetStore(other)).update(stage="parsing")
    monkeypatch.setenv("OPENX_DATA_DIR", str(other))
    listed = client.get("/api/jobs", params={"kind": "asset_import"}).json()
    assert [item["status"] for item in listed] == ["interrupted"]


def test_model_classification_job_for_pending_versions(client, monkeypatch):
    finished(client, client.post("/api/assets/import", files=assets()).json())
    pending = client.get("/api/assets/classification/pending").json()
    assert pending["count"] == 1

    class Client:
        config = ModelConfig(model="authored-review-model")

        def complete(self, body):
            result = {"function_type": "AEB", "label_road_type": "直道", "label_target_type": ["乘用车"],
                      "label_actions": ["制动"], "scenario_intent": "Authored", "confidence": .95, "reason": "Authored"}
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]}

    monkeypatch.setattr(import_jobs, "ModelClient", Client)
    assert client.post("/api/assets/classify", json={"versions": [{"asset_id": "x", "version_id": "y"}]}).status_code == 404
    job = finished(client, client.post("/api/assets/classify", json={}).json())
    assert job["status"] == "completed" and job["failed"] == 0
    assert client.get("/api/assets/classification/pending").json()["count"] == 0
    assert client.post("/api/assets/classify", json={}).status_code == 400
    forced = finished(client, client.post("/api/assets/classify", json={"versions": pending["versions"], "force": True}).json())
    assert forced["status"] == "completed"


def test_unknown_jobs(client):
    assert client.get("/api/jobs/missing").status_code == 404
    assert client.post("/api/jobs/missing/cancel").status_code == 404
