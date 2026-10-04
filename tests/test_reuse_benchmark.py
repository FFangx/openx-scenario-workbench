import importlib.util
import json
from pathlib import Path

import pytest

from openx_workbench.ablation import load_benchmark, rank, run, score
from openx_workbench.retrieval import HashingEncoder, OpenXIndex
from openx_workbench.reuse_facts import asset_structure_query

REPO = Path(__file__).resolve().parents[1]
BENCHMARK = REPO / "examples" / "reuse-benchmark" / "benchmark.json"


def _generator():
    spec = importlib.util.spec_from_file_location("build_reuse_benchmark", REPO / "scripts" / "build_reuse_benchmark.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_committed_files_match_the_specification():
    spec = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    for relative, content in _generator().rendered(spec).items():
        assert (BENCHMARK.parent / relative).read_bytes() == content.encode("utf-8"), relative


def keys(structure):
    return tuple(item.key() for item in structure.participant_signatures)


def test_assets_carry_the_specified_interaction():
    assets, _ = load_benchmark(BENCHMARK)
    structures = {asset.asset_id: asset_structure_query(asset) for asset in assets}
    assert keys(structures["acc-cutin-left-80"]) == ("vehicle@front_left:same:cruise+lane_change",)
    assert keys(structures["aeb-ped-far-40"]) == ("pedestrian@front_left:crossing:cruise",)
    assert keys(structures["bsm-rear-left-60"]) == ("vehicle@rear_left:same:cruise",)
    assert keys(structures["aeb-ccrm-50-unplaced"]) == ("vehicle@unknown:unknown:cruise",)
    assert structures["aeb-ccrs-50-curve"].road_features == frozenset({"curve"})
    assert dict(structures["aeb-ccrb-50-rain"].environment)["weather"] == "rain"


def test_labels_are_consistent():
    _, cases = load_benchmark(BENCHMARK)
    assert len(cases) == 35
    for case, _ in cases:
        assert not set(case["relevant"]) & set(case.get("confusers", {}))
        assert case["best_level"] in {"direct", "modify", "review", "new_build"}


@pytest.mark.parametrize("naming", ["descriptive", "opaque"])
def test_workbench_ranking_meets_the_benchmark_gate(naming):
    assets, cases = load_benchmark(BENCHMARK, naming)
    index = OpenXIndex(assets, HashingEncoder())
    result = score([(case, rank(index, assets, query, "full")) for case, query in cases])
    assert result["recall_at_1"] == 1
    assert result["decision_accuracy"] == 1
    assert result["verdict_accuracy"] == 1
    assert result["false_direct"] == 0
    assert result["unsafe_reuse"] == 0


def test_opaque_names_defeat_similarity_but_not_structure():
    report = run(BENCHMARK, ["hashing"])
    by_key = {(item["ranker"], item["naming"]): item for item in report["variants"]}
    assert by_key[("name", "opaque")]["recall_at_1"] < by_key[("name", "descriptive")]["recall_at_1"] < 1
    assert by_key[("full", "opaque")]["recall_at_1"] == by_key[("full", "descriptive")]["recall_at_1"] == 1
    # Similarity alone cannot say when the top hit needs changes.
    assert by_key[("structure-text", "descriptive")]["unsafe_reuse"] > 0
    assert report["expected_best"] == {"direct": 24, "modify": 7, "review": 1, "new_build": 3}


def test_benchmark_rejects_unknown_labels(tmp_path):
    spec = json.loads(BENCHMARK.read_text(encoding="utf-8"))
    spec["cases"][0]["relevant"] = {"missing-asset": "direct"}
    copy = tmp_path / "benchmark.json"
    copy.write_text(json.dumps(spec), encoding="utf-8")
    for folder in ("assets", "roads"):
        (tmp_path / folder).mkdir()
        for item in (BENCHMARK.parent / folder).iterdir():
            (tmp_path / folder / item.name).write_bytes(item.read_bytes())
    with pytest.raises(ValueError, match="unknown asset"):
        load_benchmark(copy)
