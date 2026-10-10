import json

import pytest

from openx_workbench.pdf_v2.models import SectionNode, SectionTree
from openx_workbench.pdf_v2.scene_first import read_variants
from openx_workbench.pdf_v2.scene_proposer import SceneResponseInvalid
from openx_workbench.pdf_v2.scene_schemas import ResolvedScene, SceneFirstExtraction
from openx_workbench.pdf_v2.scene_variants import (NONE, VARIANT_PROMPT_VERSION, ground_variants,
                                                   parse_variant_response, reconcile_variant_readings,
                                                   resolve_variant_prompt)


def reply(content):
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(content, ensure_ascii=False)}}],
            "usage": {"completion_tokens": 5}}


LIMITS = {
    "dimensions": [{"name": "限速标志", "kind": "限速", "how": "按被测车选一", "quote": "限速标志选取限速100 km/h 标志"}],
    "variants": [{"label": f"限速 {v} km/h", "values": {"限速标志": f"{v} km/h"}} for v in (100, 80, 60, 40)],
}


def test_the_prompt_is_frozen():
    assert VARIANT_PROMPT_VERSION == "scene-variants-prompt-v2" and "工况" in resolve_variant_prompt()
    # v2 asks for the source's language; v1 stays as it was.
    v1, v2 = resolve_variant_prompt("scene-variants-prompt-v1"), resolve_variant_prompt()
    assert "用原文的语言写" in v2 and "用原文的语言写" not in v1


def test_a_reply_lists_dimensions_and_runs():
    variants = parse_variant_response(reply(LIMITS))
    assert [v.label for v in variants.variants] == ["限速 100 km/h", "限速 80 km/h", "限速 60 km/h", "限速 40 km/h"]
    assert variants.dimensions[0].how == "按被测车选一" and variants.dimensions[0].kind == "限速"


def test_one_run_is_none_and_an_unknown_kind_is_other():
    assert parse_variant_response(reply({"dimensions": [], "variants": []})) == NONE
    assert parse_variant_response(reply({"dimensions": [], "variants": [{"label": "唯一", "values": {}}]})) == NONE
    odd = parse_variant_response(reply({
        "dimensions": [{"name": "照明", "kind": "灯光", "how": "都要做", "quote": "q"}],
        "variants": [{"label": "开灯", "values": {"照明": "开", "未声明": "x"}}, {"label": "开灯", "values": {"照明": "关"}}]}))
    assert odd.dimensions[0].kind == "其他"
    # Values only for declared dimensions; a repeated label is told apart.
    assert odd.variants[0].values == {"照明": "开"} and [v.label for v in odd.variants] == ["开灯", "开灯 (2)"]


def test_an_unknown_how_makes_the_reply_invalid():
    with pytest.raises(SceneResponseInvalid):
        parse_variant_response(reply({"dimensions": [{"name": "时段", "kind": "时段", "how": "看情况"}],
                                      "variants": [{"label": "日", "values": {}}, {"label": "夜", "values": {}}]}))


def test_an_unfound_quote_is_marked_not_dropped():
    variants = parse_variant_response(reply(LIMITS))
    kept = ground_variants(variants, "a) 若Vsmaxset＞100 km/h，限速标志选取限速100 km/h 标志；")
    assert kept.dimensions[0].review is None
    marked = ground_variants(variants, "试验车辆以 Vsmaxset 巡航")
    assert "找不到" in marked.dimensions[0].review and len(marked.variants) == 4


def test_readings_settle_on_the_count_most_agree_on():
    four = parse_variant_response(reply(LIMITS))
    two = four.model_copy(update={"variants": four.variants[:2]})
    assert reconcile_variant_readings([four, four, four]) == four
    settled = reconcile_variant_readings([two, four, four])
    assert len(settled.variants) == 4 and "2 / 4 / 4" in settled.review_flags[-1]
    # No majority: the median count.
    assert len(reconcile_variant_readings([NONE, two, four]).variants) == 2
    assert reconcile_variant_readings([None, None]) is None and reconcile_variant_readings([None, NONE]) == NONE


def _document():
    nodes = (SectionNode(node_id="7.4.1", title="7.4.1 限速试验", level=1, page_start=1, page_end=1),
             SectionNode(node_id="7.4.2", title="7.4.2 换道试验", level=1, page_start=1, page_end=1))
    tree = SectionTree(nodes=nodes, root_ids=("7.4.1", "7.4.2"))
    texts = {"7.4.1": "a) 若Vsmaxset＞100 km/h，限速标志选取限速100 km/h 标志；", "7.4.2": "试验车辆向左换道。"}
    scenes = tuple(ResolvedScene(scene_id=f"scene-00{i}-{node}", name=name, story="s", anchor_node_id=node, confidence=.9,
                                 declared_member_node_ids=(node,), node_ids=(node,))
                   for i, (node, name) in enumerate((("7.4.1", "限速试验"), ("7.4.2", "换道试验")), 1))
    return tree, texts, SceneFirstExtraction(standard="T", heading_decoder="chain", scenes=scenes)


def test_each_scene_is_read_alone_several_times():
    tree, texts, extraction = _document()
    seen = []

    def transport(request, *, sample=0, timeout=None):
        content = request["messages"][1]["content"]
        seen.append((content.rsplit("\n", 1)[-1], sample))
        if "限速试验" in content:
            assert "[7.4.1]" in content and "[7.4.2]" not in content
            return reply(LIMITS)
        return reply({"dimensions": [], "variants": []})

    result, usage, missing = read_variants(tree, texts, extraction, transport=transport, model="m", samples=3, concurrency=4)
    assert not missing and sorted(seen) == sorted((name, s) for name in ("限速试验", "换道试验") for s in range(3))
    assert len(result["scene-001-7.4.1"].variants) == 4 and result["scene-002-7.4.2"] == NONE
    assert usage["completion_tokens"] == 30


def test_a_broken_reply_is_asked_again_and_a_lost_scene_is_reported():
    tree, texts, extraction = _document()
    extraction = extraction.model_copy(update={"scenes": extraction.scenes[:1]})
    replies = iter([{"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]}, reply(LIMITS)])
    requests = []

    def transport(request, **kwargs):
        requests.append(request["messages"][1]["content"])
        return next(replies)

    result, _, missing = read_variants(tree, texts, extraction, transport=transport, model="m", samples=1)
    assert len(requests) == 2 and "上一次回复有问题" in requests[1] and len(result["scene-001-7.4.1"].variants) == 4

    def failing(request, **kwargs):
        from openx_workbench.llm_service import ModelError
        raise ModelError("单文档模型调用达到上限")

    result, _, missing = read_variants(tree, texts, extraction, transport=failing, model="m", samples=1)
    assert missing == ["scene-001-7.4.1"] and not result
