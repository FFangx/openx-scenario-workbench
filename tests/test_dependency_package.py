import io
import zipfile
from pathlib import Path

import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile
from openx_workbench.dependency_package import package_files, stage_package


FIXTURES = Path(__file__).parent / "fixtures"


def _zip(entries: dict[str, bytes]) -> bytes:
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        for name, content in entries.items():
            archive.writestr(name, content)
    return output.getvalue()


def test_dependency_package_preserves_original_layout_and_version(tmp_path):
    original = (FIXTURES / "minimal.xosc").read_bytes().replace(
        b'filepath="minimal.xodr"', b'filepath="../Roads/minimal.xodr"'
    )
    archive = _zip({"Scenes/minimal.xosc": original,
                    "Roads/minimal.xodr": (FIXTURES / "minimal.xodr").read_bytes(),
                    "Catalogs/Vehicles.xml": b"<Catalog/>"})
    store = AssetStore(tmp_path / "store")
    first = store.import_files([AssetFile("portable.zip", archive)])[0]
    assert store.import_files([AssetFile("portable.zip", archive)])[0].version_id == first.version_id
    assert first.xosc_name == "Scenes/minimal.xosc"
    assert store.file_bytes(first, "source") == archive
    assert store.file_bytes(first, "dependency", "Catalogs/Vehicles.xml") == b"<Catalog/>"
    assert any(file["role"] == "dependency" and file["original_name"] == "Catalogs/Vehicles.xml"
               for file in first.files)
    stage_package(store.file_bytes(first, "source"), tmp_path / "staged")
    assert (tmp_path / "staged" / "Scenes" / "minimal.xosc").read_bytes() == original
    assert (tmp_path / "staged" / "Catalogs" / "Vehicles.xml").read_bytes() == b"<Catalog/>"
    updated = _zip({"Scenes/minimal.xosc": original,
                    "Roads/minimal.xodr": (FIXTURES / "minimal.xodr").read_bytes(),
                    "Catalogs/Vehicles.xml": b"<Catalog updated='true'/>"})
    second = store.import_files([AssetFile("portable.zip", updated)])[0]
    assert first.asset_id == second.asset_id
    assert second.version_number == 2


@pytest.mark.parametrize("name", ["../outside.xosc", "/absolute.xosc", "C:/drive.xosc",
                                         "Scenes/../outside.xosc", "Scenes//inside.xosc"])
def test_dependency_package_rejects_unsafe_paths(name):
    with pytest.raises(ValueError, match="Unsafe"):
        package_files(_zip({name: b"x"}))


def test_dependency_package_rejects_case_insensitive_duplicate_paths():
    with pytest.raises(ValueError, match="Duplicate"):
        package_files(_zip({"A.xosc": b"x", "a.xosc": b"y"}))


def test_dependency_package_pairs_road_by_relative_path(tmp_path):
    original = (FIXTURES / "minimal.xosc").read_bytes().replace(
        b'filepath="minimal.xodr"', b'filepath="../Roads/A/minimal.xodr"'
    )
    road = (FIXTURES / "minimal.xodr").read_bytes()
    archive = _zip({"Scenes/minimal.xosc": original,
                    "Roads/A/minimal.xodr": road,
                    "Roads/B/minimal.xodr": road.replace(b'name="', b'name="other-')})
    store = AssetStore(tmp_path)
    version = store.import_files([AssetFile("two-roads.zip", archive)])[0]
    assert version.xodr_name == "Roads/A/minimal.xodr"
    assert store.file_bytes(version, "road") == road
