from dataclasses import replace
import json
from pathlib import Path

import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.batch_matching import batch_signature, match_documents
from openx_workbench.catalog import AssetFile
from openx_workbench.pdf_store import PdfDocument, StoredScene
from openx_workbench.project_store import ProjectStore
from openx_workbench.report_html import render_report
from openx_workbench.retrieval import HashingEncoder, OpenXIndex
from openx_workbench.scene_package import scene_package_to_query
from test_structured_reuse import authored_asset, requirement


def document(project_id="project"):
    return PdfDocument("doc", project_id, "authored <PDF>.pdf", "REQ", "pdf-hash", "today", 2, 2)


def test_batch_uses_one_encoding_call_and_matches_single_verdicts():
    class CountingEncoder(HashingEncoder):
        def encode_many(self, texts):
            self.calls.append(list(texts))
            return super().encode_many(texts)

    encoder = CountingEncoder(32)
    encoder.calls = []
    index = OpenXIndex([authored_asset()], encoder)
    doc = document()
    scenes = [StoredScene(doc, "one", 1, requirement()),
              StoredScene(doc, "two", 2, requirement(lane_marking="实线"))]
    encoder.calls.clear()
    batch = match_documents([doc], scenes, index, {})
    assert len(encoder.calls) == 1 and len(encoder.calls[0]) == 2  # one query text per scene
    assert batch["counts"] == {"standards": 1, "partial": 1}
    for scene, entry in zip(scenes, batch["entries"]):
        single = index.search("", query=scene_package_to_query(scene.package))[0]
        assert entry["assessment"]["level"] == single.confirmation_level
        assert entry["candidates"][0]["scores"]["combined"] == single.score
        assert entry["source"]["revision"] == scene.revision
    html = render_report(batch)
    assert "authored &lt;PDF&gt;.pdf" in html and "Review scope" in html
    assert "partial" in html and "pdf-hash" in html
    old = batch_signature([doc], scenes, index.fingerprint, {}, encoder.encoder_id)
    scenes[0] = replace(scenes[0], revision=2)
    assert old != batch_signature([doc], scenes, index.fingerprint, {}, encoder.encoder_id)


def test_the_summary_lists_the_top_candidates_each_with_its_verdict():
    assets = [authored_asset(), replace(authored_asset(target_y=-3.5), asset_id="right")]
    doc = document()
    batch = match_documents([doc], [StoredScene(doc, "one", 1, requirement())], OpenXIndex(assets, HashingEncoder(32)), {})
    assert [item["reuse"]["structural_level"] for item in batch["entries"][0]["candidates"]] == ["direct", "new_build"]
    html = render_report(batch, language="zh")
    # The direct one's files are not checked against the standard yet.
    assert "1. opaque.xosc (文件标准待复核)<br>2. opaque.xosc (需要新建)" in html and "候选（前三）" in html


def test_a_group_of_pdfs_is_one_summary_that_names_each_row_s_pdf():
    index = OpenXIndex([authored_asset()], HashingEncoder(32))
    first = document()
    second = replace(first, document_id="doc2", filename="second.pdf", sha256="hash2")
    scenes = [StoredScene(first, "one", 1, requirement()), StoredScene(second, "one", 1, requirement())]
    batch = match_documents([first, second], scenes, index, {})
    assert [(item["source"]["document_id"], item["source"]["filename"]) for item in batch["entries"]] == [
        ("doc", "authored <PDF>.pdf"), ("doc2", "second.pdf")]
    assert batch["source"]["title"] == "authored <PDF>.pdf + second.pdf" and "document_id" not in batch["source"]
    assert [item["pdf_sha256"] for item in batch["source"]["documents"]] == ["pdf-hash", "hash2"]
    assert "<th>文档</th>" in render_report(batch, language="zh")
    single = match_documents([first], scenes[:1], index, {})
    assert single["source"]["document_id"] == "doc" and "<th>Document</th>" not in render_report(single)
    assert batch["signature"] != batch_signature([first], scenes, index.fingerprint, {}, index.encoder.encoder_id)


def test_no_candidates_and_empty_document_do_not_become_new_build():
    doc = document()
    index = OpenXIndex([], HashingEncoder(32))
    batch = match_documents([doc], [StoredScene(doc, "one", 1, requirement())], index, {})
    assert batch["counts"] == {"no_candidates": 1}
    assert match_documents([doc], [], index, {})["counts"] == {}
    with pytest.raises(ValueError, match="selected document"):
        match_documents([doc], [StoredScene(replace(doc, document_id="other"), "one", 1, requirement())], index, {})


def batch_with_version(tmp_path):
    assets = AssetStore(tmp_path)
    fixtures = Path(__file__).parent / "fixtures"
    version = assets.import_files([AssetFile(name, (fixtures / name).read_bytes())
                                  for name in ("minimal.xosc", "minimal.xodr")])[0]
    projects = ProjectStore(assets)
    project = projects.create("Batch review")
    doc = document(project.project_id)
    asset = assets.load_asset(version)
    index = OpenXIndex([asset], HashingEncoder(32))
    batch = match_documents([doc], [StoredScene(doc, "one", 1, requirement())], index,
                           {asset.asset_id: version})
    return assets, version, projects, project, batch


def test_saved_batch_pins_candidate_versions_and_is_immutable(tmp_path):
    assets, version, projects, project, batch = batch_with_version(tmp_path)
    path = projects.save_batch(project.project_id, batch)
    original = json.loads(path.read_text(encoding="utf-8"))
    batch["entries"][0]["source"]["title"] = "later edit"
    assert projects.reports(project.project_id)[0] == original
    with pytest.raises(ValueError, match="referenced"):
        assets.delete_version(version)


def test_failed_batch_write_releases_pins_and_invalid_version_is_rejected(tmp_path, monkeypatch):
    assets, version, projects, project, batch = batch_with_version(tmp_path)
    def fail(*args):
        raise OSError("write failed")
    monkeypatch.setattr(projects, "_write_json", fail)
    with pytest.raises(OSError, match="write failed"):
        projects.save_batch(project.project_id, batch)
    batch["entries"][0]["candidates"][0]["candidate"]["version_id"] = "missing"
    with pytest.raises(ValueError, match="unavailable"):
        projects.save_batch(project.project_id, batch)
    assets.delete_version(version)  # Neither failure leaves a reference.
