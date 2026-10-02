import pytest
import io
import json
from types import SimpleNamespace

from openx_workbench.esmini_preview import PreviewProcess, find_esmini, managed_esmini_root


def installation(root):
    binary = root / "bin"
    binary.mkdir(parents=True)
    executable = binary / "esmini.exe"
    executable.write_bytes(b"authored discovery fixture; never executed")
    (binary / "esminiLib.dll").write_bytes(b"authored discovery fixture; never loaded")
    return executable.resolve()


@pytest.fixture
def local_machine(tmp_path, monkeypatch):
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "machine"))
    monkeypatch.delenv("OPENX_ESMINI_PATH", raising=False)
    monkeypatch.setattr("openx_workbench.esmini_preview.shutil.which", lambda command: None)
    monkeypatch.setattr("openx_workbench.esmini_preview.Path.home", lambda: tmp_path / "home")
    return tmp_path


def test_versioned_download_and_shared_install_are_discovered(local_machine):
    executable = installation(local_machine / "home" / "Downloads" / "esmini-bin_win_x64-v3.8.2" / "esmini")
    assert find_esmini() == executable
    shared = installation(local_machine / "home" / ".openx" / "tools" / "esmini")
    assert find_esmini() == shared


def test_root_bin_executable_and_quoted_paths_are_accepted(local_machine):
    executable = installation(local_machine / "separate install")
    for value in (executable, executable.parent, executable.parent.parent):
        assert find_esmini(str(value)) == executable
        assert find_esmini(f'  "{value}"  ') == executable


def test_managed_detection_is_independent_of_asset_store(local_machine, monkeypatch):
    executable = installation(managed_esmini_root())
    monkeypatch.setenv("OPENX_DATA_DIR", str(local_machine / "private QA data"))
    assert find_esmini() == executable
    assert find_esmini(str(local_machine / "invalid override")) is None


def test_configured_and_environment_installations_take_precedence(local_machine, monkeypatch):
    installation(managed_esmini_root())
    configured = installation(local_machine / "custom")
    environment = installation(local_machine / "environment")
    monkeypatch.setenv("OPENX_ESMINI_PATH", str(environment.parent))
    assert find_esmini() == environment
    assert find_esmini(str(configured)) == configured


def test_incomplete_installation_or_unrelated_executable_is_rejected(local_machine):
    executable = installation(local_machine / "custom")
    unrelated = executable.with_name("another.exe")
    unrelated.write_bytes(b"authored fixture")
    assert find_esmini(str(unrelated)) is None
    (executable.parent / "esminiLib.dll").unlink()
    assert find_esmini(str(executable)) is None


@pytest.mark.parametrize("state", ["finished", "failed"])
def test_terminal_result_survives_worker_http_shutdown(local_machine, monkeypatch, state):
    terminal = {"state": state, "frames": 5 if state == "finished" else 0, "error": "" if state == "finished" else "Unsupported curve"}
    monkeypatch.setattr("openx_workbench.esmini_preview.urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps(terminal).encode()))
    preview = PreviewProcess(SimpleNamespace(poll=lambda: 0), "http://127.0.0.1:1234", "authored", "version", local_machine, "asset")
    assert preview.status() == terminal

    def closed(*args, **kwargs):
        raise OSError("Worker server shut down")

    monkeypatch.setattr("openx_workbench.esmini_preview.urlopen", closed)
    assert preview.status() == terminal
