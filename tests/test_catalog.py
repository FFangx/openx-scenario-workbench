from pathlib import Path

import pytest

from openx_workbench.catalog import AssetFile, build_catalog, build_catalog_from_directory


FIXTURES = Path(__file__).parent / "fixtures"


def test_catalog_pairs_xosc_with_its_referenced_xodr():
    assets = build_catalog(
        [
            AssetFile("scenes/minimal.xosc", (FIXTURES / "minimal.xosc").read_bytes()),
            AssetFile("roads/minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes()),
        ]
    )

    assert len(assets) == 1
    assert assets[0].title == "Minimal cut-in"
    assert assets[0].xodr_name == "roads/minimal.xodr"
    assert assets[0].bundle.road.lane_count == 3


def test_catalog_reports_a_missing_road_reference():
    with pytest.raises(ValueError, match="minimal.xodr"):
        build_catalog(
            [AssetFile("minimal.xosc", (FIXTURES / "minimal.xosc").read_bytes())]
        )


def test_catalog_builds_from_a_directory(tmp_path):
    (tmp_path / "minimal.xosc").write_bytes((FIXTURES / "minimal.xosc").read_bytes())
    (tmp_path / "minimal.xodr").write_bytes((FIXTURES / "minimal.xodr").read_bytes())

    assert len(build_catalog_from_directory(tmp_path)) == 1
