from pathlib import Path
from threading import Event
import time

import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile
from openx_workbench import import_jobs
from openx_workbench.import_jobs import ImportJob, start_import, status


def files():
    root = Path(__file__).parent / "fixtures"
    return [AssetFile(name, (root / name).read_bytes()) for name in ("minimal.xosc", "minimal.xodr")]


def wait(job):
    until = time.monotonic() + 5
    while job.snapshot()["status"] == "running" and time.monotonic() < until:
        time.sleep(.01)
    assert job.snapshot()["status"] != "running"


def test_saved_assets_visible_while_labels_are_made_and_duplicate_start_blocked(tmp_path, monkeypatch):
    entered, release = Event(), Event()

    def slow_labels(store, version):
        entered.set()
        assert release.wait(5)
        return {}

    monkeypatch.setattr(import_jobs, "classify_asset", slow_labels)
    store = AssetStore(tmp_path)
    job = start_import(store, files())
    try:
        assert entered.wait(5)
        assert len(store.catalog()[0]) == 1
        assert status(store)["saved"] == 1
        with pytest.raises(ValueError, match="already running"):
            start_import(store, files())
        job.cancel.set()
    finally:
        release.set()
    wait(job)
    assert status(store)["status"] in {"stopped", "completed"}
    assert len(store.versions()) == 1


def test_cancellation_preserves_partial_import(tmp_path):
    store = AssetStore(tmp_path)
    cancel = Event()
    events = []
    def progress(**state):
        events.append(state)
        if state["saved"]:
            cancel.set()
    with pytest.raises(InterruptedError):
        store.import_files(files(), progress=progress, cancelled=cancel.is_set)
    assert len(store.versions()) == 1
    assert events[-1]["saved"] == 1


def test_restart_reports_interruption_and_reimport_reuses_version(tmp_path):
    store = AssetStore(tmp_path)
    job = ImportJob(store)
    job.update(stage="parsing")
    assert status(store)["status"] == "interrupted"
    job = start_import(store, files())
    wait(job)
    second = start_import(store, files())
    wait(second)
    assert second.snapshot()["status"] == "completed"
    assert len(store.versions()) == 1


def test_an_unreadable_version_is_counted_and_the_rest_are_labelled(tmp_path, monkeypatch):
    from openx_workbench.classification import classify_asset, read_classification

    store = AssetStore(tmp_path)
    original = files()
    versions = []
    for i in range(3):
        versions += store.import_files([AssetFile(f"case{i}.xosc", original[0].data), original[1]])

    def labels(store, version):
        if version.xosc_name == "case1.xosc":
            raise ValueError("authored unreadable scenario")
        return classify_asset(store, version)

    monkeypatch.setattr(import_jobs, "classify_asset", labels)
    job = start_import(store, [], versions=versions)
    wait(job)
    assert job.snapshot()["status"] == "completed"
    assert (job.snapshot()["done"], job.snapshot()["failed"]) == (3, 1)
    assert "case1.xosc" in job.snapshot()["error"]
    assert [read_classification(store, version).get("status") for version in versions] == ["rule", None, "rule"]


@pytest.mark.parametrize("confirmed", [False, True], ids=["rule", "manual_confirmed"])
def test_labels_are_made_again_only_when_outdated_or_forced_and_reviewer_labels_stay(tmp_path, confirmed):
    from openx_workbench.classification import RULES_VERSION, confirm_classification, read_classification

    store = AssetStore(tmp_path)
    job = start_import(store, files())
    wait(job)
    version = store.versions()[0]
    original = store.file_bytes(version, "scenario")
    labelled = read_classification(store, version)
    assert (labelled["status"], labelled["rules"], labelled["final_accepted"]) == ("rule", RULES_VERSION, True)
    if confirmed:
        confirm_classification(store, version, {**labelled["final"], "function_type": "ACC"})
    saved = read_classification(store, version)
    history = tmp_path / "assets" / version.asset_id / version.version_id / "classification_history"
    count = len(list(history.glob("*.json")))

    ordinary = start_import(store, [], versions=[version])
    wait(ordinary)
    assert ordinary.snapshot()["status"] == "completed"
    assert read_classification(store, version) == saved
    assert len(list(history.glob("*.json"))) == count

    explicit = start_import(store, [], versions=[version], force=True)
    wait(explicit)
    assert explicit.snapshot()["status"] == "completed"
    assert len(list(history.glob("*.json"))) == count + 1
    again = read_classification(store, version)
    assert again["status"] == ("manual_confirmed" if confirmed else "rule")
    assert again["final"]["function_type"] == ("ACC" if confirmed else labelled["final"]["function_type"])
    assert store.load_asset(version).classification == again["final"]
    assert store.file_bytes(version, "scenario") == original
    assert len(store.versions()) == 1


def test_a_model_review_record_is_outdated_and_labelled_by_the_rules(tmp_path):
    from openx_workbench.classification import _save, outdated, read_classification, rule_labels

    store = AssetStore(tmp_path)
    version = store.import_files(files())[0]
    model_labels = {"function_type": "AEB", "label_road_type": "弯道", "label_target_type": ["乘用车"],
                    "label_actions": ["制动"], "scenario_intent": "Authored model review"}
    _save(store, version, {"version_id": version.version_id, "rule": model_labels, "llm": None, "final": model_labels,
                           "status": "classified", "needs_review": False, "model": "authored-model", "final_accepted": True})
    assert outdated(read_classification(store, version))
    job = start_import(store, [], versions=[version])
    wait(job)
    record = read_classification(store, version)
    assert record["status"] == "rule" and not outdated(record)
    assert record["final"] == rule_labels(store.load_asset(version), version.xosc_name)
