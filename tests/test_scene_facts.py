"""Authored scenarios for the structure facts read beyond element types (scene_facts)."""

import json

from openx_workbench.catalog import AssetFile, build_catalog
from openx_workbench.reuse_facts import (
    actor_actions,
    asset_structure_query,
    bundle_parameters,
    bundle_participant_signatures,
    bundle_scenery_signatures,
)
from openx_workbench.reuse_structured import compare_structure
from openx_workbench.scene_facts import asset_environment, command_facts, scenery_summary
from openx_workbench.scene_package import ScenePackage, scene_package_to_query


def vehicle(name, width=1.8, category="car"):
    return (f'<ScenarioObject name="{name}"><Vehicle name="car" vehicleCategory="{category}"><BoundingBox>'
            f'<Center x="0" y="0" z="0"/><Dimensions width="{width}" length="4.5" height="1.5"/></BoundingBox>'
            '</Vehicle></ScenarioObject>')


def pedestrian(name):
    return (f'<ScenarioObject name="{name}"><Pedestrian name="adult" pedestrianCategory="pedestrian"><BoundingBox>'
            '<Center x="0" y="0" z="0"/><Dimensions width="0.5" length="0.3" height="1.8"/></BoundingBox>'
            '</Pedestrian></ScenarioObject>')


def prop(name, model="TrafficCone"):
    return (f'<ScenarioObject name="{name}"><MiscObject name="{model}" miscObjectCategory="obstacle" mass="0">'
            '<BoundingBox><Center x="0" y="0" z="0"/><Dimensions width="0.5" length="0.5" height="1"/></BoundingBox>'
            '</MiscObject></ScenarioObject>')


def speed(value, shape="linear"):
    return (f'<PrivateAction><LongitudinalAction><SpeedAction><SpeedActionDynamics dynamicsShape="{shape}" '
            f'value="3" dynamicsDimension="time"/><SpeedActionTarget><AbsoluteTargetSpeed value="{value}"/>'
            '</SpeedActionTarget></SpeedAction></LongitudinalAction></PrivateAction>')


def relative_speed():
    return ('<PrivateAction><LongitudinalAction><SpeedAction><SpeedActionDynamics dynamicsShape="linear" '
            'value="3" dynamicsDimension="time"/><SpeedActionTarget><RelativeTargetSpeed entityRef="Ego" '
            'value="2" speedTargetValueType="delta" continuous="true"/></SpeedActionTarget></SpeedAction>'
            '</LongitudinalAction></PrivateAction>')


def command(text):
    return f'<UserDefinedAction><CustomCommandAction type="Command">{text}</CustomCommandAction></UserDefinedAction>'


def override(**channels):
    inner = "".join(f'<{name} active="true" value="{value}" number="{value}"/>' for name, value in channels.items())
    return f'<PrivateAction><ControllerAction><OverrideControllerValueAction>{inner}</OverrideControllerValueAction></ControllerAction></PrivateAction>'


def place(name, x, y, value=0.0, h=0.0):
    return (f'<Private entityRef="{name}"><PrivateAction><TeleportAction><Position><WorldPosition x="{x}" y="{y}" h="{h}"/>'
            f'</Position></TeleportAction></PrivateAction>{speed(value, "step")}</Private>')


def group(actor, *events):
    body = "".join(f'<Event name="{event}" priority="overwrite"><Action name="{event}-action">{action}</Action>'
                   '<StartTrigger/></Event>' for event, action in events)
    return (f'<ManeuverGroup name="{actor}-group" maximumExecutionCount="1"><Actors selectTriggeringEntities="false">'
            f'<EntityRef entityRef="{actor}"/></Actors><Maneuver name="{actor}-maneuver">{body}</Maneuver></ManeuverGroup>')


def scenario(entities, init, groups="", environment=""):
    return ('<OpenSCENARIO><FileHeader revMajor="1" revMinor="1" description="Authored" author="test"/>'
            '<RoadNetwork><LogicFile filepath="ThreeLanes.xodr"/></RoadNetwork>'
            f'<Entities>{vehicle("Ego")}{entities}</Entities><Storyboard><Init><Actions>{environment}{init}</Actions></Init>'
            f'<Story name="Story"><Act name="Act">{groups}</Act></Story><StopTrigger/></Storyboard></OpenSCENARIO>')


def asset(xosc, environments=(), current=None):
    """A ScenarioManager case on a built-in road: no road file, only its sidecar."""
    case = {"case_id": "c", "map_id": "ThreeLanes", "map_name": "three lanes", "road_reference": "ThreeLanes.xodr",
            "road_missing": True, "environments": list(environments), "current_environment_id": current}
    return build_catalog([AssetFile("lib/c.xosc", xosc.encode()),
                          AssetFile("lib/c.case.json", json.dumps(case).encode())])[0]


def test_story_speed_is_the_scene_speed_and_test_operations_are_dropped():
    xosc = scenario("", place("Ego", 0, 0, 0.0), group(
        "Ego", ("SpeedUp", speed(22.22)), ("OnSysEngage", command("SysEngReq")),
        ("Brake", command("BrakePosition=0.5")), ("TurnOff", command("TurnOff")),
        ("just_for_test", speed(0, "step"))))
    item = asset(xosc)
    assert actor_actions(item.bundle, "Ego") == {"cruise", "system_control"}
    assert bundle_parameters(item.bundle)["ego_speed_kph"] == (79.992,)
    assert command_facts(item.bundle)["brake"]


def test_a_transition_to_standstill_is_a_stop_and_a_step_is_a_reset():
    braking = scenario(vehicle("T1"), place("Ego", 0, 0, 10) + place("T1", 30, 0, 10),
                       group("T1", ("brake", speed(0, "linear"))))
    reset = scenario(vehicle("T1"), place("Ego", 0, 0, 10) + place("T1", 30, 0, 10),
                     group("T1", ("reinit", speed(0, "step"))))
    assert actor_actions(asset(braking).bundle, "T1") == {"stop"}
    assert actor_actions(asset(reset).bundle, "T1") == {"cruise"}


def test_relative_speed_means_moving_at_no_stated_speed():
    xosc = scenario(vehicle("T1"), place("Ego", 0, 0, 10) + place("T1", -20, 3.5, 0),
                    group("T1", ("follow", relative_speed())))
    assert actor_actions(asset(xosc).bundle, "T1") == {"unknown"}


def test_commands_read_function_lane_change_parking_and_door():
    xosc = scenario("", place("Ego", 0, 0, 10), group(
        "Ego", ("on", command("EnableNOA")), ("lc", command("LaneOffset=left")),
        ("door", command("FrontLeftDoor=Open"))))
    item = asset(xosc)
    facts = command_facts(item.bundle)
    assert (facts["function"], facts["lane_change"], facts["door_open"]) == ("NOA", True, True)
    assert actor_actions(item.bundle, "Ego") == {"cruise", "lane_change", "system_control"}
    assert asset_structure_query(item).tested_function == "NOA"
    parking = asset(scenario("", place("Ego", 0, 0, 0), group(
        "Ego", ("apa", command("EnableAPA;ParkingOut;Target=(1,2,0)")))))
    assert asset_structure_query(parking).parking_operation == "park_out"


def test_driver_overrides_make_an_intervention_test_and_reverse_gear_reverses():
    xosc = scenario("", place("Ego", 0, 0, 10), group(
        "Ego", ("intervene", override(SteeringWheel=0.3)), ("reverse", override(Gear=-1))))
    item = asset(xosc)
    query = asset_structure_query(item)
    assert query.driver_intervention
    assert "reverse" in query.ego_actions


def test_preset_completes_the_environment_without_its_fog_level():
    presets = [{"id": "sunny01", "category": "sunny", "time": "20:00:00", "fog": 3, "rain": 0},
               {"id": "rainy02", "category": "sunny", "time": "12:00:00", "fog": 3, "rain": 6.28}]
    item = asset(scenario("", place("Ego", 0, 0, 10)), presets, current="rainy02")
    assert asset_environment(item.bundle) == {"weather": "rain", "time_of_day": "day"}
    night = asset(scenario("", place("Ego", 0, 0, 10)), presets[:1])
    assert asset_environment(night.bundle) == {"weather": "dry", "time_of_day": "night"}


def test_story_environment_outranks_the_preset():
    fog = ('<GlobalAction><EnvironmentAction><Environment name="Fog"><TimeOfDay animation="false" '
           'dateTime="2020-11-11T15:00:00"/><Weather cloudState="overcast"><Fog visualRange="150"/>'
           '<Precipitation precipitationType="dry" intensity="0"/></Weather></Environment></EnvironmentAction></GlobalAction>')
    events = (f'<ManeuverGroup name="env" maximumExecutionCount="1"><Actors selectTriggeringEntities="false"/>'
              f'<Maneuver name="m"><Event name="Fog_150m" priority="overwrite"><Action name="fog">{fog}</Action>'
              '<StartTrigger/></Event></Maneuver></ManeuverGroup>')
    item = asset(scenario("", place("Ego", 0, 0, 10), events),
                 [{"id": "sunny01", "category": "sunny", "time": "20:00:00"}])
    assert asset_environment(item.bundle) == {"weather": "fog", "time_of_day": "day", "fog_visibility_m": 150.0}


def test_props_are_scenery_that_can_stand_for_a_requested_obstacle():
    cones = "".join(prop(f"cone{index}") for index in range(5)) + prop("barrier", "Barrier")
    init = place("Ego", 0, 0, 10) + "".join(place(f"cone{index}", 40 + index, 0) for index in range(5))
    item = asset(scenario(cones, init + place("barrier", 45, 0)))
    assert bundle_participant_signatures(item.bundle) == ()
    assert [signature.key() for signature in bundle_scenery_signatures(item.bundle)] == [
        "obstacle@front_same_lane:unknown:static"]
    assert scenery_summary(item.bundle)["models"] == {"TrafficCone": 5, "Barrier": 1}

    package = ScenePackage("REQ", "Obstacle", "", structure={
        "ego_actions": ["匀速行驶"],
        "participants": [{"kind": "障碍物", "bearing": "正前方", "facing": "横向", "actions": ["静止"]}]})
    differences = compare_structure(scene_package_to_query(package), item)
    assert not [difference for difference in differences if difference.category.startswith("participant")]


def test_occlusion_is_read_from_widths_and_the_crossing_sweep():
    entities = vehicle("Parked", width=1.8) + pedestrian("Walker")
    init = place("Ego", 0, 0, 10) + place("Parked", 20, -3.5) + place("Walker", 25, -8, 1.5, h=1.5708)
    item = asset(scenario(entities, init))
    query = asset_structure_query(item)
    assert ("vehicle", "pedestrian") in query.occlusions

    requested = ScenePackage("REQ", "Occluded", "", structure={
        "participants": [{"kind": "乘用车", "bearing": "右前方", "facing": "同向", "actions": ["静止"]},
                         {"kind": "行人", "bearing": "右前方", "facing": "横向", "actions": ["匀速行驶"]}],
        "relations": [{"subject": "乘用车", "relation": "遮挡", "object": "行人"}],
        "test_intent": "驾驶员干预试验"})
    request = scene_package_to_query(requested)
    assert request.occlusions == {("vehicle", "pedestrian")} and request.driver_intervention
    differences = compare_structure(request, item)
    assert not [difference for difference in differences if difference.category == "relation"]
    assert [difference.requested for difference in differences if difference.category == "ego_action"] == [
        "driver_intervention"]
