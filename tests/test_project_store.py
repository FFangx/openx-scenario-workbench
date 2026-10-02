from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import os
import subprocess
import sys
import threading
import time

import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile
from openx_workbench.project_store import ProjectStore


def test_named_projects_restore_last_and_pin_saved_decisions(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    assets = AssetStore(tmp_path)
    version = assets.import_files(
        [
            AssetFile("minimal.xosc", (fixtures / "minimal.xosc").read_bytes()),
            AssetFile("minimal.xodr", (fixtures / "minimal.xodr").read_bytes()),
        ]
    )[0]
    projects = ProjectStore(assets)
    first = projects.create("First project")
    second = projects.create("Second project")
    assert ProjectStore(assets).last() == second
    projects.set_last(first.project_id)
    assert ProjectStore(assets).last() == first
    trace = {
        "candidate": {"asset_id": version.asset_id, "version_id": version.version_id},
        "reuse": {"level": "modify"},
    }
    path = projects.save_decision(first.project_id, version, trace)
    assert path.is_file()
    assert projects.reports(first.project_id)[0]["version_id"] == version.version_id
    with pytest.raises(ValueError, match="referenced"):
        assets.delete_version(version)


def test_decision_rejects_mismatched_version(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    assets = AssetStore(tmp_path)
    version = assets.import_files(
        [
            AssetFile("minimal.xosc", (fixtures / "minimal.xosc").read_bytes()),
            AssetFile("minimal.xodr", (fixtures / "minimal.xodr").read_bytes()),
        ]
    )[0]
    projects = ProjectStore(assets)
    project = projects.create("Review")
    with pytest.raises(ValueError, match="differ"):
        projects.save_decision(
            project.project_id,
            version,
            {"candidate": {"asset_id": version.asset_id, "version_id": "wrong"}},
        )


def _asset_store(tmp_path):
    assets = AssetStore(tmp_path)
    fixtures = Path(__file__).parent / "fixtures"
    version = assets.import_files(
        [
            AssetFile(name, (fixtures / name).read_bytes())
            for name in ("minimal.xosc", "minimal.xodr")
        ]
    )[0]
    return assets, version


def test_concurrent_reports_preserve_every_reference(tmp_path, monkeypatch):
    assets, version = _asset_store(tmp_path)
    project = ProjectStore(assets).create("Concurrent review")
    # Widen the old read/modify/write race without blocking inside the guard.
    read = Path.read_text

    def slow_read(path, *args, **kwargs):
        value = read(path, *args, **kwargs)
        if path.name == "version_references.json":
            time.sleep(0.02)
        return value

    monkeypatch.setattr(Path, "read_text", slow_read)
    barrier = threading.Barrier(8)

    def save(index):
        store = ProjectStore(AssetStore(tmp_path))
        barrier.wait(timeout=10)
        return store.save_decision(
            project.project_id,
            version,
            {
                "candidate": {
                    "asset_id": version.asset_id,
                    "version_id": version.version_id,
                },
                "run": index,
            },
        )

    with ThreadPoolExecutor(max_workers=8) as executor:
        reports = list(executor.map(save, range(8)))
    assert all(path.is_file() for path in reports)
    assert set(assets.references(version)) == {
        "report:" + path.stem for path in reports
    }
    with pytest.raises(ValueError, match="referenced"):
        assets.delete_version(version)


def test_store_guard_protects_references_across_processes(tmp_path):
    assets, version = _asset_store(tmp_path)
    code = """import sys
from pathlib import Path
from openx_workbench.asset_store import AssetStore
store = AssetStore(Path(sys.argv[1]))
version = store.latest()[0]
for index in range(10):
    store.pin_version(sys.argv[2] + ':' + str(index), version)
"""
    env = {**os.environ, "PYTHONPATH": str(Path(__file__).parents[1] / "src")}
    workers = [
        subprocess.Popen(
            [sys.executable, "-c", code, str(tmp_path), str(index)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        for index in range(4)
    ]
    try:
        for worker in workers:
            _, error = worker.communicate(timeout=30)
            assert worker.returncode == 0, error.decode(errors="replace")
    finally:
        for worker in workers:
            if worker.poll() is None:
                worker.kill()
                worker.wait()
    assert len(assets.references(version)) == 40


def test_deleted_version_cannot_be_referenced_by_a_new_report(tmp_path):
    assets, version = _asset_store(tmp_path)
    projects = ProjectStore(assets)
    project = projects.create("Deleted candidate")
    assets.delete_version(version)
    with pytest.raises(ValueError, match="missing"):
        projects.save_decision(
            project.project_id,
            version,
            {
                "candidate": {
                    "asset_id": version.asset_id,
                    "version_id": version.version_id,
                }
            },
        )
    assert projects.reports(project.project_id) == []


def test_failed_report_write_does_not_leave_a_reference(tmp_path, monkeypatch):
    assets, version = _asset_store(tmp_path)
    projects = ProjectStore(assets)
    project = projects.create("Failed write")

    def fail(path, value):
        raise OSError("authored disk failure")

    monkeypatch.setattr(projects, "_write_json", fail)
    with pytest.raises(OSError, match="authored"):
        projects.save_decision(
            project.project_id,
            version,
            {
                "candidate": {
                    "asset_id": version.asset_id,
                    "version_id": version.version_id,
                }
            },
        )
    assert assets.references(version) == ()
    assets.delete_version(version)
