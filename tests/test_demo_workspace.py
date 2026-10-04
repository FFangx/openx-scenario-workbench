import json
from pathlib import Path

import pytest

from openx_workbench import demo_workspace

BENCHMARK = Path(__file__).resolve().parents[1] / "examples" / "reuse-benchmark" / "benchmark.json"


@pytest.fixture
def client_for(monkeypatch):
    pytest.importorskip("fastapi")
    from fastapi.testclient import TestClient

    from openx_workbench import api

    def make(target: Path, dataset: str):
        monkeypatch.setenv("OPENX_DATA_DIR", str(target))
        summary = demo_workspace.seed(target, dataset)
        api._cache.clear()
        return TestClient(api.app, base_url="http://127.0.0.1"), summary

    yield make
    api._cache.clear()


def test_benchmark_demo_reaches_the_labelled_decisions(tmp_path, client_for):
    client, summary = client_for(tmp_path / "demo", "benchmark")
    assert summary["assets"] == 25 and sum(item["scenes"] for item in summary["documents"]) == 35
    cases = {case["title"]: case for case in json.loads(BENCHMARK.read_text(encoding="utf-8"))["cases"]}
    project = summary["project_id"]
    seen = set()
    for document in summary["documents"]:
        scenes = client.get(f"/api/projects/{project}/documents/{document['document_id']}/scenes").json()
        for scene in scenes:
            case = cases[scene["title"]]
            result = client.post("/api/search", json={"project_id": project, "document_id": document["document_id"],
                                                      "scene_id": scene["scene_id"], "encoder": "hashing"}).json()
            top = result["results"][0]
            assert result["library_size"] == 25
            expected = set(case["relevant"].values()) or {case["best_level"]}
            assert top["structural_level"] in expected, case["id"]
            if case["relevant"]:
                assert top["xosc"].removesuffix(".xosc") in case["relevant"], case["id"]
            seen.add(case["id"])
    assert len(seen) == 35


def test_fixture_demo_keeps_the_ui_check_workspace(tmp_path, client_for):
    client, summary = client_for(tmp_path / "demo", "fixtures")
    assert summary["assets"] == 6 and [item["scenes"] for item in summary["documents"]] == [4, 4]
    assert (tmp_path / "demo" / demo_workspace.MARKER).is_file()


def test_seed_refuses_a_folder_in_use(tmp_path):
    (tmp_path / "something.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(SystemExit, match="non-empty"):
        demo_workspace.seed(tmp_path)


def test_openx_demo_seeds_once_and_cleans_up(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    import uvicorn

    from openx_workbench import api

    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html>", encoding="utf-8")
    monkeypatch.setattr(api, "WEB_DIST", dist)
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path / "unused"))
    served = []

    def fake_run(app, host, port, **_):
        from openx_workbench.preferences import read_preferences

        served.append((host, port, Path(demo_workspace.os.environ["OPENX_DATA_DIR"]), read_preferences()))

    monkeypatch.setattr(uvicorn, "run", fake_run)
    keep = tmp_path / "kept"
    assert demo_workspace.main(["--dataset", "fixtures", "--data-dir", str(keep), "--no-browser"]) == 0
    marker = (keep / demo_workspace.MARKER).read_bytes()
    assert demo_workspace.main(["--data-dir", str(keep), "--no-browser", "--port", "8899"]) == 0
    assert (keep / demo_workspace.MARKER).read_bytes() == marker  # reused, not reseeded
    assert served[0][:3] == ("127.0.0.1", 8770, keep) and served[0][3]["encoder"] == "hashing"
    assert served[1][1] == 8899

    assert demo_workspace.main(["--dataset", "fixtures", "--no-browser"]) == 0
    assert not served[2][2].exists()  # the temporary workspace is removed on exit


def test_openx_demo_needs_the_built_interface(tmp_path, monkeypatch):
    pytest.importorskip("fastapi")
    from openx_workbench import api

    monkeypatch.setattr(api, "WEB_DIST", tmp_path / "missing")
    with pytest.raises(SystemExit, match="npm run build"):
        demo_workspace.main(["--no-browser"])


def test_a_normal_install_finds_the_checkout_from_its_root(tmp_path, monkeypatch):
    from openx_workbench import checkout

    repo = Path(__file__).resolve().parents[1]
    installed = tmp_path / "site-packages" / "openx_workbench" / "checkout.py"
    monkeypatch.setattr(checkout, "__file__", str(installed))
    monkeypatch.chdir(repo)
    assert checkout.checkout_root() == repo
    monkeypatch.chdir(tmp_path)
    assert checkout.checkout_root() == installed.parents[2]
