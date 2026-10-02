from pathlib import Path

from openx_workbench.evaluation import evaluate, load_corpus
from openx_workbench.retrieval import HashingEncoder, OpenXIndex


def test_authored_multicandidate_quality_gate():
    corpus = Path(__file__).parent / "fixtures" / "reuse" / "corpus.json"
    assets, cases = load_corpus(corpus)
    result = evaluate(OpenXIndex(assets, HashingEncoder()), cases)
    assert result["case_count"] == 8
    assert result["hit_at_1"] == 1
    assert result["verdict_accuracy"] == 1
    assert result["false_direct"] == 0


def test_structural_results_survive_asset_renaming():
    corpus = Path(__file__).parent / "fixtures" / "reuse" / "corpus.json"
    assets, cases = load_corpus(corpus)
    for index, asset in enumerate(assets):
        asset.title = f"Opaque renamed asset {index}"
        asset.bundle.scenario.name = asset.title
        asset.bundle.scenario.description = asset.title
    result = evaluate(OpenXIndex(assets, HashingEncoder()), cases)
    assert result["hit_at_1"] == 1
    assert result["verdict_accuracy"] == 1
