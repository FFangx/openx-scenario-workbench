import io
import json
import re
from dataclasses import asdict

import pymupdf
import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.llm_service import ModelClient, ModelConfig
from openx_workbench.pdf_extraction import extract_pdf
from openx_workbench.pdf_v2.scene_proposer import build_language_note
from openx_workbench.pdf_store import PdfStore
from openx_workbench.project_store import ProjectStore


def authored_pdf(figure=False):
    with pymupdf.open() as document:
        for heading, body in [
            ("1.1 Test conditions", "All tests use a dry straight road in daylight. No rain is permitted."),
            ("2.1 Stationary car braking", "The ego vehicle approaches a stationary target car ahead at 50 km/h. Test AEB braking."),
            ("2.2 Pedestrian crossing", "A pedestrian crosses the road ahead of the ego vehicle at 30 km/h. Test AEB braking."),
        ]:
            page = document.new_page()
            page.insert_text((60, 60), heading, fontsize=16)
            page.insert_textbox((60, 90, 500, 200), body, fontsize=11)
            if figure and heading.startswith("2.2"):  # a figure where the pedestrian starts
                page.draw_rect(pymupdf.Rect(60, 220, 400, 320))
                page.insert_text((150, 345), "图1 行人横穿示意图", fontname="china-s", fontsize=10)
        document.set_toc([[1, "1.1 Test conditions", 1], [1, "2.1 Stationary car braking", 2], [1, "2.2 Pedestrian crossing", 3]])
        return document.tobytes()


def structure_reply(body):
    """A structure batch answered like the model: the stationary car is quoted from its text, the
    pedestrian's side rests on a quote its text does not contain, or on its figure when one is sent."""
    text = message_text(body)
    assert text.startswith("===== 全文档共用的试验条件 =====")
    figures = re.findall(r"示意图：(\S+)", text)
    scenes = []
    for scene_id in re.findall(r"scene_id: (\S+)", text):
        car = scene_id.endswith("2.1")
        if car:
            bearing = {"source": "原文", "quote": "a stationary target car ahead"}
        elif figures:
            bearing = {"source": "图", "quote": figures[0], "reason": "图中行人从右侧路边出发"}
        else:
            bearing = {"source": "原文", "quote": "from the right kerb"}
        participant = {"kind": "乘用车" if car else "行人", "bearing": "正前方" if car else "右前方",
                       "facing": "未知" if car else "横向", "actions": ["静止"] if car else ["匀速行驶"],
                       "evidence": {"bearing": bearing,
                                    **({} if car else {"facing": {"source": "原文", "quote": "A pedestrian crosses the road"}})}}
        scenes.append({"scene_id": scene_id, "structure": {"tested_function": "AEB", "road_class": "直道",
                                                           "ego_actions": ["匀速行驶"], "participants": [participant]}})
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps({"scenes": scenes})}}],
            "usage": {"total_tokens": 100}}


def message_text(body):
    """The text of the user message, also when figures come with it as content parts."""
    content = body["messages"][1]["content"]
    return content if isinstance(content, str) else "\n".join(part.get("text", "") for part in content)


def variant_reply(body):
    """A scene's test conditions: the pedestrian crossing is run by day and by night, the car once."""
    pedestrian = message_text(body).endswith("Pedestrian crossing")
    payload = {"dimensions": [{"name": "时段", "kind": "时段", "how": "都要做", "quote": "A pedestrian crosses the road"}],
               "variants": [{"label": "日间", "values": {"时段": "日间"}}, {"label": "夜间", "values": {"时段": "夜间"}}]
               } if pedestrian else {"dimensions": [], "variants": []}
    return {"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload, ensure_ascii=False)}}],
            "usage": {"total_tokens": 50}}


def fake_client(*, empty=False, hallucination=False):
    """A model answering scene lists (counted in `calls`), structure batches (client.structure_calls)
    and test conditions (client.variant_calls)."""
    calls = []
    structure_calls = []
    variant_calls = []
    def opener(request, timeout):
        body = json.loads(request.data)
        if "本批场景清单" in message_text(body):
            structure_calls.append(body)
            return io.BytesIO(json.dumps(structure_reply(body)).encode())
        if "===== 场景名 =====" in message_text(body):
            variant_calls.append(body)
            return io.BytesIO(json.dumps(variant_reply(body)).encode())
        calls.append(body)
        text = body["messages"][1]["content"]
        node_ids = re.findall(r"^\[([^\]]+)\]", text, flags=re.M)
        assert len(node_ids) >= 3
        scenes = [] if empty else [
            {"name": title, "story": title + " with AEB braking.", "actors": ["ego", actor],
             "anchor_node_id": node_ids[index], "member_node_ids": [node_ids[index]],
             "shared_container_node_ids": [node_ids[0]], "confidence": .92,
             "structure": {"tested_function": "AEB", "road_class": "直道", "ego_actions": ["制动"]}}
            for index, title, actor in [(1, "Stationary target", "target_vehicle"), (2, "Pedestrian crossing", "vru")]]
        if hallucination:
            scenes[0]["member_node_ids"].append("invented-node")
        payload = {"scenes": scenes, "shared_config_node_ids": [node_ids[0]]}
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": json.dumps(payload)}}],
                                     "usage": {"total_tokens": 250}}).encode())
    client = ModelClient(ModelConfig(api_key="authored-test"), opener=opener)
    client.structure_calls = structure_calls
    client.variant_calls = variant_calls
    return client, calls


def test_v2_classification_evidence_cache_and_immutable_library(tmp_path):
    client, calls = fake_client(hallucination=True)
    assets = AssetStore(tmp_path)
    store = PdfStore(assets)
    project = ProjectStore(assets).create("Authored")
    data = authored_pdf()
    record = store.import_pdf(project.project_id, "authored.pdf", data, client=client)
    assert record.scene_count == 2
    assert record.extraction_engine.startswith("openx-v2")
    assert calls[0]["messages"][1]["content"].endswith(build_language_note(["English text"]))  # English names
    scene = store.scenes(project.project_id, record.document_id)[0]
    assert scene.package.classification["function"] == "AEB"
    assert scene.package.structure["tested_function"] == "AEB"
    assert scene.package.evidence[0].page_start == 2
    assert any(item.page_start == 1 for item in scene.package.evidence)
    assert "invented-node" not in scene.package.extraction["node_ids"]
    assert any(issue["code"] == "hallucinated_node_id" for issue in scene.package.extraction["validation"]["issues"])
    # Structure: each scene read three times; a fact kept only with a quote from its own scene's text.
    assert len(client.structure_calls) == 6
    car = scene.package.structure["participants"][0]
    assert car["bearing"] == "正前方" and car["evidence"]["bearing"]["quote"] == "a stationary target car ahead"
    pedestrian = store.scenes(project.project_id, record.document_id)[1].package.structure["participants"][0]
    assert pedestrian["bearing"] == "未知方位" and "找不到" in pedestrian["evidence"]["bearing"]["review"]
    assert pedestrian["facing"] == "横向"
    assert [call["sample"] for call in store.extraction_audit(record)["run"]["structure_calls"]] == [0, 1, 2, 0, 1, 2]
    assert store.import_pdf(project.project_id, "authored.pdf", data, client=client) == record
    assert len(calls) == 1
    # Same bytes in another project reuse the content-addressed model response.
    other = ProjectStore(assets).create("Second project")
    store.import_pdf(other.project_id, "renamed.pdf", data, client=client)
    assert len(calls) == 1 and len(client.structure_calls) == 6
    published = store.publish_scene(scene)
    revised = store.revise_scene(project.project_id, record.document_id, scene.scene_id, {"title": "Reviewed target"})
    assert published["package"]["title"] != revised.package.title
    assert store.library()[0]["revision"] == 1
    assert revised.package.evidence == scene.package.evidence
    store.publish_scene(revised)
    assert store.library()[0]["revision"] == 2
    assert list((tmp_path / "requirements").glob("*/0001.json"))
    assert store.extraction_audit(record)["run"]["model"] == client.config.model


def test_scene_names_follow_the_document_language():
    english = ["2.1 Stationary car braking", "The ego vehicle approaches a stationary target car ahead at 50 km/h."]
    chinese = ["5.1 静止目标车辆", "主车以 50 km/h 接近前方静止目标车辆，TTC 为 4 s 时 AEB 应介入（参照 ISO 22839）。"]
    assert "name 和 story 用英文写" in build_language_note(english)
    # A Chinese standard quoting units and abbreviations, and an empty one, keep the frozen request.
    assert build_language_note(chinese) == build_language_note(english + chinese) == build_language_note([]) == ""


def test_a_model_that_reads_images_gets_each_scene_figure(tmp_path):
    from dataclasses import replace

    from openx_workbench.api_common import _scene_json
    client, _ = fake_client()
    client.config = replace(client.config, image_input=True)
    assets = AssetStore(tmp_path)
    store = PdfStore(assets)
    project = ProjectStore(assets).create("Figures")
    data = authored_pdf(figure=True)
    record = store.import_pdf(project.project_id, "figure.pdf", data, client=client)
    with_images = [body for body in client.structure_calls if isinstance(body["messages"][1]["content"], list)]
    assert len(with_images) == 3  # the pedestrian scene's three readings; the car's section has no figure
    assert with_images[0]["messages"][1]["content"][-1]["image_url"]["url"].startswith("data:image/png;base64,")
    car, pedestrian = store.scenes(project.project_id, record.document_id)
    person = pedestrian.package.structure["participants"][0]
    assert person["bearing"] == "右前方" and person["evidence"]["bearing"]["source"] == "图"
    assert [figure["label"] for figure in pedestrian.package.extraction["figures"]] == ["图1"]
    assert car.package.extraction["figures"] == []
    shown = _scene_json(pedestrian)["figures"][0]
    assert shown["page"] == 3 and len(shown["clip"]) == 4
    assert store.extraction_audit(record)["figures"]["status"] == "rendered"
    # Read without images, the same PDF is another document.
    plain, _ = fake_client()
    assert store.import_pdf(project.project_id, "figure.pdf", data, client=plain).document_id != record.document_id


def test_confirmed_empty_pdf_is_persisted_without_repeat_call(tmp_path):
    client, calls = fake_client(empty=True)
    assets = AssetStore(tmp_path)
    project = ProjectStore(assets).create("Empty result")
    store = PdfStore(assets)
    data = authored_pdf()
    record = store.import_pdf(project.project_id, "rules.pdf", data, client=client)
    assert record.scene_count == 0
    assert store.import_pdf(project.project_id, "rules.pdf", data, client=client) == record
    assert len(calls) == 1


def test_service_error_envelope_does_not_retry_or_save_a_successful_document(tmp_path):
    from openx_workbench.pdf_extraction import ExtractionError

    calls = []

    def opener(request, timeout):
        calls.append(request)
        return io.BytesIO(b'{"error":{"message":"private-provider-detail"}}')

    client = ModelClient(ModelConfig(api_key="authored-test"), opener=opener)
    assets = AssetStore(tmp_path)
    project = ProjectStore(assets).create("Service failure")
    store = PdfStore(assets)
    with pytest.raises(ExtractionError, match="transport_failed") as error:
        store.import_pdf(project.project_id, "authored.pdf", authored_pdf(), client=client)
    assert len(calls) == 1
    assert store.documents(project.project_id) == []
    assert error.value.audit["run"]["retry_attempted"] is False
    assert "private-provider-detail" not in str(error.value)


def test_mixed_pdf_ocr_evidence_reaches_revision_and_library(tmp_path, monkeypatch):
    from openx_workbench.pdf_ocr import parse_ocr_pages

    with pymupdf.open(stream=authored_pdf(), filetype="pdf") as original, pymupdf.open() as pdf:
        pdf.insert_pdf(original, from_page=0, to_page=0)
        source = original[1]
        page = pdf.new_page(width=source.rect.width, height=source.rect.height)
        page.insert_image(page.rect, stream=source.get_pixmap().tobytes("png"))
        pdf.insert_pdf(original, from_page=2, to_page=2)
        data = pdf.tobytes()
    def recognize(path, pages, **kwargs):
        assert pages == [2]
        raw = {"pages": [{"number": 2, "width": 595, "height": 842, "image_width": 595, "image_height": 842,
                           "blocks": [
                               {"block_label": "paragraph_title", "block_content": "2.1 Stationary car braking", "block_bbox": [60, 45, 500, 65]},
                               {"block_label": "text", "block_content": "A target car is ahead.", "block_bbox": [60, 80, 500, 100]},
                               {"block_label": "table", "block_content": "<table><tr><td>Ego speed</td><td>50 km/h</td></tr></table>", "block_bbox": [60, 110, 500, 160]},
                           ]}]}
        return parse_ocr_pages(raw, pages), {"cached": False, "engine": "authored"}
    monkeypatch.setattr("openx_workbench.pdf_ocr.recognize_pdf_pages", recognize)
    client, calls = fake_client()
    assets = AssetStore(tmp_path)
    store = PdfStore(assets)
    project = ProjectStore(assets).create("Mixed evidence")
    record = store.import_pdf(project.project_id, "mixed.pdf", data, client=client)
    scene = store.scenes(project.project_id, record.document_id)[0]
    assert scene.package.evidence[0].page_start == 2
    assert "<td>50 km/h</td>" in scene.package.evidence[0].source_text
    assert any(b["source"] == "ocr" for b in scene.package.extraction["source_blocks"])
    published = store.publish_scene(scene)
    assert published["package"]["extraction"]["source_blocks"] == scene.package.extraction["source_blocks"]
    assert store.import_pdf(project.project_id, "mixed.pdf", data, client=client) == record
    assert len(calls) == 1


def test_scan_and_truncated_response_never_publish_empty_success(tmp_path):
    client, calls = fake_client()
    with pymupdf.open() as document:
        document.new_page()
        with pytest.raises(ValueError, match="OCR"):
            extract_pdf(document.tobytes(), "scan.pdf", client=client, root=tmp_path)
    assert calls == []
    client.opener = lambda request, timeout: io.BytesIO(json.dumps({"choices": [{"finish_reason": "length", "message": {"content": '{"scenes":[]}'}}]}).encode())
    with pytest.raises(ValueError, match="truncated"):
        extract_pdf(authored_pdf(), "rules.pdf", client=client, root=tmp_path)
    assert not list((tmp_path / "model_cache").glob("*.json"))


def test_prompts_are_frozen_and_chain_parser_is_selected():
    from openx_workbench.pdf_extraction import PROMPT_VERSION
    from openx_workbench.pdf_v2.scene_proposer import resolve_scene_prompt
    from openx_workbench.pdf_v2.parser import _resolve_heading_decoder
    assert "tested_function" in resolve_scene_prompt("scene-first-prompt-v6")
    assert "\"speed_kph\"" not in resolve_scene_prompt("scene-first-prompt-v6")
    assert '"speed_kph": null' in resolve_scene_prompt("scene-first-prompt-v7")
    assert "alternative_group" not in resolve_scene_prompt("scene-first-prompt-v7")
    v8 = resolve_scene_prompt("scene-first-prompt-v8")
    assert all(field in v8 for field in ('"alternative_group": null', '"ego_turn"', '"traffic_controls"',
                                         '"speed_limits_kph"'))
    # v9 finds the scenes with the unchanged v1 text and reads their structure in a second step.
    from openx_workbench.pdf_v2.scene_proposer import STRUCTURE_PROMPTS
    v9 = resolve_scene_prompt("scene-structure-prompt-v9")
    assert all(field in v9 for field in ('"alternative_group": null', '"ego_turn"', '"ego_lane"',
                                         '"evidence"', '"speed_limits_kph"', "参数表每行"))
    # The bearing keeps only definitions that map from the wording itself.
    assert "试验开始时" in v8 and "试验开始时" not in v9 and "对向车道驶来的车" in v9
    # v10 reads the scene's figures too, and a crossing target's bearing from where it starts.
    v10 = resolve_scene_prompt("scene-structure-prompt-v10")
    assert '"图"' in v10 and "读示意图" in v10 and "出发的一侧" in v10
    assert "也填未知" in v9 and "也填未知" not in v10
    # v11 adds the lane departure behavior, nothing else.
    assert PROMPT_VERSION == "scene-first-prompt-v11"
    assert resolve_scene_prompt(PROMPT_VERSION) == resolve_scene_prompt("scene-first-prompt-v1")
    structure = resolve_scene_prompt(STRUCTURE_PROMPTS[PROMPT_VERSION])
    assert "偏离车道" in structure and "偏离车道" not in v10
    assert _resolve_heading_decoder(None) == "chain"


def test_wrong_schema_is_not_saved_as_confirmed_empty(tmp_path):
    calls = []
    def opener(request, timeout):
        calls.append(request)
        return io.BytesIO(json.dumps({"choices": [{"finish_reason": "stop", "message": {"content": '{"unrelated":true}'}}]}).encode())
    client = ModelClient(ModelConfig(api_key="authored-test"), opener=opener)
    assets = AssetStore(tmp_path)
    project = ProjectStore(assets).create("Failure")
    store = PdfStore(assets)
    with pytest.raises(ValueError, match="schema_failed"):
        store.import_pdf(project.project_id, "bad.pdf", authored_pdf(), client=client)
    assert len(calls) == 2
    assert store.documents(project.project_id) == []
    assert len(list((tmp_path / "extraction_failures").glob("*.json"))) == 1


def test_evidence_keeps_each_clause_heading_and_older_scenes_get_it_back(tmp_path):
    client, _ = fake_client()
    assets = AssetStore(tmp_path)
    store = PdfStore(assets)
    project = ProjectStore(assets).create("Authored")
    record = store.import_pdf(project.project_id, "authored.pdf", authored_pdf(), client=client)
    scene = store.scenes(project.project_id, record.document_id)[0]
    titles = {node["node_id"]: node["title"] for node in store.extraction_audit(record)["nodes"]}
    heading = titles[scene.package.extraction["anchor_node_id"]]
    assert scene.package.evidence[0].source_text.startswith(heading + "\n")
    # Saved before evidence kept the heading line: a one-sentence clause had no text at all.
    path = (ProjectStore(assets).data(project.project_id) / "documents" / record.document_id / "scenes"
            / scene.scene_id / "0001.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    for item in payload["evidence"]:
        item["source_text"] = ""
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    older = store.scenes(project.project_id, record.document_id)[0]
    assert older.package.evidence[0].source_text == heading
    assert all(item.source_text for item in older.package.evidence)


def test_each_scene_test_conditions_are_read_and_kept_beside_its_facts(tmp_path):
    client, _ = fake_client()
    assets = AssetStore(tmp_path)
    store = PdfStore(assets)
    project = ProjectStore(assets).create("Conditions")
    record = store.import_pdf(project.project_id, "authored.pdf", authored_pdf(), client=client)
    assert len(client.variant_calls) == 6  # each scene read three times
    read = store.variants(project.project_id, record.document_id)
    assert read["scene-0001"] == {"dimensions": [], "variants": [], "review_flags": []}  # one run
    assert [item["label"] for item in read["scene-0002"]["variants"]] == ["日间", "夜间"]
    assert read["scene-0002"]["dimensions"][0]["review"] is None  # its quote is in the scene's text
    assert store.variants_unread(project.project_id) == []
    # Kept beside the scenes, not in them: a scene's facts (and so its confirmed assets) stay as they were.
    assert "夜间" not in json.dumps([asdict(scene.package) for scene in store.scenes(project.project_id, record.document_id)],
                                  ensure_ascii=False)


def _finish(started):
    import time
    until = time.monotonic() + 10
    while any(job.snapshot()["status"] == "running" for job in started) and time.monotonic() < until:
        time.sleep(.02)
    return [job.snapshot() for job in started]


def test_documents_extracted_before_get_their_conditions_read_without_extracting_again(tmp_path):
    from openx_workbench.api_jobs import read_unread_variants
    client, calls = fake_client()
    assets = AssetStore(tmp_path)
    store = PdfStore(assets)
    project = ProjectStore(assets).create("Older")
    record = store.import_pdf(project.project_id, "authored.pdf", authored_pdf(), client=client)
    scenes = store.scenes(project.project_id, record.document_id)
    kept = ProjectStore(assets).data(project.project_id) / "documents" / record.document_id / "variants.json"
    expected = store.variants(project.project_id, record.document_id)
    kept.unlink()
    for cached in (tmp_path / "model_cache").glob("*.json"):
        cached.unlink()
    assert store.variants_unread(project.project_id) == [record]
    # Without a model key nothing starts.
    assert read_unread_variants(store, ModelClient(ModelConfig(api_key=""))) == []
    [job] = _finish(read_unread_variants(store, client))
    assert job["status"] == "completed" and job["result"]["document_ids"] == [record.document_id]
    assert len(client.variant_calls) == 12 and len(calls) == 1 and len(client.structure_calls) == 6
    assert store.variants(project.project_id, record.document_id) == expected
    assert store.scenes(project.project_id, record.document_id) == scenes
    assert read_unread_variants(store, client) == []
    # A scene no reading came back for is tried again at the next start; readings kept cost nothing.
    payload = json.loads(kept.read_text(encoding="utf-8"))
    payload["scenes"]["scene-0002"] = None
    kept.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    assert store.variants_unread(project.project_id) == [record]
    [job] = _finish(read_unread_variants(store, client))
    assert job["status"] == "completed" and len(client.variant_calls) == 12
    assert store.variants(project.project_id, record.document_id) == expected
