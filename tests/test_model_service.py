import io
import json
from dataclasses import replace
from http.client import IncompleteRead
from urllib.error import HTTPError

import pytest

from openx_workbench.llm_service import ModelClient, ModelConfig, ModelError, base_url, load_config, save_config


def test_config_roundtrip_without_plaintext_key(tmp_path):
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


def test_a_reply_cut_off_mid_body_is_a_connection_failure_worth_retrying():
    class CutOff(io.BytesIO):
        def read(self, *args):
            raise IncompleteRead(b"{")
    with pytest.raises(ModelError, match="connection") as error:
        ModelClient(ModelConfig(api_key="secret-key"), opener=lambda request, timeout: CutOff()).complete({"messages": []})
    assert error.value.retryable


def test_http_redirect_cannot_forward_credentials():
    from openx_workbench.llm_service import NoRedirect
    assert NoRedirect().redirect_request(None, None, 302, "", {}, "https://elsewhere.example") is None


@pytest.mark.parametrize("response", [{"error": {"message": "secret-key"}}, {},
                                      {"choices": []}, {"choices": [None]}])
def test_http_200_error_or_missing_completion_is_a_sanitized_service_failure(response):
    client = ModelClient(ModelConfig(api_key="secret-key"),
                         opener=lambda request, timeout: io.BytesIO(json.dumps(response).encode()))
    with pytest.raises(ModelError, match="completion choices") as error:
        client.complete({"messages": []})
    assert "secret-key" not in str(error.value)


def test_effort_levels_come_from_the_model_list_and_are_sent_only_while_thinking():
    calls = []
    listing = {"data": [{"id": "deepseek-flash", "max_output_tokens": 393216, "input_modalities": ["text", "image"],
                         "effort": {"supported_levels": ["low", "high", "max"], "default_level": "high"}},
                        {"id": "plain"}]}

    def opener(request, timeout):
        calls.append(request)
        response = listing if request.method == "GET" else {
            "choices": [{"finish_reason": "stop", "message": {"content": '{"ok":true}'}}]}
        return io.BytesIO(json.dumps(response).encode())

    config = ModelConfig("https://api.deepseek.com", "deepseek-flash", "secret", reasoning_effort="max")
    catalog = ModelClient(config, opener=opener).catalog()
    assert [(item.id, item.effort_levels, item.default_effort) for item in catalog] == [
        ("deepseek-flash", ("low", "high", "max"), "high"), ("plain", (), "")]
    assert catalog[0].max_output_tokens == 393216
    assert [item.image_input for item in catalog] == [True, False]
    ModelClient(config, opener=opener).probe()
    sent = json.loads(calls[-1].data)
    assert sent["thinking"] == {"type": "enabled"} and sent["reasoning_effort"] == "max"
    ModelClient(replace(config, thinking=False), opener=opener).probe()
    assert "reasoning_effort" not in json.loads(calls[-1].data)


def test_effort_is_saved_and_validated(tmp_path):
    save_config(ModelConfig(api_key="", reasoning_effort="low", image_input=True), tmp_path)
    assert load_config(tmp_path).reasoning_effort == "low" and load_config(tmp_path).image_input is True
    with pytest.raises(ModelError):
        save_config(ModelConfig(reasoning_effort="High; drop"), tmp_path)
