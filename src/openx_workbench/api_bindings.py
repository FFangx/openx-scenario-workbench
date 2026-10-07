"""Requirement ↔ asset binding routes: the model's suggestions for a PDF, and the table a person confirms.

`POST .../bindings/suggest` starts a background job (one per PDF) that ranks every scene's candidates
and asks the configured model about them; it sends the scenes' source text and the candidates'
stories to that model. Nothing enters the binding table until a person confirms a row.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import jobs, matching
from .api_common import _catalog, _index, _store
from .api_schemas import AssetBinding, BindingCoverage, DocumentBindings, Job, documented
from .asset_store import AssetStore
from .binding_store import BindingStore, requirement_keys, scene_digest, section_of, stale_reasons
from .binding_suggest import Judge, suggest_scenes
from .llm_service import ModelClient
from .pdf_store import PdfDocument, PdfStore, StoredScene

router = APIRouter(prefix="/api", tags=["bindings"])

KIND = "binding_suggest"
STATUS_OF = {"同一测试": "same", "同一测试但要改": "modify"}  # the model's bindable verdicts


def _scope(store: AssetStore, project_id: str, document_id: str) -> str:
    return f"{store.root.resolve()}|{project_id}|{document_id}"


def _scenes(project_id: str, document_id: str) -> tuple[PdfStore, PdfDocument, list[StoredScene]]:
    pdf = PdfStore(_store())
    document = next((item for item in pdf.documents(project_id) if item.document_id == document_id), None)
    if document is None:
        raise HTTPException(404, "Unknown PDF document.")
    return pdf, document, pdf.scenes(project_id, document_id)


def _latest(store: AssetStore) -> dict[str, Any]:
    return {version.asset_id: version for version in store.latest()}


def _is_latest(item: dict[str, Any], latest: dict[str, Any]) -> bool:
    version = latest.get(item["asset_id"])
    return version is not None and version.version_id == item["version_id"]


def _suggestion_json(suggestion: dict[str, Any], scene: StoredScene, latest: dict[str, Any]) -> dict[str, Any]:
    """The suggestion, marked "scene" when the scene's facts changed since and "asset" when a candidate
    has a newer version: either way the model judged something that is no longer there."""
    candidates = [{**item, "latest": _is_latest(item, latest)} for item in suggestion["candidates"]]
    outdated = (["scene"] if suggestion["scene_digest"] != scene_digest(scene.package) else []) + (
        [] if all(item["latest"] for item in candidates) else ["asset"])
    return {key: suggestion[key] for key in ("created_at", "model", "binding", "preferred", "note", "failure")} | {
        "candidates": candidates, "outdated": outdated}


def _binding_json(entry: dict[str, Any], scene: StoredScene, latest: dict[str, Any]) -> dict[str, Any]:
    assets = [{**item, "latest": _is_latest(item, latest)} for item in entry["assets"]]
    requirement = entry["requirement"]
    return {"status": entry["status"], "changes": entry.get("changes", ""), "assets": assets,
            "source": entry["source"], "confirmed_at": entry["confirmed_at"],
            "stale": stale_reasons(entry, scene, latest),
            "confirmed_in": {key: requirement.get(key) for key in ("project_id", "document_id", "scene_id", "revision")}}


def _view(project_id: str, document_id: str) -> dict[str, Any]:
    pdf, document, scenes = _scenes(project_id, document_id)
    store = BindingStore(pdf.assets)
    keys = requirement_keys(pdf, project_id, document_id, scenes)
    latest = _latest(pdf.assets)
    entries = store.entries()
    suggestions = store.suggestions(document.sha256)
    rows = []
    for scene in scenes:
        key = keys[scene.scene_id]
        evidence = scene.package.evidence
        suggestion, entry = suggestions.get(key), entries.get(key)
        rows.append({
            "scene_id": scene.scene_id, "revision": scene.revision, "title": scene.package.title,
            "section_id": section_of(scene.package), "key": key,
            "pages": [min(item.page_start for item in evidence), max(item.page_end for item in evidence)] if evidence else None,
            "suggestion": _suggestion_json(suggestion, scene, latest) if suggestion else None,
            "binding": _binding_json(entry, scene, latest) if entry else None,
        })
    job = jobs.latest(KIND, _scope(pdf.assets, project_id, document_id))
    return {"document_id": document_id, "pdf_sha256": document.sha256, "scenes": rows,
            "job": job.snapshot() if job else None}


@router.get("/projects/{project_id}/documents/{document_id}/bindings", **documented(DocumentBindings))
def bindings(project_id: str, document_id: str) -> dict[str, Any]:
    """Every scene of the PDF with the model's suggestion and the confirmed binding, each marked when
    something changed since: the scene's facts, or a newer version of an asset it names."""
    return _view(project_id, document_id)


class SuggestRequest(BaseModel):
    scene_ids: list[str] | None = Field(None, description="Only these scenes; every scene of the PDF when omitted.")
    encoder: str | None = Field(None, description="Retrieval backend of the candidates; the preferred one when omitted.")


@router.post("/projects/{project_id}/documents/{document_id}/bindings/suggest", **documented(Job))
def suggest(project_id: str, document_id: str, request: SuggestRequest) -> dict[str, Any]:
    """Asks the configured model which candidates build the same test as each scene. Sends the scenes'
    source text and extracted facts, and each candidate's name, story and differences, to that model."""
    pdf, _, scenes = _scenes(project_id, document_id)
    if request.scene_ids is not None:
        wanted = set(request.scene_ids)
        scenes = [scene for scene in scenes if scene.scene_id in wanted]
        if len(scenes) != len(wanted):
            raise HTTPException(404, "Unknown extracted scene.")
    if not scenes or not pdf.assets.latest():
        raise ValueError("绑定建议需要资产和场景 / Suggestions need assets and scenes.")
    client = ModelClient()
    if not client.config.api_key:
        raise ValueError("绑定建议需要模型。请先在设置中填写 Key / Configure a model in Settings first.")
    encoder = request.encoder or matching.preferred_encoder()
    if encoder not in matching.ENCODERS:
        raise ValueError("Unknown encoder.")

    def work(job: jobs.Job) -> dict[str, Any]:
        store = BindingStore(pdf.assets)
        keys = requirement_keys(pdf, project_id, document_id, scenes)
        job.update(stage="ranking", total=len(scenes))
        catalog, versions = _catalog()
        index = _index(catalog, encoder)
        judge = Judge(client, pdf.assets.root / "model_cache", job.cancel)
        progress = {"ranked": 0, "judged": 0}

        def ranked(scene: StoredScene) -> None:
            progress["ranked"] += 1
            if progress["ranked"] == len(scenes):
                job.update(stage="judging")
            job.note(f"候选 {progress['ranked']}/{len(scenes)} · {scene.package.title}")

        def judged(scene: StoredScene) -> None:
            progress["judged"] += 1
            job.update(done=progress["judged"])
            job.note(f"建议 {progress['judged']}/{len(scenes)} · {scene.package.title}")

        failed = suggest_scenes(
            scenes, index, versions, judge, client.config.concurrency, digest=scene_digest,
            save=lambda scene, record: store.save_suggestion(scene.document.sha256, keys[scene.scene_id], record),
            ranked=ranked, judged=judged)
        return {"project_id": project_id, "document_ids": [document_id], "failed": failed, "usage": dict(judge.spent)}

    job = jobs.Job(KIND, _scope(pdf.assets, project_id, document_id))
    return jobs.start(job, work).snapshot()


class BoundAsset(BaseModel):
    asset_id: str
    version_id: str


class BindingRequest(BaseModel):
    status: Literal["same", "modify", "none"] = Field(
        description="same: the same test, at most other values; modify: the same test after the changes named; "
                    "none: no asset in the library builds it.")
    assets: list[BoundAsset] = Field(default_factory=list)
    preferred: str | None = Field(None, description="Asset ID of the preferred asset; the first one when omitted.")
    changes: str = Field("", max_length=2000)


def _scene(scenes: list[StoredScene], scene_id: str) -> StoredScene:
    scene = next((item for item in scenes if item.scene_id == scene_id), None)
    if scene is None:
        raise HTTPException(404, "Unknown extracted scene.")
    return scene


def _proposal(suggestion: dict[str, Any] | None, scene: StoredScene, latest: dict[str, Any]):
    """The suggestion as a binding (status, candidates, preferred id), or None when it is outdated or failed."""
    if not suggestion or suggestion.get("failure") or _suggestion_json(suggestion, scene, latest)["outdated"]:
        return None
    by_id = {item["id"]: item for item in suggestion["candidates"]}
    chosen = [by_id[key] for key in suggestion["binding"]]
    if not chosen:
        return "none", [], None
    preferred = by_id[suggestion["preferred"] or suggestion["binding"][0]]
    return STATUS_OF[preferred["verdict"]], chosen, preferred["asset_id"]


@router.put("/projects/{project_id}/documents/{document_id}/scenes/{scene_id}/binding", **documented(DocumentBindings))
def confirm(project_id: str, document_id: str, scene_id: str, request: BindingRequest) -> dict[str, Any]:
    """Stores the person's binding of the scene, replacing an earlier one; the named versions are pinned.
    It counts as the accepted suggestion when it is exactly what the current suggestion proposed."""
    pdf, document, scenes = _scenes(project_id, document_id)
    scene = _scene(scenes, scene_id)
    store = BindingStore(pdf.assets)
    key = requirement_keys(pdf, project_id, document_id, scenes)[scene_id]
    suggestion = store.suggestions(document.sha256).get(key)
    words = {(item["asset_id"], item["version_id"]): item for item in (suggestion or {}).get("candidates", [])}
    versions = {(item.asset_id, item.version_id): item for item in pdf.assets.versions()}
    preferred = request.preferred or (request.assets[0].asset_id if request.assets else None)
    chosen = []
    for item in request.assets:
        version = versions.get((item.asset_id, item.version_id))
        if version is None:
            raise HTTPException(404, "Unknown asset version.")
        said = words.get((item.asset_id, item.version_id), {})
        chosen.append({"version": version, "preferred": item.asset_id == preferred, "verdict": said.get("verdict"),
                       "reason": said.get("reason"), "changes": said.get("changes")})
    if request.assets and not any(item["preferred"] for item in chosen):
        raise ValueError("The preferred asset must be one of the bound assets.")
    proposal = _proposal(suggestion, scene, _latest(pdf.assets))
    accepted = proposal is not None and proposal[0] == request.status and proposal[2] == preferred and {
        (item["asset_id"], item["version_id"]) for item in proposal[1]} == {
        (item.asset_id, item.version_id) for item in request.assets}
    store.confirm(key, scene, request.status, chosen, changes=request.changes,
                  source="suggestion" if accepted else "manual")
    return _view(project_id, document_id)


@router.delete("/projects/{project_id}/documents/{document_id}/scenes/{scene_id}/binding", **documented(DocumentBindings))
def unbind(project_id: str, document_id: str, scene_id: str) -> dict[str, Any]:
    """Removes the scene's confirmed binding and releases the versions it pinned."""
    pdf, _, scenes = _scenes(project_id, document_id)
    _scene(scenes, scene_id)
    BindingStore(pdf.assets).remove(requirement_keys(pdf, project_id, document_id, scenes)[scene_id])
    return _view(project_id, document_id)


class AcceptRequest(BaseModel):
    scene_ids: list[str] | None = Field(
        None, description="Accept these scenes' suggestions as they are, replacing a binding. When omitted: every "
                          "scene not bound yet whose suggestion prefers an asset the model judged the same test.")


@router.post("/projects/{project_id}/documents/{document_id}/bindings/accept", **documented(DocumentBindings))
def accept(project_id: str, document_id: str, request: AcceptRequest) -> dict[str, Any]:
    """Confirms current suggestions as proposed; outdated or failed suggestions are left alone."""
    pdf, document, scenes = _scenes(project_id, document_id)
    store = BindingStore(pdf.assets)
    keys = requirement_keys(pdf, project_id, document_id, scenes)
    latest = _latest(pdf.assets)
    entries = store.entries()
    suggestions = store.suggestions(document.sha256)
    if request.scene_ids is not None:
        wanted = set(request.scene_ids)
        selected = [scene for scene in scenes if scene.scene_id in wanted]
        if len(selected) != len(wanted):
            raise HTTPException(404, "Unknown extracted scene.")
    else:
        selected = [scene for scene in scenes if keys[scene.scene_id] not in entries]
    versions = {(item.asset_id, item.version_id): item for item in pdf.assets.versions()}
    for scene in selected:
        proposal = _proposal(suggestions.get(keys[scene.scene_id]), scene, latest)
        if proposal is None:
            if request.scene_ids is not None:
                raise ValueError(f"{scene.package.title}: 建议已过期或失败，请重新建议 / "
                                 "The suggestion is outdated or failed; ask again.")
            continue
        status, chosen, preferred = proposal
        if request.scene_ids is None and status != "same":
            continue
        assets = [{"version": versions[(item["asset_id"], item["version_id"])],
                   "preferred": item["asset_id"] == preferred, "verdict": item["verdict"],
                   "reason": item["reason"], "changes": item["changes"]} for item in chosen]
        changes = next((item["changes"] for item in chosen if item["asset_id"] == preferred), "")
        store.confirm(keys[scene.scene_id], scene, status, assets, changes=changes, source="suggestion")
    return _view(project_id, document_id)


# ---------- reverse lookup and coverage ----------

def _current_scene(pdf: PdfStore, requirement: dict[str, Any]) -> StoredScene | None:
    """The latest revision of the scene a binding was confirmed for, when it is still there."""
    try:
        return pdf.revisions(requirement["project_id"], requirement["document_id"], requirement["scene_id"])[-1]
    except (ValueError, IndexError, KeyError, OSError):
        return None


@router.get("/assets/{asset_id}/bindings", **documented(list[AssetBinding]))
def asset_bindings(asset_id: str) -> list[dict[str, Any]]:
    """The requirement clauses bound to any version of the asset, across projects."""
    pdf = PdfStore(_store())
    latest = _latest(pdf.assets)
    rows = []
    for entry in BindingStore(pdf.assets).entries().values():
        item = next((asset for asset in entry["assets"] if asset["asset_id"] == asset_id), None)
        if item is None:
            continue
        requirement = entry["requirement"]
        rows.append({**{key: requirement.get(key) for key in (
            "filename", "standard", "section_id", "title", "project_id", "document_id", "scene_id")},
            "key": entry["key"], "status": entry["status"], "changes": entry.get("changes", ""),
            "preferred": item["preferred"], "group_size": len(entry["assets"]), "version_id": item["version_id"],
            "version_number": item["version_number"], "latest": _is_latest(item, latest),
            "stale": stale_reasons(entry, _current_scene(pdf, requirement), latest),
            "source": entry["source"], "confirmed_at": entry["confirmed_at"]})
    return sorted(rows, key=lambda row: (row["filename"] or "", row["section_id"] or "", row["title"] or ""))


@router.get("/projects/{project_id}/bindings/coverage", **documented(BindingCoverage))
def coverage(project_id: str) -> dict[str, Any]:
    """For every PDF of the project: which clauses have assets, which have none, which are not confirmed
    yet; and which assets of the library no clause of any project is bound to."""
    pdf = PdfStore(_store())
    store = BindingStore(pdf.assets)
    entries = store.entries()
    latest = _latest(pdf.assets)
    documents = []
    for document in pdf.documents(project_id):
        scenes = pdf.scenes(project_id, document.document_id)
        keys = requirement_keys(pdf, project_id, document.document_id, scenes)
        rows = []
        for scene in scenes:
            entry = entries.get(keys[scene.scene_id])
            rows.append({"scene_id": scene.scene_id, "section_id": section_of(scene.package), "title": scene.package.title,
                         "status": entry["status"] if entry else "unconfirmed",
                         "stale": bool(entry and stale_reasons(entry, scene, latest)),
                         "assets": [item["title"] for item in sorted(entry["assets"], key=lambda item: not item["preferred"])]
                         if entry else []})
        counts = {status: sum(row["status"] == status for row in rows) for status in ("same", "modify", "none", "unconfirmed")}
        documents.append({"document_id": document.document_id, "filename": document.filename,
                          "standard": document.source_standard, "scenes": rows,
                          "stale": sum(row["stale"] for row in rows), **counts})
    bound = {item["asset_id"] for entry in entries.values() for item in entry["assets"]}
    unused = sorted(({"asset_id": version.asset_id, "version_id": version.version_id, "title": version.title,
                      "source_name": version.source_name} for version in latest.values() if version.asset_id not in bound),
                    key=lambda item: (item["title"], item["source_name"]))
    return {"documents": documents, "asset_count": len(latest), "bound_asset_count": len(latest) - len(unused),
            "unused_assets": unused}
