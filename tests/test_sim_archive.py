import io
import json
import zipfile
from xml.etree import ElementTree as ET

import pytest

from openx_workbench.catalog import AssetFile, build_catalog
from openx_workbench.parser import map_road_features
from openx_workbench.sim_archive import expand_sim_archives, _osc_json_to_xml

RAIN_PRESET = {"id": "rainy02", "category": "rainy", "time": "20:00:00", "rain": 3, "snow": 0, "fog": 3}


LANE_CRITERION = {
    "id": "c65b", "name": "custom", "type": "customized", "category": "general", "enabled": True,
    "scope": {"type": "global", "position": {"x": -160.25, "y": -100.5, "z": 0}},
    "conditions": [{"variable": "dtlc", "operator": "gt", "value": 1.75}],
    "settings": {"action": "failure", "logLevel": "info", "logInfo": ""}, "builtIn": True, "lock": True,
}


def _sim_bytes(road_name: str = "demo.xodr", include_road: bool = True,
               map_id: str = "demo", map_name: str = "three-lane junction") -> bytes:
    payload = {
        "caseDef": {"id": "case-001", "name": "Adjacent cut-in", "mapId": map_id, "mapName": map_name},
        "caseData": {
            "environments": {"byId": {"rainy02": RAIN_PRESET}, "allIds": ["rainy02"]},
            "currEnvId": "rainy02",
            "judgements": {"byId": {"c65b": LANE_CRITERION}, "allIds": ["c65b"]},
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


def test_sim_custom_command_preserves_text_in_open_scenario_simple_content():
    content = ' {"command": "speed < 10 & ready", "enabled": true}\n'
    data = {"Storyboard": {"Init": {"Actions": {"UserDefinedAction": {
        "CustomCommandAction": {"type": "simulation", "content": content}
    }}}}}
    xml = ET.fromstring(_osc_json_to_xml(data, "Authored command"))
    command = xml.find(".//CustomCommandAction")
    assert command.attrib == {"type": "simulation"}
    assert command.text == content


def test_sim_root_order_does_not_depend_on_json_parameter_edit_order():
    data = {"Storyboard": {}, "Entities": {}, "RoadNetwork": {},
            "CatalogLocations": {}, "FileHeader": {"revMajor": "1", "revMinor": "2"},
            "VendorExtension": {"enabled": True}, "VariableDeclarations": {},
            "ParameterDeclarations": {"ParameterDeclaration": {
                "name": "$speed", "parameterType": "double", "value": "12.5"}}}
    xml = ET.fromstring(_osc_json_to_xml(data, "Authored parameters"))
    assert [child.tag for child in xml] == [
        "FileHeader", "ParameterDeclarations", "VariableDeclarations",
        "CatalogLocations", "RoadNetwork", "Entities", "Storyboard", "VendorExtension"]
    assert xml.find("ParameterDeclarations/ParameterDeclaration").get("name") == "$speed"
    assert xml.find("VendorExtension").get("enabled") == "true"
    assert next(iter(data)) == "Storyboard"  # Input remains untouched.


def test_sim_case_keeps_map_and_environment_presets() -> None:
    files, _ = expand_sim_archives([AssetFile("demo.sim", _sim_bytes())])
    sidecar = next(item for item in files if item.name == "demo/case-001.case.json")
    case = json.loads(sidecar.data)
    assert (case["map_id"], case["map_name"]) == ("demo", "three-lane junction")
    assert case["environments"] == [RAIN_PRESET]
    assert case["current_environment_id"] == "rainy02"
    assert case["road_missing"] is False
    assert case["judgements"] == [{"type": "customized", "name": "custom", "enabled": True, "scope": "global",
                                   "conditions": [{"variable": "dtlc", "operator": "gt", "value": 1.75}],
                                   "action": "failure"}]
    asset = build_catalog(files)[0]
    assert asset.bundle.source_case["map_name"] == "three-lane junction"
    assert not asset.bundle.road.file_missing


def test_sim_case_with_missing_built_in_road_is_matchable_not_previewable() -> None:
    sim = AssetFile("demo.sim", _sim_bytes("Junction3.xodr", include_road=False, map_id="Junction3"))
    files, reports = expand_sim_archives([sim])
    assert reports[0].missing_road_references == ("Junction3.xodr",)
    assert (reports[0].imported_count, reports[0].road_missing_count) == (1, 1)

    asset = build_catalog(files)[0]
    assert asset.xodr_name == ""
    assert asset.bundle.road.file_missing
    assert asset.bundle.road.name == "three-lane junction"
    assert asset.bundle.road.inferred_features == ["junction"]
    assert asset.bundle.validation["road"]["status"] == "missing"
    assert "road_file_missing" in asset.bundle.warnings
    assert [entity.name for entity in asset.bundle.scenario.entities] == ["Ego", "Target"]

    road = AssetFile(
        "Junction3.xodr",
        b'<OpenDRIVE><header/><road id="1" length="1"><planView/></road></OpenDRIVE>',
    )
    files, reports = expand_sim_archives([sim, road])
    asset = build_catalog(files)[0]
    assert asset.xodr_name == "Junction3.xodr" and not asset.bundle.road.file_missing
    assert (reports[0].imported_count, reports[0].road_missing_count) == (1, 0)


def test_standalone_scenario_still_requires_its_road() -> None:
    files, _ = expand_sim_archives([AssetFile("demo.sim", _sim_bytes("external.xodr", include_road=False))])
    with pytest.raises(ValueError, match="external.xodr"):
        build_catalog([item for item in files if not item.name.endswith(".case.json")])


@pytest.mark.parametrize(("names", "features"), [
    (("Junction3", "three-lane junction"), ["junction"]),
    (("FourLanesIntersection",), ["junction"]),
    (("two-lane roundabout junction",), ["roundabout"]),
    (("park_ground", "ground parking lot"), ["parking"]),
    (("TwoLanesSameDirection_walkCross",), ["straight"]),
    (("ThreeLanes",), ["straight"]),
    (("SeniorScene_CityHighWay",), ["motorway"]),
    (("straight_and_r=500",), ["curve"]),
    (("Town07",), []),
])
def test_map_name_road_type(names, features) -> None:
    assert map_road_features(*names) == features


def test_sim_archive_resolves_scenariomanager_map_id_reference() -> None:
    map_id = "7f3a1c20-0b5e-4d2a-9c41-5e8d2b6f0a17"
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
