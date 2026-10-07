"""Process-owned import workers; UI reruns never own the operation."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
import time

from . import jobs, preview_batch
from .classification import classify_asset, read_classification
from .llm_service import ModelClient
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

    def work(self, files, classify, versions=None, client=None, force=False):
        imported = versions if versions is not None else self.store.import_files(
            files, progress=self.update, cancelled=self.cancel.is_set,
            report_sink=lambda report: self.update(reports=[*self.snapshot()["reports"], asdict(report)]))
        # Deduplicate repeated uploads before any model request.
        imported = list({(v.asset_id, v.version_id): v for v in imported}.values())
        self.update(stage="classifying", saved=len(imported), done=0, total=len(imported))
        if classify:
            client = client or ModelClient()
            client.config = replace(client.config, timeout=min(client.config.timeout, 90))
        consecutive_failures = 0
        for index, version in enumerate(imported):
            self.check()
            self.update(current=version.xosc_name, done=index)
            old = read_classification(self.store, version)
            if not force and (old.get("status") in {"classified", "manual_confirmed"} or (old and not classify)):
                record = old
            else:
                record = classify_asset(self.store, version, use_model=classify, client=client)
            failed = record.get("status") == "failed"
            consecutive_failures = consecutive_failures + 1 if failed else 0
            self.update(done=index + 1, failed=self.snapshot()["failed"] + int(failed),
                        error=record.get("error", "") if failed else self.snapshot()["error"])
            if classify and consecutive_failures >= 3:
                # ModelClient sanitizes remote failures; never persist raw request/config objects.
                raise ValueError("连续 3 个场景分类失败，已暂停模型请求。检查模型设置后可重试；资产已保留。 / Three consecutive classification failures; assets retained.")
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


def start_import(store, files, *, classify=False, versions=None, client=None, force=False):
    if not files and versions is None:
        raise ValueError("请先选择资产文件 / Select asset files first.")
    if jobs.running(KIND, _scope(store)):
        raise ValueError("已有导入任务正在运行 / An import is already running.")
    job = ImportJob(store)
    job.update()
    return jobs.start(job, lambda current: current.work(files, classify, versions, client, force))
