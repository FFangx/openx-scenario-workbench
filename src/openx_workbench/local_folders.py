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


def documents_folder() -> Path:
    """The user's Documents folder, wherever Windows keeps it (it may be redirected, e.g. to OneDrive)."""
    if os.name == "nt":
        import ctypes
        import uuid
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD), ("Data3", wintypes.WORD),
                        ("Data4", ctypes.c_ubyte * 8)]

        known = uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7")  # FOLDERID_Documents
        guid = GUID(known.fields[0], known.fields[1], known.fields[2], (ctypes.c_ubyte * 8)(*known.bytes[8:]))
        found = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(guid), 0, None, ctypes.byref(found)) == 0:
            try:
                return Path(found.value)
            finally:
                ctypes.windll.ole32.CoTaskMemFree(found)
    return Path.home() / "Documents"


def hide(path: Path) -> None:
    """Mark a folder hidden on Windows; elsewhere its leading dot already hides it."""
    if os.name == "nt":
        import ctypes
        FILE_ATTRIBUTE_HIDDEN = 0x2
        attributes = ctypes.windll.kernel32.GetFileAttributesW(str(path))
        if attributes != -1:
            ctypes.windll.kernel32.SetFileAttributesW(str(path), attributes | FILE_ATTRIBUTE_HIDDEN)


def recycle(path: Path) -> None:
    """Move a file or folder to the Windows Recycle Bin, where the user can restore it."""
    if os.name != "nt":
        raise OSError("The Recycle Bin is only available on Windows.")
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", wintypes.UINT), ("pFrom", wintypes.LPCWSTR),
                    ("pTo", wintypes.LPCWSTR), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", wintypes.LPCWSTR)]

    FO_DELETE, FOF_SILENT, FOF_NOCONFIRMATION, FOF_ALLOWUNDO, FOF_NOERRORUI = 3, 0x4, 0x10, 0x40, 0x400
    path = path.resolve(strict=True)
    operation = SHFILEOPSTRUCTW(wFunc=FO_DELETE, pFrom=str(path) + "\0",  # the list ends with a second NUL
                                fFlags=FOF_ALLOWUNDO | FOF_NOCONFIRMATION | FOF_SILENT | FOF_NOERRORUI)
    code = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(operation))
    if code or operation.fAnyOperationsAborted or path.exists():
        raise OSError(f"Could not move {path} to the Recycle Bin (code {code}).")


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
