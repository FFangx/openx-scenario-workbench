import json
import math
from pathlib import Path

from openx_workbench.asset_store import AssetStore
from openx_workbench.catalog import AssetFile, build_catalog
from openx_workbench.classification import classify_asset, confirm_classification, read_classification, rule_labels

FIXTURES = Path(__file__).parent / "fixtures"
SCENARIO = (FIXTURES / "minimal.xosc").read_text(encoding="utf-8")


def files(xosc=SCENARIO, xodr=None):
    """The minimal scenario on a straight 100 m road whose lane has a width, so the ego can be placed."""
    return [AssetFile("minimal.xosc", xosc.encode()), AssetFile("minimal.xodr", (xodr or road((100, 0))).encode())]


def ego_does(*actions):
    """The minimal scenario with the ego doing `actions` (PrivateAction or UserDefinedAction XML) in its story."""
    events = "".join(f'<Event name="e{number}" priority="overwrite"><Action name="a{number}">{action}</Action><StartTrigger/></Event>'
                     for number, action in enumerate(actions))
    group = ('<ManeuverGroup name="EgoGroup" maximumExecutionCount="1"><Actors selectTriggeringEntities="false">'
             f'<EntityRef entityRef="Ego"/></Actors><Maneuver name="EgoManeuver">{events}</Maneuver></ManeuverGroup>')
    return SCENARIO.replace("<StartTrigger/></Act>", group + "<StartTrigger/></Act>")


def command(text):
    return f'<UserDefinedAction><CustomCommandAction type="Command">{text}</CustomCommandAction></UserDefinedAction>'


def road(*pieces, objects="", more=""):
    """Road 1 from the origin along x: (length, curvature) pieces, 0 for a line; `more` adds roads."""
    planview, s = [], 0
    for length, curvature in pieces:
        shape = f'<arc curvature="{curvature}"/>' if curvature else "<line/>"
        planview.append(f'<geometry s="{s}" x="{s}" y="0" hdg="0" length="{length}">{shape}</geometry>')
        s += length
    return (f'<OpenDRIVE><header revMajor="1" revMinor="6"/><road id="1" length="{s}" junction="-1">'
            f'<planView>{"".join(planview)}</planView><lanes><laneSection s="0"><center><lane id="0" type="none"/></center>'
            '<right><lane id="-1" type="driving"><width sOffset="0" a="3.5" b="0" c="0" d="0"/></lane></right>'
            f'</laneSection></lanes><objects>{objects}</objects></road>{more}</OpenDRIVE>')


# The ego alone, doing `action` where it reaches (x, -1.75).
ALONE = ('<OpenSCENARIO><FileHeader revMajor="1" revMinor="2" description="Road test" author="Test"/>'
         '<RoadNetwork><LogicFile filepath="minimal.xodr"/></RoadNetwork><Entities>'
         '<ScenarioObject name="Ego"><Vehicle vehicleCategory="car"/></ScenarioObject></Entities><Storyboard>'
         '<Init><Actions><Private entityRef="Ego"><PrivateAction><TeleportAction><Position>'
         '<LanePosition roadId="1" laneId="-1" s="10" offset="0"/></Position></TeleportAction></PrivateAction></Private>'
         '</Actions></Init><Story name="Story"><Act name="Act"><ManeuverGroup name="EgoGroup" maximumExecutionCount="1">'
         '<Actors selectTriggeringEntities="false"><EntityRef entityRef="Ego"/></Actors><Maneuver name="M">'
         '<Event name="Brake" priority="overwrite"><Action name="Brake">{action}</Action><StartTrigger><ConditionGroup>'
         '<Condition name="arrive" delay="0" conditionEdge="rising"><ByEntityCondition><TriggeringEntities '
         'triggeringEntitiesRule="any"><EntityRef entityRef="Ego"/></TriggeringEntities><EntityCondition>'
         '<ReachPositionCondition tolerance="5"><Position><WorldPosition x="{x}" y="-1.75"/></Position>'
         '</ReachPositionCondition></EntityCondition></ByEntityCondition></Condition></ConditionGroup></StartTrigger>'
         '</Event></Maneuver></ManeuverGroup><StartTrigger/></Act></Story></Storyboard></OpenSCENARIO>')


def test_rule_labels_are_accepted_and_a_reviewer_keeps_the_final_say(tmp_path):
    store = AssetStore(tmp_path)
    version = store.import_files(files())[0]
    original = store.file_bytes(version, "scenario")
    record = classify_asset(store, version)
    assert (record["status"], record["needs_review"], record["final_accepted"]) == ("rule", False, True)
    assert record["final"]["label_road_type"] == "直道"
    assert store.load_asset(version).classification == record["final"]
    confirmed = confirm_classification(store, version, {**record["final"], "function_type": "ACC"})
    assert confirmed["status"] == "manual_confirmed" and confirmed["differences"] == ["function_type"]
    again = classify_asset(store, version)
    assert (again["status"], again["final"]["function_type"], again["rule"]) == ("manual_confirmed", "ACC", record["rule"])
    assert read_classification(store, version)["final"]["function_type"] == "ACC"
    assert store.load_asset(version).classification["function_type"] == "ACC"
    assert store.file_bytes(version, "scenario") == original
    assert len(list((tmp_path / "assets").glob("*/*/classification_history/*.json"))) == 3


def test_rule_targets_never_treat_the_ego_as_a_target(tmp_path):
    source = SCENARIO.replace('<ScenarioObject name="Target"><Vehicle vehicleCategory="car"/></ScenarioObject>',
                              '<ScenarioObject name="Target"><Vehicle vehicleCategory="motorbike"/></ScenarioObject>')
    store = AssetStore(tmp_path)
    version = store.import_files(files(source))[0]
    record = classify_asset(store, version)
    assert record["rule"]["label_target_type"] == ["两轮车"]
    assert store.load_asset(version).classification["label_target_type"] == ["两轮车"]


def test_function_named_in_the_title_else_switched_on_by_a_command():
    plain = build_catalog(files())[0]
    assert rule_labels(plain, "CNCAP_AEB_CCRs40.xosc")["function_type"] == "AEB"
    assert rule_labels(plain, "CNCAP2024_LSS__LDW_solid_left.xosc")["function_type"] == "LDW"  # the lane-support function
    assert rule_labels(plain, "AEB_FCW_case.xosc")["function_type"] == "未知"
    commanded = build_catalog(files(ego_does(command("EnableACC"))))[0]
    assert rule_labels(commanded, "7_4_1_case.xosc")["function_type"] == "ACC"
    assert rule_labels(commanded, "LKA_case.xosc")["function_type"] == "LKA"


def test_road_is_parking_the_curve_or_junction_ahead_or_the_map_name():
    def road_label(xosc=SCENARIO, xodr=None):
        return rule_labels(build_catalog(files(xosc, xodr))[0])["label_road_type"]

    assert road_label() == "直道"
    assert road_label(xodr=road((50, 0), (200, 0.004))) == "弯道"  # the ego starts at s=10
    assert road_label(xodr=road((400, 0), (200, 0.004))) == "直道"  # the curve lies past where the test happens
    assert road_label(ego_does(command("EnableAPA;ParkingOut"))) == "停车场"
    reverse = '<PrivateAction><ControllerAction><OverrideControllerValueAction><Gear active="true" value="-1" number="-1"/></OverrideControllerValueAction></ControllerAction></PrivateAction>'
    spaces = '<object id="9" type="parkingSpace" s="20" t="-6" zOffset="0" width="2.5" length="5" height="0" hdg="0"/>'
    assert road_label(ego_does(reverse), road((400, 0), objects=spaces)) == "停车场"
    assert road_label(ego_does(reverse)) == "直道"  # reversing on a road without parking spaces
    case = {"case_id": "c", "map_id": "M1", "map_name": "十字路口", "road_reference": "M1.xodr", "road_missing": True}
    built_in = SCENARIO.replace('filepath="minimal.xodr"', 'filepath="M1.xodr"')
    missing = build_catalog([AssetFile("lib/c.xosc", built_in.encode()), AssetFile("lib/c.case.json", json.dumps(case).encode())])[0]
    assert rule_labels(missing)["label_road_type"] == "交叉口"


def test_the_road_is_read_as_far_as_the_scenario_reaches_and_a_ring_is_a_roundabout():
    def road_label(xosc, xodr):
        return rule_labels(build_catalog(files(xosc, xodr))[0])["label_road_type"]

    far_curve = road((400, 0), (300, 0.002))  # the curve starts 390 m ahead of the ego
    brake = command("BrakePosition=0.5")
    assert road_label(ALONE.format(action=brake, x=700), far_curve) == "弯道"  # the scenario runs into it
    assert road_label(ALONE.format(action=command("LaneOffset=left"), x=700), far_curve) == "弯道"
    assert road_label(ALONE.format(action=brake, x=100), far_curve) == "直道"  # it ends long before
    ring = [f'<road id="r{n}" length="{20 * math.pi / 3}" junction="-1"><planView><geometry s="0" '
            f'x="{100 + 20 * math.cos(n * math.pi / 3)}" y="{20 * math.sin(n * math.pi / 3)}" hdg="{n * math.pi / 3 + math.pi / 2}" '
            f'length="{20 * math.pi / 3}"><arc curvature="0.05"/></geometry></planView></road>' for n in range(6)]
    entry = '<road id="c" length="10" junction="5"><planView><geometry s="0" x="70" y="0" hdg="0" length="10"><line/></geometry></planView></road>'
    assert road_label(SCENARIO, road((70, 0), more=entry + "".join(ring))) == "环岛"
    assert road_label(SCENARIO, road((70, 0), more=entry)) == "交叉口"

