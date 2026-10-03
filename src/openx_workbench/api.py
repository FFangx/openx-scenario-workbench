"""HTTP API for the React workbench: a thin layer over the stores and the matcher."""

from __future__ import annotations

import json
import threading
from dataclasses import asdict, replace
from functools import lru_cache
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from .asset_store import AssetStore, AssetVersion
from .catalog import OpenXAsset
from .pdf_store import PdfStore, StoredScene
from .presentation import asset_display_title, difference_text, display
from .preview_frames import read_frame
from .project_store import ProjectStore
from .retrieval import OpenXIndex, RetrievalResult, build_encoder, catalog_fingerprint
from .reuse_trace import build_trace
from .scene_package import scene_package_to_query

FACETS = ("function_type", "label_road_type", "label_target_type")
WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"

app = FastAPI(title="OpenX Scenario Workbench API", version="0.1.0")
_lock = threading.Lock()
_cache: dict[str, Any] = {}


@app.exception_handler(ValueError)
async def _value_error(_: Request, error: ValueError) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=400)


# ---------- shared state ----------

def _store() -> AssetStore:
    return AssetStore()


def _catalog() -> tuple[list[OpenXAsset], dict[str, AssetVersion]]:
    """Parsed assets are reused until the set of stored versions changes."""
    store = _store()
    key = tuple(sorted(version.version_id for version in store.latest()))
    with _lock:
        if _cache.get("catalog_key") != key:
            _cache["catalog"] = store.catalog()
            _cache["catalog_key"] = key
        return _cache["catalog"]


def _preferred_encoder() -> str:
    try:
        value = json.loads((_store().root / "preferences.json").read_text(encoding="utf-8")).get("encoder")
    except (OSError, ValueError, AttributeError):
        value = None
    # Older preference files stored the display label; the Streamlit app treats those as BGE too.
    return value if value in {"bge", "hashing"} else "bge"


@lru_cache(maxsize=2)
def _encoder(name: str):
    return build_encoder(name)


def _index(catalog: list[OpenXAsset], encoder_name: str) -> OpenXIndex:
    identity = (encoder_name, catalog_fingerprint(catalog))
    with _lock:
        if _cache.get("index_identity") == identity:
            return _cache["index"]
        path = _store().root / "indexes" / encoder_name / f"{identity[1][:24]}.json"
        encoder = _encoder(encoder_name)
        try:
            index = OpenXIndex.load(path, catalog, encoder)
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            index = OpenXIndex(catalog, encoder)
            index.save(path)
        _cache.update(index_identity=identity, index=index)
        return index


def _scene(pdf: PdfStore, project_id: str, document_id: str, scene_id: str,
           revision: int | None = None) -> StoredScene:
    revisions = pdf.revisions(project_id, document_id, scene_id)
    if not revisions:
        raise HTTPException(404, "Unknown extracted scene.")
    if revision is None:
        return revisions[-1]
    stored = next((item for item in revisions if item.revision == revision), None)
    if stored is None:
        raise HTTPException(404, "Unknown scene revision.")
    return stored


# ---------- serializers ----------

def _source_region(package) -> dict[str, Any] | None:
    """Page and PDF-point box of the scene's first cited blocks, for an evidence thumbnail."""
    blocks = [block for block in package.extraction.get("source_blocks", []) if len(block.get("bbox") or []) == 4]
    if not blocks:
        return None
    page = blocks[0]["page_number"]
    boxes = [block["bbox"] for block in blocks if block["page_number"] == page]
    return {"page": page, "clip": [round(min(box[0] for box in boxes), 1), round(min(box[1] for box in boxes), 1),
                                   round(max(box[2] for box in boxes), 1), round(max(box[3] for box in boxes), 1)]}


def _scene_json(stored: StoredScene) -> dict[str, Any]:
    package = stored.package
    evidence = package.evidence
    return {
        "source_region": _source_region(package),
        "scene_id": stored.scene_id, "revision": stored.revision, "package_id": package.package_id,
        "title": package.title, "preferred_text": package.preferred_text,
        "section_id": evidence[0].section_id if evidence else "",
        "pages": [min(e.page_start for e in evidence), max(e.page_end for e in evidence)] if evidence else None,
        "evidence": [asdict(item) for item in evidence],
        "review_status": package.extraction.get("review_status", "pending"),
        "classification": {key: package.classification.get(key)
                           for key in ("function", "road_type", "intent", "method", "confidence")},
        "entities": package.entities, "actions": package.actions, "road_types": package.road_types,
    }


def _candidate_json(result: RetrievalResult, version: AssetVersion | None, lang: str) -> dict[str, Any]:
    asset = result.asset
    scenario, road = asset.bundle.scenario, asset.bundle.road
    return {
        # Catalog keys are "asset:version"; the stores and file routes address the bare asset ID.
        "asset_id": version.asset_id if version else asset.asset_id.split(":")[0],
        "version_id": version.version_id if version else None,
        "version_number": version.version_number if version else None,
        "source_name": version.source_name if version else "",
        "compatibility": version.compatibility if version else "not_tested",
        "title": asset.title, "display_title": asset_display_title(asset, lang),
        "xosc": asset.xosc_name, "xodr": asset.xodr_name,
        "description": scenario.description or "",
        "classification": asset.classification,
        "scores": {"combined": result.score, "semantic": result.vector_score,
                   "scenario": result.scenario_score, "road": result.road_score},
        "level": result.confirmation_level, "structural_level": result.reuse_level,
        "review_kind": result.confirmation_review_kind,
        "change_cost": result.estimated_change_cost,
        "reasons": [{"code": reason, "label": display(reason, lang)} for reason in result.reasons],
        "differences": [{**asdict(item), "category_label": display(item.category, lang),
                         "requested_label": display(item.requested, lang),
                         "candidate_label": display(item.candidate, lang),
                         "text": difference_text(item, lang)} for item in result.differences],
        "standard_checks": result.standard_checks,
        "scenario": {"name": scenario.name, "entities": [asdict(entity) for entity in scenario.entities],
                     "actions": sorted({action.kind for action in scenario.actions}),
                     "trigger_count": len(scenario.triggers),
                     "parameters": [item.get("name", "") for item in scenario.parameters],
                     "environment": scenario.environment},
        "road": {"total_length_m": road.total_length, "lane_count": road.lane_count,
                 "lane_types": road.lane_types, "geometry_types": road.geometry_types,
                 "junction_count": road.junction_count, "road_count": len(road.road_ids),
                 "revision": road.revision},
        "has_frame": bool(version and read_frame(_store(), version)),
    }


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------- projects and documents ----------

@app.get("/api/projects")
def projects() -> dict[str, Any]:
    store = ProjectStore(_store())
    last = store.last()
    return {"projects": [asdict(item) for item in store.projects()],
            "last_project_id": last.project_id if last else None}


@app.post("/api/projects/{project_id}/select")
def select_project(project_id: str) -> dict[str, str]:
    ProjectStore(_store()).set_last(project_id)
    return {"project_id": project_id}


@app.get("/api/projects/{project_id}/documents")
def documents(project_id: str) -> list[dict[str, Any]]:
    pdf = PdfStore(_store())
    return [{**asdict(document), "size_bytes": (pdf.blobs / document.sha256).stat().st_size
             if (pdf.blobs / document.sha256).exists() else None}
            for document in pdf.documents(project_id)]


@app.get("/api/projects/{project_id}/documents/{document_id}/scenes")
def scenes(project_id: str, document_id: str) -> list[dict[str, Any]]:
    return [_scene_json(item) for item in PdfStore(_store()).scenes(project_id, document_id)]


def _document(pdf: PdfStore, project_id: str, document_id: str):
    document = next((item for item in pdf.documents(project_id) if item.document_id == document_id), None)
    if document is None:
        raise HTTPException(404, "Unknown PDF document.")
    return document


@app.get("/api/projects/{project_id}/documents/{document_id}/file")
def document_file(project_id: str, document_id: str) -> Response:
    pdf = PdfStore(_store())
    return Response(pdf.pdf_bytes(_document(pdf, project_id, document_id)), media_type="application/pdf")


@lru_cache(maxsize=96)
def _page_png(sha256: str, page: int, width: int, clip: tuple[float, ...] | None) -> bytes:
    import pymupdf
    with pymupdf.open(stream=_cache["pdf:" + sha256], filetype="pdf") as document:
        if not 1 <= page <= len(document):
            raise HTTPException(404, "Page out of range.")
        target = document[page - 1]
        area = pymupdf.Rect(clip) & target.rect if clip else target.rect
        if area.is_empty:
            raise HTTPException(400, "Clip lies outside the page.")
        scale = width / area.width
        return target.get_pixmap(matrix=pymupdf.Matrix(scale, scale), clip=area, alpha=False).tobytes("png")


@app.get("/api/projects/{project_id}/documents/{document_id}/pages/{page}")
def document_page(project_id: str, document_id: str, page: int, width: int = 480, clip: str = "") -> Response:
    """Render a page, or the `clip` box (PDF points "x0,y0,x1,y1") of it, at `width` pixels."""
    try:
        box = tuple(float(value) for value in clip.split(",")) if clip else None
    except ValueError:
        raise HTTPException(400, "Clip needs four numbers.") from None
    if box is not None and len(box) != 4:
        raise HTTPException(400, "Clip needs four numbers.")
    pdf = PdfStore(_store())
    document = _document(pdf, project_id, document_id)
    with _lock:
        if "pdf:" + document.sha256 not in _cache:
            _cache["pdf:" + document.sha256] = pdf.pdf_bytes(document)
    png = _page_png(document.sha256, page, max(80, min(width, 1600)), box)
    return Response(png, media_type="image/png", headers={"Cache-Control": "max-age=86400"})


# ---------- asset library ----------

@app.get("/api/library")
def library() -> dict[str, Any]:
    catalog, versions = _catalog()
    facets: dict[str, set[str]] = {key: set() for key in FACETS}
    for asset in catalog:
        for key in FACETS:
            value = asset.classification.get(key)
            for item in value if isinstance(value, list) else [value]:
                if item:
                    facets[key].add(str(item))
    imported = [version.created_at for version in versions.values()]
    return {"asset_count": len(catalog), "last_import": max(imported) if imported else None,
            "encoder": _preferred_encoder(), "facets": {key: sorted(values) for key, values in facets.items()}}


def _version(asset_id: str, version_id: str) -> AssetVersion:
    version = next((item for item in _store().versions()
                    if item.asset_id == asset_id and item.version_id == version_id), None)
    if version is None:
        raise HTTPException(404, "Unknown asset version.")
    return version


@app.get("/api/assets/{asset_id}/versions/{version_id}/frame")
def asset_frame(asset_id: str, version_id: str) -> Response:
    frame = read_frame(_store(), _version(asset_id, version_id))
    if frame is None:
        raise HTTPException(404, "No simulation frame has been generated for this version.")
    return Response(frame[0], media_type="image/jpeg")


@app.get("/api/assets/{asset_id}/versions/{version_id}/files/{role}")
def asset_file(asset_id: str, version_id: str, role: str) -> Response:
    if role not in {"scenario", "road"}:
        raise HTTPException(404, "Unknown file role.")
    version = _version(asset_id, version_id)
    name = (version.xosc_name if role == "scenario" else version.xodr_name).rsplit("/", 1)[-1]
    return Response(_store().file_bytes(version, role), media_type="application/xml",
                    headers={"Content-Disposition": f'inline; filename="{name}"'})


# ---------- matching ----------

class MatchRequest(BaseModel):
    project_id: str
    document_id: str | None = None
    scene_id: str | None = None
    revision: int | None = None
    text: str = ""
    filters: dict[str, str] = Field(default_factory=dict)
    top_k: int = Field(8, ge=1, le=50)
    encoder: str | None = None
    lang: str = "en"


class DecisionRequest(MatchRequest):
    asset_id: str
    version_id: str


def _run(request: MatchRequest) -> tuple[StoredScene | None, list[RetrievalResult], dict, str]:
    catalog, versions = _catalog()
    stored = None
    if request.scene_id:
        if not request.document_id:
            raise ValueError("A scene needs its document ID.")
        stored = _scene(PdfStore(_store()), request.project_id, request.document_id,
                        request.scene_id, request.revision)
    query = scene_package_to_query(stored.package) if stored else None
    text = request.text.strip()
    if query and text and text not in query.text:
        query = replace(query, text=f"{query.text} {text}")
    if query is None and not text:
        raise ValueError("Select a scene or enter search text.")
    encoder = request.encoder or _preferred_encoder()
    if encoder not in {"bge", "hashing"}:
        raise ValueError("Unknown encoder.")
    results = _index(catalog, encoder).search(query.text if query else text, query=query,
                                              top_k=len(catalog)) if catalog else []
    return stored, results, versions, encoder


def _matches(asset: OpenXAsset, filters: dict[str, str]) -> bool:
    for key, wanted in filters.items():
        value = asset.classification.get(key)
        if wanted not in (value if isinstance(value, list) else [value]):
            return False
    return True


@app.post("/api/search")
def search(request: MatchRequest) -> dict[str, Any]:
    unknown = set(request.filters) - set(FACETS)
    if unknown:
        raise ValueError(f"Unknown filter: {', '.join(sorted(unknown))}.")
    stored, results, versions, encoder = _run(request)
    kept = [result for result in results if _matches(result.asset, request.filters)]
    return {"encoder": encoder, "total": len(kept), "library_size": len(results),
            "scene": _scene_json(stored) if stored else None,
            "results": [_candidate_json(result, versions.get(result.asset.asset_id), request.lang)
                        for result in kept[:request.top_k]]}


def _trace_for(request: DecisionRequest) -> tuple[dict, AssetVersion | None]:
    stored, results, versions, _ = _run(request)
    result = next((item for item in results
                   if (stored_version := versions.get(item.asset.asset_id)) is not None
                   and stored_version.asset_id == request.asset_id), None)
    version = versions.get(result.asset.asset_id) if result else None
    if result is None or version is None or version.version_id != request.version_id:
        raise ValueError("The selected asset version is no longer the latest in the library. Search again.")
    identity = ({"document_id": stored.document.document_id, "pdf_sha256": stored.document.sha256,
                 "scene_id": stored.scene_id, "revision": stored.revision} if stored else {})
    return build_trace(result, stored.package if stored else None, version, identity), version


@app.post("/api/trace")
def trace(request: DecisionRequest) -> dict[str, Any]:
    return _trace_for(request)[0]


@app.post("/api/decisions")
def save_decision(request: DecisionRequest) -> dict[str, Any]:
    if not request.scene_id:
        raise ValueError("Select a PDF scene before saving a reuse decision.")
    payload, version = _trace_for(request)
    if payload["reuse"]["level"] == "review":
        raise ValueError("Resolve the open review items before saving a reuse decision.")
    path = ProjectStore(_store()).save_decision(request.project_id, version, payload)
    return {"report_id": path.stem, "saved_to": str(path)}


@app.get("/api/projects/{project_id}/reports")
def reports(project_id: str) -> list[dict[str, Any]]:
    result = []
    for report in ProjectStore(_store()).reports(project_id):
        trace = report.get("trace") or {}
        source = trace.get("source") or {}
        result.append({**{key: report.get(key) for key in ("report_id", "saved_at", "asset_id", "version_id")},
                       "scene": {key: source.get(key) for key in ("title", "scene_id", "revision", "document_id")},
                       "level": (trace.get("reuse") or {}).get("level")})
    return result


if WEB_DIST.is_dir():
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=WEB_DIST, html=True), name="web")


def main() -> None:
    import argparse
    import uvicorn
    parser = argparse.ArgumentParser(description="Serve the workbench API (and the built web UI if present).")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run(app, host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
