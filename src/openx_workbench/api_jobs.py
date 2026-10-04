"""Background job routes and the uploads that start them.

Every long operation answers with a job snapshot at once; clients poll
`GET /api/jobs/{id}` and may `POST /api/jobs/{id}/cancel`.
"""

from __future__ import annotations

from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from . import import_jobs, jobs
from .api_schemas import Job, PendingClassification, documented
from .asset_store import AssetStore
from .catalog import AssetFile
from .classification import read_classification
from .pdf_store import PdfStore

router = APIRouter(prefix="/api", tags=["jobs"])

PDF_KIND = "pdf_import"
ASSET_SUFFIXES = (".sim", ".xosc", ".xodr", ".zip")
REVIEWED = {"classified", "manual_confirmed"}


class VersionRef(BaseModel):
    asset_id: str
    version_id: str


class ClassifyRequest(BaseModel):
    versions: list[VersionRef] | None = None
    force: bool = False


def _uploads(files: list[UploadFile], suffixes: tuple[str, ...], message: str) -> list[tuple[str, bytes]]:
    if not files:
        raise ValueError(message)
    named = [(upload.filename or "", upload) for upload in files]
    if any(not name.casefold().endswith(suffixes) for name, _ in named):
        raise ValueError(message)
    return [(name, upload.file.read()) for name, upload in named]


# ---------- jobs ----------

@router.get("/jobs", **documented(list[Job]))
def job_list(kind: Literal["pdf_import", "asset_import"] | None = None) -> list[dict[str, Any]]:
    store = AssetStore()
    result = jobs.recent(kind, str(store.root.resolve()))
    if kind in (None, import_jobs.KIND) and not any(item["kind"] == import_jobs.KIND for item in result):
        # A finished or interrupted import from an earlier service run.
        persisted = import_jobs.status(store)
        if persisted:
            result.append({**persisted, "kind": import_jobs.KIND, "messages": [], "result": {}, "cancelling": False})
    return result


def _job(job_id: str) -> jobs.Job:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(404, "Unknown or expired job.")
    return job


@router.get("/jobs/{job_id}", **documented(Job))
def job_status(job_id: str) -> dict[str, Any]:
    return _job(job_id).snapshot()


@router.post("/jobs/{job_id}/cancel", **documented(Job))
def job_cancel(job_id: str) -> dict[str, Any]:
    """Stops after the current step; work already saved is kept."""
    job = _job(job_id)
    job.cancel.set()
    return job.snapshot()


# ---------- PDF extraction ----------

def _extract(pdf: PdfStore, project_id: str, files: list[tuple[str, bytes]], standard: str):
    def work(job: jobs.Job) -> dict[str, Any]:
        imported: list[str] = []
        job.update(stage="extracting", total=len(files))
        for index, (name, data) in enumerate(files):
            job.check()
            job.update(done=index)
            job.note(name)
            document = pdf.import_pdf(project_id, name, data, standard, progress=job.note)
            imported.append(document.document_id)
            job.update(done=index + 1, result={"project_id": project_id, "document_ids": imported})
        return {"project_id": project_id, "document_ids": imported}
    return work


def _start_extraction(pdf: PdfStore, project_id: str, files: list[tuple[str, bytes]], standard: str) -> dict[str, Any]:
    pdf.documents(project_id)  # rejects an unknown project before any work starts
    job = jobs.Job(PDF_KIND, str(pdf.root.resolve()))
    return jobs.start(job, _extract(pdf, project_id, files, standard)).snapshot()


@router.post("/projects/{project_id}/documents", **documented(Job))
def import_pdfs(project_id: str, files: list[UploadFile] = File(...), standard: str = Form("")) -> dict[str, Any]:
    """Extracts scenes with the configured model; sends the PDF text to that model."""
    uploads = _uploads(files, (".pdf",), "请选择 PDF 文件 / Select PDF files.")
    return _start_extraction(PdfStore(), project_id, uploads, standard.strip())


@router.post("/projects/{project_id}/documents/{document_id}/reextract", **documented(Job))
def reextract_pdf(project_id: str, document_id: str) -> dict[str, Any]:
    pdf = PdfStore()
    document = next((item for item in pdf.documents(project_id) if item.document_id == document_id), None)
    if document is None:
        raise HTTPException(404, "Unknown PDF document.")
    return _start_extraction(pdf, project_id, [(document.filename, pdf.pdf_bytes(document))], document.source_standard)


# ---------- asset import and classification ----------

@router.post("/assets/import", **documented(Job))
def import_assets(files: list[UploadFile] = File(...), classify: bool = Form(False)) -> dict[str, Any]:
    uploads = _uploads(files, ASSET_SUFFIXES, "请选择 .sim、.xosc、.xodr 或 .zip 文件 / Select .sim, .xosc, .xodr or .zip files.")
    store = AssetStore()
    return import_jobs.start_import(store, [AssetFile(name, data) for name, data in uploads], classify=classify).snapshot()


@router.post("/assets/import/demo", **documented(Job))
def import_demo() -> dict[str, Any]:
    """Downloads the public esmini cut-in example, then imports it."""
    from .demo import DemoDownloadError, fetch_public_demo
    try:
        demo = fetch_public_demo()
    except DemoDownloadError as error:
        raise HTTPException(502, f"公开示例下载失败 / Could not download the public example: {error}") from None
    files = [AssetFile(demo.xosc_name, demo.xosc_data), AssetFile(demo.xodr_name, demo.xodr_data)]
    return import_jobs.start_import(AssetStore(), files).snapshot()


@router.get("/assets/classification/pending", **documented(PendingClassification))
def pending_classification() -> dict[str, Any]:
    store = AssetStore()
    pending = [version for version in store.versions()
               if read_classification(store, version).get("status") not in REVIEWED]
    return {"count": len(pending),
            "versions": [{"asset_id": item.asset_id, "version_id": item.version_id} for item in pending]}


@router.post("/assets/classify", **documented(Job))
def classify_assets(request: ClassifyRequest) -> dict[str, Any]:
    """Model classification for the given versions, or every version still awaiting review.

    Reviewed versions are skipped unless `force` is set.
    """
    store = AssetStore()
    versions = store.versions()
    if request.versions is None:
        selected = [item for item in versions if read_classification(store, item).get("status") not in REVIEWED]
    else:
        wanted = {(item.asset_id, item.version_id) for item in request.versions}
        selected = [item for item in versions if (item.asset_id, item.version_id) in wanted]
        if len(selected) != len(wanted):
            raise HTTPException(404, "Unknown asset version.")
    if not selected:
        raise ValueError("没有待分类的资产版本 / No asset versions need classification.")
    return import_jobs.start_import(store, [], classify=True, versions=selected, force=request.force).snapshot()
