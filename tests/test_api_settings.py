import json

import pytest

pytest.importorskip("fastapi")
from fastapi.testclient import TestClient

from openx_workbench import api, api_settings
from openx_workbench.llm_service import ModelError, ModelInfo, load_config

SECRET = "authored-test-key"


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path))
    for name in ("OPENX_LLM_URL", "OPENX_LLM_MODEL", "OPENX_LLM_API_KEY", "DEEPSEEK_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    api._cache.clear()
    yield TestClient(api.app, base_url="http://127.0.0.1")
    api._cache.clear()


def model(**values):
    return {"base_url": "https://models.example/v1", "model": "authored-model", "thinking": False,
            "max_tokens": 4096, "timeout": 60, **values}


def test_settings_report_defaults_and_data_folder(client, tmp_path):
    settings = client.get("/api/settings").json()
    assert settings["data_dir"] == str(tmp_path)
    assert settings["model"]["has_key"] is False and settings["model"]["readable"] is True
    assert settings["preferences"] == {"language": "zh", "appearance": "system", "encoder": "bge"}


def test_saved_key_is_never_returned_and_only_follows_the_same_endpoint(client, tmp_path):
    saved = client.put("/api/settings/model", json=model(api_key=SECRET))
    assert saved.status_code == 200 and saved.json()["has_key"] is True
    assert SECRET not in saved.text and SECRET not in client.get("/api/settings").text
    assert SECRET not in (tmp_path / "model_settings.json").read_text(encoding="utf-8")

    client.put("/api/settings/model", json=model(model="renamed-model"))
    assert load_config(tmp_path).api_key == SECRET and load_config(tmp_path).model == "renamed-model"

    moved = client.put("/api/settings/model", json=model(base_url="https://elsewhere.example/v1"))
    assert moved.json()["has_key"] is False and load_config(tmp_path).api_key == ""

    client.put("/api/settings/model", json=model(api_key=SECRET))
    removed = client.delete("/api/settings/model/key")
    assert removed.json()["has_key"] is False and load_config(tmp_path).api_key == ""


def test_model_list_and_probe_use_the_draft_with_the_saved_key(client, monkeypatch):
    seen = []

    class Client:
        def __init__(self, config):
            seen.append(config)

        def catalog(self):
            return [ModelInfo("a", ("low", "high"), "high", 4096, True), ModelInfo("b")]

        def probe(self):
            if seen[-1].model == "broken":
                raise ModelError("模型未通过 JSON 响应测试 / Model failed the JSON response test.")
            return seen[-1].model

    monkeypatch.setattr(api_settings, "ModelClient", Client)
    client.put("/api/settings/model", json=model(api_key=SECRET))
    assert client.post("/api/settings/model/models", json=model()).json() == {
        "models": ["a", "b"],
        "details": [{"id": "a", "effort_levels": ["low", "high"], "default_effort": "high", "max_output_tokens": 4096,
                     "image_input": True},
                    {"id": "b", "effort_levels": [], "default_effort": "", "max_output_tokens": None, "image_input": False}]}
    assert seen[-1].api_key == SECRET
    assert client.post("/api/settings/model/test", json=model(model="draft-model")).json() == {"model": "draft-model"}
    failed = client.post("/api/settings/model/test", json=model(model="broken"))
    assert failed.status_code == 400 and "JSON" in failed.json()["detail"]
    assert client.post("/api/settings/model/test", json=model(model=" ")).status_code == 400
    assert client.put("/api/settings/model", json=model(base_url="http://remote.example/v1")).status_code == 400
    assert client.put("/api/settings/model", json=model(timeout=5)).status_code == 422


def test_preferences_keep_the_desktop_file_format(client, tmp_path):
    updated = client.put("/api/settings/preferences", json={"language": "en", "appearance": "dark", "encoder": "hashing"})
    assert updated.json() == {"language": "en", "appearance": "dark", "encoder": "hashing"}
    stored = json.loads((tmp_path / "preferences.json").read_text(encoding="utf-8"))
    assert stored == {"language": "English", "appearance": "dark", "encoder": "hashing"}
    assert client.put("/api/settings/preferences", json={"appearance": "sepia"}).status_code == 422
    assert client.put("/api/settings/preferences", json={"encoder": "unknown"}).status_code == 400


def _esmini(folder):
    (folder / "bin").mkdir(parents=True)
    (folder / "bin" / "esmini.exe").write_bytes(b"")
    (folder / "bin" / "esminiLib.dll").write_bytes(b"")
    return folder / "bin" / "esmini.exe"


def test_esmini_folder_is_validated_before_it_is_saved(client, tmp_path, monkeypatch):
    install = tmp_path / "authored-esmini"
    executable = _esmini(install)
    choices = iter([None, tmp_path, install])
    monkeypatch.setattr(api_settings, "choose_folder", lambda title, initial: next(choices))
    assert client.post("/api/settings/preview/browse").json()["cancelled"] is True
    assert client.post("/api/settings/preview/browse").status_code == 400
    chosen = client.post("/api/settings/preview/browse").json()
    assert chosen["executable"] == str(executable.resolve()) and chosen["configured"] == chosen["executable"]
    assert client.post("/api/settings/preview/detect").json()["configured"] == ""


def test_open_folder_accepts_only_known_targets(client, tmp_path, monkeypatch):
    opened = []
    monkeypatch.setattr(api_settings, "open_folder", opened.append)
    assert client.post("/api/settings/open-folder", json={"target": "data"}).json() == {"opened": str(tmp_path)}
    assert opened == [tmp_path]
    assert client.post("/api/settings/open-folder", json={"target": "C:/Windows"}).status_code == 422
    monkeypatch.setattr(api_settings, "find_esmini", lambda value: None)
    assert client.post("/api/settings/open-folder", json={"target": "esmini"}).status_code == 400


def test_projects_can_be_created(client):
    created = client.post("/api/projects", json={"name": "Authored project"}).json()
    listed = client.get("/api/projects").json()
    assert listed["last_project_id"] == created["project_id"]
    assert client.post("/api/projects", json={"name": ""}).status_code == 422


def test_other_sites_cannot_drive_the_api(client):
    assert client.put("/api/settings/preferences", json={"language": "en"},
                      headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.get("/api/settings", headers={"Host": "attacker.example"}).status_code == 403
    assert client.put("/api/settings/preferences", json={"language": "en"},
                      headers={"Origin": "http://localhost:5173"}).status_code == 200
