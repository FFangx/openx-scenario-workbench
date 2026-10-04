"""Shared API fixture: a throwaway data folder with one asset, one project and one rule-extracted PDF."""
from pathlib import Path

import pymupdf
import pytest


def _pdf(title: str) -> bytes:
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text((72, 72), f"7.4.1 {title} scenario\nTarget vehicle cuts in on a straight road. TTC = 3.0 s.")
    data = document.tobytes()
    document.close()
    return data


@pytest.fixture
def workbench(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from openx_workbench import api
    from openx_workbench.asset_store import AssetStore
    from openx_workbench.catalog import AssetFile
    from openx_workbench.pdf_store import PdfStore
    from openx_workbench.project_store import ProjectStore

    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    api._cache.clear()
    assets = AssetStore()
    fixtures = Path(__file__).parent / "fixtures"
    version = assets.import_files([AssetFile(name, (fixtures / name).read_bytes())
                                   for name in ("minimal.xosc", "minimal.xodr")])[0]
    project = ProjectStore(assets).create("API")
    document = PdfStore(assets).import_pdf(project.project_id, "rules.pdf", _pdf("Cut-in"), "Test", engine="legacy")
    scene = PdfStore(assets).scenes(project.project_id, document.document_id)[0]
    base = {"project_id": project.project_id, "document_id": document.document_id,
            "scene_id": scene.scene_id, "encoder": "hashing"}
    yield TestClient(api.app, base_url="http://127.0.0.1"), base, version
    api._cache.clear()
