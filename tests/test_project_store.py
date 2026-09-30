from pathlib import Path

import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile
from openx_workbench.project_store import ProjectStore


def test_named_projects_restore_last_and_pin_saved_decisions(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    assets = AssetStore(tmp_path)
    version = assets.import_files([
        AssetFile("minimal.xosc", (fixtures / "minimal.xosc").read_bytes()),
        AssetFile("minimal.xodr", (fixtures / "minimal.xodr").read_bytes()),
    ])[0]
    projects = ProjectStore(assets)
    first = projects.create("First project")
    second = projects.create("Second project")
    assert ProjectStore(assets).last() == second
    projects.set_last(first.project_id)
    assert ProjectStore(assets).last() == first
    trace = {"candidate": {"asset_id": version.asset_id, "version_id": version.version_id},
             "reuse": {"level": "modify"}}
    path = projects.save_decision(first.project_id, version, trace)
    assert path.is_file()
    assert projects.reports(first.project_id)[0]["version_id"] == version.version_id
    with pytest.raises(ValueError, match="referenced"):
        assets.delete_version(version)


def test_decision_rejects_mismatched_version(tmp_path):
    fixtures = Path(__file__).parent / "fixtures"
    assets = AssetStore(tmp_path)
    version = assets.import_files([
        AssetFile("minimal.xosc", (fixtures / "minimal.xosc").read_bytes()),
        AssetFile("minimal.xodr", (fixtures / "minimal.xodr").read_bytes()),
    ])[0]
    projects = ProjectStore(assets)
    project = projects.create("Review")
    with pytest.raises(ValueError, match="differ"):
        projects.save_decision(project.project_id, version,
                               {"candidate": {"asset_id": version.asset_id, "version_id": "wrong"}})
