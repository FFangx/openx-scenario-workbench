"""Reentrant, cross-process guard for machine-local store mutations."""

from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

_registry_guard = threading.Lock()
_locks: dict[str, threading.RLock] = {}
_active = threading.local()


@contextmanager
def store_transaction(root: Path):
    root = root.resolve()
    key = os.path.normcase(str(root))
    with _registry_guard:
        lock = _locks.setdefault(key, threading.RLock())
    with lock:
        active = getattr(_active, "roots", set())
        if key in active:
            yield
            return
        root.mkdir(parents=True, exist_ok=True)
        with (root / ".store.lock").open("a+b") as handle:
            if os.name == "nt":
                import msvcrt
                import time

                # Windows permits locking beyond EOF. Writing a sentinel before
                # locking would itself race with another process's byte lock.
                deadline = time.monotonic() + 30
                while True:
                    handle.seek(0)
                    try:
                        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Local asset store is busy.")
                        time.sleep(0.05)
            else:
                import fcntl

                fcntl.flock(handle, fcntl.LOCK_EX)
            _active.roots = active | {key}
            try:
                yield
            finally:
                _active.roots = active
                if os.name == "nt":
                    handle.seek(0)
                    msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
                else:
                    fcntl.flock(handle, fcntl.LOCK_UN)


def serialized(method):
    @wraps(method)
    def guarded(self, *args, **kwargs):
        with store_transaction(self.root):
            return method(self, *args, **kwargs)

    return guarded
