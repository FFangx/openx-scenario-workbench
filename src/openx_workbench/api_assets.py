"""Asset management routes: the version table, version detail, classification,
deletion, standard export, and the shared library of published requirements."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import import_jobs
from .api_common import _cache, _lock, _store, _version
from .classification import FUNCTIONS, ROADS, TARGETS, classify_asset, confirm_classification, read_classification
from .pdf_store import PdfStore
from .preview_frames import read_frame

router = APIRouter(prefix="/api", tags=["assets"])


def _busy() -> None:
    state = import_jobs.status(_store())
    if state and state["status"] == "running":
        raise ValueError("导入任务结束后才能修改资产 / Wait for the running import to finish.")


@router.get("/classification-schema")
def classification_schema() -> dict[str, list[str]]:
    return {"function_type": list(FUNCTIONS), "label_road_type": list(ROADS), "label_target_type": list(TARGETS)}


@router.get("/assets")
def assets() -> list[dict[str, Any]]:
    """Every stored version with its labels; listing never parses files or calls a model."""
    store = _store()
    latest = {(item.asset_id, item.version_id) for item in store.latest()}
    rows = []
    for version in store.versions():
        record = read_classification(store, version)
        final = record.get("final", {})
        rows.append({"asset_id": version.asset_id, "version_id": version.version_id,
                     "version_number": version.version_number, "name": version.title or version.xosc_name,
                     "xosc_name": version.xosc_name, "xodr_name": version.xodr_name, "source_name": version.source_name,
                     "created_at": version.created_at, "compatibility": version.compatibility,
                     "latest": (version.asset_id, version.version_id) in latest,
                     "function": final.get("function_type", "未知"), "road": final.get("label_road_type", "未知"),
                     "targets": final.get("label_target_type", []),
                     "classification": record.get("status", "pending"), "needs_review": bool(record.get("needs_review"))})
    return rows


@router.get("/assets/{asset_id}/versions/{version_id}")
def asset_detail(asset_id: str, version_id: str) -> dict[str, Any]:
    store = _store()
    version = _version(asset_id, version_id)
    detail: dict[str, Any] = {
        "version": asdict(version), "classification": read_classification(store, version) or None,
        "references": list(store.references(version)), "has_frame": read_frame(store, version) is not None,
        "history": [{"version_id": item.version_id, "version_number": item.version_number, "created_at": item.created_at,
                     "compatibility": item.compatibility, "source_name": item.source_name}
                    for item in sorted((v for v in store.versions() if v.asset_id == asset_id),
                                       key=lambda v: v.version_number, reverse=True)],
        "standard_export": version.source_name.casefold().endswith(".sim"),
    }
    try:
        asset = store.load_asset(version)
        road = asset.bundle.road
        detail["summary"] = {"title": asset.title, "entities": len(asset.bundle.scenario.entities),
                             "road_length_m": road.total_length, "lane_count": road.lane_count,
                             "junction_count": road.junction_count, "description": asset.bundle.scenario.description or ""}
        detail["validation"] = asset.bundle.validation
    except Exception as error:  # noqa: BLE001 - an unreadable version is shown, not hidden
        detail["error"] = str(error)
    return detail


@router.post("/assets/{asset_id}/versions/{version_id}/classification/rules")
def classify_by_rules(asset_id: str, version_id: str) -> dict[str, Any]:
    _busy()
    return classify_asset(_store(), _version(asset_id, version_id))


class ClassificationRequest(BaseModel):
    function_type: str
    label_road_type: str
    label_target_type: list[str]
    label_actions: list[str]
    scenario_intent: str


@router.put("/assets/{asset_id}/versions/{version_id}/classification")
def confirm(asset_id: str, version_id: str, request: ClassificationRequest) -> dict[str, Any]:
    """A reviewer's labels; they replace model and rule suggestions for search."""
    _busy()
    return confirm_classification(_store(), _version(asset_id, version_id), request.model_dump())


@router.get("/assets/{asset_id}/versions/{version_id}/classification/download")
def classification_download(asset_id: str, version_id: str) -> Response:
    record = read_classification(_store(), _version(asset_id, version_id))
    if not record:
        raise HTTPException(404, "No classification record for this version.")
    return Response(json.dumps(record, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="classification.json"'})


@router.delete("/assets/{asset_id}/versions/{version_id}")
def delete_version(asset_id: str, version_id: str) -> dict[str, str]:
    """Removes the version's files; refused while a project or report references it."""
    _busy()
    store = _store()
    version = _version(asset_id, version_id)
    references = store.references(version)
    if references:
        raise ValueError(f"此版本已被 {len(references)} 条项目或报告记录引用，无法删除 / "
                         f"Referenced by {len(references)} project or report items; it cannot be deleted.")
    from .api_preview import preview_stop, preview_status
    playing = preview_status()
    if (playing.get("asset_id"), playing.get("version_id")) == (asset_id, version_id):
        preview_stop()
    store.delete_version(version)
    return {"deleted": version_id}


# ---------- standard export (SIM assets) ----------

@router.post("/assets/{asset_id}/versions/{version_id}/standard-export")
def standard_export(asset_id: str, version_id: str) -> dict[str, Any]:
    """Converts a separate copy and checks it; the original asset is unchanged."""
    from .standard_export import build_standard_export
    _busy()
    export = build_standard_export(_store(), _version(asset_id, version_id))
    with _lock:
        _cache["standard_export"] = (asset_id, version_id, export)
    return {"ready": export.ready, "audit": export.audit}


@router.get("/assets/{asset_id}/versions/{version_id}/standard-export/download")
def standard_export_download(asset_id: str, version_id: str) -> Response:
    prepared = _cache.get("standard_export")
    if not prepared or prepared[:2] != (asset_id, version_id):
        raise HTTPException(404, "Prepare the standard export first.")
    export = prepared[2]
    kind = "standard" if export.ready else "diagnostic"
    return Response(export.package(diagnostic=not export.ready), media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="openx-{kind}-{version_id}.zip"'})


# ---------- published requirements ----------

@router.get("/requirements")
def requirements() -> list[dict[str, Any]]:
    """Latest published revision of every confirmed requirement scene, across projects."""
    return [{"library_id": record["library_id"], "revision": record["revision"], "reviewed_at": record["reviewed_at"],
             "project_id": record["project_id"], "document_id": record["document_id"], "scene_id": record["scene_id"],
             "title": record["package"]["title"], "preferred_text": record["package"]["preferred_text"],
             "classification": record["package"].get("classification", {}), "structure": record["package"].get("structure", {})}
            for record in PdfStore(_store()).library()]


@router.get("/requirements/{library_id}/download")
def requirement_download(library_id: str) -> Response:
    record = next((item for item in PdfStore(_store()).library() if item["library_id"] == library_id), None)
    if record is None:
        raise HTTPException(404, "Unknown requirement.")
    return Response(json.dumps(record, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="requirement-scene.json"'})
