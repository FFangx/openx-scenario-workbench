"""Process-owned import workers; UI reruns never own the operation."""
from __future__ import annotations

from dataclasses import asdict
import json
import time

from . import jobs, preview_batch
from .classification import classify_asset, outdated, read_classification
from .pdf_store import PdfStore
from .preferences import read_preferences

KIND = "asset_import"


class ImportJob(jobs.Job):
    def __init__(self, store):
        super().__init__(KIND, _scope(store))
        self.store = store
        self.state.update(saved=0, failed=0, reports=[])

    def update(self, **values):
        # Persisted so a restarted service can report the interruption.
        with self.lock:
            self.state.update(values, updated=time.time())
            PdfStore._write_json(self.store.root / "import_status.json", self.state)

    def work(self, files, versions=None, force=False):
        imported = versions if versions is not None else self.store.import_files(
            files, progress=self.update, cancelled=self.cancel.is_set,
            report_sink=lambda report: self.update(reports=[*self.snapshot()["reports"], asdict(report)]))
        imported = list({(v.asset_id, v.version_id): v for v in imported}.values())
        self.update(stage="classifying", saved=len(imported), done=0, total=len(imported))
        failed = 0
        for done, version in enumerate(imported, 1):
            self.check()
            self.update(current=version.xosc_name)
            if force or outdated(read_classification(self.store, version)):
                try:
                    classify_asset(self.store, version)
                except Exception as error:  # noqa: BLE001 - one unreadable version keeps its assets and the rest
                    failed += 1
                    self.update(failed=failed, error=f"{version.xosc_name}: {error}")
            self.update(done=done)
        # The setting "make previews after an import"; a preview run already going is left to finish.
        if (versions is None and imported and read_preferences().get("auto_preview") is True
                and not jobs.running(preview_batch.KIND, _scope(self.store))):
            preview_batch.start(self.store)
            self.note("已开始生成预览 / Making previews")
        return {"versions": [{"asset_id": v.asset_id, "version_id": v.version_id} for v in imported]}


def _scope(store):
    return str(store.root.resolve())


def current_job(store):
    return jobs.latest(KIND, _scope(store))


def status(store):
    job = current_job(store)
    if job:
        return job.snapshot()
    path = store.root / "import_status.json"
    if not path.exists():
        return None
    result = json.loads(path.read_text(encoding="utf-8"))
    if result["status"] == "running":
        result.update(status="interrupted", error="服务重启中断了任务；已保存的资产仍可使用。 / Service restarted; saved assets retained.")
    return result


def start_import(store, files, *, versions=None, force=False):
    """Imports `files` and labels the new versions; with `versions`, labels those again instead."""
    if not files and versions is None:
        raise ValueError("请先选择资产文件 / Select asset files first.")
    if jobs.running(KIND, _scope(store)):
        raise ValueError("已有导入任务正在运行 / An import is already running.")
    job = ImportJob(store)
    job.update()
    return jobs.start(job, lambda current: current.work(files, versions, force))
