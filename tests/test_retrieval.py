from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from openx_workbench.catalog import AssetFile, build_catalog
from openx_workbench.retrieval import (
    HashingEncoder,
    OpenXIndex,
    SentenceTransformerEncoder,
    bundle_query_text,
)
from openx_workbench.scene_package import EvidenceRef, ScenePackage, scene_package_to_query


FIXTURES = Path(__file__).parent / "fixtures"


def _catalog():
    cut_in = (FIXTURES / "minimal.xosc").read_bytes()
    lane_change = cut_in.replace(b"Minimal cut-in", b"Lane-change baseline")
    lane_change = lane_change.replace(b"SpeedAction", b"LaneChangeAction")
    return build_catalog(
        [
            AssetFile("cut-in.xosc", cut_in),
            AssetFile("lane-change.xosc", lane_change),
            AssetFile("minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes()),
        ]
    )


def test_hybrid_retrieval_ranks_matching_openx_asset_first():
    assets = _catalog()
    query = assets[0].bundle
    results = OpenXIndex(assets).search(
        bundle_query_text(query), query_bundle=query, top_k=2
    )

    assert results[0].asset.title == "Minimal cut-in"
    assert results[0].road_score == 1.0
    assert "scenario_structure_match" in results[0].reasons
    assert "road_structure_match" in results[0].reasons


def test_text_only_retrieval_returns_a_grounded_candidate():
    results = OpenXIndex(_catalog()).search("Minimal cut-in SpeedAction", top_k=1)

    assert results[0].asset.title == "Minimal cut-in"
    assert results[0].reasons == ("vector_text_match",)
    assert results[0].reuse_level in {"direct", "modify"}


def test_scene_package_query_reports_grounded_reuse_differences():
    package = ScenePackage(
        package_id="L2_7.4.1",
        title="Pedestrian crossing at junction",
        preferred_text="A pedestrian crosses at a junction when TTC is 2.0 s.",
        evidence=[EvidenceRef("standard.pdf", "7.4.1", 8, 8, "source clause")],
    )

    result = OpenXIndex(_catalog()).search(
        "",
        query=scene_package_to_query(package),
        top_k=1,
    )[0]

    assert {item.category for item in result.differences} >= {"entity", "road"}
    assert result.differences[0].action


def test_unverified_pdf_parameter_prevents_direct_reuse():
    package = ScenePackage(
        package_id="L2_7.4.2",
        title="Minimal cut-in",
        preferred_text="Target vehicle cut-in on a straight road at TTC = 3.0 s.",
        parameters={"ttc_s": 3.0},
    )

    result = OpenXIndex(_catalog()).search(
        "",
        query=scene_package_to_query(package),
        top_k=1,
    )[0]

    assert any(item.category == "parameter" for item in result.differences)
    assert result.reuse_level != "direct"


def test_index_vectors_can_be_saved_and_reloaded(tmp_path):
    assets = _catalog()
    path = tmp_path / "openx-index.json"
    original = OpenXIndex(assets, HashingEncoder(dimensions=32))
    original.save(path)

    loaded = OpenXIndex.load(path, assets, HashingEncoder(dimensions=32))
    results = loaded.search("Minimal cut-in", top_k=1)

    assert results[0].asset.title == "Minimal cut-in"
    assert loaded.vectors == original.vectors


def test_saved_index_rejects_a_different_encoder(tmp_path):
    assets = _catalog()
    path = tmp_path / "openx-index.json"
    OpenXIndex(assets, HashingEncoder(dimensions=32)).save(path)

    with pytest.raises(ValueError, match="different encoder"):
        OpenXIndex.load(path, assets, HashingEncoder(dimensions=64))


def test_sentence_transformer_encoder_batches_and_normalizes(monkeypatch):
    calls = []

    class FakeModel:
        def __init__(self, model_name):
            calls.append(("model", model_name))

        def encode(self, texts, **options):
            calls.append((texts, options))
            return [[1.0, 0.0] for _ in texts]

    monkeypatch.setitem(
        sys.modules,
        "sentence_transformers",
        SimpleNamespace(SentenceTransformer=FakeModel),
    )
    encoder = SentenceTransformerEncoder("test/bge")

    assert encoder.encode_many(["one", "two"]) == [(1.0, 0.0), (1.0, 0.0)]
    assert calls[1][1]["normalize_embeddings"] is True
    assert calls[1][1]["batch_size"] == 64
