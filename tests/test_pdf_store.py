import pymupdf
import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.pdf_store import PdfStore
from openx_workbench.project_store import ProjectStore


def _pdf(title: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), f"7.4.1 {title} scenario\nTarget vehicle cuts in on a straight road. TTC = 3.0 s.")
    data = document.tobytes()
    document.close()
    return data


def test_multiple_pdfs_persist_per_project_and_evidence_survives_revision(tmp_path):
    assets = AssetStore(tmp_path)
    projects = ProjectStore(assets)
    project = projects.create("ADAS")
    other = projects.create("Other")
    store = PdfStore(assets)
    first_bytes = _pdf("Cut-in")
    first = store.import_pdf(project.project_id, "one.pdf", first_bytes, "Test", engine="legacy")
    second = store.import_pdf(project.project_id, "two.pdf", _pdf("Braking"), "Test", engine="legacy")
    assert store.import_pdf(project.project_id, "one.pdf", first_bytes, "Test", engine="legacy") == first
    assert len(store.documents(project.project_id)) == 2
    assert store.documents(other.project_id) == []
    assert len(store.all_scenes(project.project_id)) == 2
    scene = store.scenes(project.project_id, first.document_id)[0]
    source = scene.package.evidence[0]
    revised = store.revise_scene(project.project_id, first.document_id, scene.scene_id,
                                 {"title": "Reviewed cut-in", "parameters": {"ttc_s": 2.5}})
    assert revised.revision == 2
    assert revised.package.title == "Reviewed cut-in"
    assert revised.package.parameters["ttc_s"] == 2.5
    reopened = PdfStore(assets).scenes(project.project_id, first.document_id)[0]
    assert reopened.package.evidence[0] == source
    assert [item.revision for item in store.revisions(project.project_id, first.document_id,
                                                       scene.scene_id)] == [1, 2]
    assert PdfStore(assets).pdf_bytes(second).startswith(b"%PDF")
    with pytest.raises(ValueError, match="Only extracted facts"):
        store.revise_scene(project.project_id, first.document_id, scene.scene_id,
                           {"evidence": []})


def test_same_filename_with_changed_pdf_creates_new_document(tmp_path):
    assets = AssetStore(tmp_path)
    project = ProjectStore(assets).create("Review")
    store = PdfStore(assets)
    first = store.import_pdf(project.project_id, "rules.pdf", _pdf("Cut-in"), engine="legacy")
    second = store.import_pdf(project.project_id, "rules.pdf", _pdf("Crossing"), engine="legacy")
    assert first.document_id != second.document_id
    assert first.sha256 != second.sha256
