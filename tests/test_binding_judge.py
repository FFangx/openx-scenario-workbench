import json

import pytest

from openx_workbench.binding_judge import JudgementInvalid, judge_request, parse_judgement
from openx_workbench.scene_package import EvidenceRef
from test_structured_reuse import authored_asset, requirement, search


def reply(data, finish="stop"):
    return {"choices": [{"finish_reason": finish, "message": {"content": json.dumps(data, ensure_ascii=False)}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5}}


def candidates(**verdicts):
    return [{"id": key, "verdict": value, "reason": "依据"} for key, value in verdicts.items()]


def test_request_sends_source_text_story_and_differences_and_can_hide_names():
    package = requirement()
    package.evidence = [EvidenceRef("doc.pdf", "5.1", 3, 3, "目标车辆在本车道前方匀速行驶。")]
    package.structure["participants"][0]["evidence"] = {"bearing": {"source": "原文", "quote": "前方"}}
    asset = authored_asset(function="AEB")
    asset.title = "Library name 7.1"
    result = search(package, asset)[0]
    named = judge_request(package, [(result.asset, result.differences)])["messages"][1]["content"]
    hidden = judge_request(package, [(result.asset, result.differences)], show_names=False)["messages"][1]["content"]
    assert "[5.1] 目标车辆在本车道前方匀速行驶。" in named and "### C1" in named
    assert "素材故事：" in named and "与需求的差异：" in named
    assert "Library name 7.1" in named and "Library name 7.1" not in hidden
    assert '"evidence"' not in named  # the quoted evidence is left out; the source text is sent whole
    assert package.structure["participants"][0]["evidence"]  # the stored structure is untouched


def test_binding_keeps_only_candidates_judged_the_same_test():
    judgement = parse_judgement(reply({
        "candidates": candidates(C1="同一测试", C2="不是", C3="同一测试但要改"),
        "binding": ["C2", "C3", "C1", "C3"], "preferred": "C2", "note": "C2 名字像，但故事不同"}), 3)
    assert judgement.binding == ("C3", "C1")
    assert judgement.preferred == "C3"  # the named preference was dropped from the binding
    assert [item.verdict for item in judgement.candidates] == ["同一测试", "不是", "同一测试但要改"]
    assert judgement.note and judgement.usage == {"prompt_tokens": 10, "completion_tokens": 5}


def test_empty_binding_means_no_asset_fits():
    judgement = parse_judgement(reply({"candidates": candidates(C1="不是", C2="拿不准"), "binding": [],
                                       "preferred": None}), 2)
    assert judgement.binding == () and judgement.preferred is None


@pytest.mark.parametrize("envelope", [
    reply({"candidates": candidates(C1="同一测试"), "binding": ["C1"]}),  # C2 not judged
    reply({"candidates": candidates(C1="同一测试", C2="差不多"), "binding": []}),  # unknown verdict
    reply({"candidates": candidates(C1="同一测试", C2="不是"), "binding": ["C9"]}),  # no such candidate
    reply({"candidates": candidates(C1="同一测试", C2="不是"), "binding": ["C1"]}, finish="length"),
    {"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]},
])
def test_replies_that_do_not_cover_the_candidates_are_refused(envelope):
    with pytest.raises(JudgementInvalid):
        parse_judgement(envelope, 2)
