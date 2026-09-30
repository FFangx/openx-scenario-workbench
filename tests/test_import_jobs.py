from pathlib import Path
from threading import Event
import json
import time

import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile
from openx_workbench.import_jobs import ImportJob, start_import, status
from openx_workbench.llm_service import ModelConfig


def files():
    root = Path(__file__).parent / "fixtures"
    return [AssetFile(name, (root / name).read_bytes()) for name in ("minimal.xosc", "minimal.xodr")]


def wait(job):
    until = time.monotonic() + 5
    while job.snapshot()["status"] == "running" and time.monotonic() < until:
        time.sleep(.01)
    assert job.snapshot()["status"] != "running"


def test_saved_assets_visible_while_model_waits_and_duplicate_start_blocked(tmp_path):
    entered, release = Event(), Event()
    class Client:
        config = ModelConfig(timeout=900)
        def complete(self, body):
            entered.set()
            assert release.wait(5)
            raise ValueError("Mock model timed out")
    store = AssetStore(tmp_path)
    client = Client()
    job = start_import(store, files(), classify=True, client=client)
    try:
        assert entered.wait(5)
        assert len(store.catalog()[0]) == 1
        assert status(store)["saved"] == 1
        assert client.config.timeout == 90
        with pytest.raises(ValueError, match="already running"):
            start_import(store, files())
        job.cancel.set()
    finally:
        release.set()
    wait(job)
    assert status(store)["status"] == "stopped"
    assert status(store)["failed"] == 1
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


def test_three_model_failures_stop_remaining_requests(tmp_path):
    store = AssetStore(tmp_path)
    original = files()
    versions = []
    for i in range(4):
        versions += store.import_files([AssetFile(f"case{i}.xosc", original[0].data), original[1]])
    class Client:
        config = ModelConfig()
        calls = 0
        def complete(self, body):
            self.calls += 1
            raise ValueError("Mock unavailable")
    client = Client()
    job = start_import(store, [], versions=versions, classify=True, client=client)
    wait(job)
    assert client.calls == 3
    assert job.snapshot()["status"] == "failed"
    assert job.snapshot()["done"] == 3
    assert len(store.versions()) == 4


@pytest.mark.parametrize("confirmed", [False, True], ids=["classified", "manual_confirmed"])
def test_explicit_reclassification_calls_model_while_resume_skips_reviewed_versions(tmp_path, confirmed):
    from openx_workbench.classification import classify_asset, confirm_classification, read_classification

    store = AssetStore(tmp_path)
    version = store.import_files(files())[0]
    original = store.file_bytes(version, "scenario")

    class Client:
        config = ModelConfig(model="authored-review-model")
        calls = 0

        def complete(self, body):
            self.calls += 1
            result = {"function_type": "AEB", "label_road_type": "直道",
                      "label_target_type": ["乘用车"], "label_actions": ["制动"],
                      "scenario_intent": "Authored braking classification", "confidence": .95,
                      "reason": "Authored regression response"}
            return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(result)}}]}

    client = Client()
    reviewed = classify_asset(store, version, use_model=True, client=client)
    if confirmed:
        confirm_classification(store, version, {**reviewed["final"], "function_type": "ACC"})
    saved = read_classification(store, version)
    client.calls = 0
    ordinary = start_import(store, [], versions=[version], classify=True, client=client)
    wait(ordinary)
    assert ordinary.snapshot()["status"] == "completed"
    assert client.calls == 0
    assert read_classification(store, version) == saved
    explicit = start_import(store, [], versions=[version], classify=True, client=client, force=True)
    wait(explicit)
    assert explicit.snapshot()["status"] == "completed"
    assert client.calls == 1
    assert read_classification(store, version)["status"] == "classified"
    assert read_classification(store, version)["final"]["function_type"] == "AEB"
    assert store.file_bytes(version, "scenario") == original
    assert len(store.versions()) == 1
