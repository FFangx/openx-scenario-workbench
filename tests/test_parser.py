from pathlib import Path

import pytest

from openx_workbench.parser import parse_bundle, parse_xodr, parse_xosc


FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_xosc_extracts_public_scenario_structure():
    scenario = parse_xosc((FIXTURES / "minimal.xosc").read_bytes())
    assert scenario.revision == "1.2"
    assert scenario.road_file == "minimal.xodr"
    assert [entity.name for entity in scenario.entities] == ["Ego", "Target"]
    assert any(action.kind == "SpeedAction" for action in scenario.actions)
    assert any(trigger.kind == "SimulationTimeCondition" for trigger in scenario.triggers)
    assert any(
        trigger.value == 1.0 and trigger.rule == "greaterThan"
        for trigger in scenario.triggers
    )
    assert any(position.actor == "Ego" for position in scenario.positions)


def test_parse_xodr_summarizes_network():
    road = parse_xodr((FIXTURES / "minimal.xodr").read_bytes())
    assert road.revision == "1.7"
    assert road.road_ids == ["1"]
    assert road.total_length == 100.0
    assert road.lane_count == 3
    assert road.lane_types == {"driving": 2, "none": 1}
    assert road.geometry_types == {"line": 1}


def test_parse_xodr_reads_speed_limits_traffic_lights_and_marked_areas():
    road = parse_xodr(
        '<OpenDRIVE><header revMajor="1" revMinor="6"/><road id="1" length="100"><planView/>'
        '<objects><object id="1" type="crosswalk" s="10" t="0"/><object id="2" type="stopline" s="20" t="0"/>'
        '<object id="3" type="parkingSpace" s="30" t="0"/><object id="4" type="pole" s="40" t="0"/></objects>'
        '<signals><signal id="1" s="5" t="3" dynamic="no" country="CHN" type="1010203800001413" value="80" unit="km/h"/>'
        '<signal id="2" s="9" t="3" dynamic="no" country="DE" type="274" value="30" unit="mph"/>'
        '<signal id="3" s="50" t="3" dynamic="yes" type="1.000.001" value="-1"/>'
        '<signal id="4" s="60" t="3" dynamic="no" type="Graphics" value="0" unit="m"/></signals></road></OpenDRIVE>')
    assert road.speed_limits_kph == [48.3, 80.0]
    assert road.furniture == {"crosswalk": 1, "parking_space": 1, "stop_line": 1, "traffic_light": 1}


def test_bundle_warns_when_filename_does_not_match():
    bundle = parse_bundle(
        (FIXTURES / "minimal.xosc").read_bytes(),
        (FIXTURES / "minimal.xodr").read_bytes(),
        "another-road.xodr",
    )
    assert "road_file_mismatch" in bundle.warnings


@pytest.mark.parametrize("parse", [parse_xosc, parse_xodr])
def test_parser_rejects_a_different_xml_document(parse):
    with pytest.raises(ValueError, match="root element"):
        parse("<unrelated />")
