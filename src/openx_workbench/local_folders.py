"""Native folder actions for the local desktop workbench."""
from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys


def choose_folder(title: str, initial: Path) -> Path | None:
    # A separate process gives Tk its own main thread and keeps UI resources
    # out of the web server's worker threads. No folder contents are uploaded.
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve()), title, str(initial)],
        capture_output=True, text=True, encoding="utf-8", timeout=180,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    if result.returncode:
        raise OSError("The native folder browser could not open.")
    value = json.loads(result.stdout)
    return Path(value) if value else None


def open_folder(path: Path) -> None:
    path = path.resolve(strict=True)
    if not path.is_dir():
        raise NotADirectoryError(path)
    if os.name == "nt":
        os.startfile(str(path))
    else:
        subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])


if __name__ == "__main__":
    import tkinter as tk
    from tkinter import filedialog

    window = tk.Tk()
    window.withdraw()
    window.attributes("-topmost", True)
    try:
        selected = filedialog.askdirectory(parent=window, title=sys.argv[1], initialdir=sys.argv[2], mustexist=True)
        print(json.dumps(selected, ensure_ascii=True))
    finally:
        window.destroy()
