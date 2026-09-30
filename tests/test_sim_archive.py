import io
import json
import zipfile

from openx_workbench.catalog import AssetFile, build_catalog
from openx_workbench.sim_archive import expand_sim_archives


def _sim_bytes(road_name: str = "demo.xodr", include_road: bool = True) -> bytes:
    payload = {
        "caseDef": {"id": "case-001", "name": "Adjacent cut-in"},
        "caseData": {
            "openSCENARIO": {
                "FileHeader": {"revMajor": "1", "revMinor": "1", "description": "Cut-in", "author": "demo"},
                "RoadNetwork": {"LogicFile": {"filepath": road_name}},
                "Entities": {
                    "ScenarioObject": [
                        {"name": "Ego", "Vehicle": {"name": "ego", "vehicleCategory": "car"}},
                        {"name": "Target", "Vehicle": {"name": "target", "vehicleCategory": "car"}},
                    ]
                },
                "Storyboard": {"Init": {}, "StopTrigger": {}},
            }
        },
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("bundle/case/case-001.json", json.dumps(payload))
        if include_road:
            archive.writestr(
                f"map/{road_name}",
                '<OpenDRIVE><header revMajor="1" revMinor="7" name="demo"/>'
                '<road id="1" length="100"><planView><geometry s="0" x="0" y="0" hdg="0" length="100"><line/></geometry></planView>'
                '<lanes><laneSection s="0"><left/><center/><right/></laneSection></lanes></road></OpenDRIVE>',
            )
    return buffer.getvalue()


def test_sim_archive_becomes_pairable_openx_assets() -> None:
    files, reports = expand_sim_archives([AssetFile("demo.sim", _sim_bytes())])
    catalog = build_catalog(files)

    assert len(catalog) == 1
    assert catalog[0].xosc_name == "demo/case-001.xosc"
    assert catalog[0].xodr_name == "demo.xodr"
    assert catalog[0].title == "Adjacent cut-in"
    assert [entity.name for entity in catalog[0].bundle.scenario.entities] == ["Ego", "Target"]
    assert reports[0].case_count == 1
    assert reports[0].imported_count == 1
    assert reports[0].missing_road_references == ()


def test_sim_archive_reports_missing_road_and_accepts_supplement() -> None:
    sim = AssetFile("demo.sim", _sim_bytes("external.xodr", include_road=False))
    files, reports = expand_sim_archives([sim])
    assert not any(item.name.endswith(".xosc") for item in files)
    assert reports[0].missing_road_references == ("external.xodr",)

    road = AssetFile(
        "external.xodr",
        b'<OpenDRIVE><header/><road id="1" length="1"><planView/></road></OpenDRIVE>',
    )
    files, reports = expand_sim_archives([sim, road])
    assert len(build_catalog(files)) == 1
    assert reports[0].imported_count == 1


def test_sim_archive_resolves_scenariomanager_map_id_reference() -> None:
    map_id = "235c2ca0-1db7-11f1-8053-fbed59545267"
    payload = {
        "caseDef": {"id": "case-001", "name": "Obstacle response"},
        "caseData": {
            "openSCENARIO": {
                "RoadNetwork": {"LogicFile": {"filepath": f"{map_id}.xodr"}},
                "Entities": {},
                "Storyboard": {"Init": {}, "StopTrigger": {}},
            }
        },
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("bundle/case/case-001.json", json.dumps(payload))
        archive.writestr(
            f"map/{map_id}/two-lane-road.xodr",
            '<OpenDRIVE><header/><road id="1" length="10"><planView/></road></OpenDRIVE>',
        )

    files, reports = expand_sim_archives([AssetFile("l2.sim", buffer.getvalue())])
    catalog = build_catalog(files)

    assert len(catalog) == 1
    assert catalog[0].xodr_name == f"{map_id}.xodr"
    assert reports[0].contained_road_count == 1
    assert reports[0].imported_count == 1
    assert reports[0].missing_road_references == ()
