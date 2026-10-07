"""Process-owned background jobs: submit, poll a snapshot, request a stop.

PDF extraction, asset import and model classification all outlive a single HTTP
request. Each runs in a daemon thread that owns its state; callers only read
snapshots and set the cancel flag, which the work checks between steps.
"""
from __future__ import annotations

from threading import Event, Lock, Thread
import time
from typing import Any, Callable
import uuid

MESSAGE_LIMIT = 200
FINISHED_LIMIT = 20
_jobs: dict[str, "Job"] = {}
_registry_lock = Lock()


class Job:
    def __init__(self, kind: str, scope: str = ""):
        self.kind = kind
        self.scope = scope
        self.lock = Lock()
        self.cancel = Event()
        self.state: dict[str, Any] = dict(
            id=uuid.uuid4().hex, kind=kind, status="running", stage="queued", current="",
            done=0, total=0, started=time.time(), updated=time.time(), error="", messages=[], result={})

    @property
    def id(self) -> str:
        return self.state["id"]

    def snapshot(self) -> dict[str, Any]:
        with self.lock:
            return {**self.state, "messages": list(self.state["messages"]), "cancelling": self.cancel.is_set()}

    def update(self, **values: Any) -> None:
        with self.lock:
            self.state.update(values, updated=time.time())

    def note(self, message: str) -> None:
        """Progress text from long steps; also the job's current activity."""
        with self.lock:
            self.state["messages"] = [*self.state["messages"], str(message)][-MESSAGE_LIMIT:]
            self.state.update(current=str(message), updated=time.time())

    def check(self) -> None:
        if self.cancel.is_set():
            raise InterruptedError()

    def run(self, work: Callable[["Job"], Any]) -> None:
        try:
            result = work(self)
            if result is not None:
                self.update(result=result)
            self.update(status="stopped" if self.cancel.is_set() else "completed", finished=time.time())
        except InterruptedError:
            self.update(status="stopped", finished=time.time())
        except Exception as exc:  # noqa: BLE001 - the job reports every failure to its poller
            self.update(status="failed", error=str(exc), finished=time.time())


def _running(kind: str, scope: str) -> Job | None:
    return next((job for job in _jobs.values() if job.kind == kind and job.scope == scope
                 and job.snapshot()["status"] == "running"), None)


def running(kind: str, scope: str = "") -> Job | None:
    with _registry_lock:
        return _running(kind, scope)


def start(job: Job, work: Callable[[Job], Any] | None = None) -> Job:
    """Register and start `job`; one running job per kind and scope."""
    with _registry_lock:
        if _running(job.kind, job.scope):
            raise ValueError("已有同类任务正在运行 / A job of this kind is already running.")
        _prune()
        _jobs[job.id] = job
        target = job.run if work is None else (lambda: job.run(work))
        Thread(target=target, daemon=True, name=f"openx-{job.kind}").start()
        return job


def get(job_id: str) -> Job | None:
    with _registry_lock:
        return _jobs.get(job_id)


def latest(kind: str, scope: str = "") -> Job | None:
    with _registry_lock:
        matches = [job for job in _jobs.values() if job.kind == kind and job.scope == scope]
    return max(matches, key=lambda job: job.state["started"], default=None)


def recent(kind: str | None = None, scope: str | None = None) -> list[dict[str, Any]]:
    with _registry_lock:
        matches = [job for job in _jobs.values()
                   if (kind is None or job.kind == kind) and (scope is None or job.scope == scope)]
    return sorted((job.snapshot() for job in matches), key=lambda state: state["started"], reverse=True)


def _prune() -> None:
    finished = sorted((job for job in _jobs.values() if job.snapshot()["status"] != "running"),
                      key=lambda job: job.state["started"])
    for job in finished[:max(0, len(finished) - FINISHED_LIMIT)]:
        del _jobs[job.id]
