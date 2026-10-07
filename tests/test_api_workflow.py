import json
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from openx_workbench import api_preview, grounding
from openx_workbench.asset_store import AssetStore

CORPUS = json.loads((Path(__file__).parent / "fixtures" / "reuse" / "corpus.json").read_text(encoding="utf-8"))
STRUCTURE = next(case for case in CORPUS["cases"] if case["id"] == "forward-en")["structure"]


def scene_url(base, tail=""):
    return f"/api/projects/{base['project_id']}/documents/{base['document_id']}/scenes/{base['scene_id']}{tail}"


def test_schema_lists_the_typed_vocabulary(workbench):
    client, _, _ = workbench
    schema = client.get("/api/scene-schema").json()
    assert "AEB" in schema["tested_function"] and "正前方" in schema["bearing"]


def test_revision_then_publication_moves_the_queue_state(workbench):
    client, base, _ = workbench
    listed = client.get(f"/api/projects/{base['project_id']}/documents/{base['document_id']}/scenes").json()
    assert listed[0]["queue_status"] == "pending" and listed[0]["document_id"] == base["document_id"]
    revised = client.post(scene_url(base, "/revisions"), json={"edits": {"title": "Edited", "structure": STRUCTURE}}).json()
    assert (revised["revision"], revised["title"], revised["structure"]["tested_function"]) == (2, "Edited", "AEB")
    assert [item["revision"] for item in client.get(scene_url(base, "/revisions")).json()] == [1, 2]
    assert client.post(scene_url(base, "/revisions"), json={"edits": {"evidence": []}}).status_code == 400
    assert client.post(scene_url(base, "/publish"), json={"revision": 2}).json()["revision"] == 2
    every = client.get(f"/api/projects/{base['project_id']}/scenes").json()
    assert [(item["revision"], item["queue_status"]) for item in every] == [(2, "confirmed")]
    assert client.post(scene_url(base, "/publish"), json={"revision": 9}).status_code == 404


def test_extraction_record_of_a_rule_extracted_pdf(workbench):
    client, base, _ = workbench
    url = f"/api/projects/{base['project_id']}/documents/{base['document_id']}/extraction"
    record = client.get(url).json()
    assert record["outdated"] is True and record["has_record"] is False
    assert client.get(url + "/download").status_code == 404


def test_batch_summary_downloads_and_saves_only_while_current(workbench):
    client, base, _ = workbench
    url = f"/api/projects/{base['project_id']}/batch"
    request = {"document_ids": [base["document_id"]], "encoder": "hashing"}
    matched = client.post(url, json=request).json()
    assert matched["trace"]["kind"] == "batch_match" and matched["trace"]["scene_count"] == 1
    html = client.get(f"{url}/{matched['signature']}/download?format=html&lang=en")
    assert "attachment" in html.headers["content-disposition"] and "OpenX document assessment" in html.text
    assert client.get(f"{url}/{'0' * 64}/download").status_code == 404
    saved = client.post(url + "/save", json={"signature": matched["signature"]}).json()
    latest = client.get(f"/api/projects/{base['project_id']}/reports").json()[0]
    assert (latest["report_id"], latest["kind"]) == (saved["report_id"], "batch")
    stale = client.post(url, json=request).json()
    client.post(scene_url(base, "/revisions"), json={"edits": {"title": "Changed after matching"}})
    refused = client.post(url + "/save", json={"signature": stale["signature"]})
    assert refused.status_code == 400 and "Match again" in refused.json()["detail"]
    assert client.post(url, json={"document_ids": [base["document_id"]] * 2}).status_code == 400
    assert client.post(url, json={"document_ids": []}).status_code == 422
    assert client.post(f"/api/projects/{base['project_id']}/batch/save", json={"signature": "0" * 64}).status_code == 404


def test_report_and_explanations_follow_the_current_assessment(workbench, monkeypatch):
    client, base, version = workbench
    request = {**base, "asset_id": version.asset_id, "version_id": version.version_id, "lang": "en"}
    report = client.post("/api/trace/report", json=request)
    assert report.headers["content-type"].startswith("text/html") and "OpenX reuse trace" in report.text
    evidence = client.post("/api/explanation", json={**request, "mode": "evidence"}).json()
    assert evidence["evidence"][0]["evidence_id"] == "P1" and "explanation_id" not in evidence
    structural = client.post("/api/explanation", json={**request, "mode": "structural"}).json()
    assert structural["explanation"]["method"] == "structural"
    traced = client.post("/api/trace", json={**request, "explanation_id": structural["explanation_id"]}).json()
    assert traced["explanation"]["method"] == "structural"
    other_language = client.post("/api/trace", json={**request, "lang": "zh", "explanation_id": structural["explanation_id"]}).json()
    assert "explanation" not in other_language

    def unavailable(*args, **kwargs):
        raise RuntimeError("Model output failed evidence validation: authored")
    monkeypatch.setattr(grounding, "model_explanation", unavailable)
    failed = client.post("/api/explanation", json={**request, "mode": "model"})
    assert failed.status_code == 400 and "evidence validation" in failed.json()["detail"]


class FakePreview:
    def __init__(self, version, state, frames):
        self.asset_id, self.version_id = version.asset_id, version.version_id
        self.url, self.token, self.workdir = "http://127.0.0.1:1", "token", Path(".")
        self.state, self.frames, self.stopped = state, frames, False

    def status(self):
        return {"state": self.state, "frames": self.frames, "error": "authored failure" if self.state == "failed" else ""}

    def stop(self):
        self.stopped = True


def test_preview_records_whether_the_version_played(workbench, monkeypatch):
    client, _, version = workbench
    url = f"/api/assets/{version.asset_id}/versions/{version.version_id}/preview"
    monkeypatch.setattr(api_preview, "_current", {"preview": None})
    monkeypatch.setattr(api_preview, "find_esmini", lambda value: None)
    assert client.post(url, json={}).status_code == 400
    assert client.get("/api/preview").json() == {"state": "idle"}

    monkeypatch.setattr(api_preview, "find_esmini", lambda value: Path("esmini.exe"))
    started = []
    monkeypatch.setattr(api_preview, "start_preview", lambda store, v, exe, duration: started.append(duration) or FakePreview(v, "running", 3))
    running = client.post(url, json={"duration": 2}).json()
    assert started == [2] and running["stream_url"] == "http://127.0.0.1:1/stream?token=token"
    assert AssetStore().versions()[0].compatibility == "playable"
    assert client.post(url, json={"duration": 500}).status_code == 422

    preview = api_preview._current["preview"]
    preview.state, preview.frames = "failed", 0
    failed = client.get("/api/preview").json()
    assert failed["state"] == "failed" and AssetStore().versions()[0].compatibility_detail == "authored failure"
    assert client.post("/api/preview/stop").json() == {"state": "idle"} and preview.stopped

    def broken(*args, **kwargs):
        raise RuntimeError("authored start failure")
    monkeypatch.setattr(api_preview, "start_preview", broken)
    assert "authored start failure" in client.post(url, json={}).json()["detail"]
    assert client.get("/api/preview").json() == {"state": "idle"}
