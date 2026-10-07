"""esmini playback for one asset version at a time, previews for the whole library, and road drawings.

The worker serves an MJPEG stream on its own loopback port; the page embeds that URL
in an <img>. Polling the status here also records whether the version played.
"""

from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import preview_batch
from .api_common import _store, _version
from .api_schemas import Job, PreviewStatus, documented
from .esmini_preview import PreviewProcess, find_esmini, record_outcome, start_preview
from .preferences import read_preferences

router = APIRouter(prefix="/api", tags=["preview"])
_lock = threading.Lock()
_current: dict[str, Any] = {"preview": None}


class PreviewRequest(BaseModel):
    duration: int = Field(30, ge=1, le=120, description="Seconds of simulation; 2 captures a still frame.")


def _record(preview: PreviewProcess, status: dict) -> None:
    """Store the outcome on the version once, as the desktop workbench did."""
    store = _store()
    version = next((item for item in store.versions()
                    if (item.asset_id, item.version_id) == (preview.asset_id, preview.version_id)), None)
    if version is not None:
        record_outcome(store, version, status)


def _status(preview: PreviewProcess | None) -> dict[str, Any]:
    if preview is None:
        return {"state": "idle"}
    status = preview.status()
    _record(preview, status)
    result = {"asset_id": preview.asset_id, "version_id": preview.version_id, "state": status["state"],
              "frames": status.get("frames", 0), "error": status.get("error", ""),
              "snapshot_error": status.get("snapshot_error", "")}
    if status["state"] in {"starting", "running"}:
        result["stream_url"] = f"{preview.url}/stream?token={preview.token}"
    if status["state"] == "failed":
        try:
            result["log"] = (preview.workdir / "worker.log").read_text(errors="replace")[-4000:]
        except OSError:
            pass  # a finished worker may already have removed its staging files
    return result


@router.post("/assets/{asset_id}/versions/{version_id}/preview", **documented(PreviewStatus))
def preview_start(asset_id: str, version_id: str, request: PreviewRequest) -> dict[str, Any]:
    version = _version(asset_id, version_id)
    if version.road_missing:
        raise ValueError("道路文件缺失，无法预览 / The road file is missing; this version cannot be previewed.")
    executable = find_esmini(str(read_preferences().get("esmini_path", "")))
    if executable is None:
        raise ValueError("尚未找到 esmini，请在设置 → 本机服务中选择安装位置 / esmini was not found; choose it under Settings → Local service.")
    with _lock:
        previous, _current["preview"] = _current["preview"], None
        if previous:
            previous.stop()
        try:
            _current["preview"] = start_preview(_store(), version, executable, duration=request.duration)
        except Exception as error:  # noqa: BLE001 - every start failure is the version's preview outcome
            _store().set_compatibility(version, "failed", str(error))
            raise ValueError(f"预览未能启动 / Preview could not start: {error}") from None
        return _status(_current["preview"])


@router.get("/preview", **documented(PreviewStatus))
def preview_status() -> dict[str, Any]:
    with _lock:
        return _status(_current["preview"])


@router.post("/preview/stop", **documented(PreviewStatus))
def preview_stop() -> dict[str, Any]:
    with _lock:
        preview, _current["preview"] = _current["preview"], None
    if preview:
        preview.stop()
    return {"state": "idle"}


class PreviewBatchRequest(BaseModel):
    retry_failed: bool = Field(False, description="Also try again the versions esmini failed on before.")


@router.post("/previews", **documented(Job))
def previews(request: PreviewBatchRequest) -> dict[str, Any]:
    """Saves an esmini frame for every latest version that has none yet, one at a time, and draws each
    road from above. Versions whose road was not imported are skipped."""
    return preview_batch.start(_store(), retry_failed=request.retry_failed).snapshot()


@router.get("/assets/{asset_id}/versions/{version_id}/road-drawing")
def road_drawing(asset_id: str, version_id: str) -> Response:
    """The version's road from above (PNG), with where each participant starts; drawn once, then kept."""
    data = preview_batch.road_drawing(_store(), _version(asset_id, version_id))
    if data is None:
        raise HTTPException(404, "This version has no road to draw.")
    return Response(data, media_type="image/png", headers={"Cache-Control": "private, max-age=3600"})
