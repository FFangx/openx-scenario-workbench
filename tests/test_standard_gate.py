from dataclasses import replace
import io
import json

import pytest

from openx_workbench.retrieval import HashingEncoder, OpenXIndex, catalog_fingerprint
from openx_workbench.reuse_trace import checked_trace
from openx_workbench.schema_validation import standard_gate
from openx_workbench.grounding import deterministic_explanation, model_explanation
from openx_workbench.scene_package import EvidenceRef
from openx_workbench.scene_package import scene_package_to_query
from test_structured_reuse import authored_asset, requirement
from test_project_store import _asset_store
from openx_workbench.project_store import ProjectStore
from test_batch_matching import batch_with_version


@pytest.mark.parametrize("status", ["invalid", "unavailable", "unsupported", "unknown"])
def test_standard_gate_changes_confirmation_but_keeps_structural_evidence_and_ranking(status):
    asset = authored_asset()
    asset.bundle.validation = {"scenario": {"status": status}, "road": {"status": "valid"}}
    result = OpenXIndex([asset], HashingEncoder(32)).search("", query=scene_package_to_query(requirement()))[0]
    assert result.reuse_level == "direct"  # Structural comparison remains independently inspectable.
    assert result.confirmation_level == "review" and result.confirmation_review_kind == "standards"
    assert not result.standard_checks["passed"]
    fingerprint = catalog_fingerprint([asset])
    asset.bundle.validation["scenario"] = {"status": "valid"}
    assert result.confirmation_level == "direct"
    assert catalog_fingerprint([asset]) != fingerprint


def test_missing_or_malformed_checks_fail_closed():
    for record in (None, {}, {"scenario": {"status": "valid"}}, {"scenario": None, "road": {"status": "valid"}}):
        assert not standard_gate(record)["passed"]


def test_model_explanation_cannot_upgrade_failed_standards(tmp_path):
    _, version = _asset_store(tmp_path)
    asset = authored_asset()
    asset.bundle.validation = {"scenario": {"status": "invalid"}, "road": {"status": "valid"}}
    package = requirement()
    package.evidence = [EvidenceRef("authored.pdf", "7.1", 1, 1, "Ego and target drive ahead on a straight road.")]
    result = OpenXIndex([asset], HashingEncoder(32)).search("", query=scene_package_to_query(package))[0]
    assert result.reuse_level == "direct"
    explanation = deterministic_explanation(package, result, version)
    assert explanation.verdict == "review"
    assert any("standard" in item.text.lower() for item in explanation.observations)
    assert '"standard_check": {"status": "invalid"}' in next(item.text for item in explanation.evidence if item.evidence_id == "X1")

    def opener(request, timeout):
        payload = json.loads(request.data)
        assert json.loads(payload["messages"][1]["content"])["fixed_verdict"] == "review"
        content = {"verdict": "direct", "observations": [{"text": "The structural match requires standard review.", "citations": ["P1", "X1"]}]}
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content)}}]}).encode())

    assert model_explanation(package, result, version, opener=opener, api_key="authored-test-key").verdict == "review"


def test_forged_direct_single_cannot_bypass_backend_or_pin_a_version(tmp_path):
    assets, version = _asset_store(tmp_path)
    projects = ProjectStore(assets)
    project = projects.create("Standard gate")
    trace = {"candidate": {"asset_id": version.asset_id, "version_id": version.version_id,
                           "parsed_facts": {"validation": {"scenario": {"status": "valid"}, "road": {"status": "valid"}}}},
             "reuse": {"level": "direct"}, "standard_checks": {"passed": True}}
    forged = replace(version, files=())
    with pytest.raises(ValueError, match="Standard checks"):
        projects.save_decision(project.project_id, forged, trace)
    assert projects.reports(project.project_id) == [] and assets.references(version) == ()


def test_forged_batch_summary_cannot_bypass_backend(tmp_path):
    assets, version, projects, project, batch = batch_with_version(tmp_path)
    batch["entries"][0]["assessment"] = {"level": "direct"}
    with pytest.raises(ValueError, match="Standard checks"):
        projects.save_batch(project.project_id, batch)
    assert projects.reports(project.project_id) == [] and assets.references(version) == ()


def test_direct_batch_without_candidate_is_never_confirmed(tmp_path):
    assets, version, projects, project, batch = batch_with_version(tmp_path)
    batch["entries"][0].update(assessment={"level": "direct"}, candidates=[])
    with pytest.raises(ValueError, match="checked asset candidate"):
        projects.save_batch(project.project_id, batch)
    assert checked_trace(batch)["counts"] == {"standards": 1}
    assert projects.reports(project.project_id) == []


def test_old_direct_report_is_reviewed_without_mutating_history():
    old = {"candidate": {"parsed_facts": {"validation": {"scenario": {"status": "invalid"}}}},
           "reuse": {"level": "direct"}}
    batch = {"kind": "batch_match", "entries": [{"assessment": {"level": "direct"}, "candidates": [old]}],
             "counts": {"direct": 1}}
    display = checked_trace(batch)
    assert display["counts"] == {"standards": 1}
    assert display["entries"][0]["assessment"]["structural_level"] == "direct"
    assert old["reuse"]["level"] == "direct" and batch["counts"] == {"direct": 1}
