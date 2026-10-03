import os
import subprocess
import sys
import threading
import time
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from openx_workbench.launcher import InstanceLock, Launcher, Service, send_control
from openx_workbench.windows_job import WindowsJob

pytestmark = pytest.mark.skipif(os.name != "nt", reason="Windows desktop lifecycle")


def test_single_instance_lock_recovers_after_release(tmp_path):
    first = InstanceLock(tmp_path / "instance.lock")
    second = InstanceLock(tmp_path / "instance.lock")
    try:
        assert first.acquire()
        assert not second.acquire()
        first.close()
        assert second.acquire()
    finally:
        first.close()
        second.close()


def test_owned_job_terminates_grandchild(tmp_path):
    pid_file = tmp_path / "child.pid"
    code = (
        "import subprocess,sys,time; from pathlib import Path; sys.stdin.readline(); "
        "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)']); "
        "Path(sys.argv[1]).write_text(str(p.pid)); time.sleep(60)"
    )
    job = WindowsJob()
    process = subprocess.Popen([sys.executable, "-c", code, str(pid_file)], stdin=subprocess.PIPE)
    import ctypes
    from ctypes import wintypes
    kernel = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    child_handle = None
    try:
        job.assign(process)
        process.stdin.write(b"start\n")
        process.stdin.close()
        deadline = time.monotonic() + 5
        while not pid_file.exists() and time.monotonic() < deadline:
            time.sleep(0.05)
        child_handle = kernel.OpenProcess(0x100000, False, int(pid_file.read_text()))
        assert child_handle
        assert kernel.WaitForSingleObject(child_handle, 0) == 258
        job.close()
        process.wait(timeout=5)
        assert kernel.WaitForSingleObject(child_handle, 5000) == 0
    finally:
        job.close()
        if child_handle:
            kernel.CloseHandle(child_handle)
        process.wait(timeout=5)


def test_real_service_health_restart_and_stop(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path / "data"))
    service = Service(tmp_path)
    try:
        for _ in range(2):
            previous = service.process
            service.start()
            if previous:
                assert previous.poll() is not None
            deadline = time.monotonic() + 20
            while not service.ready() and time.monotonic() < deadline:
                time.sleep(0.1)
            assert service.ready()
        process = service.process
        service.stop()
        assert process.poll() is not None
    finally:
        service.stop()


def test_real_web_service_serves_the_built_workbench(tmp_path, monkeypatch):
    from openx_workbench.launcher import web_available
    if not web_available():
        pytest.skip("web/dist is not built or the [web] extra is not installed")
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path / "data"))
    service = Service(tmp_path, "web")
    try:
        service.start()
        deadline = time.monotonic() + 30
        while not service.ready() and time.monotonic() < deadline:
            time.sleep(0.1)
        assert service.ready()
        with urlopen(service.url + "/", timeout=5) as response:
            assert b'<div id="root">' in response.read()
        with urlopen(service.url + "/api/projects", timeout=5) as response:
            assert response.status == 200
        assert (tmp_path / "web-service.log").exists()
    finally:
        service.stop()


def test_launcher_keeps_streamlit_as_classic_companion(tmp_path):
    launcher = Launcher(tmp_path, no_browser=True, ui="web")
    assert (launcher.service.kind, launcher.classic.kind) == ("web", "streamlit")
    single = Launcher(tmp_path, no_browser=True, ui="streamlit")
    assert single.classic is single.service
    with pytest.raises(ValueError):
        Service(tmp_path, "desktop")
    launcher.server.server_close()
    single.server.server_close()


def test_control_requires_token_and_duplicate_open_reuses_service(tmp_path, monkeypatch):
    monkeypatch.setenv("OPENX_DATA_DIR", str(tmp_path / "data"))
    revision = ["authored-v1"]
    monkeypatch.setattr("openx_workbench.launcher.source_revision", lambda: revision[0])
    launcher = Launcher(tmp_path, no_browser=True, ui="streamlit")
    thread = threading.Thread(target=launcher.run, kwargs={"headless": True})
    thread.start()
    try:
        deadline = time.monotonic() + 20
        while (launcher.service.process is None or not launcher.service.ready()) and time.monotonic() < deadline:
            time.sleep(0.1)
        assert launcher.service.ready()
        process = launcher.service.process
        launcher.open()
        assert launcher.service.process is process
        revision[0] = "authored-v2"
        launcher.open()
        assert process.poll() is not None
        assert launcher.service.process is not process
        process = launcher.service.process
        assert not launcher.service.needs_restart()
        url = f"http://127.0.0.1:{launcher.server.server_port}/stop"
        with pytest.raises(HTTPError) as error:
            urlopen(Request(url, data=b"", method="POST"), timeout=2)
        assert error.value.code == 403
        assert not launcher.done.is_set()
        assert send_control(tmp_path / "instance.json", "open")
        assert send_control(tmp_path / "instance.json", "stop")
        thread.join(timeout=10)
        assert not thread.is_alive()
        assert process.poll() is not None
        assert not (tmp_path / "instance.json").exists()
    finally:
        launcher.done.set()
        thread.join(timeout=10)
