from pathlib import Path
import hashlib
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


def _built_in_road_sim() -> bytes:
    payload = {"RoadNetwork": {"LogicFile": {"filepath": "ThreeLanes.xodr"}},
               "Entities": {}, "Storyboard": {"Init": {}, "StopTrigger": {}}}
    archive_bytes = io.BytesIO()
    with zipfile.ZipFile(archive_bytes, "w") as archive:
        archive.writestr("bundle/case/one.json", json.dumps({
            "caseDef": {"id": "one", "name": "one", "mapId": "ThreeLanes", "mapName": "three lanes"},
            "caseData": {"openSCENARIO": payload, "environments": {"byId": {}, "allIds": []}},
        }))
    return archive_bytes.getvalue()


def test_sim_case_without_its_road_is_stored_and_reopened(tmp_path):
    store = AssetStore(tmp_path)
    version = store.import_files([AssetFile("built-in.sim", _built_in_road_sim())])[0]
    assert version.road_missing and version.compatibility == "road_missing"
    assert {record["role"] for record in version.files} == {"source", "scenario", "case"}
    with pytest.raises(FileNotFoundError):
        store.file_bytes(version, "road")
    assets, _ = AssetStore(tmp_path).catalog()
    assert assets[0].bundle.road.file_missing
    assert assets[0].bundle.road.inferred_features == ["straight"]
    assert assets[0].bundle.source_case["map_id"] == "ThreeLanes"


def test_reimport_adds_case_metadata_to_an_older_version(tmp_path):
    store = AssetStore(tmp_path)
    sim = AssetFile("sample.sim", _built_in_road_sim())
    version = store.import_files([sim])[0]
    folder = tmp_path / "assets" / version.asset_id / version.version_id
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    manifest["files"] = [record for record in manifest["files"] if record["role"] != "case"]
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    (folder / "case.json").unlink()

    again = AssetStore(tmp_path).import_files([sim])[0]
    assert again.version_id == version.version_id and again.version_number == 1
    assert any(record["role"] == "case" for record in again.files)
    assert AssetStore(tmp_path).catalog()[0][0].bundle.source_case["map_name"] == "three lanes"


def test_reimport_refreshes_case_metadata_read_before_more_was_kept(tmp_path):
    store = AssetStore(tmp_path)
    sim = AssetFile("sample.sim", _built_in_road_sim())
    version = store.import_files([sim])[0]
    folder = tmp_path / "assets" / version.asset_id / version.version_id
    older = json.loads((folder / "case.json").read_text(encoding="utf-8"))
    del older["judgements"]
    (folder / "case.json").write_bytes(json.dumps(older).encode("utf-8"))
    manifest = json.loads((folder / "manifest.json").read_text(encoding="utf-8"))
    for record in manifest["files"]:
        if record["role"] == "case":
            record["sha256"] = hashlib.sha256((folder / "case.json").read_bytes()).hexdigest()
    (folder / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    assert "judgements" not in AssetStore(tmp_path).catalog()[0][0].bundle.source_case

    again = AssetStore(tmp_path).import_files([sim])[0]
    assert again.version_id == version.version_id
    assert [record["role"] for record in again.files].count("case") == 1
    assert AssetStore(tmp_path).catalog()[0][0].bundle.source_case["judgements"] == []


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
