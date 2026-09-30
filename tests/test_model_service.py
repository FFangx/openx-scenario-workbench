import io
import json
from urllib.error import HTTPError

import pytest

from openx_workbench.llm_service import ModelClient, ModelConfig, ModelError, base_url, load_config, save_config


def test_config_roundtrip_without_plaintext_key(tmp_path):
    import os
    config = ModelConfig("https://example.org/v1/chat/completions", "chosen-model", "secret-test-key")
    save_config(config, tmp_path)
    loaded = load_config(tmp_path)
    assert loaded.base_url == "https://example.org/v1"
    assert loaded.api_key == config.api_key
    assert loaded.model == config.model
    assert config.api_key not in repr(loaded)
    assert config.api_key not in (tmp_path / "model_settings.json").read_text()
    save_config(ModelConfig(api_key=""), tmp_path)
    assert load_config(tmp_path).api_key == ""


def test_models_and_probe_use_same_endpoint_and_selected_model():
    calls = []
    def opener(request, timeout):
        calls.append(request)
        response = {"data": [{"id": "b"}, {"id": "a"}, {"id": "b"}]} if request.method == "GET" else {
            "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]}
        return io.BytesIO(json.dumps(response).encode())
    client = ModelClient(ModelConfig("https://example.org/v1", "a", "secret"), opener=opener)
    assert client.models() == ["a", "b"]
    assert client.probe() == "a"
    assert calls[0].full_url == "https://example.org/v1/models"
    assert calls[1].full_url == "https://example.org/v1/chat/completions"
    assert json.loads(calls[1].data)["model"] == "a"
    assert "thinking" not in json.loads(calls[1].data)


def test_service_errors_do_not_echo_secret_or_remote_body():
    def fail(request, timeout):
        raise HTTPError(request.full_url, 401, "secret-key", {}, io.BytesIO(b"secret-key"))
    with pytest.raises(ModelError, match="401") as error:
        ModelClient(ModelConfig(api_key="secret-key"), opener=fail).models()
    assert "secret-key" not in str(error.value)
    with pytest.raises(ModelError):
        base_url("http://remote.example/v1")
    assert base_url("http://localhost:9999/v1/") == "http://localhost:9999/v1"


def test_http_redirect_cannot_forward_credentials():
    from openx_workbench.llm_service import NoRedirect
    assert NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.example") is None
