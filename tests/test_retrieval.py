from pathlib import Path
from dataclasses import replace
import sys
from types import SimpleNamespace

import pytest

from openx_workbench.catalog import AssetFile, build_catalog
from openx_workbench.retrieval import (
    HashingEncoder,
    OpenXIndex,
    SentenceTransformerEncoder,
    bundle_to_query,
    bundle_query_text,
    rank_candidates,
)
from openx_workbench.reuse_differences import ReuseDifference
from openx_workbench.reuse_facts import bundle_participant_relations
from openx_workbench.scene_package import EvidenceRef, ScenePackage, scene_package_to_query


FIXTURES = Path(__file__).parent / "fixtures"


class ZeroEncoder:
    encoder_id = "zero"

    def encode(self, text):
        return (0.0,)

    def encode_many(self, texts):
        return [(0.0,) for _ in texts]


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


def test_structural_match_is_not_lost_beyond_semantic_recall_limit():
    correct, distractor = _catalog()
    assets = [replace(distractor, asset_id=f"wrong-{index}") for index in range(120)] + [correct]

    class MisleadingEncoder:
        encoder_id = "misleading-test"

        def encode(self, text):
            return (1.0, 0.0)

        def encode_many(self, texts):
            return [(0.0, 1.0) if "Minimal cut-in" in text else (1.0, 0.0) for text in texts]

    index = OpenXIndex(assets, MisleadingEncoder())
    results = index.search("", query_bundle=correct.bundle, top_k=1)
    assert results[0].asset.asset_id == correct.asset_id


def test_text_only_retrieval_returns_a_grounded_candidate():
    results = OpenXIndex(_catalog()).search("Minimal cut-in SpeedAction", top_k=1)

    assert results[0].asset.title == "Minimal cut-in"
    assert results[0].reasons == ("vector_text_match",)
    assert results[0].reuse_level == "review"
    assert results[0].differences == ()
    assert results[0].estimated_change_cost is None


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


def test_matching_trigger_parameter_allows_direct_reuse():
    source = (FIXTURES / "minimal.xosc").read_bytes().replace(
        b'<SimulationTimeCondition value="1" rule="greaterThan"/>',
        b'<TimeToCollisionCondition value="3" rule="lessThan"/>',
    )
    assets = build_catalog(
        [
            AssetFile("ttc.xosc", source),
            AssetFile("minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes()),
        ]
    )
    package = ScenePackage(
        package_id="REQ_TTC",
        title="Collision intervention",
        preferred_text="Target vehicle intervention at TTC = 3 s.",
        parameters={"ttc_s": 3.0},
    )

    result = OpenXIndex(assets, ZeroEncoder()).search(
        "",
        query=scene_package_to_query(package),
        top_k=1,
    )[0]

    assert result.reuse_level == "direct"
    assert result.differences == ()


def test_parameter_delta_is_a_low_cost_modification():
    source = (FIXTURES / "minimal.xosc").read_bytes().replace(
        b'<SimulationTimeCondition value="1" rule="greaterThan"/>',
        b'<TimeToCollisionCondition value="3" rule="lessThan"/>',
    )
    assets = build_catalog(
        [
            AssetFile("ttc.xosc", source),
            AssetFile("minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes()),
        ]
    )
    package = ScenePackage(
        package_id="REQ_TTC",
        title="Collision intervention",
        preferred_text="Target vehicle intervention at TTC = 2 s.",
        parameters={"ttc_s": 2.0},
    )

    result = OpenXIndex(assets, ZeroEncoder()).search(
        "",
        query=scene_package_to_query(package),
        top_k=1,
    )[0]

    assert result.reuse_level == "modify"
    assert [(item.category, item.cost) for item in result.differences] == [
        ("parameter", 0.5)
    ]
    assert result.estimated_change_cost == 0.5


def test_simulation_time_is_not_an_interaction_trigger():
    query = bundle_to_query(_catalog()[0].bundle)

    assert query.trigger_kinds == frozenset()


def test_structural_identity_is_direct_even_with_zero_vector_score():
    package = ScenePackage(
        package_id="DEMO_1",
        title="Minimal cut-in",
        preferred_text="Target vehicle cut-in on a straight road.",
    )

    result = OpenXIndex(_catalog()[:1], ZeroEncoder()).search(
        "",
        query=scene_package_to_query(package),
        top_k=1,
    )[0]

    assert result.vector_score == 0.0
    assert result.differences == ()
    assert result.reuse_level == "direct"


def test_scenario_family_and_entity_type_block_unrelated_reuse():
    package = ScenePackage(
        package_id="EuroNCAP_4.3.2",
        title="Car-to-PTW",
        preferred_text="A vehicle approaches a stationary motorcyclist.",
    )

    result = OpenXIndex(_catalog()[:1], ZeroEncoder()).search(
        "",
        query=scene_package_to_query(package),
        top_k=1,
    )[0]

    assert result.reuse_level == "new_build"
    assert {item.category for item in result.differences} >= {"scenario", "entity"}


def test_unlabelled_family_requires_verification_instead_of_rebuild():
    query = scene_package_to_query(ScenePackage(
        package_id="authored", title="Car-to-Car", preferred_text="Two vehicles interact."
    ))
    result = OpenXIndex(_catalog()[:1], ZeroEncoder()).search("", query=query, top_k=1)[0]
    difference = next(item for item in result.differences if item.category == "scenario")
    assert difference.candidate == "unknown"
    assert not difference.blocking
    assert result.reuse_level == "modify"


def test_matching_family_with_one_missing_action_is_modify_and_ranks_first():
    source = (FIXTURES / "minimal.xosc").read_bytes()
    partial = source.replace(
        b'Minimal cut-in',
        b'Overtaking vehicle in the adjacent lane',
    )
    unrelated = source.replace(b'Minimal cut-in', b'Car-to-Car safety backup')
    assets = build_catalog(
        [
            AssetFile("overtaking.xosc", partial),
            AssetFile("car-to-car.xosc", unrelated),
            AssetFile("minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes()),
        ]
    )
    package = ScenePackage(
        package_id="EuroNCAP_4.3.4.2",
        title="Lane change with overtaking vehicle",
        preferred_text="Prevent a lane change into the path of an adjacent vehicle.",
    )

    result = OpenXIndex(assets, ZeroEncoder()).search(
        "",
        query=scene_package_to_query(package),
        top_k=2,
    )[0]

    assert result.asset.xosc_name == "overtaking.xosc"
    assert result.reuse_level == "modify"
    assert [(item.category, item.requested) for item in result.differences] == [
        ("action", "lane_change")
    ]


def test_two_stage_ranking_lets_a_standout_name_lead_only_among_structurally_tied_reviews():
    def review(cost):
        return (ReuseDifference("participant", "x", "unknown", "verify", cost=cost, verified=False),)

    modify = (ReuseDifference("parameter", "x", "y", "set", cost=0.5),)
    blocked = (ReuseDifference("family", "x", "y", "rebuild", blocking=True, cost=10),)
    # 0 verified; 1-3 tied reviews (cost within 1.0 of the cheapest); 4 a costlier review;
    # 5 blocked; 6-19 filler reviews. Only 3 and 5 have standout names.
    differences = [modify, review(4), review(4.5), review(5), review(9), blocked] + [review(20)] * 14
    similarities = [0.1, 0.2, 0.1, 0.9, 0.1, 0.95] + [0.1] * 14
    scores = [0.0] * len(differences)

    order = rank_candidates(differences, similarities, scores)

    assert order[:6] == [0, 3, 1, 2, 5, 4]


def test_two_stage_ranking_keeps_structural_order_without_a_standout_name():
    differences = [(ReuseDifference("participant", "x", "unknown", "verify", cost=cost, verified=False),)
                   for cost in (5, 4.5, 4)]
    assert rank_candidates(differences, [0.9, 0.5, 0.1], [0.0] * 3) == [2, 1, 0]


def test_two_stage_ranking_leaves_new_builds_in_structural_order():
    differences = [(ReuseDifference("family", "x", "y", "rebuild", blocking=True, cost=cost),) for cost in (10, 12)]
    differences += [(ReuseDifference("family", "x", "y", "rebuild", blocking=True, cost=30),)] * 18
    similarities = [0.1, 0.9] + [0.1] * 18
    assert rank_candidates(differences, similarities, [0.0] * 20)[:2] == [0, 1]


def test_lane_positions_produce_ego_relative_participant_relations():
    source = (FIXTURES / "minimal.xosc").read_bytes()
    target_position = (
        b'<Private entityRef="Target"><PrivateAction><TeleportAction><Position>'
        b'<LanePosition roadId="1" laneId="-2" s="2" offset="0"/>'
        b'</Position></TeleportAction></PrivateAction></Private>'
    )
    source = source.replace(b"</Actions></Init>", target_position + b"</Actions></Init>")
    asset = build_catalog(
        [
            AssetFile("relative.xosc", source),
            AssetFile("minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes()),
        ]
    )[0]

    assert bundle_participant_relations(asset.bundle) == {
        "rear",
        "right",
        "adjacent_lane",
    }


def test_participant_action_ownership_is_part_of_asset_structure():
    target_action = (FIXTURES / "minimal.xosc").read_bytes()
    ego_action = target_action.replace(
        b'<EntityRef entityRef="Target"/>',
        b'<EntityRef entityRef="Ego"/>',
    )
    assets = build_catalog(
        [
            AssetFile("target-action.xosc", target_action),
            AssetFile("ego-action.xosc", ego_action),
            AssetFile("minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes()),
        ]
    )

    results = OpenXIndex(assets, ZeroEncoder()).search(
        "",
        query_bundle=next(
            asset.bundle for asset in assets if asset.xosc_name == "target-action.xosc"
        ),
        top_k=2,
    )

    assert results[0].asset.xosc_name == "target-action.xosc"
    assert results[0].reuse_level == "direct"
    assert results[1].asset.xosc_name == "ego-action.xosc"
    assert results[1].reuse_level == "new_build"
    assert any(
        item.category == "participant_signature"
        for item in results[1].differences
    )


def test_unknown_participant_topology_requires_verification_not_rebuild():
    source = (FIXTURES / "minimal.xosc").read_bytes()
    target_position = (
        b'<Private entityRef="Target"><PrivateAction><TeleportAction><Position>'
        b'<LanePosition roadId="1" laneId="-1" s="30" offset="0"/>'
        b'</Position></TeleportAction></PrivateAction></Private>'
    )
    grounded = source.replace(
        b"</Actions></Init>",
        target_position + b"</Actions></Init>",
    )
    road = (FIXTURES / "minimal.xodr").read_bytes()
    query_bundle = build_catalog(
        [AssetFile("grounded.xosc", grounded), AssetFile("minimal.xodr", road)]
    )[0].bundle
    candidate = build_catalog(
        [AssetFile("unknown.xosc", source), AssetFile("minimal.xodr", road)]
    )

    result = OpenXIndex(candidate, ZeroEncoder()).search(
        "",
        query_bundle=query_bundle,
        top_k=1,
    )[0]

    assert result.reuse_level == "modify"
    assert [item.category for item in result.differences] == [
        "participant_topology"
    ]


def test_index_vectors_can_be_saved_and_reloaded(tmp_path):
    assets = _catalog()
    path = tmp_path / "openx-index.json"
    original = OpenXIndex(assets, HashingEncoder(dimensions=32))
    original.save(path)

    loaded = OpenXIndex.load(path, assets, HashingEncoder(dimensions=32))
    results = loaded.search("Minimal cut-in", top_k=1)

    assert results[0].asset.title == "Minimal cut-in"
    assert loaded.vectors == original.vectors


def test_faiss_recall_survives_persisted_index(tmp_path):
    pytest.importorskip("faiss")
    assets = _catalog()
    path = tmp_path / "openx-index.json"
    built = OpenXIndex(assets, HashingEncoder(dimensions=32))
    built.save(path)
    reopened = OpenXIndex.load(path, assets, HashingEncoder(dimensions=32))

    assert built.recall_backend == reopened.recall_backend == "faiss-flat-ip"
    assert [item.asset.asset_id for item in reopened.search("Minimal cut-in", top_k=2)] == [
        item.asset.asset_id for item in built.search("Minimal cut-in", top_k=2)
    ]


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
    assert encoder.encode_many(["two", "one", "two"]) == [(1.0, 0.0)] * 3
    assert calls[-1][0] == ["two", "one"]
    assert encoder.encode_many([]) == []
    default_encoder = SentenceTransformerEncoder()
    assert default_encoder.encoder_id == "sentence-transformers:BAAI/bge-m3"
    assert calls[-1] == ("model", "BAAI/bge-m3")


def test_m3_long_inputs_use_small_batches_without_losing_text_or_input_order(monkeypatch):
    calls = []

    class FakeModel:
        def __init__(self, model_name):
            pass

        def encode(self, texts, **options):
            calls.append((texts, options))
            return [[float(len(text)), 1.0] for text in texts]

    monkeypatch.setitem(sys.modules, "sentence_transformers",
                        SimpleNamespace(SentenceTransformer=FakeModel))
    inputs = ["长" * 6000, "", "medium" * 100, "short", "长" * 6000]
    vectors = SentenceTransformerEncoder().encode_many(inputs)
    assert vectors == [(float(len(text)), 1.0) for text in inputs]
    assert [options["batch_size"] for _, options in calls] == [64, 8, 1]
    assert calls[-1][0] == [inputs[0]]
    assert all(options["normalize_embeddings"] for _, options in calls)
