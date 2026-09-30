"""Process-owned import workers; UI reruns never own the operation."""
from __future__ import annotations

from dataclasses import asdict, replace
import json
from threading import Event, Lock, Thread
import time
import uuid

from .asset_store import AssetStore
from .classification import classify_asset, read_classification
from .llm_service import ModelClient
from .pdf_store import PdfStore

_jobs = {}
_registry_lock = Lock()


class ImportJob:
    def __init__(self, store):
        self.store = store
        self.lock = Lock()
        self.cancel = Event()
        self.state = dict(id=uuid.uuid4().hex, status="running", stage="queued",
                          current="", done=0, total=0, saved=0, failed=0,
                          started=time.time(), updated=time.time(), error="", reports=[])

    def snapshot(self):
        with self.lock:
            return dict(self.state)

    def update(self, **values):
        with self.lock:
            self.state.update(values, updated=time.time())
            PdfStore._write_json(self.store.root / "import_status.json", self.state)

    def run(self, files, classify, versions=None, client=None, force=False):
        try:
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
                if self.cancel.is_set():
                    raise InterruptedError()
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
                    raise ValueError("连续 3 个场景分类失败，已暂停模型请求。检查模型设置后可重试；资产已保留。 / Three consecutive classification failures; assets retained.")
            self.update(status="stopped" if self.cancel.is_set() else "completed", finished=time.time())
        except InterruptedError:
            self.update(status="stopped", finished=time.time())
        except Exception as exc:
            # ModelClient sanitizes remote failures; never persist raw request/config objects.
            self.update(status="failed", error=str(exc), finished=time.time())


def current_job(store):
    with _registry_lock:
        return _jobs.get(str(store.root.resolve()))


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
    with _registry_lock:
        key = str(store.root.resolve())
        old = _jobs.get(key)
        if old and old.snapshot()["status"] == "running":
            raise ValueError("已有导入任务正在运行 / An import is already running.")
        job = ImportJob(store)
        job.update()
        _jobs[key] = job
        Thread(target=job.run, args=(files, classify, versions, client, force), daemon=True,
               name="openx-asset-import").start()
        return job
