from pathlib import Path
from types import SimpleNamespace

import pytest

from openx_workbench.local_folders import choose_folder, open_folder


def test_browser_returns_unicode_folder_and_cancel_without_shell(tmp_path, monkeypatch):
    calls = []
    selected = tmp_path / "仿真工具"

    def run(args, **kwargs):
        calls.append((args, kwargs))
        return SimpleNamespace(returncode=0, stdout='"' + selected.as_posix() + '"')

    monkeypatch.setattr("openx_workbench.local_folders.subprocess.run", run)
    assert choose_folder("选择安装", tmp_path) == selected
    assert calls[0][0][-2:] == ["选择安装", str(tmp_path)]
    assert not calls[0][1].get("shell")
    monkeypatch.setattr("openx_workbench.local_folders.subprocess.run", lambda *a, **k: SimpleNamespace(returncode=0, stdout='""'))
    assert choose_folder("选择安装", tmp_path) is None


def test_open_folder_rejects_file_before_launch(tmp_path):
    file = tmp_path / "file.txt"
    file.write_text("authored")
    with pytest.raises(NotADirectoryError):
        open_folder(file)
    with pytest.raises(FileNotFoundError):
        open_folder(Path(tmp_path / "missing"))
