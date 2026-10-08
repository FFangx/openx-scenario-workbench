"""One local model configuration and bounded OpenAI-compatible HTTP transport."""
from __future__ import annotations

import base64
import ctypes
import json
import os
import re
from dataclasses import asdict, dataclass, field, replace
from http.client import HTTPException
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .atomic_write import write_json
from .asset_store import default_store_root


@dataclass(frozen=True)
class ModelConfig:
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    api_key: str = field(default="", repr=False)
    thinking: bool = True
    # Thinking effort sent as `reasoning_effort` while thinking is on; empty keeps the service
    # default. Levels come from the service's model list (DeepSeek: effort.supported_levels).
    reasoning_effort: str = ""
    # Output limit of every call: the model's own maximum (the settings take it from the service's
    # model list). Only generated tokens are billed, and thinking counts against it.
    max_tokens: int = 64000
    timeout: int = 900
    # Model requests a PDF extraction sends at once (its structure calls). DeepSeek allows thousands
    # per account; a service that rate-limits answers 429 and the call is retried after a pause.
    concurrency: int = 64
    # The model reads images: a PDF extraction then sends each scene's figures with its text. The
    # settings take it from the service's model list (input_modalities).
    image_input: bool = False


@dataclass(frozen=True)
class ModelInfo:
    """One entry of the service's model list, with what it declares about thinking effort."""
    id: str
    effort_levels: tuple[str, ...] = ()
    default_effort: str = ""
    max_output_tokens: int | None = None
    image_input: bool = False


EFFORT = re.compile(r"^[a-z][a-z0-9_-]{0,19}$")


class ModelError(ValueError):
    # True when trying again may succeed: rate limits, server errors, timeouts.
    retryable = False


def _failure(message: str, *, retryable: bool = False) -> ModelError:
    error = ModelError(message)
    error.retryable = retryable
    return error


MAX_TOKENS_LIMIT = 1_048_576


def base_url(value: str) -> str:
    parsed = urlsplit(value.strip())
    if parsed.scheme not in {"https", "http"} or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ModelError("请输入有效的模型服务地址 / Invalid model service URL.")
    if parsed.scheme == "http" and parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise ModelError("远程模型地址需要 HTTPS / Remote services require HTTPS.")
    path = parsed.path.rstrip("/")
    for suffix in ("/chat/completions", "/models"):
        if path.endswith(suffix):
            path = path[:-len(suffix)]
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def draft_config(saved: ModelConfig, endpoint: str, key: str = "", **values) -> ModelConfig:
    """Settings edits over the saved config; a saved key never silently follows an edited endpoint."""
    try:
        same_endpoint = base_url(endpoint) == base_url(saved.base_url)
    except ModelError:
        same_endpoint = False
    return replace(saved, base_url=endpoint, api_key=key.strip() or (saved.api_key if same_endpoint else ""), **values)


def _protect(data: bytes, *, decrypt=False) -> bytes:
    if os.name != "nt":
        return data
    from ctypes import wintypes
    class Blob(ctypes.Structure):
        _fields_ = [("size", wintypes.DWORD), ("data", ctypes.POINTER(ctypes.c_ubyte))]
    buffer = ctypes.create_string_buffer(data)
    incoming = Blob(len(data), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    outgoing = Blob()
    function = ctypes.windll.crypt32.CryptUnprotectData if decrypt else ctypes.windll.crypt32.CryptProtectData
    if not function(ctypes.byref(incoming), None, None, None, None, 1, ctypes.byref(outgoing)):
        raise ModelError("无法访问本机保存的密钥，请重新输入 / Cannot access the saved key.")
    try:
        return ctypes.string_at(outgoing.data, outgoing.size)
    finally:
        ctypes.windll.kernel32.LocalFree(outgoing.data)


def load_config(root: Path | None = None) -> ModelConfig:
    path = (root or default_store_root()) / "model_settings.json"
    if path.exists():
        payload = json.loads(path.read_text(encoding="utf-8"))
        protected = payload.pop("protected_key", "")
        key = _protect(base64.b64decode(protected), decrypt=True) if protected else b""
        return ModelConfig(**payload, api_key=key.decode())
    return ModelConfig(
        base_url=os.getenv("OPENX_LLM_URL", "https://api.deepseek.com"),
        model=os.getenv("OPENX_LLM_MODEL", "deepseek-v4-flash"),
        api_key=os.getenv("OPENX_LLM_API_KEY") or os.getenv("DEEPSEEK_API_KEY", ""),
    )


def save_config(config: ModelConfig, root: Path | None = None) -> None:
    normalized = base_url(config.base_url)
    if (not config.model.strip() or not 256 <= config.max_tokens <= MAX_TOKENS_LIMIT or not 10 <= config.timeout <= 1800
            or not 1 <= config.concurrency <= 256):
        raise ModelError("请检查模型名、输出上限、超时和并发数 / Check model, output limit, timeout and concurrency.")
    if config.reasoning_effort and not EFFORT.match(config.reasoning_effort):
        raise ModelError("思考等级无效 / Invalid thinking effort.")
    target = (root or default_store_root()) / "model_settings.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    value = asdict(config)
    value.pop("api_key")
    value.update(base_url=normalized, model=config.model.strip(), protected_key=base64.b64encode(_protect(config.api_key.encode())).decode() if config.api_key else "")
    write_json(target, value, ensure_ascii=False, indent=2, permissions=0o600)


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class ModelClient:
    def __init__(self, config: ModelConfig | None = None, *, opener=None):
        self.config = config or load_config()
        self.opener = opener or build_opener(NoRedirect()).open

    def request(self, route: str, body=None, *, timeout=None):
        if not self.config.api_key:
            raise ModelError("请在设置中填写 API Key / Configure an API key in Settings.")
        request = Request(base_url(self.config.base_url) + route,
                          data=json.dumps(body, ensure_ascii=False, allow_nan=False).encode() if body is not None else None,
                          headers={"Authorization": "Bearer " + self.config.api_key, "Content-Type": "application/json"},
                          method="POST" if body is not None else "GET")
        try:
            with self.opener(request, timeout=timeout or self.config.timeout) as response:
                raw = response.read(8_000_001)
            if len(raw) > 8_000_000:
                raise ModelError("模型响应过大 / Model response exceeds size limit.")
            result = json.loads(raw)
            if not isinstance(result, dict):
                raise ValueError()
            return result
        except HTTPError as error:
            hints = {401: "Key 无效", 403: "无访问权限", 404: "地址或模型不存在", 429: "额度不足或限流"}
            raise _failure(f"模型服务 HTTP {error.code}: {hints.get(error.code, '请检查地址、模型参数或服务状态')} / Model request failed.",
                           retryable=error.code == 429 or error.code >= 500) from None
        except (URLError, OSError, TimeoutError, HTTPException):  # HTTPException: a reply cut off mid-body (IncompleteRead)
            raise _failure("模型服务连接失败或超时 / Model connection failed or timed out.", retryable=True) from None
        except ModelError:
            raise
        except (ValueError, TypeError):
            raise ModelError("模型服务未返回有效 JSON / Invalid JSON response from model service.") from None

    def models(self) -> list[str]:
        return [item.id for item in self.catalog()]

    def catalog(self) -> list[ModelInfo]:
        """The service's models in id order; effort levels only where the service declares them."""
        result = self.request("/models", timeout=30)
        found: dict[str, ModelInfo] = {}
        for item in result.get("data", []):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                continue
            effort = item.get("effort") if isinstance(item.get("effort"), dict) else {}
            levels = tuple(level for level in effort.get("supported_levels") or ()
                           if isinstance(level, str) and EFFORT.match(level))
            default = effort.get("default_level") if effort.get("default_level") in levels else ""
            limit = item.get("max_output_tokens")
            modalities = item.get("input_modalities") if isinstance(item.get("input_modalities"), list) else []
            found.setdefault(item["id"], ModelInfo(item["id"], levels, default,
                                                   limit if isinstance(limit, int) and limit > 0 else None,
                                                   "image" in modalities))
        if not found:
            raise ModelError("服务未提供模型清单，可手动输入模型名 / No model list; enter a model ID manually.")
        return [found[key] for key in sorted(found)]

    def complete(self, body, *, timeout=None):
        # Every call may use the whole output limit: a smaller cap only truncates a long thought.
        request = {**body, "model": self.config.model, "max_tokens": self.config.max_tokens}
        if urlsplit(base_url(self.config.base_url)).hostname == "api.deepseek.com":
            request["thinking"] = {"type": "enabled" if self.config.thinking else "disabled"}
        else:
            request.pop("thinking", None)
        if self.config.thinking and self.config.reasoning_effort:
            request["reasoning_effort"] = self.config.reasoning_effort
        response = self.request("/chat/completions", request, timeout=min(timeout or self.config.timeout, self.config.timeout))
        choices = response.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            # Some compatible services return an error envelope with HTTP 200.
            # Treat it as a service failure, not malformed model-authored JSON
            # eligible for a second expensive document extraction request.
            raise ModelError("模型服务未返回有效候选响应 / Model service returned no valid completion choices.")
        return response

    def probe(self) -> str:
        response = self.complete({"messages": [{"role": "user", "content": 'Return only this JSON: {"ok":true}'}],
                                  "response_format": {"type": "json_object"}})
        try:
            choice = response["choices"][0]
            if choice.get("finish_reason") != "stop" or json.loads(choice["message"]["content"]).get("ok") is not True:
                raise ValueError()
        except (KeyError, IndexError, ValueError, TypeError, AttributeError):
            raise ModelError("模型未通过 JSON 响应测试；请检查模型能力或输出上限 / Model failed the JSON response test.") from None
        return self.config.model
