"""HTTP API for the React workbench: a thin layer over the stores and the matcher."""

from __future__ import annotations

import json
from dataclasses import asdict
from functools import lru_cache
from typing import Any
from urllib.parse import urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field

from . import matching
from .api_assets import router as assets_router
from .api_common import (FACETS, DecisionRequest, MatchRequest, _cache, _catalog, _lock, _matches, _run,
                         _scene_json, _candidate_json, _store, _trace_for, _version)
from .api_jobs import router as jobs_router
from .api_preview import router as preview_router
from .api_schemas import (Health, Library, Overview, PdfDocument, Project, ProjectList, Report, ReportDetail,
                          SavedDecision, SearchResponse, SelectedProject, Trace, documented)
from .api_settings import router as settings_router
from .api_workflow import router as workflow_router
from .checkout import checkout_root
from .pdf_store import PdfStore
from .preview_frames import read_frame
from .project_store import ProjectStore
from .report_html import render_report
from .reuse_trace import checked_trace, sign_off

LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1"}
WEB_DIST = checkout_root() / "web" / "dist"

app = FastAPI(title="OpenX Scenario Workbench API", version="0.1.0")


@app.exception_handler(ValueError)
async def _value_error(_: Request, error: ValueError) -> JSONResponse:
    return JSONResponse({"detail": str(error)}, status_code=400)


@app.middleware("http")
async def _this_machine_only(request: Request, call_next):
    """The service binds to loopback; also refuse other sites driving it through the user's browser.

    A foreign Host header means DNS rebinding; a foreign Origin on a write means a cross-site form or fetch.
    """
    host = urlsplit("//" + request.headers.get("host", "")).hostname
    origin = request.headers.get("origin")
    if host not in LOCAL_HOSTS or (request.method not in {"GET", "HEAD", "OPTIONS"} and origin
                                   and urlsplit(origin).hostname not in LOCAL_HOSTS):
        return JSONResponse({"detail": "Only pages served from this computer may use the workbench API."},
                            status_code=403)
    return await call_next(request)


app.include_router(assets_router)
app.include_router(jobs_router)
app.include_router(preview_router)
app.include_router(settings_router)
app.include_router(workflow_router)


@app.get("/api/health", **documented(Health))
def health() -> dict[str, str]:
    return {"status": "ok"}


# ---------- projects and documents ----------

@app.get("/api/projects", **documented(ProjectList))
def projects() -> dict[str, Any]:
    store = ProjectStore(_store())
    last = store.last()
    return {"projects": [asdict(item) for item in store.projects()],
            "last_project_id": last.project_id if last else None}


class ProjectRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)


@app.post("/api/projects", **documented(Project))
def create_project(request: ProjectRequest) -> dict[str, Any]:
    return asdict(ProjectStore(_store()).create(request.name))


@app.post("/api/projects/{project_id}/select", **documented(SelectedProject))
def select_project(project_id: str) -> dict[str, str]:
    ProjectStore(_store()).set_last(project_id)
    return {"project_id": project_id}


@app.get("/api/projects/{project_id}/documents", **documented(list[PdfDocument]))
def documents(project_id: str) -> list[dict[str, Any]]:
    pdf = PdfStore(_store())
    return [{**asdict(document), "size_bytes": (pdf.blobs / document.sha256).stat().st_size
             if (pdf.blobs / document.sha256).exists() else None}
            for document in pdf.documents(project_id)]


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

@app.get("/api/library", **documented(Library))
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
            "encoder": matching.preferred_encoder(), "facets": {key: sorted(values) for key, values in facets.items()}}


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

@app.post("/api/search", **documented(SearchResponse))
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


@app.post("/api/trace", **documented(Trace))
def trace(request: DecisionRequest) -> dict[str, Any]:
    return _trace_for(request)[0]


@app.post("/api/decisions", **documented(SavedDecision))
def save_decision(request: DecisionRequest) -> dict[str, Any]:
    if not request.scene_id:
        raise ValueError("Select a PDF scene before saving a reuse decision.")
    payload, version = _trace_for(request)
    payload = sign_off(payload, {item.item: item.reason for item in request.confirmations})
    path = ProjectStore(_store()).save_decision(request.project_id, version, payload)
    return {"report_id": path.stem, "saved_to": str(path)}


@app.get("/api/projects/{project_id}/reports", **documented(list[Report]))
def reports(project_id: str) -> list[dict[str, Any]]:
    result = []
    for report in ProjectStore(_store()).reports(project_id):
        trace = checked_trace(report.get("trace") or {})
        source = trace.get("source") or {}
        reuse = trace.get("reuse") or {}
        result.append({**{key: report.get(key) for key in ("report_id", "saved_at", "asset_id", "version_id")},
                       "kind": "batch" if trace.get("kind") == "batch_match" else "decision",
                       "scene": {key: source.get(key) for key in ("title", "scene_id", "revision", "document_id")},
                       "level": reuse.get("level"), "review_kind": reuse.get("review_kind") or "",
                       "signed_off": bool(reuse.get("review_signoff")),
                       "counts": trace.get("counts"), "scene_count": trace.get("scene_count")})
    return result


def _report(project_id: str, report_id: str) -> dict[str, Any]:
    report = next((item for item in ProjectStore(_store()).reports(project_id) if item["report_id"] == report_id), None)
    if report is None:
        raise HTTPException(404, "Unknown report.")
    return {**report, "trace": checked_trace(report["trace"])}


@app.get("/api/projects/{project_id}/reports/{report_id}", **documented(ReportDetail))
def report_detail(project_id: str, report_id: str) -> dict[str, Any]:
    """The saved snapshot, plus which of its source scenes still exist to reopen for review."""
    report = _report(project_id, report_id)
    trace = report["trace"]
    sources = [entry["source"] for entry in trace.get("entries", [])] if trace.get("kind") == "batch_match"         else [trace.get("source") or {}]
    pdf = PdfStore(_store())
    known = {document.document_id for document in pdf.documents(project_id)}
    existing = {(document_id, scene.scene_id) for document_id in {s.get("document_id") for s in sources} & known
                for scene in pdf.scenes(project_id, document_id)}
    return {**report, "reopenable": [{"document_id": d, "scene_id": s} for d, s in sorted(existing)
                                     if any(src.get("document_id") == d and src.get("scene_id") == s for src in sources)]}


@app.get("/api/projects/{project_id}/reports/{report_id}/download")
def report_download(project_id: str, report_id: str, format: str = "json", lang: str = "zh") -> Response:
    report = _report(project_id, report_id)
    stem = f"openx-{'batch' if report['trace'].get('kind') == 'batch_match' else 'decision'}-{report_id}"
    if format == "html":
        return Response(render_report(report["trace"], language="zh" if lang == "zh" else "en"), media_type="text/html",
                        headers={"Content-Disposition": f'attachment; filename="{stem}.html"'})
    if format != "json":
        raise HTTPException(400, "Unknown format.")
    return Response(json.dumps(report["trace"], ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": f'attachment; filename="{stem}.json"'})


@app.get("/api/overview", **documented(Overview))
def overview() -> dict[str, Any]:
    store = _store()
    versions = store.versions()
    latest = store.latest()
    recent = sorted(versions, key=lambda item: item.created_at, reverse=True)[:8]
    return {"assets": len(latest), "versions": len(versions),
            "playable": sum(item.compatibility == "playable" for item in latest),
            "unavailable": sum(item.compatibility in {"unsupported", "failed", "timeout"} for item in latest),
            "untested": sum(item.compatibility == "not_tested" for item in latest),
            "recent": [{key: getattr(item, key) for key in ("asset_id", "version_id", "title", "source_name",
                                                             "version_number", "compatibility", "created_at")}
                       for item in recent]}


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
