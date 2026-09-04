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


def test_parse_xodr_summarizes_network():
    road = parse_xodr((FIXTURES / "minimal.xodr").read_bytes())
    assert road.revision == "1.7"
    assert road.road_ids == ["1"]
    assert road.lane_count == 3


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
