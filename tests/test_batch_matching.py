from dataclasses import replace
import json
from pathlib import Path

import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.batch_matching import batch_signature, match_document
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
    batch = match_document(doc, scenes, index, {})
    assert len(encoder.calls) == 1 and len(encoder.calls[0]) == 4
    assert batch["counts"] == {"standards": 1, "partial": 1}
    for scene, entry in zip(scenes, batch["entries"]):
        single = index.search("", query=scene_package_to_query(scene.package))[0]
        assert entry["assessment"]["level"] == single.confirmation_level
        assert entry["candidates"][0]["scores"]["combined"] == single.score
        assert entry["source"]["revision"] == scene.revision
    html = render_report(batch)
    assert "authored &lt;PDF&gt;.pdf" in html and "Review scope" in html
    assert "partial" in html and "pdf-hash" in html
    old = batch_signature(doc, scenes, index.fingerprint, {}, encoder.encoder_id)
    scenes[0] = replace(scenes[0], revision=2)
    assert old != batch_signature(doc, scenes, index.fingerprint, {}, encoder.encoder_id)


def test_no_candidates_and_empty_document_do_not_become_new_build():
    doc = document()
    index = OpenXIndex([], HashingEncoder(32))
    batch = match_document(doc, [StoredScene(doc, "one", 1, requirement())], index, {})
    assert batch["counts"] == {"no_candidates": 1}
    assert match_document(doc, [], index, {})["counts"] == {}
    with pytest.raises(ValueError, match="selected document"):
        match_document(doc, [StoredScene(replace(doc, document_id="other"), "one", 1, requirement())], index, {})


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
    batch = match_document(doc, [StoredScene(doc, "one", 1, requirement())], index,
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
