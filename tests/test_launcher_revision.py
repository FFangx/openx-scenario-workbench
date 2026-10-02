from openx_workbench import launcher


def test_source_revision_tracks_python_changes_but_ignores_runtime_files(tmp_path, monkeypatch):
    entry = tmp_path / "launcher.py"
    entry.write_text("version = 1", encoding="utf-8")
    monkeypatch.setattr(launcher, "__file__", str(entry))
    original = launcher.source_revision()
    (tmp_path / "service.log").write_text("runtime output", encoding="utf-8")
    assert launcher.source_revision() == original
    entry.write_text("version = 2", encoding="utf-8")
    edited = launcher.source_revision()
    assert edited != original
    module = tmp_path / "nested" / "new.py"
    module.parent.mkdir()
    module.write_text("feature = True", encoding="utf-8")
    assert launcher.source_revision() != edited
