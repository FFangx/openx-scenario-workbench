"""Windows tray launcher, with authenticated local control and owned child processes."""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.request import Request, urlopen

from .asset_store import default_store_root
from .windows_job import WindowsJob


WEB_DIST = Path(__file__).resolve().parents[2] / "web" / "dist"
HEALTH = {"web": "/api/health", "streamlit": "/_stcore/health"}


def web_available():
    """The React workbench needs its built bundle and the optional web dependencies."""
    from importlib.util import find_spec
    return (WEB_DIST / "index.html").is_file() and all(find_spec(name) for name in ("fastapi", "uvicorn"))


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def source_revision():
    """Detect source updates without relying on Streamlit's module reloads."""
    package = Path(__file__).resolve().parent
    digest = hashlib.sha256()
    for path in sorted(package.rglob("*.py")):
        digest.update(path.relative_to(package).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def tray_image():
    from PIL import Image, ImageDraw
    image = Image.new("RGB", (64, 64), "#123544")
    draw = ImageDraw.Draw(image)
    draw.ellipse((10, 10, 54, 54), outline="#8ae0c2", width=7)
    draw.line((24, 24, 40, 40), fill="white", width=5)
    draw.line((40, 24, 24, 40), fill="white", width=5)
    return image


class InstanceLock:
    def __init__(self, path):
        self.file = path.open("a+b")
        self.file.write(b"0")
        self.file.flush()
        self.file.seek(0)

    def acquire(self):
        import msvcrt
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            return True
        except OSError:
            return False

    def close(self):
        self.file.close()


def send_control(path, action):
    record = json.loads(path.read_text(encoding="utf-8"))
    port = int(record["port"])
    if not 0 < port < 65536:
        raise ValueError("Invalid launcher port")
    request = Request(f"http://127.0.0.1:{port}/{action}", data=b"",
                      headers={"Authorization": f"Bearer {record['token']}"}, method="POST")
    with urlopen(request, timeout=3) as response:
        return response.status == 202


class Service:
    def __init__(self, root, kind="streamlit"):
        if kind not in HEALTH:
            raise ValueError(f"Unknown service kind: {kind}")
        self.root = root
        self.kind = kind
        self.process = None
        self.job = None
        self.url = ""
        self.source_revision = None

    def needs_restart(self):
        return self.source_revision != source_revision()

    def start(self):
        self.stop()
        revision = source_revision()
        port = free_port()
        self.url = f"http://127.0.0.1:{port}"
        self.job = WindowsJob()
        env = os.environ.copy()
        env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1]) + os.pathsep + env.get("PYTHONPATH", "")
        # Use python.exe with CREATE_NO_WINDOW, retaining functional stdout/stderr.
        python = Path(sys.executable).with_name("python.exe")
        log_name = "service" if self.kind == "streamlit" else "web-service"
        log_path = self.root / f"{log_name}.log"
        if log_path.exists() and log_path.stat().st_size > 5_000_000:
            log_path.replace(self.root / f"{log_name}.previous.log")
        try:
            with log_path.open("ab") as log:
                self.process = subprocess.Popen(
                    [str(python), "-m", "openx_workbench.launcher", "--serve", str(port), "--ui", self.kind],
                    stdin=subprocess.PIPE, stdout=log, stderr=log, env=env,
                    cwd=Path(__file__).resolve().parents[2], creationflags=subprocess.CREATE_NO_WINDOW | 4)
            # Child waits on stdin: assign ownership before it can spawn any workers.
            self.job.assign(self.process)
            self.job.resume(self.process)
            self.process.stdin.write(b"start\n")
            self.process.stdin.close()
            self.source_revision = revision
            logging.info("Service started: kind=%s pid=%s url=%s", self.kind, self.process.pid, self.url)
        except Exception:
            self.stop()
            raise

    def ready(self):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("网页服务已退出，请查看 service.log。")
        try:
            with urlopen(self.url + HEALTH[self.kind], timeout=0.5) as response:
                return response.status == 200
        except OSError:
            return False

    def stop(self):
        if self.job:
            self.job.close()
            self.job = None
        if self.process:
            if self.process.poll() is None:
                self.process.kill()
            self.process.wait(timeout=5)
            logging.info("Service stopped: pid=%s", self.process.pid)
            self.process = None


class Launcher:
    def __init__(self, root, *, no_browser=False, ui=None):
        self.root = root
        self.no_browser = no_browser
        ui = ui or ("web" if web_available() else "streamlit")
        logging.info("Primary workbench: %s", ui)
        self.service = Service(root, ui)
        # The Streamlit workbench still owns imports and preview generation; start it only on request.
        self.classic = Service(root, "streamlit") if ui == "web" else self.service
        self.done = threading.Event()
        self.guard = threading.Lock()
        self.icon = None
        self.token = secrets.token_hex(32)
        owner = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                if not hmac.compare_digest(self.headers.get("Authorization", ""), "Bearer " + owner.token):
                    self.send_error(403)
                    return
                action = self.path.removeprefix("/")
                if action not in {"open", "restart", "stop", "classic"}:
                    self.send_error(404)
                    return
                self.send_response(202)
                self.end_headers()
                owner.dispatch(action)

            def log_message(self, *args):
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)

    def dispatch(self, action):
        if action == "stop":
            self.done.set()
        elif action == "classic":
            threading.Thread(target=self.open, kwargs={"service": self.classic}, daemon=True).start()
        else:
            threading.Thread(target=self.open, args=(action == "restart",), daemon=True).start()

    def open(self, restart=False, service=None):
        service = service or self.service
        with self.guard:
            if self.done.is_set():
                return
            if restart and self.classic is not self.service and self.classic.process is not None:
                self.classic.stop()  # restarted on its next open, with the current sources
            try:
                if (restart or service.process is None or service.process.poll() is not None
                    or service.needs_restart()):
                    service.start()
                deadline = time.monotonic() + 40
                while not self.done.is_set():
                    if service.ready():
                        logging.info("Service ready: %s", service.url)
                        if self.icon:
                            self.icon.title = "OpenX · 运行中"
                        if not self.no_browser:
                            webbrowser.open(service.url)
                        return
                    if time.monotonic() > deadline:
                        raise TimeoutError("网页服务启动超时，请查看日志文件夹。")
                    self.done.wait(0.2)
            except Exception as exc:
                logging.exception("Service startup failed")
                service.stop()
                if self.icon:
                    self.icon.title = "OpenX · 启动失败"
                    self.icon.notify(str(exc), "OpenX 启动失败")

    def run(self, headless=False):
        if not headless:
            import pystray
            self.icon = pystray.Icon("OpenX", tray_image(), "OpenX · 启动中", pystray.Menu(
                pystray.MenuItem("打开工作台", lambda: self.dispatch("open"), default=True),
                *([pystray.MenuItem("打开经典工作台（导入与仿真预览）", lambda: self.dispatch("classic"))]
                  if self.classic is not self.service else []),
                pystray.MenuItem("重启服务", lambda: self.dispatch("restart")),
                pystray.MenuItem("查看日志", lambda: os.startfile(str(self.root))),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem("关闭 OpenX", lambda: self.dispatch("stop"))))
        record_path = self.root / "instance.json"
        try:
            threading.Thread(target=self.server.serve_forever, daemon=True).start()
            record_path.write_text(json.dumps({"port": self.server.server_port, "token": self.token}), encoding="utf-8")
            if self.icon:
                self.icon.run_detached()
                logging.info("Tray started")
            self.dispatch("open")
            while not self.done.wait(1):
                if self.icon and self.service.process and self.service.process.poll() is not None:
                    self.icon.title = "OpenX · 服务已停止，可重启"
        finally:
            self.done.set()
            self.server.shutdown()
            self.server.server_close()
            with self.guard:
                self.service.stop()
                self.classic.stop()
            record_path.unlink(missing_ok=True)
            if self.icon:
                self.icon.stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--headless", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--serve", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--ui", choices=sorted(HEALTH), help="Workbench to open (default: web when built).")
    parser.add_argument("--classic", action="store_true", help="Open the Streamlit workbench.")
    args = parser.parse_args()
    if args.serve:
        if sys.stdin.readline().strip() != "start":
            return
        if args.ui == "web":
            import uvicorn
            uvicorn.run("openx_workbench.api:app", host="127.0.0.1", port=args.serve, log_level="warning")
            return
        import runpy
        sys.argv = ["streamlit", "run", str(Path(__file__).with_name("app.py")),
                    "--server.address", "127.0.0.1", "--server.port", str(args.serve),
                    "--server.headless", "true", "--browser.gatherUsageStats", "false"]
        runpy.run_module("streamlit", run_name="__main__")
        return
    if os.name != "nt":
        raise RuntimeError("This launcher currently supports Windows only.")
    root = default_store_root() / "launcher"
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(handlers=[RotatingFileHandler(root / "launcher.log", maxBytes=1_000_000,
                                                     backupCount=2, encoding="utf-8")], level=logging.INFO)
    lock = InstanceLock(root / "instance.lock")
    try:
        if not lock.acquire():
            for _ in range(30):
                try:
                    action = "stop" if args.stop else "classic" if args.classic else "open"
                    if send_control(root / "instance.json", action):
                        return
                except (OSError, ValueError, KeyError):
                    time.sleep(0.1)
            raise RuntimeError("已有 OpenX 启动器未响应。请查看启动器日志。")
        if not args.stop:
            launcher = Launcher(root, no_browser=args.no_browser, ui=args.ui)
            if args.classic:
                launcher.service = launcher.classic
            launcher.run(headless=args.headless)
    except Exception as exc:
        logging.exception("Launcher failed")
        if not args.headless:
            import ctypes
            ctypes.windll.user32.MessageBoxW(None, f"{exc}\n\n日志：{root}", "OpenX", 0x10)
        raise
    finally:
        lock.close()


if __name__ == "__main__":
    main()
