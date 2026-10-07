import json

import pytest

from openx_workbench.pdf_v2.models import SectionNode, SectionTree
from openx_workbench.pdf_v2.scene_first import read_structures
from openx_workbench.pdf_v2.scene_schemas import (ResolvedScene, SceneFirstExtraction, SceneStructure,
                                                  parse_scene_structure)
from openx_workbench.pdf_v2.structure_evidence import (check_contradictions, ground_structure, quote_found,
                                                       normalize, reconcile)


def structure(**raw) -> SceneStructure:
    dropped = set()
    parsed = parse_scene_structure(raw, dropped)
    assert not dropped
    return parsed


def car(bearing, quote=None, source="原文", **extra):
    evidence = {"bearing": {"source": source, "quote": quote, "reason": extra.pop("reason", None)}} if quote or source != "原文" else {}
    return {"kind": "乘用车", "bearing": bearing, "actions": ["静止"], "evidence": evidence, **extra}


TEXT = "试验道路为单向两车道，主车沿右侧车道行驶，\n右侧车道有两辆静止车辆目标。儿童从两车之间（近端）横穿。"


def test_quotes_are_found_across_line_breaks_widths_and_ellipses():
    source = normalize(TEXT + "<table><tr><td>防撞缓冲车</td></tr></table>")
    assert quote_found("右侧车道有两辆静止车辆目标", source)
    assert quote_found("「主车沿右侧车道行驶，右侧车道」", source)  # spans a line break, wrapped in quotes
    assert quote_found("试验道路为单向两车道……儿童从两车之间", source)
    assert quote_found("防撞缓冲车", source)  # a table cell
    assert not quote_found("左侧车道有两辆静止车辆目标", source)
    assert not quote_found("儿童从两车之间……试验道路", source)  # parts out of order
    assert not quote_found("……", source)


def test_a_fact_keeps_its_value_only_with_a_quote_from_its_own_text():
    raw = structure(ego_lane="最右侧车道", evidence={"ego_lane": {"source": "原文", "quote": "主车沿右侧车道行驶"}},
                    ego_turn="左转", participants=[
        car("右前方", "右侧车道有两辆静止车辆目标"),
        car("正前方", "前方同车道有静止车辆"),  # not in this scene's text
        car("左前方", "主车沿右侧车道行驶", source="推出"),  # implied without a reason
        {"kind": "行人", "bearing": "未知方位", "facing": "横向", "alternative_group": "A"},
    ])
    grounded = ground_structure(raw, TEXT)
    first, second, third, child = grounded.participants
    assert first.bearing == "右前方" and first.evidence["bearing"].source == "原文" and not first.evidence["bearing"].review
    assert second.bearing == "未知方位" and second.evidence["bearing"].source == "未知"
    assert "找不到" in second.evidence["bearing"].review and "正前方" in second.evidence["bearing"].review
    assert third.bearing == "未知方位" and "理由" in third.evidence["bearing"].review
    # No evidence at all: the facing reads as unknown; an either-or group stays, marked.
    assert child.facing == "未知" and child.alternative_group == "A"
    assert "任选组" in child.evidence["alternative_group"].review
    assert grounded.ego_lane == "最右侧车道" and grounded.ego_turn == "未知"
    assert "左转" in grounded.evidence["ego_turn"].review


def test_an_implied_fact_with_its_reason_stands():
    raw = structure(participants=[car("左前方", "主车沿右侧车道行驶", source="推出",
                                      reason="单向两车道，主车在右侧车道，相邻车道只能在左侧")])
    grounded = ground_structure(raw, TEXT)
    assert grounded.participants[0].bearing == "左前方"
    assert grounded.participants[0].evidence["bearing"].reason.startswith("单向两车道")


def test_contradictions_are_marked_not_changed():
    raw = structure(
        participants=[car("右前方", "右侧车道有两辆静止车辆目标"), car("正前方", "右侧车道有两辆静止车辆目标"),
                      {"kind": "行人", "bearing": "左前方", "facing": "横向", "age": "儿童",
                       "evidence": {"bearing": {"source": "原文", "quote": "儿童从两车之间（近端）横穿"}}}],
        relations=[["乘用车", "遮挡", "行人"]])
    checked = check_contradictions(raw)
    assert [p.bearing for p in checked.participants] == ["右前方", "正前方", "左前方"]
    first, second, child = (p.evidence["bearing"].review for p in checked.participants)
    assert "正前方" in first and "右前方" in second
    assert "近端" in child and "遮挡" in child  # the occluding cars stand right or ahead, the child left
    split = check_contradictions(structure(
        participants=[car("右前方", "q"), car("左前方", "r"), {"kind": "行人", "bearing": "左前方", "facing": "横向"}],
        relations=[["乘用车", "遮挡", "行人"]]))
    assert "evidence" not in split.participants[2].model_dump(mode="json")  # occluders on both sides: not judged
    blocked = check_contradictions(structure(
        participants=[car("右前方", "q"), {"kind": "行人", "bearing": "左前方", "facing": "横向"}],
        relations=[["乘用车", "遮挡", "行人"]]))
    assert "遮挡" in blocked.participants[1].evidence["bearing"].review
    assert check_contradictions(structure(participants=[car("右前方", "q")])).participants[0].evidence["bearing"].review is None


def test_two_readings_that_disagree_read_as_unknown():
    first = structure(ego_turn="左转", participants=[
        car("右前方", "q1", facing="同向"), {"kind": "行人", "bearing": "右前方", "facing": "横向"}])
    second = structure(ego_turn="右转", participants=[
        {"kind": "行人", "bearing": "右前方", "facing": "横向"}, car("正前方", "q2", facing="同向")])
    merged = reconcile(first, second)
    vehicle, pedestrian = merged.participants
    assert vehicle.bearing == "未知方位" and "两次读取不一致" in vehicle.evidence["bearing"].review
    assert vehicle.facing == "同向" and pedestrian.bearing == "右前方"
    assert merged.ego_turn == "未知" and not merged.review_flags
    assert reconcile(first, None) is first and reconcile(None, second) is second
    # Different participants cannot be compared one by one: the first reading stands, marked.
    other = reconcile(first, structure(participants=[car("右前方", "q1")]))
    assert other.participants == first.participants and "参与者不一致" in other.review_flags[0]
    grouped = reconcile(structure(participants=[car("正前方", alternative_group="A"), car("正前方", alternative_group="A")]),
                        structure(participants=[car("正前方"), car("正前方")]))
    assert grouped.review_flags == ("两次读取的任选分组不一致，请核对",)


def test_a_third_reading_settles_what_two_disagree_on():
    from openx_workbench.pdf_v2.structure_evidence import reconcile_readings
    left, ahead = (structure(ego_lane=lane, participants=[car(bearing, "q-" + bearing)])
                   for lane, bearing in (("最左侧车道", "左前方"), ("未知", "正前方")))
    merged = reconcile_readings([ahead, left, left])
    assert merged.participants[0].bearing == "左前方" and merged.participants[0].evidence["bearing"].quote == "q-左前方"
    assert merged.ego_lane == "最左侧车道"
    split = reconcile_readings([left, ahead, structure(participants=[car("右前方", "q-右前方")])])
    assert split.participants[0].bearing == "未知方位"
    assert split.participants[0].evidence["bearing"].review.startswith("三次读取不一致（「左前方」/「正前方」/「右前方」）")
    # A reading that names other participants takes no part in their vote.
    other = reconcile_readings([left, left, structure(participants=[car("正前方", "q"), car("正前方", "q")])])
    assert other.participants[0].bearing == "左前方" and "参与者不一致" in other.review_flags[0]


def test_structures_without_evidence_read_back_unchanged():
    stored = {"road_class": "直道", "participants": [{"kind": "乘用车", "bearing": "正前方", "facing": "同向",
                                                    "actions": ["静止"], "age": "未知"}]}
    dumped = SceneStructure.model_validate(stored).model_dump(mode="json")
    assert "evidence" not in dumped and "ego_lane" not in dumped and "review_flags" not in dumped
    assert "evidence" not in dumped["participants"][0]


def _document(count, root="1"):
    nodes = [SectionNode(node_id=root, title=f"{root} 场景", level=1, child_ids=tuple(f"{root}.{i}" for i in range(1, count + 1)),
                         page_start=1, page_end=1)]
    nodes += [SectionNode(node_id=f"{root}.{i}", title=f"{root}.{i} 场景{i}", level=2, parent_id=root, page_start=1, page_end=1)
              for i in range(1, count + 1)]
    tree = SectionTree(nodes=tuple(nodes), root_ids=(root,))
    texts = {root: "", **{f"{root}.{i}": f"主车前方同车道有静止车辆{i}" for i in range(1, count + 1)}}
    scenes = tuple(ResolvedScene(scene_id=f"scene-{i:03d}-{root}.{i}", name=f"场景{i}", story="s", anchor_node_id=f"{root}.{i}",
                                 confidence=.9, declared_member_node_ids=(f"{root}.{i}",), node_ids=(f"{root}.{i}",))
                   for i in range(1, count + 1))
    return tree, texts, SceneFirstExtraction(standard="T", heading_decoder="chain", scenes=scenes)


def _reply(scene_ids, quote=lambda scene_id: "主车前方同车道有静止车辆" + scene_id.rsplit(".", 1)[1]):
    scenes = [{"scene_id": scene_id, "structure": {"participants": [car("正前方", quote(scene_id))]}} for scene_id in scene_ids]
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"scenes": scenes})}}],
            "usage": {"completion_tokens": 10}}


def test_batches_are_read_twice_concurrently_and_grounded_per_scene(monkeypatch):
    import re
    from openx_workbench.pdf_v2 import scene_first
    monkeypatch.setattr(scene_first, "STRUCTURE_BATCH_SCENES", 4)
    tree, texts, extraction = _document(5)
    seen = []

    def transport(request, *, sample=0, timeout=None):
        content = request["messages"][1]["content"]
        ids = re.findall(r"scene_id: (\S+)", content)
        seen.append((tuple(ids), sample, timeout))
        # The second scene quotes its neighbour's sentence: not its own text.
        return _reply(ids, lambda scene_id: "主车前方同车道有静止车辆" + ("1" if scene_id.endswith("1.2") else scene_id.rsplit(".", 1)[1]))

    result, calls, missing = read_structures(tree, texts, extraction, transport=transport, model="m",
                                             prompt_version="scene-structure-prompt-v9", samples=2, concurrency=4)
    assert not missing and len(calls) == 4 and all(call.status == "ok" for call in calls)
    assert sorted((len(ids), sample) for ids, sample, _ in seen) == [(1, 0), (1, 1), (4, 0), (4, 1)]
    assert {timeout for _, _, timeout in seen} == {180, 360}
    bearings = [scene.structure.participants[0].bearing for scene in result.scenes]
    assert bearings == ["正前方", "未知方位", "正前方", "正前方", "正前方"]
    assert sum(call.usage["completion_tokens"] for call in calls) == 40


def test_a_batch_is_retried_for_broken_replies_and_missing_scenes_only(monkeypatch):
    import re
    from openx_workbench.pdf_v2 import scene_first
    monkeypatch.setattr(scene_first, "STRUCTURE_BATCH_SCENES", 4)
    tree, texts, extraction = _document(3)
    replies = iter([
        {"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]},
        None,  # answer only the first scene
        None,
    ])
    requests = []

    def transport(request, *, sample=0, timeout=None):
        content = request["messages"][1]["content"]
        requests.append(content)
        ids = re.findall(r"scene_id: (\S+)", content)
        reply = next(replies)
        return reply if reply else _reply(ids[:1])

    result, calls, missing = read_structures(tree, texts, extraction, transport=transport, model="m",
                                             prompt_version="scene-structure-prompt-v9", samples=1)
    assert len(requests) == 3 and "上一次回复有问题" in requests[1]
    assert len(re.findall(r"scene_id:", requests[2])) == 2 and "上一次回复有问题" not in requests[2]
    assert missing == ["scene-003-1.3"]
    assert calls[0].status == "partial" and calls[0].attempts == 3 and "scene-003-1.3" in calls[0].failure_detail
    assert result.scenes[2].structure is None and result.scenes[0].structure is not None


def test_a_quote_across_a_page_break_is_found():
    tree, texts, extraction = _document(4)
    for i in range(1, 5):  # a running header on every page, a page number inside scene 2's sentence
        texts[f"1.{i}"] = f"STD-HEADER-2023\n第{i}段正文"
    texts["1.2"] = "目标车停在右侧车道\n17\nSTD-HEADER-2023\n的路边"

    def transport(request, **kwargs):
        return _reply(["scene-002-1.2"], lambda scene_id: "目标车停在右侧车道的路边")

    result, _, _ = read_structures(tree, texts, extraction.model_copy(update={"scenes": extraction.scenes[1:2]}),
                                   transport=transport, model="m", prompt_version="scene-structure-prompt-v9", samples=1)
    assert result.scenes[0].structure.participants[0].bearing == "正前方"


def test_a_scene_read_alone_brings_the_clause_it_repeats():
    import re
    tree, texts, extraction = _document(3, root="A")
    texts["A.3"] = "在夜间条件下，按照A.1的方法进行试验（图A.2 不是条款，3.5 m 也不是）"
    seen = {}

    def transport(request, **kwargs):
        content = request["messages"][1]["content"]
        ids = re.findall(r"scene_id: (\S+)", content)
        seen.update({scene_id: content for scene_id in ids})
        return _reply(ids, lambda scene_id: "主车前方同车道有静止车辆")

    from openx_workbench.pdf_v2 import scene_first
    original, scene_first.STRUCTURE_BATCH_SCENES = scene_first.STRUCTURE_BATCH_SCENES, 1
    try:
        result, _, missing = read_structures(tree, texts, extraction, transport=transport, model="m",
                                             prompt_version="scene-structure-prompt-v9", samples=1)
    finally:
        scene_first.STRUCTURE_BATCH_SCENES = original
    assert not missing
    night = seen["scene-003-A.3"]
    # The referenced clause comes along as a section the scene uses, and its quote counts.
    assert "[A.1] (L2)" in night and "共用章节：A.1" in night and "[A.2]" not in night
    assert result.scenes[2].structure.participants[0].bearing == "正前方"
    assert "共用章节" not in seen["scene-002-A.2"]


def test_a_failure_that_cannot_pass_next_time_is_not_retried():
    from openx_workbench.llm_service import ModelError
    tree, texts, extraction = _document(1)
    attempts = []

    def transport(request, **kwargs):
        attempts.append(1)
        raise ModelError("单文档模型调用达到上限")

    _, calls, missing = read_structures(tree, texts, extraction, transport=transport, model="m",
                                        prompt_version="scene-structure-prompt-v9", samples=1)
    assert len(attempts) == 1 and missing == ["scene-001-1.1"] and calls[0].status == "failed"


def test_a_stated_ego_lane_is_kept_as_an_adjustable_check():
    from openx_workbench.reuse_policy import TIER_ADJUSTABLE, difference_tier
    from openx_workbench.scene_package import ScenePackage, scene_package_to_query
    package = ScenePackage("p", "t", "x", structure={"ego_lane": "最右侧车道", "participants": []})
    query = scene_package_to_query(package)
    assert "ego_lane=最右侧车道" in query.unverified
    assert difference_tier("unverified", "ego_lane=最右侧车道") == TIER_ADJUSTABLE


@pytest.mark.parametrize("field", ["bearing", "facing"])
def test_an_unknown_value_needs_no_evidence(field):
    raw = structure(participants=[{"kind": "乘用车", "evidence": {field: {"source": "原文", "quote": "不存在的话"}}}])
    assert ground_structure(raw, TEXT).participants[0].evidence == {}


def test_a_clause_that_is_all_heading_brings_the_clause_and_figure_it_names():
    from openx_workbench.pdf_v2.figures import Figure
    from openx_workbench.pdf_v2.scene_first import _Document, scene_figures
    tree, texts, extraction = _document(3, root="A")
    nodes = [node.model_copy(update={"section_id": node.node_id}) for node in tree.nodes]
    nodes[3] = nodes[3].model_copy(update={"title": "A.3 在夜间条件下，按照A.1的方法进行试验，位置如图A.2所示"})
    tree = tree.model_copy(update={"nodes": tuple(nodes)})
    texts["A.3"] = ""  # a one-sentence clause: its heading is all it says
    figures = [Figure("图A.2", "图A.2 试验示意图", 1, (0, 0, 10, 10), b"\x89PNG", "A.2")]
    night = extraction.scenes[2]
    assert _Document(tree, texts, extraction, figures).referenced(night) == ("A.1",)
    assert [figure.label for figure in scene_figures(tree, texts, extraction, figures)[night.scene_id]] == ["图A.2"]
    # Its own number is no reference to itself or to anything else.
    assert _Document(tree, texts, extraction, figures).referenced(extraction.scenes[0]) == ()
