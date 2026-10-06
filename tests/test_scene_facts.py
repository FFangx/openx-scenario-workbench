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
from openx_workbench.reuse import classify_reuse_level
from openx_workbench.scene_facts import (
    asset_environment,
    background_participants,
    command_facts,
    lateral_direction,
    named_conditions,
    route_turn,
    scenery_summary,
    scoring_criteria,
)
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


def asset(xosc, environments=(), current=None, judgements=()):
    """A ScenarioManager case on a built-in road: no road file, only its sidecar."""
    case = {"case_id": "c", "map_id": "ThreeLanes", "map_name": "three lanes", "road_reference": "ThreeLanes.xodr",
            "road_missing": True, "environments": list(environments), "current_environment_id": current,
            "judgements": list(judgements)}
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


def criterion(kind, *conditions, enabled=True):
    return {"type": kind, "name": kind, "enabled": enabled, "scope": "global", "action": "failure",
            "conditions": [dict(zip(("variable", "operator", "value"), item)) for item in conditions]}


def test_scoring_criteria_skip_the_defaults_every_case_carries():
    judgements = [criterion("timeout", ("timeout", None, 600)), criterion("collision", enabled=False),
                  criterion("customized", ("lonacc", "lt", -5)), criterion("customized", ("lonacc", "ge", 5.0)),
                  criterion("customized", ("dtlc", "gt", 0.3), enabled=False), criterion("offtrack"),
                  criterion("stopandgo", ("stopTrigger", None, {"red": True, "vru": False}),
                            ("startDelay", None, 10))]
    item = asset(scenario("", place("Ego", 0, 0, 10)), judgements=judgements)
    assert scoring_criteria(item.bundle) == (
        "lonacc<-5", "lonacc>=5", "offtrack", "stopandgo: stopTrigger=red, startDelay=10")
    assert scoring_criteria(asset(scenario("", place("Ego", 0, 0, 10))).bundle) == ()


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


def watched_by(actor, watched):
    """A maneuver group whose event starts when the ego comes near `watched`."""
    condition = ('<Condition name="near" delay="0" conditionEdge="rising"><ByEntityCondition><TriggeringEntities '
                 'triggeringEntitiesRule="any"><EntityRef entityRef="Ego"/></TriggeringEntities><EntityCondition>'
                 f'<RelativeDistanceCondition entityRef="{watched}" relativeDistanceType="longitudinal" value="30" '
                 'freespace="false" rule="lessThan"/></EntityCondition></ByEntityCondition></Condition>')
    return group(actor, ("go", speed(5))).replace("<StartTrigger/>",
                                                  f"<StartTrigger><ConditionGroup>{condition}</ConditionGroup></StartTrigger>")


def test_background_participants_take_no_part_in_the_test():
    # A lead car brakes; a row of parked cars stands in the ego's lane edge, another row and a
    # bystander further left. Of the row in the path only the first is met, the rest is hidden.
    lane_row = [f"Lane{index}" for index in range(4)]
    side_row = [f"Side{index}" for index in range(3)]
    entities = vehicle("Lead") + "".join(map(vehicle, lane_row + side_row)) + pedestrian("Bystander")
    init = (place("Ego", 0, 0, 10) + place("Lead", 20, 0, 10)
            + "".join(place(name, 50 + 6 * index, -0.9) for index, name in enumerate(lane_row))
            + "".join(place(name, 50 + 6 * index, 5.5) for index, name in enumerate(side_row))
            + place("Bystander", 60, 9))
    item = asset(scenario(entities, init, group("Lead", ("brake", speed(0)))))
    assert background_participants(item.bundle) == {name.casefold() for name in lane_row[1:] + side_row + ["Bystander"]}
    signatures = {signature.actor: signature.background for signature in asset_structure_query(item).participant_signatures}
    assert not signatures["Lead"] and not signatures["Lane0"] and signatures["Side0"]


def test_referenced_occluding_and_lone_participants_take_part():
    # The watched car is referenced by a condition; the van hides the crossing pedestrian.
    entities = vehicle("Watched") + vehicle("Van", width=2.2) + pedestrian("Walker") + vehicle("Far")
    init = (place("Ego", 0, 0, 10) + place("Watched", -30, 3.5) + place("Van", 20, -3.5)
            + place("Walker", 25, -8) + place("Far", 80, 12))
    item = asset(scenario(entities, init, watched_by("Walker", "Watched")))
    assert background_participants(item.bundle) == {"far"}
    # With nothing taking part there is no lead to set a background against.
    lone = asset(scenario(vehicle("Parked"), place("Ego", 0, 0, 10) + place("Parked", 80, 12)))
    assert background_participants(lone.bundle) == frozenset()


def test_a_thin_pedestrian_hides_no_car():
    entities = pedestrian("Walker") + vehicle("Parked")
    init = place("Ego", 0, 0, 10) + place("Walker", 40, 0) + place("Parked", 44, 0)
    item = asset(scenario(entities, init, group("Ego", ("on", command("EnableAEB")))))
    assert background_participants(item.bundle) == frozenset()


def test_left_over_background_costs_little_and_is_grouped():
    parked = [f"Parked{index}" for index in range(6)]
    entities = vehicle("Lead") + "".join(map(vehicle, parked))
    init = place("Ego", 0, 0, 10) + place("Lead", 30, 0, 10) + "".join(
        place(name, 40 + 6 * index, 5.5) for index, name in enumerate(parked))
    item = asset(scenario(entities, init, group("Lead", ("brake", speed(0)))))
    package = ScenePackage("REQ", "Lead brakes", "", structure={
        "participants": [{"kind": "乘用车", "bearing": "正前方", "facing": "同向", "actions": ["刹停"]}]})
    differences = [difference for difference in compare_structure(scene_package_to_query(package), item)
                   if difference.category.endswith("participant") or difference.category.startswith("participant")]
    assert [(difference.category, difference.candidate) for difference in differences] == [
        ("background_participant", "6 × vehicle@front_left:same:static")]
    assert classify_reuse_level(tuple(differences)) == "modify"


def checks(xosc, *names):
    """The scenario stops on the library's named checks (UserDefinedValueCondition)."""
    conditions = "".join(
        f'<Condition name="{name}" delay="0" conditionEdge="rising"><ByValueCondition>'
        f'<UserDefinedValueCondition name="{name}" value="1" rule="equalTo"/></ByValueCondition></Condition>'
        for name in ("EndTheCase", *names))
    return xosc.replace("<StopTrigger/></Storyboard>",
                        f"<StopTrigger><ConditionGroup>{conditions}</ConditionGroup></StopTrigger></Storyboard>")


def test_named_lane_change_checks_make_the_ego_change_lanes():
    plain = scenario("", place("Ego", 0, 0, 10), group("Ego", ("on", command("SysEngReq"))))
    checked = asset(checks(plain, "Check_LaneChangeCompleted", "Check_LaneChangeCancelled"))
    assert named_conditions(checked.bundle) == ("Check_LaneChangeCompleted", "Check_LaneChangeCancelled")
    assert "lane_change" in actor_actions(checked.bundle, "Ego")
    assert "lane_change" not in actor_actions(asset(plain).bundle, "Ego")
    assert named_conditions(asset(checks(plain)).bundle) == ()  # teardown alone says nothing


def test_activation_checks_confirm_an_activation_boundary_test():
    package = ScenePackage("REQ", "Activation at Vsmax", "", structure={
        "test_intent": "激活边界试验", "ego_actions": ["匀速行驶"],
        "participants": [{"kind": "乘用车", "bearing": "正前方", "facing": "同向", "actions": ["匀速行驶"]}]})
    query = scene_package_to_query(package)
    xosc = scenario(vehicle("Lead"), place("Ego", 0, 0, 10) + place("Lead", 30, 0, 10))

    def intent(item):
        return [difference.tier for difference in compare_structure(query, item)
                if difference.requested.startswith("test_intent")]

    assert intent(asset(xosc)) == ["core"]
    assert intent(asset(checks(xosc, "Check_LaneChangeCompleted"))) == ["core"]
    confirmed = asset(checks(xosc, "Check_SysEngReq_Accepted", "Check_SysEngReq_Rejected"))
    assert asset_structure_query(confirmed).test_intent == "activation_boundary"
    assert intent(confirmed) == []


def child(name):
    return pedestrian(name).replace('name="adult"', 'name="Child01"')


def test_a_child_model_confirms_a_requested_child():
    package = ScenePackage("REQ", "Child crossing", "", structure={"participants": [
        {"kind": "行人", "bearing": "正前方", "facing": "横向", "actions": ["匀速行驶"], "age": "儿童"}]})
    query = scene_package_to_query(package)
    init = place("Ego", 0, 0, 10) + place("Kid", 30, 0, 1)

    def ages(entities):
        item = asset(scenario(entities, init, group("Kid", ("walk", speed(1.4)))))
        return [difference.tier for difference in compare_structure(query, item)
                if difference.requested.startswith("participant age")]

    assert ages(pedestrian("Kid")) == ["core"]
    assert ages(child("Kid")) == []


def test_a_tricycle_model_authored_as_a_car_stands_for_either():
    tricycle = vehicle("Trike").replace('name="car"', 'name="058-Tricycle01"')
    item = asset(scenario(tricycle, place("Ego", 0, 0, 10) + place("Trike", 30, 0, 0)))
    for kind in ("三轮车", "乘用车"):
        package = ScenePackage("REQ", "Standing target", "", structure={"participants": [
            {"kind": kind, "bearing": "正前方", "facing": "同向", "actions": ["静止"]}]})
        differences = compare_structure(scene_package_to_query(package), item)
        assert not [difference for difference in differences if difference.blocking], kind


def lane_change(value, kind="RelativeTargetLane", ref="Ego"):
    target = (f'<RelativeTargetLane entityRef="{ref}" value="{value}"/>' if kind == "RelativeTargetLane"
              else f'<AbsoluteTargetLane value="{value}"/>')
    return ('<PrivateAction><LateralAction><LaneChangeAction><LaneChangeActionDynamics dynamicsShape="sinusoidal" '
            f'value="3" dynamicsDimension="time"/><LaneChangeTarget>{target}</LaneChangeTarget></LaneChangeAction>'
            '</LateralAction></PrivateAction>')


def route(*headings):
    points = "".join(f'<Waypoint routeStrategy="shortest"><Position><WorldPosition x="{index * 50}" y="0" h="{heading}"/>'
                     '</Position></Waypoint>' for index, heading in enumerate(headings))
    return (f'<PrivateAction><RoutingAction><AssignRouteAction><Route name="r" closed="false">{points}</Route>'
            '</AssignRouteAction></RoutingAction></PrivateAction>')


def test_lateral_direction_and_route_turn_of_the_ego():
    lane_start = ('<Private entityRef="Ego"><PrivateAction><TeleportAction><Position><LanePosition roadId="1" '
                  'laneId="-2" s="10" offset="0"/></Position></TeleportAction></PrivateAction></Private>')

    def read(init, *events):
        return asset(scenario("", init, group("Ego", *events))).bundle

    assert lateral_direction(read(place("Ego", 0, 0, 10), ("lc", lane_change(1)))) == "left"
    assert lateral_direction(read(place("Ego", 0, 0, 10), ("lc", command("ALCAMode=right")))) == "right"
    assert lateral_direction(read(lane_start, ("lc", lane_change(-1, "AbsoluteTargetLane")))) == "left"
    assert lateral_direction(read(lane_start, ("lc", lane_change(-3, "AbsoluteTargetLane")))) == "right"
    assert lateral_direction(read(place("Ego", 0, 0, 10), ("lc", command("LaneChangeReq")))) == ""
    assert route_turn(read(place("Ego", 0, 0, 10), ("go", route(0, 0, -1.57)))) == "right"
    assert route_turn(read(place("Ego", 0, 0, 10), ("go", route(3.14, 2.62, 1.57)))) == "right"
    assert route_turn(read(place("Ego", 0, 0, 10), ("go", route(0.0, 0.01)))) == "straight"

    package = ScenePackage("REQ", "Lane change to the left", "", structure={
        "ego_actions": ["变道"], "params": {"lateral_direction": "左"},
        "participants": [{"kind": "乘用车", "bearing": "左后方", "facing": "同向", "actions": ["匀速行驶"]}]})
    query = scene_package_to_query(package)

    def side(item):
        return [difference.requested for difference in compare_structure(query, item)
                if difference.requested.startswith("lateral_direction")]

    entities, init = vehicle("Rear"), place("Ego", 0, 0, 10) + place("Rear", -20, 3.5, 10)
    assert side(asset(scenario(entities, init, group("Ego", ("lc", command("ALCAMode=left")))))) == []
    assert side(asset(scenario(entities, init, group("Ego", ("lc", command("ALCAMode=right")))))) == [
        "lateral_direction=左"]
