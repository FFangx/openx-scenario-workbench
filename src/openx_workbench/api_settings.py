"""Settings routes: language model, esmini, data folder, XSD registry and workbench preferences.

The saved API key never leaves this process; responses only say whether one exists.
"""

from __future__ import annotations

from dataclasses import asdict, replace
from pathlib import Path
from subprocess import TimeoutExpired
from typing import Any, Literal

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import jobs, schema_updates
from .api_schemas import (Job, ModelList, ModelProbe, ModelSettings, OpenedFolder, Preferences, PreviewSettings,
                          SchemaCheck, SchemaStatus, Settings, documented)
from .asset_store import AssetStore
from .esmini_preview import find_esmini
from .llm_service import MAX_TOKENS_LIMIT, ModelClient, ModelConfig, draft_config, load_config, save_config
from .local_folders import choose_folder, open_folder
from .matching import ENCODERS, known_encoder
from .preferences import read_preferences, save_preferences
from .schema_validation import SCHEMA_REVISION, schema_root

router = APIRouter(prefix="/api/settings", tags=["settings"])

# preferences.json keeps the labels the desktop app has always written.
LANGUAGE_LABELS = {"zh": "中文", "en": "English"}


class ModelDraft(BaseModel):
    base_url: str
    model: str = ""
    api_key: str = Field("", description="Blank keeps the saved key when the endpoint is unchanged.")
    thinking: bool = True
    reasoning_effort: str = Field("", max_length=20, description="Blank keeps the service default.")
    max_tokens: int = Field(64000, ge=256, le=MAX_TOKENS_LIMIT)
    timeout: int = Field(900, ge=10, le=1800)
    concurrency: int = Field(64, ge=1, le=256, description="Model requests a PDF extraction sends at once.")
    image_input: bool = Field(False, description="The model reads images: PDF extraction sends scene figures.")


class PreferencesUpdate(BaseModel):
    language: Literal["zh", "en"] | None = None
    appearance: Literal["light", "dark", "system"] | None = None
    encoder: str | None = None
    show_file_names: bool | None = None


class FolderRequest(BaseModel):
    target: Literal["data", "esmini"]


class SchemaRevision(BaseModel):
    revision: str = Field(pattern=r"^[0-9a-f]{40}$")


def _saved_model() -> tuple[ModelConfig, bool]:
    try:
        return load_config(), True
    except (ValueError, OSError):
        return ModelConfig(), False


def _model_json(config: ModelConfig, readable: bool = True) -> dict[str, Any]:
    return {"base_url": config.base_url, "model": config.model, "thinking": config.thinking,
            "reasoning_effort": config.reasoning_effort, "max_tokens": config.max_tokens, "timeout": config.timeout,
            "concurrency": config.concurrency, "image_input": config.image_input,
            "has_key": bool(config.api_key), "readable": readable}


def _draft(request: ModelDraft) -> ModelConfig:
    saved, _ = _saved_model()
    return draft_config(saved, request.base_url, request.api_key, model=request.model.strip(),
                        thinking=request.thinking, reasoning_effort=request.reasoning_effort.strip(),
                        max_tokens=request.max_tokens, timeout=request.timeout, concurrency=request.concurrency,
                        image_input=request.image_input)


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
            "encoder": known_encoder(prefs.get("encoder")), "show_file_names": prefs.get("show_file_names") is True}


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
    if request.show_file_names is not None:
        values["show_file_names"] = request.show_file_names
    if values:
        save_preferences(**values)
    return _preferences_json()


@router.post("/model/models", **documented(ModelList))
def model_list(request: ModelDraft) -> dict[str, Any]:
    catalog = ModelClient(_draft(request)).catalog()
    return {"models": [item.id for item in catalog], "details": [asdict(item) for item in catalog]}


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


# ---------- XSD registry updates ----------
# Only these routes reach the network, and only when the user asks; validation stays offline.

def _schema_scope() -> str:
    return str(schema_root().resolve())


def _schema_status() -> dict[str, Any]:
    job = jobs.latest(schema_updates.KIND, _schema_scope())
    return {**schema_updates.status(), "pinned": SCHEMA_REVISION, "job": job.snapshot() if job else None}


def _idle() -> None:
    if jobs.running(schema_updates.KIND, _schema_scope()):
        raise ValueError("规范预览仍在进行 / A schema preview is still running.")


@router.get("/schemas", **documented(SchemaStatus))
def schema_status() -> dict[str, Any]:
    return _schema_status()


@router.post("/schemas/check", **documented(SchemaCheck))
def schema_check() -> dict[str, Any]:
    """Compares the newest esmini schema folder with the installed registry; reads GitHub, changes nothing."""
    return schema_updates.check()


@router.post("/schemas/preview", **documented(Job))
def schema_preview(request: SchemaRevision) -> dict[str, Any]:
    """Downloads `revision` beside the active registry and lists the library verdicts it would change."""
    store = AssetStore()
    job = jobs.Job(schema_updates.KIND, _schema_scope())
    return jobs.start(job, lambda job: schema_updates.preview(store, job, request.revision)).snapshot()


@router.post("/schemas/apply", **documented(SchemaStatus))
def schema_apply(request: SchemaRevision) -> dict[str, Any]:
    _idle()
    schema_updates.apply(request.revision)
    return _schema_status()


@router.post("/schemas/rollback", **documented(SchemaStatus))
def schema_rollback() -> dict[str, Any]:
    _idle()
    schema_updates.rollback()
    return _schema_status()


@router.delete("/schemas/staged", **documented(SchemaStatus))
def schema_discard() -> dict[str, Any]:
    _idle()
    schema_updates.discard()
    return _schema_status()
