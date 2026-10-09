"""Requirement ↔ asset binding routes: the model's suggestions for the PDFs a person selected, and the table
a person confirms.

`POST .../bindings/suggest` starts a background job (one per project) that ranks every scene's candidates
and asks the configured model about them, three times each at its deepest thinking; it sends the scenes'
source text and the candidates' stories to that model. Nothing enters the binding table until a person
confirms a row, and "accept all" leaves the scenes whose readings disagree to a person.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal
from urllib.parse import quote

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel, Field

from . import binding_export, jobs, matching
from .api_common import _catalog, _index, _store
from .api_schemas import AssetBinding, BindingCoverage, GroupBindings, Job, SavedExport, SceneBinding, documented
from .asset_store import AssetStore
from .atomic_write import write_bytes
from .binding_store import BindingStore, requirement_keys, scene_digest, section_of, stale_reasons
from .binding_suggest import Judge, judge_efforts, suggest_scenes
from .llm_service import ModelClient
from .pdf_store import PdfDocument, PdfStore, StoredScene
from .project_store import ProjectStore, folder_name

router = APIRouter(prefix="/api", tags=["bindings"])

KIND = "binding_suggest"
STATUS_OF = {"同一测试": "same", "同一测试但要改": "modify"}  # the model's bindable verdicts


def _scope(store: AssetStore, project_id: str) -> str:
    return f"{store.root.resolve()}|{project_id}"


class Group:
    """The selected PDFs of a project, their scenes in that order and each scene's requirement key."""

    def __init__(self, project_id: str, document_ids: list[str]):
        if not document_ids:
            raise ValueError("Select at least one PDF.")
        if len(set(document_ids)) != len(document_ids):
            raise ValueError("Select each PDF once.")
        self.pdf = PdfStore(_store())
        self.project_id = project_id
        known = {item.document_id: item for item in self.pdf.documents(project_id)}
        if any(item not in known for item in document_ids):
            raise HTTPException(404, "Unknown PDF document.")
        self.documents: list[PdfDocument] = [known[item] for item in document_ids]
        self.scenes: list[StoredScene] = []
        self.keys: dict[tuple[str, str], str] = {}
        for document in self.documents:
            scenes = self.pdf.scenes(project_id, document.document_id)
            self.scenes.extend(scenes)
            for scene_id, key in requirement_keys(self.pdf, project_id, document.document_id, scenes).items():
                self.keys[(document.document_id, scene_id)] = key

    def key(self, scene: StoredScene) -> str:
        return self.keys[(scene.document.document_id, scene.scene_id)]

    def scene(self, document_id: str, scene_id: str) -> StoredScene:
        scene = next((item for item in self.scenes
                      if item.document.document_id == document_id and item.scene_id == scene_id), None)
        if scene is None:
            raise HTTPException(404, "Unknown extracted scene.")
        return scene

    def select(self, refs: list[SceneRef] | None) -> list[StoredScene]:
        return self.scenes if refs is None else [self.scene(ref.document_id, ref.scene_id) for ref in refs]


def _latest(store: AssetStore) -> dict[str, Any]:
    return {version.asset_id: version for version in store.latest()}


def _is_latest(item: dict[str, Any], latest: dict[str, Any]) -> bool:
    version = latest.get(item["asset_id"])
    return version is not None and version.version_id == item["version_id"]


def _stable(suggestion: dict[str, Any]) -> bool | None:
    """Every reading (two at least) names the same preferred asset; None for a failed suggestion or one
    kept before readings were counted."""
    if suggestion.get("failure") or "readings" not in suggestion:
        return None
    return suggestion["readings"] >= 2 and suggestion["agree"] == suggestion["readings"]


def _suggestion_json(suggestion: dict[str, Any], scene: StoredScene, latest: dict[str, Any]) -> dict[str, Any]:
    """The suggestion, marked "scene" when the scene's facts changed since and "asset" when a candidate
    has a newer version: either way the model judged something that is no longer there."""
    candidates = [{**item, "latest": _is_latest(item, latest)} for item in suggestion["candidates"]]
    outdated = (["scene"] if suggestion["scene_digest"] != scene_digest(scene.package) else []) + (
        [] if all(item["latest"] for item in candidates) else ["asset"])
    return {key: suggestion[key] for key in ("created_at", "model", "binding", "preferred", "note", "failure")} | {
        "candidates": candidates, "outdated": outdated, "readings": suggestion.get("readings"),
        "agree": suggestion.get("agree"), "other_preferred": suggestion.get("other_preferred", []),
        "stable": _stable(suggestion), "recorded": bool(suggestion.get("recorded"))}


def _binding_json(entry: dict[str, Any], scene: StoredScene, latest: dict[str, Any]) -> dict[str, Any]:
    assets = [{**item, "latest": _is_latest(item, latest)} for item in entry["assets"]]
    requirement = entry["requirement"]
    return {"status": entry["status"], "changes": entry.get("changes", ""), "assets": assets,
            "source": entry["source"], "confirmed_at": entry["confirmed_at"],
            "stale": stale_reasons(entry, scene, latest),
            "confirmed_in": {key: requirement.get(key) for key in ("project_id", "document_id", "scene_id", "revision")}}


def _rows(group: Group, scenes: list[StoredScene]) -> list[dict[str, Any]]:
    """Each scene with the model's suggestion and the confirmed binding."""
    store = BindingStore(group.pdf.assets)
    latest = _latest(group.pdf.assets)
    entries = store.entries()
    suggestions = {document.sha256: store.suggestions(document.sha256) for document in {
        scene.document.document_id: scene.document for scene in scenes}.values()}
    rows = []
    for scene in scenes:
        key = group.key(scene)
        evidence = scene.package.evidence
        suggestion, entry = suggestions[scene.document.sha256].get(key), entries.get(key)
        rows.append({
            "document_id": scene.document.document_id, "filename": scene.document.filename,
            "scene_id": scene.scene_id, "revision": scene.revision, "title": scene.package.title,
            "section_id": section_of(scene.package), "key": key,
            "pages": [min(item.page_start for item in evidence), max(item.page_end for item in evidence)] if evidence else None,
            "suggestion": _suggestion_json(suggestion, scene, latest) if suggestion else None,
            "binding": _binding_json(entry, scene, latest) if entry else None,
        })
    return rows


def _view(group: Group) -> dict[str, Any]:
    job = jobs.latest(KIND, _scope(group.pdf.assets, group.project_id))
    return {"documents": [{"document_id": item.document_id, "filename": item.filename, "pdf_sha256": item.sha256}
                          for item in group.documents],
            "scenes": _rows(group, group.scenes), "job": job.snapshot() if job else None}


@router.get("/projects/{project_id}/bindings", **documented(GroupBindings))
def bindings(project_id: str, document_ids: list[str] = Query(description="The PDFs shown together, in this order.")
             ) -> dict[str, Any]:
    """Every scene of the selected PDFs with the model's suggestion and the confirmed binding, each marked
    when something changed since: the scene's facts, or a newer version of an asset it names."""
    return _view(Group(project_id, document_ids))


@router.get("/projects/{project_id}/bindings/export", response_class=Response)
def export(project_id: str, document_ids: list[str] = Query(description="The PDFs exported together, in this order."),
           format: Literal["csv", "html"] = "csv", lang: Literal["zh", "en"] = "zh") -> Response:
    """The reuse assessment of the selected PDFs as a file: every clause with the assets confirmed for reuse, or
    the model's suggestion while none is confirmed. CSV opens in a spreadsheet; HTML reads in a browser."""
    group = Group(project_id, document_ids)
    content = _export(group, format, lang)
    name = f"{_export_stem(group)}-reuse-assessment.{format}"
    media = "text/csv; charset=utf-8" if format == "csv" else "text/html; charset=utf-8"
    return Response(content, media_type=media,
                    headers={"Content-Disposition": f"attachment; filename=\"reuse-assessment.{format}\"; filename*=UTF-8''{quote(name)}"})


class ExportRequest(BaseModel):
    document_ids: list[str] = Field(description="The PDFs exported together, in this order.")
    format: Literal["csv", "html"] = "csv"
    lang: Literal["zh", "en"] = "zh"


@router.post("/projects/{project_id}/bindings/export", **documented(SavedExport))
def save_export(project_id: str, request: ExportRequest) -> dict[str, str]:
    """The same file as the download, saved in the project folder's exports folder, named with the time."""
    group = Group(project_id, request.document_ids)
    content = _export(group, request.format, request.lang)
    folder = ProjectStore(group.pdf.assets).exports(project_id, request.lang)
    label = "复用评估表" if request.lang == "zh" else "reuse assessment"
    path = folder / f"{_export_stem(group)} {label} {datetime.now().strftime('%Y-%m-%d %H%M')}.{request.format}"
    try:
        write_bytes(path, content, prefix="writing-", suffix=".tmp")
    except PermissionError:
        raise ValueError("同名文件正被其他程序打开（例如 Excel），请关闭后重试。/ "
                         "A file of that name is open in another program (such as Excel); close it and try again.") from None
    return {"filename": path.name, "path": str(path)}


def _export(group: Group, format: str, lang: str) -> bytes:
    lines = binding_export.table(_rows(group, group.scenes), lang)
    if format == "csv":
        return binding_export.to_csv(lines)
    return binding_export.to_html(lines, [item.filename for item in group.documents], lang)


def _export_stem(group: Group) -> str:
    stem = group.documents[0].filename.rsplit(".", 1)[0]
    return folder_name(stem + (f"+{len(group.documents) - 1}" if len(group.documents) > 1 else ""))


class SceneRef(BaseModel):
    document_id: str
    scene_id: str


class SuggestRequest(BaseModel):
    document_ids: list[str] = Field(description="The PDFs whose scenes are suggested for, in one job.")
    scenes: list[SceneRef] | None = Field(None, description="Only these scenes; every scene of the PDFs when omitted.")
    encoder: str | None = Field(None, description="Retrieval backend of the candidates; the preferred one when omitted.")


@router.post("/projects/{project_id}/bindings/suggest", **documented(Job))
def suggest(project_id: str, request: SuggestRequest) -> dict[str, Any]:
    """Asks the configured model which candidates build the same test as each scene, three times each at
    the deepest thinking effort the model declares. Sends the scenes' source text and extracted facts, and
    each candidate's name, story and differences, to that model."""
    group = Group(project_id, request.document_ids)
    scenes = group.select(request.scenes)
    if not scenes or not group.pdf.assets.latest():
        raise ValueError("生成复用建议需要资产和条款 / Suggestions need assets and clauses.")
    client = ModelClient()
    if not client.config.api_key:
        raise ValueError("生成复用建议需要配置模型。请先在设置中填写 Key / Configure a model in Settings first.")
    encoder = request.encoder or matching.preferred_encoder()
    if encoder not in matching.ENCODERS:
        raise ValueError("Unknown encoder.")

    def work(job: jobs.Job) -> dict[str, Any]:
        store = BindingStore(group.pdf.assets)
        job.update(stage="loading")
        efforts = judge_efforts(client)
        catalog, versions = _catalog()
        job.note(f"素材库 {len(catalog)} 个素材 · 建立检索索引")
        index = _index(catalog, encoder)  # texts new to the encoder are encoded first: minutes for BGE-M3 after a library change
        judge = Judge(client, group.pdf.assets.root / "model_cache", job.cancel, efforts)
        progress = {"ranked": 0, "judged": 0}
        job.update(stage="ranking", total=len(scenes), ranked=0)

        def ranked(scene: StoredScene) -> None:
            progress["ranked"] += 1
            job.update(ranked=progress["ranked"])
            if progress["ranked"] == len(scenes):
                job.update(stage="judging")
            job.note(f"候选 {progress['ranked']}/{len(scenes)} · {scene.package.title}")

        def judged(scene: StoredScene) -> None:
            progress["judged"] += 1
            job.update(done=progress["judged"])
            job.note(f"建议 {progress['judged']}/{len(scenes)} · {scene.package.title}")

        failed = suggest_scenes(
            scenes, index, versions, judge, client.config.concurrency, digest=scene_digest,
            save=lambda scene, record: store.save_suggestion(scene.document.sha256, group.key(scene), record),
            ranked=ranked, judged=judged)
        return {"project_id": project_id, "document_ids": request.document_ids, "failed": failed,
                "effort": efforts[0], "usage": dict(judge.spent)}

    job = jobs.Job(KIND, _scope(group.pdf.assets, project_id), project=project_id)
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


@router.put("/projects/{project_id}/documents/{document_id}/scenes/{scene_id}/binding", **documented(SceneBinding))
def confirm(project_id: str, document_id: str, scene_id: str, request: BindingRequest) -> dict[str, Any]:
    """Stores the person's binding of the scene, replacing an earlier one; the named versions are pinned.
    It counts as the accepted suggestion when it is exactly what the current suggestion proposed."""
    group = Group(project_id, [document_id])
    scene = group.scene(document_id, scene_id)
    store = BindingStore(group.pdf.assets)
    key = group.key(scene)
    suggestion = store.suggestions(scene.document.sha256).get(key)
    words = {(item["asset_id"], item["version_id"]): item for item in (suggestion or {}).get("candidates", [])}
    versions = {(item.asset_id, item.version_id): item for item in group.pdf.assets.versions()}
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
    proposal = _proposal(suggestion, scene, _latest(group.pdf.assets))
    accepted = proposal is not None and proposal[0] == request.status and proposal[2] == preferred and {
        (item["asset_id"], item["version_id"]) for item in proposal[1]} == {
        (item.asset_id, item.version_id) for item in request.assets}
    store.confirm(key, scene, request.status, chosen, changes=request.changes,
                  source="suggestion" if accepted else "manual")
    return _rows(group, [scene])[0]


@router.delete("/projects/{project_id}/documents/{document_id}/scenes/{scene_id}/binding", **documented(SceneBinding))
def unbind(project_id: str, document_id: str, scene_id: str) -> dict[str, Any]:
    """Removes the scene's confirmed binding and releases the versions it pinned."""
    group = Group(project_id, [document_id])
    scene = group.scene(document_id, scene_id)
    BindingStore(group.pdf.assets).remove(group.key(scene))
    return _rows(group, [scene])[0]


class AcceptRequest(BaseModel):
    document_ids: list[str] = Field(description="The PDFs shown together; the reply lists their scenes.")
    scenes: list[SceneRef] | None = Field(
        None, description="Accept these scenes' suggestions as they are, replacing a binding. When omitted: every "
                          "scene not bound yet whose suggestion prefers an asset the model judged the same test, "
                          "unless its readings disagree.")


@router.post("/projects/{project_id}/bindings/accept", **documented(GroupBindings))
def accept(project_id: str, request: AcceptRequest) -> dict[str, Any]:
    """Confirms current suggestions as proposed; outdated or failed suggestions are left alone, and so are
    unsettled ones (readings that disagree) unless the scenes are named."""
    group = Group(project_id, request.document_ids)
    store = BindingStore(group.pdf.assets)
    latest = _latest(group.pdf.assets)
    entries = store.entries()
    suggestions = {document.sha256: store.suggestions(document.sha256) for document in group.documents}
    selected = group.select(request.scenes) if request.scenes is not None else [
        scene for scene in group.scenes if group.key(scene) not in entries]
    versions = {(item.asset_id, item.version_id): item for item in group.pdf.assets.versions()}
    for scene in selected:
        suggestion = suggestions[scene.document.sha256].get(group.key(scene))
        proposal = _proposal(suggestion, scene, latest)
        if proposal is None:
            if request.scenes is not None:
                raise ValueError(f"{scene.package.title}: 建议已失效或未得到有效结果，请重新生成建议 / "
                                 "The suggestion is outdated or failed; ask again.")
            continue
        status, chosen, preferred = proposal
        if request.scenes is None and (status != "same" or _stable(suggestion) is False):
            continue
        assets = [{"version": versions[(item["asset_id"], item["version_id"])],
                   "preferred": item["asset_id"] == preferred, "verdict": item["verdict"],
                   "reason": item["reason"], "changes": item["changes"]} for item in chosen]
        changes = next((item["changes"] for item in chosen if item["asset_id"] == preferred), "")
        store.confirm(group.key(scene), scene, status, assets, changes=changes, source="suggestion")
    return _view(group)


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
