import copy
import json
from pathlib import Path

import pymupdf
import pytest

from openx_workbench.native_layout import overlay_native_headings, parse_layout_pages, rescue_native_structure
from openx_workbench.pdf_extraction import ExtractionError, extract_pdf
from openx_workbench.pdf_v2.models import ParsedBlock, ParsedDocument
from openx_workbench.pdf_v2.parser import parse_pdf_structure
from test_pdf_v2_migration import authored_pdf, fake_client


def native_document():
    return ParsedDocument(source_pdf="authored.pdf", parser="pymupdf", document_type="born_digital", page_count=1,
        preprocessing={"existing": "retained"}, blocks=(
            ParsedBlock(block_id="title", page_number=1, bbox=(60, 60, 300, 80), text="1 Test conditions"),
            ParsedBlock(block_id="body", page_number=1, bbox=(60, 100, 400, 140), text="Use a dry road in daylight.")))


def prediction(block, **overrides):
    return {"page_number": block.page_number, "bbox": block.bbox, "label": "paragraph_title", "score": .95, **overrides}


def test_overlay_preserves_all_original_evidence_and_marks_review():
    doc = native_document()
    result = overlay_native_headings(doc, [prediction(doc.blocks[0])])
    assert result.blocks[0].heading_level == 1
    for old, new in zip(doc.blocks, result.blocks):
        assert (old.block_id, old.text, old.bbox, old.source, old.page_number) == (new.block_id, new.text, new.bbox, new.source, new.page_number)
    assert result.preprocessing["existing"] == "retained"
    assert result.preprocessing["native_layout"]["promoted_block_ids"] == ["title"]
    assert result.structure_flags[0].kind == "layout_heading_promoted"
    assert doc.blocks[0].block_type == "paragraph"


@pytest.mark.parametrize("case", ["merged", "duplicate", "caption", "low_confidence", "table", "toc_line", "unnumbered", "ocr"])
def test_overlay_refuses_ambiguous_or_nonchapter_evidence(case):
    doc = native_document()
    regions = [prediction(doc.blocks[0])]
    if case == "merged":
        fragment = ParsedBlock(block_id="fragment", page_number=1, bbox=(290, 60, 310, 80), text="body fragment")
        doc = doc.model_copy(update={"blocks": (*doc.blocks, fragment)})
    elif case == "duplicate":
        regions *= 2
    elif case in {"caption", "low_confidence"}:
        regions[0].update({"label": "figure_title"} if case == "caption" else {"score": .49})
    else:
        update = {"table": {"block_type": "table"}, "toc_line": {"text": "1 Test conditions .... 3"},
                  "unnumbered": {"text": "Test conditions"}, "ocr": {"source": "ocr"}}[case]
        doc = doc.model_copy(update={"blocks": (doc.blocks[0].model_copy(update=update), doc.blocks[1])})
    result = overlay_native_headings(doc, regions)
    assert all(b.block_type != "heading" for b in result.blocks)
    assert result.preprocessing["native_layout"]["promoted_block_ids"] == []


def test_overlay_reuses_toc_and_numbering_gates():
    doc = native_document()
    blocks = tuple(ParsedBlock(block_id=f"toc-{i}", page_number=1, bbox=(60, 30*i, 300, 30*i+20),
                              text=f"{i} Chapter title {i+1}") for i in range(1, 5))
    doc = doc.model_copy(update={"page_count": 5, "blocks": blocks})
    result = overlay_native_headings(doc, [prediction(b) for b in blocks])
    assert all(b.block_type == "paragraph" for b in result.blocks)
    assert {f.kind for f in result.structure_flags} == {"toc_page_heading_rejected"}
    doc = native_document()
    second = doc.blocks[1].model_copy(update={"text": "9 Spurious item"})
    doc = doc.model_copy(update={"blocks": (doc.blocks[0], second)})
    result = overlay_native_headings(doc, [prediction(b) for b in doc.blocks])
    assert result.blocks[0].block_type == "heading"
    assert any(f.kind == "numbering_discontinuity" for f in result.structure_flags)


def layout_payload():
    return {"runtime": {"paddlex": "authored"}, "provenance": {"model": "PP-DocLayoutV2", "model_sha256": "authored"},
        "pages": [{"number": 1, "width": 595, "height": 842, "image_width": 1190, "image_height": 1684,
                   "regions": [{"label": "paragraph_title", "score": .9, "bbox": [120, 120, 600, 160]}]}]}


@pytest.mark.parametrize("bad", ["missing", "duplicate", "invalid_entry", "invalid_payload", "dimensions", "box", "outside", "confidence"])
def test_invalid_layout_cannot_become_source_evidence(bad):
    payload = copy.deepcopy(layout_payload())
    if bad == "missing":
        payload["pages"] = []
    elif bad == "duplicate":
        payload["pages"] *= 2
    elif bad == "invalid_entry":
        payload["pages"].append(None)
    elif bad == "invalid_payload":
        payload = []
    elif bad == "dimensions":
        payload["pages"][0]["width"] = True
    elif bad in {"box", "outside"}:
        payload["pages"][0]["regions"][0]["bbox"][0] = float("nan") if bad == "box" else -1
    else:
        payload["pages"][0]["regions"][0]["score"] = 1.1
    with pytest.raises(ValueError):
        parse_layout_pages(payload, [1])


def flat_pdf():
    with pymupdf.open() as pdf:
        for heading, body in [("1 Test conditions", "Use a dry road in daylight."),
                              ("2 Stationary target", "Test AEB braking at 50 km/h."),
                              ("3 Pedestrian crossing", "Test AEB braking at 30 km/h.")]:
            page = pdf.new_page()
            page.insert_text((60, 60), heading, fontsize=11)
            page.insert_text((60, 100), body, fontsize=11)
        return pdf.tobytes()


def test_healthy_native_pdf_never_starts_layout_worker(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail("Healthy chapters must not initialize Paddle")
    monkeypatch.setattr("openx_workbench.native_layout.rescue_native_structure", forbidden)
    client, calls = fake_client()
    assert len(extract_pdf(authored_pdf(), "normal.pdf", client=client, root=tmp_path).packages) == 2
    assert len(calls) == 1


@pytest.mark.parametrize("failure", ["unavailable", "no_headings"])
def test_failed_rescue_stays_failed_without_model_request(tmp_path, monkeypatch, failure):
    def rescue(path, doc, **kwargs):
        assert Path(path).is_file()
        if failure == "unavailable":
            raise ValueError("Local layout unavailable")
        return overlay_native_headings(doc, [])
    monkeypatch.setattr("openx_workbench.native_layout.rescue_native_structure", rescue)
    client, calls = fake_client()
    with pytest.raises(ExtractionError, match="Unreliable PDF structure") as caught:
        extract_pdf(flat_pdf(), "flat.pdf", client=client, root=tmp_path)
    assert calls == []
    assert caught.value.audit["preprocessing"]["native_layout"]["status"] == ("failed" if failure == "unavailable" else "completed")


def test_rescued_chapters_reach_shared_scene_first_with_native_anchors(tmp_path, monkeypatch):
    def rescue(path, doc, **kwargs):
        assert Path(path).is_file()
        assert not any(b.block_type == "heading" for b in doc.blocks)
        return overlay_native_headings(doc, [prediction(b) for b in doc.blocks if b.text[0].isdigit()])
    monkeypatch.setattr("openx_workbench.native_layout.rescue_native_structure", rescue)
    client, calls = fake_client()
    result = extract_pdf(flat_pdf(), "flat.pdf", client=client, root=tmp_path)
    assert len(result.packages) == 2 and len(calls) == 1
    assert result.audit["structure_quality"]["block_coverage_rate"] == 1
    assert len(result.audit["preprocessing"]["native_layout"]["promoted_block_ids"]) == 3
    assert all(b["source"] == "native_text" for p in result.packages for b in p.extraction["source_blocks"])
    assert any(f["kind"] == "layout_heading_promoted" for p in result.packages for f in p.extraction["structure_flags"])


def test_ocr_only_failure_does_not_run_native_rescue(tmp_path, monkeypatch):
    doc = native_document().model_copy(update={"document_type": "scanned",
        "blocks": tuple(b.model_copy(update={"source": "ocr"}) for b in native_document().blocks)})
    monkeypatch.setattr("openx_workbench.pdf_extraction.parse_pdf_structure", lambda *args, **kwargs: (doc, ()))
    def forbidden(*args, **kwargs):
        pytest.fail("OCR evidence must not be retried as native text")
    monkeypatch.setattr("openx_workbench.native_layout.rescue_native_structure", forbidden)
    client, calls = fake_client()
    with pytest.raises(ExtractionError):
        extract_pdf(flat_pdf(), "scan.pdf", client=client, root=tmp_path)
    assert calls == []


def test_low_coverage_after_rescue_stops_before_model(tmp_path, monkeypatch):
    def rescue(path, doc, **kwargs):
        return overlay_native_headings(doc, [prediction(b) for b in doc.blocks if b.text.startswith("3 ")])
    monkeypatch.setattr("openx_workbench.native_layout.rescue_native_structure", rescue)
    client, calls = fake_client()
    with pytest.raises(ExtractionError, match="low_block_coverage") as caught:
        extract_pdf(flat_pdf(), "partial.pdf", client=client, root=tmp_path)
    assert calls == []
    assert caught.value.audit["structure_quality"]["block_coverage_rate"] < .8


def test_layout_review_and_heading_evidence_survive_publication(tmp_path, monkeypatch):
    from openx_workbench.asset_store import AssetStore
    from openx_workbench.pdf_store import PdfStore
    from openx_workbench.project_store import ProjectStore
    def rescue(path, doc, **kwargs):
        return overlay_native_headings(doc, [prediction(b) for b in doc.blocks if b.text[0].isdigit()])
    monkeypatch.setattr("openx_workbench.native_layout.rescue_native_structure", rescue)
    assets = AssetStore(tmp_path)
    project = ProjectStore(assets).create("Authored layout regression")
    store = PdfStore(assets)
    client, _ = fake_client()
    record = store.import_pdf(project.project_id, "flat.pdf", flat_pdf(), client=client)
    scene = store.scenes(project.project_id, record.document_id)[0]
    published = store.publish_scene(scene)
    revised = store.revise_scene(project.project_id, record.document_id, scene.scene_id, {"title": "Reviewed"})
    assert published["package"]["extraction"]["source_blocks"] == revised.package.extraction["source_blocks"]
    assert published["package"]["extraction"]["structure_flags"] == revised.package.extraction["structure_flags"]
    assert published["package"]["extraction"]["review_status"] == "confirmed"
    assert revised.package.extraction["review_status"] == "pending"
    flags = published["package"]["extraction"]["structure_flags"]
    evidence = published["package"]["extraction"]["source_blocks"]
    assert any(f["kind"] == "layout_heading_promoted" and any(b["block_id"] == f["block_id"] for b in evidence) for f in flags)
    assert store.extraction_audit(record)["preprocessing"]["native_layout"]["status"] == "completed"


def test_layout_cache_is_validated_and_preserves_model_provenance(tmp_path, monkeypatch):
    path = tmp_path / "flat.pdf"
    path.write_bytes(flat_pdf())
    doc, _ = parse_pdf_structure(path)
    calls = []
    def worker(command, log, timeout):
        pages = json.loads(Path(command[2]).read_text(encoding="utf-8"))
        payload = layout_payload()
        payload["pages"] = [{**page, "regions": []} for page in pages]
        Path(command[3]).write_text(json.dumps(payload), encoding="utf-8")
        calls.append(command)
        return 0
    monkeypatch.setattr("openx_workbench.pdf_ocr._run_worker", worker)
    first = rescue_native_structure(path, doc, root=tmp_path)
    second = rescue_native_structure(path, doc, root=tmp_path)
    assert len(calls) == 1
    assert not first.preprocessing["native_layout"]["cached"]
    assert second.preprocessing["native_layout"]["cached"]
    assert second.preprocessing["native_layout"]["model_sha256"] == "authored"
    cache = next((tmp_path / "layout_cache").glob("*.json"))
    payload = json.loads(cache.read_text(encoding="utf-8"))
    payload["pages"] = []
    cache.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="coverage"):
        rescue_native_structure(path, doc, root=tmp_path)
    assert len(calls) == 1
