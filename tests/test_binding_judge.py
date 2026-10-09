import json

import pytest

from openx_workbench import binding_judge
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


def test_a_kept_story_is_told_once_and_the_request_reads_the_same(monkeypatch):
    package = requirement()
    result = search(package, authored_asset(function="AEB"))[0]
    pool = [(result.asset, result.differences)]
    told, story = [], binding_judge.asset_story
    monkeypatch.setattr(binding_judge, "asset_story", lambda asset: told.append(asset) or story(asset))
    stories = {}
    first = judge_request(package, pool, stories=stories)
    assert judge_request(package, pool, stories=stories) == first == judge_request(package, pool)  # cached replies still match
    assert len(told) == 2  # once for the kept stories, once for the request that keeps none


def test_reasons_are_asked_in_the_interface_language():
    package = requirement()
    result = search(package, authored_asset(function="AEB"))[0]
    pool = [(result.asset, result.differences)]
    chinese, english = judge_request(package, pool), judge_request(package, pool, language="en")
    assert chinese["messages"][0]["content"] == binding_judge.SYSTEM  # the cached Chinese replies still answer it
    assert english["messages"][0]["content"] == binding_judge.SYSTEM + binding_judge.ENGLISH
    assert english["messages"][1] == chinese["messages"][1]


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


CONDITIONS = {"dimensions": [{"name": "时段", "kind": "时段", "how": "都要做", "quote": "在夜间条件下重复"}],
              "variants": [{"label": "日间", "values": {"时段": "日间"}}, {"label": "夜间", "values": {"时段": "夜间"}},
                           {"label": "预试验", "values": {}}]}


def test_a_scene_with_test_conditions_asks_for_an_asset_per_condition():
    package = requirement()
    result = search(package, authored_asset(function="AEB"))[0]
    pool = [(result.asset, result.differences)]
    plain = judge_request(package, pool)
    asked = judge_request(package, pool, conditions=CONDITIONS, language="en")
    assert asked["messages"][0]["content"] == binding_judge.SYSTEM + binding_judge.CONDITIONS + binding_judge.ENGLISH
    assert asked["messages"][1]["content"].endswith(
        "## 工况\n维度：时段（都要做）\n- V1 日间：时段=日间\n- V2 夜间：时段=夜间\n- V3 预试验")
    # A scene of one run reads as before, so its cached replies still answer it.
    one = {"dimensions": [], "variants": [{"label": "日间", "values": {}}]}
    assert judge_request(package, pool, conditions=one) == judge_request(package, pool, conditions=None) == plain


def test_each_condition_gets_a_candidate_of_the_binding_or_none():
    judgement = parse_judgement(reply({
        "candidates": candidates(C1="同一测试", C2="同一测试但要改", C3="不是"),
        "binding": ["C1"], "preferred": "C1",
        "conditions": [{"id": "V2", "asset": "C2", "fit": "修改复用", "changes": "改为夜间"},
                       {"id": "V1", "asset": "C1", "fit": "直接复用", "changes": "不用改"},
                       {"id": "V3", "asset": "C3", "fit": "直接复用"}]}), 3, 3)
    assert [(item.id, item.asset, item.fit, item.changes) for item in judgement.conditions] == [
        ("V1", "C1", "直接复用", "不用改"), ("V2", "C2", "修改复用", "改为夜间"), ("V3", None, "", "")]
    assert judgement.binding == ("C1", "C2")  # a candidate given a condition joins the binding; one judged "不是" never
    assert judgement.preferred is None  # with test conditions, no preferred asset
    unnamed = parse_judgement(reply({"candidates": candidates(C1="同一测试"), "binding": ["C1"],
                                     "conditions": [{"id": "V1", "asset": "C1"}, {"id": "V2", "asset": None}]}), 1, 2)
    assert unnamed.conditions[0].fit == "修改复用"  # a fit it does not name is the cautious one


@pytest.mark.parametrize("conditions", [
    None,  # no list
    [{"id": "V1", "asset": "C1"}],  # V2 not answered
    [{"id": "V1", "asset": "C1"}, {"id": "V1", "asset": None}, {"id": "V2", "asset": None}],  # V1 twice
    [{"id": "V1", "asset": "C9"}, {"id": "V2", "asset": None}],  # no such candidate
    [{"id": "V1", "asset": "C1"}, {"id": "V3", "asset": None}],  # no such condition
])
def test_replies_that_do_not_cover_the_conditions_are_refused(conditions):
    with pytest.raises(JudgementInvalid):
        parse_judgement(reply({"candidates": candidates(C1="同一测试"), "binding": ["C1"],
                               **({"conditions": conditions} if conditions is not None else {})}), 1, 2)
