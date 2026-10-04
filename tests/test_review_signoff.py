"""Saving a decision that needs review: every open item is confirmed with a reason, and the trace keeps them."""
import pytest

from openx_workbench import reuse_policy
from openx_workbench.reuse import classify_reuse_level
from openx_workbench.reuse_differences import ReuseDifference
from openx_workbench.reuse_trace import review_items, sign_off


def _change(cost, verified=True):
    return ReuseDifference("parameter", "ttc_s=3", "ttc_s=2", "set parameter in XOSC", cost=cost, verified=verified)


def test_costly_verified_changes_are_a_major_modification():
    below = reuse_policy.MAJOR_MODIFY_COST - 0.5
    assert classify_reuse_level((_change(below),)) == "modify"
    assert classify_reuse_level((_change(below), _change(0.5))) == "major_modify"
    assert classify_reuse_level((_change(reuse_policy.MAJOR_MODIFY_COST), _change(0.5, verified=False))) == "review"


def _trace(level, structural, differences):
    return {"reuse": {"level": level, "structural_level": structural, "differences": differences}}


def test_review_items_are_the_unverified_differences_or_the_standards_gate():
    verified = {"category": "parameter", "requested": "ttc_s=3", "candidate": "ttc_s=2", "verified": True}
    open_item = {"category": "unverified", "requested": "lane_marking=实线", "candidate": "not extracted",
                 "verified": False}
    assert review_items(_trace("modify", "modify", [verified])["reuse"]) == []
    assert review_items(_trace("review", "review", [verified, open_item])["reuse"]) == [
        {"id": "difference:unverified:lane_marking=实线:not extracted", "kind": "difference", "difference": 1}]
    assert review_items(_trace("review", "direct", [])["reuse"]) == [
        {"id": "standards", "kind": "standards", "difference": None}]


def test_sign_off_needs_a_reason_for_every_item_and_nothing_else():
    trace = _trace("review", "direct", [])
    with pytest.raises(ValueError, match="1 open"):
        sign_off(trace, {})
    with pytest.raises(ValueError, match="1 open"):
        sign_off(trace, {"standards": "   "})
    with pytest.raises(ValueError, match="do not match"):
        sign_off(trace, {"standards": "XSD unavailable offline; checked in esmini", "other": "x"})
    with pytest.raises(ValueError, match="do not match"):
        sign_off(_trace("direct", "direct", []), {"standards": "x"})
    signed = sign_off(trace, {"standards": " XSD unavailable offline; checked in esmini "})
    assert signed["reuse"]["level"] == "review"
    assert signed["reuse"]["review_signoff"]["items"] == [
        {"id": "standards", "kind": "standards", "reason": "XSD unavailable offline; checked in esmini"}]
    assert "review_signoff" not in trace["reuse"]


def test_a_reviewed_decision_is_saved_with_its_reasons(workbench):
    client, base, version = workbench
    scene_path = f"/api/projects/{base['project_id']}/documents/{base['document_id']}/scenes/{base['scene_id']}"
    # A typed requirement whose lane marking the XML reader cannot check: one item to review.
    revised = client.post(f"{scene_path}/revisions", json={"edits": {"structure": {"lane_marking": "实线"}}})
    assert revised.status_code == 200
    request = {**base, "revision": revised.json()["revision"]}
    candidate = client.post("/api/search", json=request).json()["results"][0]
    assert candidate["level"] == "review" and candidate["review_items"]
    decision = {**request, "asset_id": version.asset_id, "version_id": version.version_id}

    refused = client.post("/api/decisions", json=decision)
    assert refused.status_code == 400 and "Confirm each review item" in refused.json()["detail"]
    confirmations = [{"item": item["id"], "reason": "Solid marking confirmed in the source drawing"}
                     for item in candidate["review_items"]]
    saved = client.post("/api/decisions", json={**decision, "confirmations": confirmations})
    assert saved.status_code == 200

    listed = client.get(f"/api/projects/{base['project_id']}/reports").json()[0]
    assert listed["level"] == "review" and listed["signed_off"] is True
    detail = client.get(f"/api/projects/{base['project_id']}/reports/{saved.json()['report_id']}").json()
    signoff = detail["trace"]["reuse"]["review_signoff"]
    assert [item["reason"] for item in signoff["items"]] == ["Solid marking confirmed in the source drawing"] * len(
        confirmations)
    html = client.get(f"/api/projects/{base['project_id']}/reports/{saved.json()['report_id']}/download?format=html")
    assert "Solid marking confirmed in the source drawing" in html.text
