from types import SimpleNamespace

import pytest

pytest.importorskip("fastapi")

from openx_workbench import import_jobs, standard_export
from openx_workbench.asset_store import AssetStore
from openx_workbench.import_jobs import ImportJob


def version_url(version, tail=""):
    return f"/api/assets/{version.asset_id}/versions/{version.version_id}{tail}"


LABELS = {"function_type": "AEB", "label_road_type": "直道", "label_target_type": ["乘用车"],
          "label_actions": ["SpeedAction"], "scenario_intent": "Authored cut-in"}


def test_table_lists_versions_with_their_labels(workbench):
    client, _, version = workbench
    rows = client.get("/api/assets").json()
    assert [(row["version_id"], row["latest"], row["classification"], row["function"]) for row in rows] \
        == [(version.version_id, True, "pending", "未知")]
    schema = client.get("/api/classification-schema").json()
    assert "AEB" in schema["function_type"] and "行人" in schema["label_target_type"]


def test_detail_shows_summary_validation_and_history(workbench):
    client, _, version = workbench
    detail = client.get(version_url(version)).json()
    assert detail["version"]["version_id"] == version.version_id and detail["summary"]["entities"] >= 1
    assert set(detail["validation"]) == {"scenario", "road"} and detail["history"][0]["version_number"] == 1
    assert detail["classification"] is None and detail["references"] == [] and detail["standard_export"] is False
    assert client.get(f"/api/assets/{version.asset_id}/versions/{'0' * 20}").status_code == 404


def test_rule_suggestion_then_confirmed_labels(workbench):
    client, _, version = workbench
    assert client.get(version_url(version, "/classification/download")).status_code == 404
    rule = client.post(version_url(version, "/classification/rules")).json()
    assert rule["status"] == "rule_only" and rule["needs_review"] is True
    confirmed = client.put(version_url(version, "/classification"), json=LABELS).json()
    assert confirmed["status"] == "manual_confirmed" and confirmed["final"] == LABELS
    assert client.get("/api/assets").json()[0]["function"] == "AEB"
    assert client.get("/api/library").json()["facets"]["function_type"] == ["AEB"]
    record = client.get(version_url(version, "/classification/download"))
    assert "attachment" in record.headers["content-disposition"] and record.json()["status"] == "manual_confirmed"
    assert client.put(version_url(version, "/classification"), json={**LABELS, "function_type": "invented"}).status_code == 400


def test_changes_wait_for_a_running_import(workbench):
    client, _, version = workbench
    job = ImportJob(AssetStore())
    import_jobs.jobs.start(job, lambda current: current.cancel.wait(5))
    try:
        refused = client.post(version_url(version, "/classification/rules"))
        assert refused.status_code == 400 and "running import" in refused.json()["detail"]
        assert client.delete(version_url(version)).status_code == 400
    finally:
        job.cancel.set()


def test_referenced_versions_cannot_be_deleted(workbench):
    client, base, version = workbench
    trace = client.post("/api/trace", json={**base, "asset_id": version.asset_id, "version_id": version.version_id}).json()
    from openx_workbench.project_store import ProjectStore
    ProjectStore(AssetStore()).save_decision(base["project_id"], version, trace)
    refused = client.delete(version_url(version))
    assert refused.status_code == 400 and "cannot be deleted" in refused.json()["detail"]
    assert len(client.get(version_url(version)).json()["references"]) == 1


def test_unreferenced_version_is_deleted(workbench):
    client, _, version = workbench
    assert client.delete(version_url(version)).json() == {"deleted": version.version_id}
    assert client.get("/api/assets").json() == []
    assert client.get("/api/library").json()["asset_count"] == 0


def test_standard_export_is_for_sim_assets_and_downloads_once_prepared(workbench, monkeypatch):
    client, _, version = workbench
    refused = client.post(version_url(version, "/standard-export"))
    assert refused.status_code == 400 and "SIM" in refused.json()["detail"]
    assert client.get(version_url(version, "/standard-export/download")).status_code == 404
    prepared = SimpleNamespace(ready=False, audit={"ready": False, "validation": {}}, package=lambda diagnostic: b"zip:" + str(diagnostic).encode())
    monkeypatch.setattr(standard_export, "build_standard_export", lambda store, v: prepared)
    assert client.post(version_url(version, "/standard-export")).json() == {"ready": False, "audit": {"ready": False, "validation": {}}}
    package = client.get(version_url(version, "/standard-export/download"))
    assert package.content == b"zip:True" and f"openx-diagnostic-{version.version_id}.zip" in package.headers["content-disposition"]


def test_published_requirements_are_listed_and_downloadable(workbench):
    client, base, _ = workbench
    assert client.get("/api/requirements").json() == []
    client.post(f"/api/projects/{base['project_id']}/documents/{base['document_id']}/scenes/{base['scene_id']}/publish", json={"revision": 1})
    listed = client.get("/api/requirements").json()
    assert [(item["scene_id"], item["revision"]) for item in listed] == [(base["scene_id"], 1)]
    record = client.get(f"/api/requirements/{listed[0]['library_id']}/download").json()
    assert record["package"]["extraction"]["review_status"] == "confirmed"
    assert client.get("/api/requirements/unknown/download").status_code == 404
