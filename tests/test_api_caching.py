"""The API's catalog, index and ranking caches: what is recomputed when, and what an index build blocks."""
import threading
from pathlib import Path

import pytest

pytest.importorskip("fastapi")

from openx_workbench import api_common, matching
from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile
from openx_workbench.classification import classify_asset, confirm_classification
from openx_workbench.retrieval import HashingEncoder, OpenXIndex, VectorCache, asset_structure_text, asset_text

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


class _CountingEncoder(HashingEncoder):
    def __init__(self):
        super().__init__(32)
        self.encoded = []

    def encode_many(self, texts):
        self.encoded += texts
        return super().encode_many(texts)


def test_a_library_change_encodes_only_new_texts(workbench, monkeypatch):
    counting = _CountingEncoder()
    monkeypatch.setattr(matching, "encoder", lambda name: counting)
    catalog, _ = api_common._catalog()
    first = matching.open_index(catalog, matching.index_identity(catalog, "hashing"))
    assert len(counting.encoded) == 2 * len(catalog)

    # Reopening the same library encodes nothing.
    counting.encoded.clear()
    assert matching.open_index(catalog, matching.index_identity(catalog, "hashing")).vectors == first.vectors
    assert counting.encoded == []

    # One new asset encodes its name and structure texts only, and matches a full rebuild.
    _import(AssetStore(), "rear.xosc")
    grown, _ = api_common._catalog()
    index = matching.open_index(grown, matching.index_identity(grown, "hashing"))
    assert len(grown) == len(catalog) + 1 and len(counting.encoded) == 2
    rebuilt = OpenXIndex(grown, HashingEncoder(32))
    assert (index.vectors, index.structure_vectors) == (rebuilt.vectors, rebuilt.structure_vectors)
    assert [item.asset.asset_id for item in index.search("rear", top_k=2)] == [
        item.asset.asset_id for item in rebuilt.search("rear", top_k=2)]


def test_saved_vectors_keep_only_the_current_library(workbench, monkeypatch):
    counting = _CountingEncoder()
    monkeypatch.setattr(matching, "encoder", lambda name: counting)
    folder = AssetStore().root / "indexes" / "hashing"
    folder.mkdir(parents=True, exist_ok=True)
    # Whole-library index files from earlier versions are removed; a damaged vector file starts empty.
    (folder / "0123456789abcdef01234567.bin").write_bytes(b'{"schema_version":3}\n')
    (folder / "0123456789abcdef01234567.json").write_bytes(b'{"schema_version":2,"vectors":[]}')
    (folder / matching.VECTOR_FILE).write_bytes(b"not a vector file")
    catalog = _open_latest()
    assert [path.name for path in folder.iterdir()] == [matching.VECTOR_FILE]
    assert VectorCache(folder / matching.VECTOR_FILE, counting).vectors.keys() == _keys(catalog)

    # Relabelling an asset encodes its changed texts only and drops the ones it replaced.
    asset = _import(AssetStore(), "rear.xosc")
    before = _keys(_open_latest())
    confirm_classification(AssetStore(), asset, {**classify_asset(AssetStore(), asset)["rule"], "function_type": "ACC"})
    counting.encoded.clear()
    relabelled = _open_latest()
    assert counting.encoded and {VectorCache.key(text) for text in counting.encoded} == _keys(relabelled) - before
    assert VectorCache(folder / matching.VECTOR_FILE, counting).vectors.keys() == _keys(relabelled)


def test_the_model_loads_once_while_a_search_waits_for_the_preload(monkeypatch):
    builds, started, release = [], threading.Event(), threading.Event()

    def slow_build(name):
        builds.append(name)
        started.set()
        release.wait(10)
        return HashingEncoder(32)

    monkeypatch.setattr(matching, "build_encoder", slow_build)
    monkeypatch.setattr(matching, "preferred_encoder", lambda: "bge")
    matching._build_encoder.cache_clear()
    try:
        matching.preload_encoder()
        assert started.wait(10)
        search = threading.Thread(target=matching.encoder, args=("bge",))
        search.start()
        release.set()
        search.join(10)
        assert builds == ["bge"]
    finally:
        release.set()
        matching._build_encoder.cache_clear()


def _open_latest():
    catalog, _ = api_common._catalog()
    matching.open_index(catalog, matching.index_identity(catalog, "hashing"))
    return catalog


def _keys(catalog):
    return {VectorCache.key(text) for asset in catalog for text in (asset_text(asset), asset_structure_text(asset))}
