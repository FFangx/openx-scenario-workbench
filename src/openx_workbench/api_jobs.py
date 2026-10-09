"""Background job routes and the uploads that start them.

Every long operation answers with a job snapshot at once; clients poll
`GET /api/jobs/{id}` and may `POST /api/jobs/{id}/cancel`.
"""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
from threading import Lock
from typing import Any, Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from . import import_jobs, jobs
from .api_schemas import Job, PendingClassification, documented
from .asset_store import AssetStore
from .catalog import AssetFile
from .classification import outdated, read_classification
from .pdf_store import PdfStore

router = APIRouter(prefix="/api", tags=["jobs"])

PDF_KIND = "pdf_import"
VARIANTS_KIND = "pdf_variants"
# PDFs extracted at once. Each one already sends its model calls together (Settings, concurrency)
# and may run OCR or the layout model locally.
PDFS_AT_ONCE = 3
ASSET_SUFFIXES = (".sim", ".xosc", ".xodr", ".zip")


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
def job_list(kind: Literal["pdf_import", "asset_import", "preview_batch"] | None = None) -> list[dict[str, Any]]:
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
        unique: dict[str, tuple[str, bytes]] = {}
        for name, data in files:  # the same file uploaded twice is one document, extracted once
            unique.setdefault(hashlib.sha256(data).hexdigest(), (name, data))
        several = len(unique) > 1
        imported: list[str | None] = [None] * len(unique)  # in upload order
        lock = Lock()
        job.update(stage="extracting", total=len(unique))

        def extracted() -> dict[str, Any]:
            return {"project_id": project_id, "document_ids": [item for item in imported if item]}

        def one(index: int, name: str, data: bytes) -> None:
            job.check()  # a stopped job starts no further PDF
            job.note(name)
            note = (lambda text: job.note(f"{name} · {text}")) if several else job.note
            document = pdf.import_pdf(project_id, name, data, standard, progress=note)
            with lock:
                imported[index] = document.document_id
                job.update(result=extracted())

        failures: list[str] = []
        with ThreadPoolExecutor(max_workers=min(PDFS_AT_ONCE, len(unique))) as pool:
            futures = {pool.submit(one, index, name, data): name for index, (name, data) in enumerate(unique.values())}
            for done, future in enumerate(as_completed(futures), 1):
                try:
                    future.result()
                except InterruptedError:
                    pass
                except Exception as error:  # noqa: BLE001 - one PDF failing leaves the others to finish
                    if not several:
                        raise
                    failures.append(f"{futures[future]}: {error}")
                job.update(done=done)
        job.check()
        if failures:
            raise ValueError("；".join(failures))  # the progress panel shows the error on one line
        return extracted()
    return work


def _start_extraction(pdf: PdfStore, project_id: str, files: list[tuple[str, bytes]], standard: str) -> dict[str, Any]:
    pdf.documents(project_id)  # rejects an unknown project before any work starts
    job = jobs.Job(PDF_KIND, str(pdf.root.resolve()), project=project_id)
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


def read_unread_variants(pdf: PdfStore | None = None, client=None) -> list[jobs.Job]:
    """Reads the test conditions of documents extracted before they were read, as the service starts:
    one background job per project, its documents one after another. Nothing is extracted again and no
    scene changes. Without a model key nothing starts; a scene no reading came back for is tried again
    at the next start."""
    from .llm_service import ModelClient, load_config
    pdf = pdf or PdfStore()
    client = client or ModelClient(load_config(pdf.root))
    if not client.config.api_key:
        return []
    started = []
    for project in pdf.projects.projects():
        documents = pdf.variants_unread(project.project_id)
        if not documents:
            continue

        def work(job: jobs.Job, documents=documents) -> dict[str, Any]:
            job.update(stage="reading", total=len(documents))
            for done, document in enumerate(documents, 1):
                job.check()
                job.note(document.filename)
                pdf.read_variants(document, client=client, progress=job.note)
                job.update(done=done)
            return {"document_ids": [document.document_id for document in documents]}

        job = jobs.Job(VARIANTS_KIND, str(pdf.root.resolve()) + "/" + project.project_id, project=project.project_id)
        started.append(jobs.start(job, work))
    return started


# ---------- asset import and labels ----------

@router.post("/assets/import", **documented(Job))
def import_assets(files: list[UploadFile] = File(...)) -> dict[str, Any]:
    uploads = _uploads(files, ASSET_SUFFIXES, "请选择 .sim、.xosc、.xodr 或 .zip 文件 / Select .sim, .xosc, .xodr or .zip files.")
    store = AssetStore()
    return import_jobs.start_import(store, [AssetFile(name, data) for name, data in uploads]).snapshot()


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
    pending = [version for version in store.versions() if outdated(read_classification(store, version))]
    return {"count": len(pending),
            "versions": [{"asset_id": item.asset_id, "version_id": item.version_id} for item in pending]}


@router.post("/assets/classify", **documented(Job))
def classify_assets(request: ClassifyRequest) -> dict[str, Any]:
    """Rule labels for the given versions, or every version whose labels are missing or outdated.

    Versions labelled by the current rules are skipped unless `force` is set; a reviewer's labels
    always stay final.
    """
    store = AssetStore()
    versions = store.versions()
    if request.versions is None:
        selected = [item for item in versions if outdated(read_classification(store, item))]
    else:
        wanted = {(item.asset_id, item.version_id) for item in request.versions}
        selected = [item for item in versions if (item.asset_id, item.version_id) in wanted]
        if len(selected) != len(wanted):
            raise HTTPException(404, "Unknown asset version.")
    if not selected:
        raise ValueError("没有需要更新标签的资产版本 / No asset versions need new labels.")
    return import_jobs.start_import(store, [], versions=selected, force=request.force).snapshot()
