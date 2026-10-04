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


@pytest.fixture(autouse=True)
def api_contract(monkeypatch):
    """Every JSON response a test receives from the workbench API must match its documented model.

    The models in api_schemas only document the routes (they do not reshape responses), so this is
    what keeps them, and the web client's generated types, true to what the API returns.
    """
    try:
        from fastapi.routing import APIRoute
        from fastapi.testclient import TestClient
        from pydantic import TypeAdapter
        from openx_workbench import api
    except ImportError:
        yield
        return
    routes = [(route, TypeAdapter(route.responses[200]["model"])) for route in api.app.routes
              if isinstance(route, APIRoute) and 200 in route.responses]
    original = TestClient.request

    def request(self, method, url, *args, **kwargs):
        response = original(self, method, url, *args, **kwargs)
        if (self.app is api.app and response.status_code == 200
                and response.headers.get("content-type", "").startswith("application/json")):
            path = response.request.url.path
            for route, adapter in routes:
                if method.upper() in route.methods and route.path_regex.match(path):
                    adapter.validate_python(response.json())
                    break
        return response

    monkeypatch.setattr(TestClient, "request", request)
    yield
