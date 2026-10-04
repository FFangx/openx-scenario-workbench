"""Settings routes: language model, esmini, data folder and workbench preferences.

The saved API key never leaves this process; responses only say whether one exists.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path
from subprocess import TimeoutExpired
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from .api_schemas import (ModelList, ModelProbe, ModelSettings, OpenedFolder, Preferences, PreviewSettings, Settings,
                          documented)
from .asset_store import AssetStore
from .esmini_preview import find_esmini
from .llm_service import ModelClient, ModelConfig, draft_config, load_config, save_config
from .local_folders import choose_folder, open_folder
from .matching import ENCODERS, known_encoder
from .preferences import read_preferences, save_preferences

router = APIRouter(prefix="/api/settings", tags=["settings"])

# preferences.json keeps the labels the desktop app has always written.
LANGUAGE_LABELS = {"zh": "中文", "en": "English"}


class ModelDraft(BaseModel):
    base_url: str
    model: str = ""
    api_key: str = Field("", description="Blank keeps the saved key when the endpoint is unchanged.")
    thinking: bool = True
    max_tokens: int = Field(64000, ge=256, le=131072)
    timeout: int = Field(900, ge=10, le=1800)


class PreferencesUpdate(BaseModel):
    language: Literal["zh", "en"] | None = None
    appearance: Literal["light", "dark", "system"] | None = None
    encoder: str | None = None


class FolderRequest(BaseModel):
    target: Literal["data", "esmini"]


def _saved_model() -> tuple[ModelConfig, bool]:
    try:
        return load_config(), True
    except (ValueError, OSError):
        return ModelConfig(), False


def _model_json(config: ModelConfig, readable: bool = True) -> dict[str, Any]:
    return {"base_url": config.base_url, "model": config.model, "thinking": config.thinking,
            "max_tokens": config.max_tokens, "timeout": config.timeout,
            "has_key": bool(config.api_key), "readable": readable}


def _draft(request: ModelDraft) -> ModelConfig:
    saved, _ = _saved_model()
    return draft_config(saved, request.base_url, request.api_key, model=request.model.strip(),
                        thinking=request.thinking, max_tokens=request.max_tokens, timeout=request.timeout)


def _preview_json() -> dict[str, Any]:
    configured = str(read_preferences().get("esmini_path", ""))
    detected = find_esmini(configured)
    return {"configured": configured, "executable": str(detected) if detected else None,
            "folder": str(detected.parent) if detected else None}


def _preferences_json() -> dict[str, Any]:
    prefs = read_preferences()
    appearance = prefs.get("appearance", "system")
    return {"language": "en" if prefs.get("language") == "English" else "zh",
            "appearance": appearance if appearance in {"light", "dark", "system"} else "system",
            "encoder": known_encoder(prefs.get("encoder"))}


@router.get("", **documented(Settings))
def settings() -> dict[str, Any]:
    return {"model": _model_json(*_saved_model()), "preview": _preview_json(),
            "data_dir": str(AssetStore().root), "preferences": _preferences_json()}


@router.put("/preferences", **documented(Preferences))
def update_preferences(request: PreferencesUpdate) -> dict[str, Any]:
    values: dict[str, Any] = {}
    if request.language:
        values["language"] = LANGUAGE_LABELS[request.language]
    if request.appearance:
        values["appearance"] = request.appearance
    if request.encoder is not None:
        if request.encoder not in ENCODERS:
            raise ValueError("Unknown encoder.")
        values["encoder"] = request.encoder
    if values:
        save_preferences(**values)
    return _preferences_json()


@router.post("/model/models", **documented(ModelList))
def model_list(request: ModelDraft) -> dict[str, list[str]]:
    return {"models": ModelClient(_draft(request)).models()}


@router.post("/model/test", **documented(ModelProbe))
def model_test(request: ModelDraft) -> dict[str, str]:
    draft = _draft(request)
    if not draft.model:
        raise ValueError("请先选择或输入模型名 / Choose or enter a model ID first.")
    return {"model": ModelClient(draft).probe()}


@router.put("/model", **documented(ModelSettings))
def model_save(request: ModelDraft) -> dict[str, Any]:
    save_config(_draft(request))
    return _model_json(load_config())


@router.delete("/model/key", **documented(ModelSettings))
def model_remove_key() -> dict[str, Any]:
    saved, _ = _saved_model()
    save_config(replace(saved, api_key=""))
    return _model_json(load_config())


@router.post("/preview/browse", **documented(PreviewSettings))
def preview_browse() -> dict[str, Any]:
    """Opens the native folder dialog on this machine; the browser and service share a desktop."""
    current = find_esmini(str(read_preferences().get("esmini_path", "")))
    try:
        folder = choose_folder("选择 esmini 安装文件夹 / Select esmini installation folder",
                               current.parent if current else Path.home())
    except (OSError, ValueError, TimeoutExpired):
        raise ValueError("无法打开文件夹选择窗口，请在本机桌面使用工作台。 / "
                         "Could not open the folder browser. Use the workbench on this computer's desktop.") from None
    if folder is None:
        return {**_preview_json(), "cancelled": True}
    resolved = find_esmini(str(folder))
    if resolved is None:
        raise ValueError("此文件夹没有完整的 esmini。请选择含 esmini.exe 和 esminiLib.dll 的 bin 文件夹，或安装根目录。 / "
                         "Choose the esmini installation or bin folder containing esmini.exe and esminiLib.dll.")
    save_preferences(esmini_path=str(resolved))
    return _preview_json()


@router.post("/preview/detect", **documented(PreviewSettings))
def preview_detect() -> dict[str, Any]:
    save_preferences(esmini_path="")
    return _preview_json()


@router.post("/open-folder", **documented(OpenedFolder))
def open_local_folder(request: FolderRequest) -> dict[str, str]:
    """Only fixed, server-known folders; the client never supplies a path."""
    if request.target == "data":
        path = AssetStore().root
    else:
        executable = find_esmini(str(read_preferences().get("esmini_path", "")))
        if executable is None:
            raise ValueError("尚未找到 esmini / esmini was not found.")
        path = executable.parent
    try:
        open_folder(path)
    except OSError:
        raise ValueError("无法打开此文件夹，请检查它是否仍然存在。 / Could not open this folder. Check that it still exists.") from None
    return {"opened": str(path)}
