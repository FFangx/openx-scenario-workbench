from pathlib import Path

import pytest

from openx_workbench.parser import parse_xosc
from openx_workbench.retrieval import HashingEncoder, OpenXIndex
from test_structured_reuse import authored_asset, requirement
from openx_workbench.scene_package import scene_package_to_query


FIXTURES = Path(__file__).parent / "fixtures"


def source(declarations, speed="$speed"):
    xml = (FIXTURES / "minimal.xosc").read_text(encoding="utf-8")
    return xml.replace('value="12.5"', f'value="{speed}"').replace("<RoadNetwork>", declarations + "<RoadNetwork>")


def test_lexical_shadowing_aliases_and_parameterized_road_are_audited():
    xml = source('''<ParameterDeclarations>
      <ParameterDeclaration name="speed" parameterType="double" value="12.5"/>
      <ParameterDeclaration name="alias" parameterType="double" value="$speed"/>
      <ParameterDeclaration name="road" parameterType="string" value="minimal.xodr"/>
      </ParameterDeclarations>''', "$alias")
    xml = xml.replace('filepath="minimal.xodr"', 'filepath="$road"')
    xml = xml.replace('<Story name="Story">', '''<Story name="Story"><ParameterDeclarations>
      <ParameterDeclaration name="speed" parameterType="double" value="99"/>
      </ParameterDeclarations>''')
    parsed = parse_xosc(xml)
    assert parsed.road_file == "minimal.xodr"
    assert next(action for action in parsed.actions if action.kind == "SpeedAction").target_value == 12.5
    assert parsed.parameter_resolutions[-1]["raw"] == "$alias"
    assert not parsed.parameter_issues
    assert 'value="$alias"' in xml  # Only the parsed view changes.


def test_numeric_expression_and_event_condition_ownership():
    parsed = parse_xosc(source('''<ParameterDeclarations>
      <ParameterDeclaration name="speed" parameterType="double" value="36"/>
      </ParameterDeclarations>''', "${($speed + 9) / 3.6}"))
    assert next(action for action in parsed.actions if action.kind == "SpeedAction").target_value == 12.5
    event = parsed.events[0]
    assert event["name"] == "Event" and event["priority"] == "overwrite"
    assert event["actions"] == [parsed.actions[-1].source_path]
    assert event["conditions"] == [parsed.triggers[0].source_path]
    assert parsed.triggers[0].event_path == event["source_path"]
    assert parsed.triggers[0].attributes == {"value": "1", "rule": "greaterThan"}


def test_sim_prefixed_declaration_resolves_without_changing_source_or_audit():
    xml = source('''<ParameterDeclarations>
      <ParameterDeclaration name="$speed" parameterType="double" value="12.5"/>
      <ParameterDeclaration name="$alias" parameterType="double" value="$speed"/>
      </ParameterDeclarations>''', "$alias")
    parsed = parse_xosc(xml)
    assert parsed.actions[-1].target_value == 12.5
    assert not parsed.parameter_issues
    assert parsed.parameters[0]["name"] == "$speed"
    assert parsed.parameter_resolutions[-1]["raw"] == "$alias"
    assert 'name="$speed"' in xml


@pytest.mark.parametrize("names", [("speed", "$speed"), ("$speed", "speed"), ("speed", "speed")])
def test_conflicting_parameter_declarations_remain_unresolved(names):
    xml = source('<ParameterDeclarations>' + ''.join(
        f'<ParameterDeclaration name="{name}" parameterType="double" value="{value}"/>'
        for name, value in zip(names, (12.5, 99))
    ) + '</ParameterDeclarations>')
    parsed = parse_xosc(xml)
    assert parsed.actions[-1].target_value is None
    assert any("ambiguous" in issue["detail"] for issue in parsed.parameter_issues)


@pytest.mark.parametrize("value", ["$missing", "${1/0}", "${__import__('os')}", "${2 ** 3}", "${1e309}", "$speed"])
def test_unresolved_or_unsupported_expression_is_retained(value):
    parsed = parse_xosc(source('''<ParameterDeclarations>
      <ParameterDeclaration name="speed" parameterType="double" value="$speed"/>
      </ParameterDeclarations>''', value))
    assert parsed.actions[-1].target_value is None
    assert parsed.parameter_issues[0]["raw"] == value


def test_global_story_action_is_not_counted_twice_and_init_phase_is_preserved():
    xml = (FIXTURES / "minimal.xosc").read_text(encoding="utf-8")
    xml = xml.replace('<Action name="Accelerate">', '<Action name="Accelerate"><GlobalAction><EnvironmentAction/></GlobalAction>')
    xml = xml.replace("<Actions>", "<Actions><GlobalAction><EnvironmentAction/></GlobalAction>")
    parsed = parse_xosc(xml)
    global_actions = [action for action in parsed.actions if action.kind == "EnvironmentAction"]
    assert len(global_actions) == 2
    assert {action.phase for action in global_actions} == {"init", "story"}
    assert all(action.actor is None for action in global_actions)


def test_unresolved_candidate_parameter_prevents_direct_reuse():
    asset = authored_asset()
    asset.bundle.scenario.parameter_issues = [{"path": "/OpenSCENARIO[1]", "attribute": "value", "raw": "$missing", "detail": "undeclared"}]
    result = OpenXIndex([asset], HashingEncoder(32)).search("", query=scene_package_to_query(requirement()))[0]
    assert result.reuse_level == "review"
    assert result.review_kind == "partial"
    assert result.differences[0].category == "parameter_resolution"


def test_dynamic_parameter_mutation_is_not_treated_as_static_evidence():
    xml = source('''<ParameterDeclarations>
      <ParameterDeclaration name="speed" parameterType="double" value="12.5"/>
      </ParameterDeclarations>''')
    xml = xml.replace("<Actions>", '<Actions><GlobalAction><ParameterAction parameterRef="speed"><SetAction value="20"/></ParameterAction></GlobalAction>')
    parsed = parse_xosc(xml)
    assert parsed.actions[-2].target_value == 12.5
    assert "execution review" in parsed.parameter_issues[0]["detail"]
