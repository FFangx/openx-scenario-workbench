"""The API's catalog, index and ranking caches: what is recomputed when, and what an index build blocks."""
import threading
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from openx_workbench import api_common, matching
from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile
from openx_workbench.classification import classify_asset, confirm_classification
from openx_workbench.retrieval import HashingEncoder, OpenXIndex

FIXTURES = Path(__file__).parent / "fixtures"


def _import(store, name):
    files = [AssetFile(name, (FIXTURES / "reuse" / name).read_bytes()),
             AssetFile("minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes())]
    return store.import_files(files)[0]


def test_catalog_parses_each_version_once(workbench, monkeypatch):
    store = AssetStore()
    second = _import(store, "rear.xosc")
    loads = []
    original = AssetStore.load_asset
    monkeypatch.setattr(AssetStore, "load_asset", lambda self, version: loads.append(version.version_id)
                        or original(self, version))
    assets, _ = api_common._catalog()
    assert len(loads) == 2 and api_common._catalog()[0] is assets and len(loads) == 2

    # A new label reparses only the relabelled version.
    confirm_classification(store, second, {**classify_asset(store, second)["rule"], "label_road_type": "直道", "function_type": "ACC"})
    loads.clear()
    relabelled, versions = api_common._catalog()
    assert loads == [second.version_id]
    assert {versions[asset.asset_id].version_id: asset.classification.get("function_type") for asset in relabelled}[
        second.version_id] == "ACC"


def test_trace_and_decision_reuse_the_search_ranking(workbench, monkeypatch):
    client, base, version = workbench
    calls = []
    original = matching.search
    monkeypatch.setattr(matching, "search", lambda *args, **kwargs: calls.append(1) or original(*args, **kwargs))
    client.post("/api/search", json=base)
    client.post("/api/search", json={**base, "lang": "zh", "filters": {"function_type": "AEB"}})
    request = {**base, "asset_id": version.asset_id, "version_id": version.version_id}
    client.post("/api/trace", json=request)
    client.post("/api/decisions", json=request)
    assert len(calls) == 1
    client.post("/api/search", json={**base, "text": "another query"})
    assert len(calls) == 2


def test_an_index_build_does_not_hold_the_shared_lock(workbench, monkeypatch):
    building, release = threading.Event(), threading.Event()

    def slow_open(catalog, identity):
        building.set()
        release.wait(10)
        return OpenXIndex(catalog, HashingEncoder(32))

    monkeypatch.setattr(matching, "open_index", slow_open)
    catalog, _ = api_common._catalog()
    worker = threading.Thread(target=api_common._index, args=(catalog, "hashing"))
    worker.start()
    try:
        assert building.wait(10)
        # Other requests take the shared lock while the build runs.
        assert api_common._lock.acquire(timeout=1)
        api_common._lock.release()
        assert api_common._catalog()[0] is catalog
    finally:
        release.set()
        worker.join(10)
    assert api_common._index(catalog, "hashing") is api_common._cache["index"]


def test_an_index_saved_in_the_previous_format_is_rebuilt(workbench):
    catalog, _ = api_common._catalog()
    identity = matching.index_identity(catalog, "hashing")
    path = AssetStore().root / "indexes" / "hashing" / f"{identity[1][:24]}.bin"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text('{"schema_version":2,"vectors":[]}', encoding="utf-8")
    index = matching.open_index(catalog, identity)
    assert index.fingerprint == identity[1]
    reopened = OpenXIndex.load(path, catalog, matching.encoder("hashing"))
    assert reopened.vectors == index.vectors and reopened.structure_vectors == index.structure_vectors
