import json
import re

import pymupdf

from openx_workbench.pdf_v2.figures import Figure, caption_label, find_figures, referenced_labels
from openx_workbench.pdf_v2.models import SectionNode, SectionTree
from openx_workbench.pdf_v2.parser import parse_pdf_structure
from openx_workbench.pdf_v2.section_tree import build_section_tree
from openx_workbench.pdf_v2.scene_first import read_structures
from openx_workbench.pdf_v2.scene_schemas import ResolvedScene, SceneFirstExtraction, parse_scene_structure
from openx_workbench.pdf_v2.structure_evidence import ground_structure


def test_captions_are_told_from_sentences_that_name_a_figure():
    assert caption_label("图C.10 日间儿童目标横穿被车辆目标遮挡试验示意图") == "图C.10"
    assert caption_label("图2- 6 跟车距离设置示意图") == "图2-6"
    assert caption_label("图 A.1 前方车辆静止（夜间）场景示意图") == "图A.1"
    assert caption_label("图5所示为试验道路") is None
    assert caption_label("图5 中目标车停在右侧车道，主车匀速驶近。") is None
    assert referenced_labels("试验场景如图C.10和图 5 所示，见图C.10") == ["图C.10", "图5"]
    # A caption followed by its page number, and a figure of another standard, are no references.
    assert referenced_labels("图8 换道试验示意图 25") == ["图8"]
    assert referenced_labels("尺寸符合GB 5768.4—2017中图B.4的要求，按照图C.1、图C.2进行") == ["图C.1", "图C.2"]


def _pdf() -> bytes:
    document = pymupdf.open()
    page = document.new_page(width=595, height=842)
    page.insert_text((72, 60), "1.1 试验场景", fontname="china-s", fontsize=12)
    page.insert_text((72, 100), "试验时主车沿右侧车道匀速行驶，目标车静止在前方同车道。", fontname="china-s", fontsize=10)
    page.draw_rect(pymupdf.Rect(100, 160, 480, 300))  # the road
    page.draw_line((100, 230), (480, 230), dashes="[6] 0")
    page.insert_text((120, 260), "试验车辆", fontname="china-s", fontsize=9)  # a label in the drawing
    page.insert_text((80, 330), "标引序号说明：", fontname="china-s", fontsize=9)
    page.insert_text((80, 345), "①——目标车道边线。", fontname="china-s", fontsize=9)
    page.insert_text((240, 380), "图1 试验示意图 12", fontname="china-s", fontsize=10)  # and its page number
    page.insert_text((72, 430), "图2 只有图题的图", fontname="china-s", fontsize=10)  # nothing drawn above it
    page = document.new_page(width=595, height=842)
    page.insert_text((72, 60), "1.2 另一个场景", fontname="china-s", fontsize=12)
    page.draw_rect(pymupdf.Rect(100, 100, 480, 200))
    # A caption laid out in one block with the text after it.
    page.insert_textbox(pymupdf.Rect(72, 210, 520, 300), "图3 合并的图题\n测试方法：主车以 60 km/h 匀速驶近目标。",
                        fontname="china-s", fontsize=10)
    data = document.tobytes()
    document.close()
    return data


def test_a_figure_is_the_drawing_between_its_caption_and_the_text_above(tmp_path):
    data = _pdf()
    path = tmp_path / "f.pdf"
    path.write_bytes(data)
    parsed, outline = parse_pdf_structure(path, heading_decoder="greedy")
    tree = build_section_tree(parsed, outline=outline)
    figures = find_figures(data, parsed.blocks, tree)
    assert [figure.label for figure in figures] == ["图1", "图3"]
    figure, merged = figures
    x0, y0, x1, y1 = figure.clip
    body = next(b for b in parsed.blocks if b.text.startswith("试验时"))
    caption = next(b for b in parsed.blocks if b.text.startswith("图1"))
    # Below the running text; the road, its label, the key and the caption are inside.
    assert body.bbox[3] < y0 <= 160 and x0 <= 100 and x1 >= 480 and y1 >= caption.bbox[3]
    assert figure.png.startswith(b"\x89PNG") and figure.caption == "图1 试验示意图" and figure.page_number == 1
    # Each figure belongs to the section it is in.
    titles = {node.node_id: node.title for node in tree.nodes}
    assert titles[figure.node_id].startswith("1.1") and titles[merged.node_id].startswith("1.2")
    assert merged.page_number == 2 and merged.clip[1] >= 96 and merged.clip[3] < 240


def _scene_document():
    nodes = (SectionNode(node_id="1", title="1 场景", level=1, child_ids=("1.1", "1.2"), page_start=1, page_end=1),
             SectionNode(node_id="1.1", title="1.1 场景一", level=2, parent_id="1", page_start=1, page_end=1,
                         block_ids=("p1-b0", "p1-b1")),
             SectionNode(node_id="1.2", title="1.2 场景二", level=2, parent_id="1", page_start=1, page_end=1,
                         block_ids=("p1-b2",)))
    tree = SectionTree(nodes=nodes, root_ids=("1",))
    texts = {"1": "", "1.1": "儿童从停放车辆之间横穿，位置如图1所示\n图1 试验示意图", "1.2": "前方同车道有静止车辆，见图1"}
    scenes = tuple(ResolvedScene(scene_id=f"scene-00{i}-1.{i}", name=f"场景{i}", story="s", anchor_node_id=f"1.{i}",
                                 confidence=.9, declared_member_node_ids=(f"1.{i}",), node_ids=(f"1.{i}",))
                   for i in (1, 2))
    figures = [Figure("图1", "图1 试验示意图", 1, (0, 0, 100, 50), b"\x89PNG-1", "1.1")]
    return tree, texts, SceneFirstExtraction(standard="T", heading_decoder="chain", scenes=scenes), figures


def _child(bearing, quote, reason):
    return {"kind": "行人", "bearing": bearing, "facing": "横向", "actions": ["匀速行驶"], "age": "儿童",
            "evidence": {"bearing": {"source": "图", "quote": quote, "reason": reason},
                         "facing": {"source": "原文", "quote": "横穿"}}}


def test_a_scene_is_read_with_its_figures_and_a_figure_reading_names_one_of_them():
    tree, texts, extraction, figures = _scene_document()
    requests = {}

    def transport(request, **kwargs):
        content = request["messages"][1]["content"]
        text = content if isinstance(content, str) else "\n".join(part.get("text", "") for part in content)
        scene_id = re.findall(r"scene_id: (\S+)", text)[0]
        requests[scene_id] = content
        participant = _child("右前方", "图1", "图中儿童从主车右侧路边出发") if scene_id.endswith("1.1") else \
            _child("右前方", "图3", "图中目标在右前方")
        reply = {"scenes": [{"scene_id": scene_id, "structure": {"participants": [participant]}}]}
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(reply)}}]}

    result, calls, missing = read_structures(tree, texts, extraction, transport=transport, model="m",
                                             prompt_version="scene-structure-prompt-v10", samples=1, figures=figures)
    assert not missing
    first = requests["scene-001-1.1"]
    images = [part for part in first if part["type"] == "image_url"]
    assert len(images) == 1 and images[0]["image_url"]["url"].startswith("data:image/png;base64,")
    assert "示意图：图1" in first[0]["text"] and first[1]["text"].startswith("图1（第 1 页）")
    # The second scene names figure 1 in its text, so it is read with it too.
    assert any(part["type"] == "image_url" for part in requests["scene-002-1.2"])
    assert [call.figures for call in calls] == [("图1",), ("图1",)]
    read, wrong = (scene.structure.participants[0] for scene in result.scenes)
    assert read.bearing == "右前方" and read.evidence["bearing"].source == "图"
    assert wrong.bearing == "未知方位" and "不是本场景附的示意图" in wrong.evidence["bearing"].review
    # Without figures (a model that reads no images) the request stays plain text.
    plain = {}
    read_structures(tree, texts, extraction, transport=lambda request, **kwargs: plain.setdefault(0, request) and transport(request),
                    model="m", prompt_version="scene-structure-prompt-v10", samples=1)
    assert isinstance(plain[0]["messages"][1]["content"], str)


def test_standing_targets_read_from_one_figure_may_stand_on_two_sides():
    from openx_workbench.pdf_v2.structure_evidence import check_contradictions
    row = lambda bearing: {"kind": "乘用车", "bearing": bearing, "actions": ["静止"],  # noqa: E731
                           "evidence": {"bearing": {"source": "图", "quote": "图C.4", "reason": "图中一排停放的车"}}}
    checked = check_contradictions(parse_scene_structure({"participants": [row("左前方"), row("右前方")]}, set()))
    assert all(p.evidence["bearing"].review is None for p in checked.participants)


def test_a_figure_reading_without_what_it_shows_reads_as_unknown():
    raw = parse_scene_structure({"participants": [_child("右前方", "图1", None)]}, set())
    grounded = ground_structure(raw, "文字", figures=["图1"])
    assert grounded.participants[0].bearing == "未知方位"
    assert "没有写图里看到的" in grounded.participants[0].evidence["bearing"].review
    kept = ground_structure(parse_scene_structure({"participants": [_child("右前方", "图 1", "图中在右前方")]}, set()),
                            "文字", figures=["图1"])
    assert kept.participants[0].bearing == "右前方"
    assert ground_structure(kept, "文字").participants[0].bearing == "未知方位"  # the figure was not sent


def test_a_retry_note_follows_the_figures():
    tree, texts, extraction, figures = _scene_document()
    extraction = extraction.model_copy(update={"scenes": extraction.scenes[:1]})
    requests = []

    def transport(request, **kwargs):
        requests.append(request["messages"][1]["content"])
        if len(requests) == 1:
            return {"choices": [{"finish_reason": "stop", "message": {"content": "not json"}}]}
        reply = {"scenes": [{"scene_id": "scene-001-1.1", "structure": {"participants": []}}]}
        return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(reply)}}]}

    read_structures(tree, texts, extraction, transport=transport, model="m",
                    prompt_version="scene-structure-prompt-v10", samples=1, figures=figures)
    assert len(requests) == 2 and requests[1][-1]["type"] == "text" and "上一次回复有问题" in requests[1][-1]["text"]
    assert requests[1][:-1] == requests[0]
