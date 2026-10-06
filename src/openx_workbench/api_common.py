"""State and serializers shared by the API routers (kept free of FastAPI app wiring)."""

from __future__ import annotations

import threading
from dataclasses import asdict
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, Field

from . import matching
from .asset_store import AssetStore, AssetVersion
from .catalog import OpenXAsset
from .pdf_store import PdfStore, StoredScene
from .presentation import asset_display_title, difference_text, display
from .preview_frames import read_frame
from .retrieval import OpenXIndex, RetrievalResult, catalog_fingerprint
from .reuse_trace import review_items
from .schema_validation import registry_stamp

FACETS = ("function_type", "label_road_type", "label_target_type")
RANKINGS_KEPT = 16
_lock = threading.Lock()  # guards _cache; never held while an index is built
_index_build = threading.Lock()  # one index build at a time
_cache: dict[str, Any] = {}


# ---------- shared state ----------

def _store() -> AssetStore:
    return AssetStore()


def _classification_stamp(store: AssetStore, version: AssetVersion) -> int:
    path = store.root / "assets" / version.asset_id / version.version_id / "classification.json"
    try:
        return path.stat().st_mtime_ns
    except OSError:
        return 0


def _catalog() -> tuple[list[OpenXAsset], dict[str, AssetVersion]]:
    """The latest version of every asset, as `AssetStore.catalog` returns it.

    A version's scenario and road never change, so each is parsed once and reparsed only when its
    classification, its SIM case metadata (refreshed by a re-import) or the installed XSD registry does.
    The catalog fingerprint is computed once per change, not per request.
    """
    store = _store()
    latest = store.latest()
    stamps = [(_classification_stamp(store, version),
               tuple(record["sha256"] for record in version.files if record["role"] == "case"))
              for version in latest]
    schemas = registry_stamp()
    key = (schemas, tuple(sorted((version.version_id, version.compatibility, stamp)
                                 for version, stamp in zip(latest, stamps))))
    with _lock:
        if _cache.get("catalog_key") != key:
            parsed = _cache.get("parsed", {})
            fresh = {}
            for version, stamp in zip(latest, stamps):
                identity = (version.asset_id, version.version_id, stamp, schemas)
                fresh[identity] = parsed.get(identity) or store.load_asset(version)
            assets = list(fresh.values())
            _cache.update(parsed=fresh, catalog_key=key, catalog=(assets, {
                asset.asset_id: version for asset, version in zip(assets, latest)}),
                catalog_fingerprint=catalog_fingerprint(assets))
        return _cache["catalog"]


def _fingerprint(catalog: list[OpenXAsset]) -> str:
    with _lock:
        cached = _cache.get("catalog")
        if cached is not None and cached[0] is catalog:
            return _cache["catalog_fingerprint"]
    return catalog_fingerprint(catalog)


def _index(catalog: list[OpenXAsset], encoder_name: str) -> OpenXIndex:
    """The index for this catalog and encoder. A build (minutes for BGE-M3 on a large library) holds only
    `_index_build`, so requests that need no new index are still served meanwhile."""
    identity = matching.index_identity(catalog, encoder_name, _fingerprint(catalog))
    with _lock:
        if _cache.get("index_identity") == identity:
            return _cache["index"]
    with _index_build:
        with _lock:
            if _cache.get("index_identity") == identity:
                return _cache["index"]
        index = matching.open_index(catalog, identity)
        with _lock:
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
        "document_id": stored.document.document_id, "structure": package.structure,
        "triggers": package.triggers, "weather": package.weather, "time_of_day": package.time_of_day,
        "parameters": package.parameters,
        "issues": [issue.get("detail") or issue.get("code", "")
                   for issue in package.extraction.get("validation", {}).get("issues", [])]
        + [flag["detail"] for flag in package.extraction.get("structure_flags", [])],
        "ocr": any(block.get("source") == "ocr" for block in package.extraction.get("source_blocks", [])),
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
        "review_items": review_items({"level": result.confirmation_level, "structural_level": result.reuse_level,
                                      "differences": [asdict(item) for item in result.differences]}),
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
                 "revision": road.revision, "file_missing": road.file_missing,
                 "inferred_features": road.inferred_features,
                 "lanes_same_direction": road.lanes_same_direction, "lanes_total": road.lanes_total,
                 "lane_markings": road.lane_markings},
        "has_frame": bool(version and read_frame(_store(), version)),
    }


def _version(asset_id: str, version_id: str) -> AssetVersion:
    version = next((item for item in _store().versions()
                    if item.asset_id == asset_id and item.version_id == version_id), None)
    if version is None:
        raise HTTPException(404, "Unknown asset version.")
    return version


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


class ReviewConfirmation(BaseModel):
    item: str = Field(description="A review item ID from the candidate's review_items.")
    reason: str = Field(max_length=2000)


class DecisionRequest(MatchRequest):
    asset_id: str
    version_id: str
    explanation_id: str | None = None
    confirmations: list[ReviewConfirmation] = Field(default_factory=list,
                                                     description="Only when saving a decision that needs review.")


def _run(request: MatchRequest) -> tuple[StoredScene | None, list[RetrievalResult], dict, str]:
    catalog, versions = _catalog()
    stored = None
    if request.scene_id:
        if not request.document_id:
            raise ValueError("A scene needs its document ID.")
        stored = _scene(PdfStore(_store()), request.project_id, request.document_id,
                        request.scene_id, request.revision)
    query = matching.scene_query(stored.package if stored else None, request.text, skip_contained=True)
    if query is None and not request.text.strip():
        raise ValueError("Select a scene or enter search text.")
    encoder = request.encoder or matching.preferred_encoder()
    if encoder not in matching.ENCODERS:
        raise ValueError("Unknown encoder.")
    results = _ranking(_index(catalog, encoder), query, request.text) if catalog else []
    return stored, results, versions, encoder


def _ranking(index: OpenXIndex, query, text: str) -> list[RetrievalResult]:
    """The whole library ranked for `query`, kept so the assessment, report and decision of a candidate
    reuse the ranking its search produced instead of ranking the library again."""
    key = (index.encoder.encoder_id, index.fingerprint, query, text)
    with _lock:
        rankings = _cache.setdefault("rankings", {})
        if key in rankings:
            rankings[key] = rankings.pop(key)  # most recently used last
            return rankings[key]
    results = matching.search(index, query, text, top_k=len(index.assets))
    with _lock:
        rankings[key] = results
        while len(rankings) > RANKINGS_KEPT:
            rankings.pop(next(iter(rankings)))
    return results


def _matches(asset: OpenXAsset, filters: dict[str, str]) -> bool:
    for key, wanted in filters.items():
        value = asset.classification.get(key)
        if wanted not in (value if isinstance(value, list) else [value]):
            return False
    return True


def _candidate_for(request: DecisionRequest) -> tuple[StoredScene | None, RetrievalResult, AssetVersion]:
    """The ranked result for the requested asset, checked to still be its latest version."""
    stored, results, versions, _ = _run(request)
    result = next((item for item in results
                   if (stored_version := versions.get(item.asset.asset_id)) is not None
                   and stored_version.asset_id == request.asset_id), None)
    version = versions.get(result.asset.asset_id) if result else None
    if result is None or version is None or version.version_id != request.version_id:
        raise ValueError("The selected asset version is no longer the latest in the library. Search again.")
    return stored, result, version


def _trace_for(request: DecisionRequest) -> tuple[dict, AssetVersion | None]:
    stored, result, version = _candidate_for(request)
    trace = matching.assessment_trace(result, stored.package if stored else None, version, stored)
    explanation = _cache.get("explanations", {}).get(request.explanation_id or "")
    if explanation and explanation["key"] == _explanation_key(request):
        # An explanation the user generated for this exact assessment travels with its exports.
        trace["explanation"] = explanation["explanation"]
    return trace, version


def _explanation_key(request: DecisionRequest) -> tuple:
    return (request.project_id, request.document_id, request.scene_id, request.revision,
            request.asset_id, request.version_id, request.lang)
