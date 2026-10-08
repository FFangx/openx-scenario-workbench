"""Launch an isolated, localhost-only esmini RAM-frame preview worker."""

from __future__ import annotations

import ctypes
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.request import urlopen
from xml.etree import ElementTree as ET

from .asset_store import AssetStore, AssetVersion
from .atomic_write import write_bytes
from .dependency_package import stage_package
from .preview_frames import frame_path, save_frame


def managed_esmini_root() -> Path:
    """Keep the simulator installation separate from selectable asset stores."""
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local" / "share")) / "OpenXScenarioWorkbench" / "tools" / "esmini"


def find_esmini(value: str = "") -> Path | None:
    # An explicit override must be valid itself; silently selecting a different
    # installation makes settings validation and playback disagree.
    manual = str(value).strip().strip('"')
    candidates = [manual] if manual else [
        os.environ.get("OPENX_ESMINI_PATH", ""), shutil.which("esmini.exe"), shutil.which("esmini"),
        managed_esmini_root(), Path.home() / ".openx" / "tools" / "esmini",
        Path(__file__).resolve().parents[2] / "tools" / "esmini",
        Path.home() / "Downloads" / "esmini", Path.home() / "Desktop" / "esmini",
    ]
    if not manual:
        # Search common install locations one level deep, never entire disks.
        roots = [Path.home() / "Downloads", Path.home() / "Desktop",
                 Path.home() / "Documents", Path(os.environ.get("ProgramFiles", "C:/Program Files"))]
        for root in roots:
            if root.is_dir():
                candidates.extend(sorted(root.glob("esmini*")))
    for item in candidates:
        if not item:
            continue
        path = Path(str(item).strip().strip('"')).expanduser()
        executables = (path / "esmini.exe", path / "bin" / "esmini.exe",
                       path / "esmini" / "bin" / "esmini.exe") if path.is_dir() else (path,)
        for executable in executables:
            if executable.name.casefold() in {"esmini", "esmini.exe"} and executable.is_file() and (executable.parent / "esminiLib.dll").is_file():
                return executable.resolve()
    return None


# Seconds for the worker to load esmini and the scenario. Generous: a preview run starts several side
# by side, and a start slowed by its neighbours is not the scenario's failure.
START_TIMEOUT = 20.0


@dataclass
class PreviewProcess:
    process: subprocess.Popen
    url: str
    token: str
    version_id: str
    workdir: Path
    asset_id: str = ""
    _last_status: dict | None = field(default=None, init=False, repr=False)

    def status(self) -> dict:
        try:
            if not self.url:  # the worker names the port the system gave it once it listens
                self.url = f"http://127.0.0.1:{int((self.workdir / 'port').read_text())}"
            with urlopen(f"{self.url}/status?token={self.token}", timeout=1) as response:
                status = json.load(response)
                self._last_status = dict(status)
                return status
        except Exception:
            if self.process.poll() is not None and self._last_status and self._last_status["state"] in {"finished", "failed"}:
                return dict(self._last_status)
            return {"state": "stopped" if self.process.poll() is not None else "starting",
                    "frames": 0, "error": "Preview worker exited." if self.process.poll() is not None else ""}

    def stop(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=3)
        shutil.rmtree(self.workdir, ignore_errors=True)


def record_outcome(store: AssetStore, version: AssetVersion, status: dict) -> str:
    """Store on the version whether it played, as the desktop workbench did; returns its preview state."""
    if status["state"] == "failed":
        if version.compatibility != "failed" or version.compatibility_detail != status.get("error", ""):
            store.set_compatibility(version, "failed", status.get("error", ""))
        return "failed"
    if status["state"] == "finished" and not status.get("frames"):
        if version.compatibility != "failed":
            store.set_compatibility(version, "failed", "esmini finished without rendered frames.")
        return "failed"
    if status.get("frames"):
        if version.compatibility != "playable":
            store.set_compatibility(version, "playable")
        return "playable"
    return version.compatibility


def start_preview(store: AssetStore, version: AssetVersion, executable: Path,
                  *, duration: int = 30) -> PreviewProcess:
    if not executable.is_file() or not (executable.parent / "esminiLib.dll").is_file():
        raise FileNotFoundError("Select an esmini.exe next to esminiLib.dll.")
    root = Path(tempfile.mkdtemp(prefix="openx-preview-"))
    scenario = store.file_bytes(version, "scenario")
    road = store.file_bytes(version, "road")
    try:
        if version.source_name.casefold().endswith(".zip"):
            stage_package(store.file_bytes(version, "source"), root)
            scenario_path = root.joinpath(*Path(version.xosc_name.replace("\\", "/")).parts)
            road_path = root.joinpath(*Path(version.xodr_name.replace("\\", "/")).parts)
        else:
            scenario_path = root / "xosc" / "scenario.xosc"
            road_path = root / "xodr" / Path(version.xodr_name).name
        scenario_path.parent.mkdir(parents=True, exist_ok=True)
        road_path.parent.mkdir(parents=True, exist_ok=True)
        xml = ET.fromstring(scenario)
        logic = xml.find(".//RoadNetwork/LogicFile")
        if logic is None:
            raise ValueError("Scenario has no RoadNetwork/LogicFile.")
        logic.set("filepath", os.path.relpath(road_path, scenario_path.parent).replace("\\", "/"))
        scenario = ET.tostring(xml, encoding="utf-8", xml_declaration=True)
        scenario_path.write_bytes(scenario)
        road_path.write_bytes(road)
        token = os.urandom(16).hex()
        command = [sys.executable, "-m", "openx_workbench.esmini_preview", "--worker",
                   str(executable), str(scenario_path), str(root), token,
                   str(min(max(duration, 1), 120)), str(frame_path(store, version))]
        env = os.environ.copy()
        package_root = str(Path(__file__).resolve().parents[1])
        env["PYTHONPATH"] = package_root + os.pathsep + env.get("PYTHONPATH", "")
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        with (root / "worker.log").open("wb") as error_log:
            process = subprocess.Popen(command, cwd=root, env=env, stdout=subprocess.DEVNULL,
                                       stderr=error_log, creationflags=flags)
        preview = PreviewProcess(process, "", token, version.version_id, root, version.asset_id)
        deadline = time.monotonic() + START_TIMEOUT
        while time.monotonic() < deadline:
            status = preview.status()
            if status["state"] in {"running", "finished", "failed"}:
                return preview
            if process.poll() is not None:
                detail = (root / "worker.log").read_text(errors="replace")[-1000:]
                preview.stop()
                raise RuntimeError(f"Preview worker exited: {detail}")
            time.sleep(0.1)
        preview.stop()
        raise TimeoutError(f"esmini preview did not start within {START_TIMEOUT:g} seconds.")
    except Exception:
        shutil.rmtree(root, ignore_errors=True)
        raise


class _Frame(ctypes.Structure):
    _fields_ = [("width", ctypes.c_int), ("height", ctypes.c_int),
                ("pixel_size", ctypes.c_int), ("pixel_format", ctypes.c_int),
                ("data", ctypes.POINTER(ctypes.c_ubyte))]


class _State:
    def __init__(self):
        self.condition = threading.Condition()
        self.frame: bytes | None = None
        self.frames = 0
        self.state = "starting"
        self.error = ""
        self.snapshot_error = ""


def _simulate(executable: Path, scenario: Path, root: Path, duration: int, state: _State,
              snapshot: Path | None = None) -> None:
    try:
        from PIL import Image
        dll_dir = os.add_dll_directory(str(executable.parent)) if hasattr(os, "add_dll_directory") else None
        lib = ctypes.CDLL(str(executable.parent / "esminiLib.dll"))
        lib.SE_SetWindowPosAndSize.argtypes = [ctypes.c_int] * 4
        lib.SE_SaveImagesToRAM.argtypes = [ctypes.c_bool]
        lib.SE_SaveImagesToRAM.restype = ctypes.c_int
        lib.SE_AddPath.argtypes = [ctypes.c_char_p]
        lib.SE_AddPath.restype = ctypes.c_int
        lib.SE_Init.argtypes = [ctypes.c_char_p] + [ctypes.c_int] * 4
        lib.SE_Init.restype = ctypes.c_int
        lib.SE_StepDT.argtypes = [ctypes.c_double]
        lib.SE_StepDT.restype = ctypes.c_int
        lib.SE_FetchImage.argtypes = [ctypes.POINTER(_Frame)]
        lib.SE_FetchImage.restype = ctypes.c_int
        lib.SE_GetQuitFlag.restype = ctypes.c_int
        lib.SE_Close.argtypes = []
        resource_dir = executable.parent.parent / "resources"
        if resource_dir.is_dir():
            lib.SE_AddPath(os.fsencode(resource_dir))
        lib.SE_AddPath(os.fsencode(root))
        lib.SE_AddPath(os.fsencode(scenario.parent))
        lib.SE_SetWindowPosAndSize(0, 0, 640, 360)
        if lib.SE_SaveImagesToRAM(True) != 0:
            raise RuntimeError("esmini could not enable in-memory frame capture.")
        if lib.SE_Init(os.fsencode(scenario), 0, 3, 0, 0) != 0:
            raise RuntimeError("esmini rejected the scenario.")
        try:
            state.state = "running"
            deadline = time.monotonic() + duration
            while not lib.SE_GetQuitFlag() and time.monotonic() < deadline:
                if lib.SE_StepDT(0.1) != 0:
                    raise RuntimeError("esmini failed while stepping the simulation.")
                frame = _Frame()
                if lib.SE_FetchImage(ctypes.byref(frame)) != 0 or not frame.data:
                    raise RuntimeError("esmini did not return a rendered frame.")
                if frame.pixel_size not in (3, 4) or frame.width <= 0 or frame.height <= 0:
                    raise RuntimeError("esmini returned an unsupported frame format.")
                raw = ctypes.string_at(frame.data, frame.width * frame.height * frame.pixel_size)
                fmt = ("BGRX" if frame.pixel_size == 4 else "BGR") if frame.pixel_format == 0x80E0 else ("RGBX" if frame.pixel_size == 4 else "RGB")
                image = Image.frombytes("RGB", (frame.width, frame.height), raw, "raw", fmt)
                image = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
                output = io.BytesIO()
                image.save(output, "JPEG", quality=76)
                with state.condition:
                    state.frame = output.getvalue()
                    state.frames += 1
                    state.condition.notify_all()
                if snapshot is not None and state.frames in (1, 10):
                    # Keep an early frame even when the scenario ends before 1 s.
                    try:
                        save_frame(snapshot, state.frame, state.frames)
                        state.snapshot_error = ""
                    except OSError as exc:
                        state.snapshot_error = str(exc)
                time.sleep(0.1)
        finally:
            lib.SE_Close()
            if dll_dir:
                dll_dir.close()
        state.state = "finished"
    except Exception as exc:
        state.error = str(exc)
        try:
            diagnostics = "\n".join(line for line in (root / "log.txt").read_text(errors="replace").splitlines()
                                    if "[error]" in line.lower())[-4000:]
            if diagnostics:
                state.error += "\n\nesmini diagnostics:\n" + diagnostics
        except OSError:
            pass
        state.state = "failed"
    finally:
        with state.condition:
            state.condition.notify_all()


def _serve(executable: Path, scenario: Path, root: Path, token: str, duration: int,
           snapshot: Path | None = None) -> None:
    state = _State()

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            from urllib.parse import parse_qs, urlsplit
            parsed = urlsplit(self.path)
            if parse_qs(parsed.query).get("token") != [token]:
                self.send_error(403)
                return
            if parsed.path == "/status":
                body = json.dumps({"state": state.state, "frames": state.frames,
                                   "error": state.error, "snapshot_error": state.snapshot_error}).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/stream":
                self.send_response(200)
                self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                seen = 0
                try:
                    while True:
                        with state.condition:
                            state.condition.wait_for(lambda: state.frames > seen or state.state in ("failed", "finished"), timeout=2)
                            if state.frames == seen and state.state in ("failed", "finished"):
                                break
                            if state.frames == seen:
                                continue
                            seen, frame = state.frames, state.frame
                        self.wfile.write(b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " +
                                         str(len(frame)).encode() + b"\r\n\r\n" + frame + b"\r\n")
                        self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
            else:
                self.send_error(404)

        def log_message(self, *_args):
            return

    # Port 0: the system picks one no other socket holds, so previews started side by side never share
    # one. The parent reads it from `port` in this worker's own folder.
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    server.daemon_threads = True
    write_bytes(root / "port", str(server.server_address[1]).encode(), prefix="port-", suffix=".tmp")
    threading.Thread(target=_simulate, args=(executable, scenario, root, duration, state, snapshot), daemon=True).start()
    timer = threading.Timer(duration + 20, server.shutdown)
    timer.daemon = True
    timer.start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        shutil.rmtree(root, ignore_errors=True)


if __name__ == "__main__" and sys.argv[1:2] == ["--worker"]:
    _serve(Path(sys.argv[2]), Path(sys.argv[3]), Path(sys.argv[4]),
           sys.argv[5], int(sys.argv[6]), Path(sys.argv[7]) if len(sys.argv) > 7 else None)
