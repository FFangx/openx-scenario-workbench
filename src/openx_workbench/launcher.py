"""Windows tray launcher, with authenticated local control and owned child processes."""
from __future__ import annotations

import argparse
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

from .app_icon import app_icon
from .asset_store import default_store_root
from .checkout import checkout_root, package_revision
from .windows_job import WindowsJob


WEB_DIST = checkout_root() / "web" / "dist"
HEALTH = "/api/health"


def web_available():
    """The workbench serves its built React bundle; a source checkout needs `npm run build` once."""
    return (WEB_DIST / "index.html").is_file()


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def source_revision():
    """Detect source updates so an open service restarts with the current code."""
    return package_revision(Path(__file__).resolve().parent)


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
    def __init__(self, root):
        self.root = root
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
        log_path = self.root / "web-service.log"
        if log_path.exists() and log_path.stat().st_size > 5_000_000:
            log_path.replace(self.root / "web-service.previous.log")
        try:
            with log_path.open("ab") as log:
                self.process = subprocess.Popen(
                    [str(python), "-m", "openx_workbench.launcher", "--serve", str(port)],
                    stdin=subprocess.PIPE, stdout=log, stderr=log, env=env,
                    cwd=Path(__file__).resolve().parents[2], creationflags=subprocess.CREATE_NO_WINDOW | 4)
            # Child waits on stdin: assign ownership before it can spawn any workers.
            self.job.assign(self.process)
            self.job.resume(self.process)
            self.process.stdin.write(b"start\n")
            self.process.stdin.close()
            self.source_revision = revision
            logging.info("Service started: pid=%s url=%s", self.process.pid, self.url)
        except Exception:
            self.stop()
            raise

    def ready(self):
        if self.process is None or self.process.poll() is not None:
            raise RuntimeError("网页服务已退出，请查看 web-service.log。")
        try:
            with urlopen(self.url + HEALTH, timeout=0.5) as response:
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
    def __init__(self, root, *, no_browser=False):
        if not web_available():
            raise RuntimeError("网页界面尚未构建：请在 web 文件夹运行 npm ci 和 npm run build。 / "
                               "The web interface is not built: run npm ci and npm run build in the web folder.")
        self.root = root
        self.no_browser = no_browser
        self.service = Service(root)
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
                if action not in {"open", "restart", "stop"}:
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
        else:
            threading.Thread(target=self.open, args=(action == "restart",), daemon=True).start()

    def open(self, restart=False):
        service = self.service
        with self.guard:
            if self.done.is_set():
                return
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
            self.icon = pystray.Icon("OpenX", app_icon(), "OpenX · 启动中", pystray.Menu(
                pystray.MenuItem("打开工作台", lambda: self.dispatch("open"), default=True),
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
            record_path.unlink(missing_ok=True)
            if self.icon:
                self.icon.stop()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stop", action="store_true")
    parser.add_argument("--headless", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-browser", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--serve", type=int, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.serve:
        if sys.stdin.readline().strip() != "start":
            return
        import uvicorn
        from .api import app
        from .matching import preload_encoder
        preload_encoder()  # after the app's imports, so the model's imports do not interleave with them
        uvicorn.run(app, host="127.0.0.1", port=args.serve, log_level="warning")
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
                    action = "stop" if args.stop else "open"
                    if send_control(root / "instance.json", action):
                        return
                except (OSError, ValueError, KeyError):
                    time.sleep(0.1)
            raise RuntimeError("已有 OpenX 启动器未响应。请查看启动器日志。")
        if not args.stop:
            launcher = Launcher(root, no_browser=args.no_browser)
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
