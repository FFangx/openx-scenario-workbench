import io
import json
from pathlib import Path

import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile
from openx_workbench.grounding import deterministic_explanation, model_explanation
from openx_workbench.pdf_pipeline import PdfPage, extract_scene_packages_from_pages
from openx_workbench.retrieval import OpenXIndex
from openx_workbench.scene_package import scene_package_to_query


def _case(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    store = AssetStore(tmp_path)
    version = store.import_files([
        AssetFile("minimal.xosc", (fixtures / "minimal.xosc").read_bytes()),
        AssetFile("minimal.xodr", (fixtures / "minimal.xodr").read_bytes()),
    ])[0]
    asset = store.load_asset(version)
    package = extract_scene_packages_from_pages([
        PdfPage(4, "7.4.1 Cut-in scenario\nTarget vehicle changes lane on a straight road. TTC = 3.0 s.")],
        "public-rules.pdf", "Public",
    )[0]
    query = scene_package_to_query(package)
    result = OpenXIndex([asset]).search(query.text, query=query)[0]
    return package, result, version


def test_structural_explanation_keeps_verdict_and_file_page_citations(tmp_path):
    package, result, version = _case(tmp_path)
    explanation = deterministic_explanation(package, result, version)
    assert explanation.verdict == result.reuse_level
    assert not explanation.insufficient_evidence
    assert {item.evidence_id for item in explanation.evidence} == {"P1", "X1", "R1", "S1"}
    story = next(item.text for item in explanation.evidence if item.evidence_id == "S1")
    assert story.startswith("road: straight") and "participants (" in story
    assert "public-rules.pdf" in explanation.evidence[0].location
    assert all("P1" in item.citations for item in explanation.observations)
    road_evidence = json.loads(next(item.text for item in explanation.evidence if item.evidence_id == "R1"))
    assert road_evidence["lane_element_count"] == result.asset.bundle.road.lane_count
    assert "lane_count" not in road_evidence


def test_model_json_must_cite_pdf_and_asset_and_cannot_replace_verdict(tmp_path):
    package, result, version = _case(tmp_path)
    requests = []

    def opener(request, timeout):
        requests.append((request, timeout))
        content = {"observations": [{"text": "The source requests a cut-in; the candidate has parsed entities.",
                                      "citations": ["P1", "X1"]}]}
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop",
                                                   "message": {"content": json.dumps(content)}}]}).encode())

    explanation = model_explanation(package, result, version, opener=opener,
                                    api_key="test-key", model="test-model")
    assert explanation.verdict == result.reuse_level
    assert explanation.observations[0].citations == ("P1", "X1")
    assert requests[0][0].get_header("Authorization") == "Bearer test-key"

    def fabricated(request, timeout):
        content = {"observations": [{"text": "Invented", "citations": ["P9", "X1"]}]}
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop",
                                                   "message": {"content": json.dumps(content)}}]}).encode())

    with pytest.raises(RuntimeError, match="evidence validation"):
        model_explanation(package, result, version, opener=fabricated, api_key="test-key")
