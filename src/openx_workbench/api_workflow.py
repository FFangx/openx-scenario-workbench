"""PDF requirement workflow routes: scene queue, fact revisions, publication, extraction
records, whole-document matching, assessment reports and grounded explanations."""

from __future__ import annotations

from dataclasses import asdict
import json
from typing import Any, Literal, get_args
import uuid

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import matching
from .api_common import (DecisionRequest, _cache, _candidate_for, _catalog, _explanation_key, _index, _lock,
                         _scene, _scene_json, _store, _trace_for)
from .api_schemas import (BatchResult, Explanation, ExtractionRecord, Publication, QueuedScene, Revision, SavedBatch,
                          SceneSchema, documented)
from .batch_matching import batch_signature, match_documents
from .pdf_store import PdfStore, StoredScene
from .project_store import ProjectStore
from .report_html import render_report
from .reuse_trace import checked_trace

router = APIRouter(prefix="/api", tags=["workflow"])
BATCH_LIMIT = 8


def _document(pdf: PdfStore, project_id: str, document_id: str):
    document = next((item for item in pdf.documents(project_id) if item.document_id == document_id), None)
    if document is None:
        raise HTTPException(404, "Unknown PDF document.")
    return document


def _queue(pdf: PdfStore, project_id: str, scenes: list[StoredScene]) -> list[dict[str, Any]]:
    """Scenes with their queue state: assessment saved, revision confirmed, or still to review."""
    published = {(item["document_id"], item["scene_id"], item["revision"])
                 for item in pdf.library() if item["project_id"] == project_id}
    assessed = {(source.get("document_id"), source.get("scene_id"), source.get("revision"))
                for report in ProjectStore(pdf.assets).reports(project_id)
                for source in [report.get("trace", {}).get("source") or {}]}
    result = []
    for stored in scenes:
        key = (stored.document.document_id, stored.scene_id, stored.revision)
        result.append({**_scene_json(stored), "published": key in published,
                       "queue_status": "assessed" if key in assessed else "confirmed" if key in published else "pending"})
    return result


# ---------- scene queue ----------

@router.get("/scene-schema", **documented(SceneSchema))
def scene_schema() -> dict[str, list[str]]:
    """Controlled vocabulary for the typed requirement editor."""
    from .pdf_v2 import scene_schemas as schema
    fields = {"road_class": schema.RoadClass, "tested_function": schema.TestedFunction, "test_intent": schema.TestIntent,
              "ego_actions": schema.EgoAction, "semantic_triggers": schema.SemanticTrigger, "weather": schema.Weather,
              "time_of_day": schema.TimeOfDay, "participant_kind": schema.ParticipantKind, "bearing": schema.Bearing,
              "facing": schema.Facing, "participant_actions": schema.ParticipantAction, "age": schema.PedestrianAge,
              "ego_turn": schema.EgoTurn, "traffic_controls": schema.TrafficControl, "ego_lane": schema.EgoLane}
    return {key: list(get_args(annotation)) for key, annotation in fields.items()}


@router.get("/projects/{project_id}/documents/{document_id}/scenes", **documented(list[QueuedScene]))
def scenes(project_id: str, document_id: str) -> list[dict[str, Any]]:
    pdf = PdfStore(_store())
    return _queue(pdf, project_id, pdf.scenes(project_id, document_id))


@router.get("/projects/{project_id}/scenes", **documented(list[QueuedScene]))
def all_scenes(project_id: str) -> list[dict[str, Any]]:
    """Every scene of every PDF in the project, newest PDF first."""
    pdf = PdfStore(_store())
    return _queue(pdf, project_id, pdf.all_scenes(project_id))


class RevisionRequest(BaseModel):
    edits: dict[str, Any] = Field(description="Only extracted facts: title, preferred_text, structure, or the legacy fields.")


@router.post("/projects/{project_id}/documents/{document_id}/scenes/{scene_id}/revisions", **documented(QueuedScene))
def revise(project_id: str, document_id: str, scene_id: str, request: RevisionRequest) -> dict[str, Any]:
    """Saves edited facts as a new immutable revision; matching then uses it."""
    pdf = PdfStore(_store())
    stored = pdf.revise_scene(project_id, document_id, scene_id, request.edits)
    return _queue(pdf, project_id, [stored])[0]


@router.get("/projects/{project_id}/documents/{document_id}/scenes/{scene_id}/revisions", **documented(list[Revision]))
def revisions(project_id: str, document_id: str, scene_id: str) -> list[dict[str, Any]]:
    return [{"revision": item.revision, "title": item.package.title, "parameters": item.package.parameters,
             "structure": item.package.structure}
            for item in PdfStore(_store()).revisions(project_id, document_id, scene_id)]


class PublishRequest(BaseModel):
    revision: int


@router.post("/projects/{project_id}/documents/{document_id}/scenes/{scene_id}/publish", **documented(Publication))
def publish(project_id: str, document_id: str, scene_id: str, request: PublishRequest) -> dict[str, Any]:
    """Confirms a saved revision into the shared requirement library."""
    pdf = PdfStore(_store())
    record = pdf.publish_scene(_scene(pdf, project_id, document_id, scene_id, request.revision))
    return {key: record[key] for key in ("library_id", "revision", "reviewed_at")}


# ---------- extraction record ----------

@router.get("/projects/{project_id}/documents/{document_id}/extraction", **documented(ExtractionRecord))
def extraction(project_id: str, document_id: str) -> dict[str, Any]:
    from .pdf_extraction import ENGINE_VERSION
    pdf = PdfStore(_store())
    document = _document(pdf, project_id, document_id)
    audit = pdf.extraction_audit(document)
    issues = (audit.get("structure_quality") or {}).get("issues", []) + ((audit.get("run") or {}).get("validation") or {}).get("issues", [])
    return {"engine": document.extraction_engine, "current_engine": ENGINE_VERSION,
            "outdated": document.extraction_engine != ENGINE_VERSION, "has_record": bool(audit),
            "model": (audit.get("run") or {}).get("model"),
            "issues": [issue.get("detail") or issue.get("message") or issue.get("code", "") for issue in issues],
            "flags": [f"P{flag['page_number']}: {flag['detail']}" for flag in audit.get("structure_flags", [])],
            "ocr": bool(audit.get("preprocessing"))}


@router.get("/projects/{project_id}/documents/{document_id}/extraction/download")
def extraction_download(project_id: str, document_id: str) -> Response:
    pdf = PdfStore(_store())
    audit = pdf.extraction_audit(_document(pdf, project_id, document_id))
    if not audit:
        raise HTTPException(404, "No extraction record for this document.")
    return Response(json.dumps(audit, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="extraction.json"'})


# ---------- whole-document matching ----------

class BatchRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, description="The PDFs matched together, in this order.")
    encoder: str | None = None


def _batch(project_id: str, document_ids: list[str], encoder: str | None) -> tuple[dict, str]:
    pdf = PdfStore(_store())
    if len(set(document_ids)) != len(document_ids):
        raise ValueError("Select each PDF once.")
    documents = [_document(pdf, project_id, document_id) for document_id in document_ids]
    scenes = [scene for document in documents for scene in pdf.scenes(project_id, document.document_id)]
    catalog, versions = _catalog()
    encoder = encoder or matching.preferred_encoder()
    if encoder not in matching.ENCODERS:
        raise ValueError("Unknown encoder.")
    if not catalog or not scenes:
        raise ValueError("批量匹配需要资产和场景 / Matching needs assets and scenes.")
    index = _index(catalog, encoder)
    signature = batch_signature(documents, scenes, index.fingerprint, versions, index.encoder.encoder_id)
    return {"documents": documents, "scenes": scenes, "index": index, "versions": versions, "encoder": encoder}, signature


def _cached_batch(project_id: str, signature: str) -> dict:
    entry = _cache.get("batches", {}).get(signature)
    if entry is None or entry["project_id"] != project_id:
        raise HTTPException(404, "This summary has expired. Match the PDFs again.")
    return entry


@router.post("/projects/{project_id}/batch", **documented(BatchResult))
def batch(project_id: str, request: BatchRequest) -> dict[str, Any]:
    """Matches every scene of the selected PDFs against the current library in one summary; the result is
    kept for saving and download."""
    inputs, _ = _batch(project_id, request.document_ids, request.encoder)
    trace = match_documents(inputs["documents"], inputs["scenes"], inputs["index"], inputs["versions"])
    with _lock:
        cache = _cache.setdefault("batches", {})
        cache[trace["signature"]] = {"trace": trace, "encoder": inputs["encoder"], "project_id": project_id,
                                     "document_ids": request.document_ids}
        while len(cache) > BATCH_LIMIT:
            cache.pop(next(iter(cache)))
    return {"signature": trace["signature"], "trace": checked_trace(trace)}


class BatchSaveRequest(BaseModel):
    signature: str


@router.post("/projects/{project_id}/batch/save", **documented(SavedBatch))
def batch_save(project_id: str, request: BatchSaveRequest) -> dict[str, str]:
    entry = _cached_batch(project_id, request.signature)
    _, current = _batch(project_id, entry["document_ids"], entry["encoder"])
    if current != request.signature:
        raise ValueError("场景、资产或编码器已改变，请重新匹配 / Scenes, assets or encoder changed. Match again.")
    path = ProjectStore(_store()).save_batch(project_id, entry["trace"])
    return {"report_id": path.stem}


@router.get("/projects/{project_id}/batch/{signature}/download")
def batch_download(project_id: str, signature: str, format: Literal["json", "html"] = "json",
                   lang: str = "zh") -> Response:
    trace = _cached_batch(project_id, signature)["trace"]
    if format == "html":
        return Response(render_report(trace, language="zh" if lang == "zh" else "en"), media_type="text/html",
                        headers={"Content-Disposition": 'attachment; filename="openx-document.html"'})
    return Response(json.dumps(trace, ensure_ascii=False, indent=2), media_type="application/json",
                    headers={"Content-Disposition": 'attachment; filename="openx-document.json"'})


# ---------- assessment report and explanation ----------

@router.post("/trace/report")
def trace_report(request: DecisionRequest) -> Response:
    """The current assessment as a self-contained HTML report."""
    trace, _ = _trace_for(request)
    return Response(render_report(trace, language="zh" if request.lang == "zh" else "en"), media_type="text/html",
                    headers={"Content-Disposition": 'attachment; filename="openx-reuse-report.html"'})


class ExplanationRequest(DecisionRequest):
    mode: Literal["evidence", "structural", "model"] = "evidence"


@router.post("/explanation", **documented(Explanation))
def explanation(request: ExplanationRequest) -> dict[str, Any]:
    """`evidence` lists exactly what a model request would send; `structural` explains from the
    comparison alone; `model` sends that evidence to the configured model and validates its citations."""
    from .grounding import deterministic_explanation, model_explanation
    stored, result, version = _candidate_for(request)
    if stored is None:
        raise ValueError("Select a PDF scene to explain an assessment.")
    baseline = deterministic_explanation(stored.package, result, version)
    payload: dict[str, Any] = {"evidence": [asdict(item) for item in baseline.evidence],
                               "insufficient": list(baseline.insufficient_evidence)}
    if request.mode == "evidence" or baseline.insufficient_evidence:
        return payload
    if request.mode == "model":
        try:
            explained = model_explanation(stored.package, result, version, language=request.lang)
        except RuntimeError as error:
            raise ValueError(str(error)) from None
    else:
        explained = baseline
    explanation_id = uuid.uuid4().hex
    with _lock:
        cache = _cache.setdefault("explanations", {})
        cache[explanation_id] = {"key": _explanation_key(request), "explanation": asdict(explained)}
        while len(cache) > 32:
            cache.pop(next(iter(cache)))
    return {**payload, "explanation_id": explanation_id, "explanation": asdict(explained)}
