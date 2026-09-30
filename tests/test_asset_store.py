from pathlib import Path
import io
import json
import zipfile

import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile


FIXTURES = Path(__file__).parent / "fixtures"


def _files(xosc: bytes | None = None) -> list[AssetFile]:
    return [
        AssetFile("minimal.xosc", xosc or (FIXTURES / "minimal.xosc").read_bytes()),
        AssetFile("minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes()),
    ]


def test_global_versions_are_immutable_and_reopenable(tmp_path):
    store = AssetStore(tmp_path)
    first = store.import_files(_files())[0]
    assert store.import_files(_files())[0].version_id == first.version_id
    changed = (FIXTURES / "minimal.xosc").read_bytes().replace(b"Minimal cut-in", b"Changed cut-in")
    second = store.import_files(_files(changed))[0]
    assert first.asset_id == second.asset_id
    assert first.version_id != second.version_id
    assert (first.version_number, second.version_number) == (1, 2)
    assert AssetStore(tmp_path).file_bytes(first, "scenario") != AssetStore(tmp_path).file_bytes(second, "scenario")
    latest, mapping = AssetStore(tmp_path).catalog()
    assert len(latest) == 1
    assert mapping[latest[0].asset_id].version_id == second.version_id


def test_referenced_version_cannot_be_deleted(tmp_path):
    store = AssetStore(tmp_path)
    version = store.import_files(_files())[0]
    store.pin_version("project-1", version)
    with pytest.raises(ValueError, match="referenced"):
        AssetStore(tmp_path).delete_version(version)
    assert len(store.versions()) == 1


def test_sim_cases_share_one_original_archive_blob(tmp_path):
    road = (FIXTURES / "minimal.xodr").read_bytes()
    payload = {"RoadNetwork": {"LogicFile": {"filepath": "minimal.xodr"}},
               "Entities": {}, "Storyboard": {"Init": {}, "StopTrigger": {}}}
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("map/minimal.xodr", road)
        for case_id in ("one", "two"):
            archive.writestr(f"bundle/case/{case_id}.json", json.dumps({
                "caseDef": {"id": case_id, "name": case_id},
                "caseData": {"openSCENARIO": payload},
            }))
    store = AssetStore(tmp_path)
    versions = store.import_files([AssetFile("sample.sim", archive_bytes.getvalue())])
    assert len(versions) == 2
    assert len(list((tmp_path / "blobs").iterdir())) == 1
    assert all(store.file_bytes(version, "source") == archive_bytes.getvalue() for version in versions)
    store.delete_version(versions[0])
    assert len(list((tmp_path / "blobs").iterdir())) == 1
    store.delete_version(versions[1])
    assert not list((tmp_path / "blobs").iterdir())
