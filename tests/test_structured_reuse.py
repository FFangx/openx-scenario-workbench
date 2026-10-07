"""Public, authored counterexamples for the PDF structure-to-decision contract."""

from dataclasses import replace
from pathlib import Path

import pytest

from openx_workbench.catalog import AssetFile, build_catalog
from openx_workbench.retrieval import HashingEncoder, OpenXIndex
from openx_workbench.reuse_structured import participant_differences
from openx_workbench.scene_package import ParticipantSignature, ScenePackage, scene_package_to_query


def authored_asset(*, speed=10, final_speed=10, function="AEB", weather="dry", target_y=0):
    fixture = Path(__file__).parent / "fixtures"
    source = (fixture / "minimal.xosc").read_text(encoding="utf-8")
    source = source.replace('description="Minimal cut-in"', 'description="Opaque 001"')
    source = source.replace(
        '<LanePosition roadId="1" laneId="-1" s="10" offset="0"/>',
        '<WorldPosition x="0" y="0" h="0"/>',
    )
    initial = f'''<Private entityRef="Ego"><PrivateAction><LongitudinalAction><SpeedAction>
      <SpeedActionTarget><AbsoluteTargetSpeed value="10"/></SpeedActionTarget>
      </SpeedAction></LongitudinalAction></PrivateAction></Private>
      <Private entityRef="Target"><PrivateAction><TeleportAction><Position>
      <WorldPosition x="20" y="{target_y}" h="0"/></Position></TeleportAction></PrivateAction>
      <PrivateAction><LongitudinalAction><SpeedAction><SpeedActionTarget>
      <AbsoluteTargetSpeed value="{speed}"/></SpeedActionTarget></SpeedAction>
      </LongitudinalAction></PrivateAction></Private>'''
    source = source.replace("</Actions></Init>", initial + "</Actions></Init>")
    source = source.replace('value="12.5"', f'value="{final_speed}"')
    source = source.replace(
        "</Entities>",
        f'''</Entities><Environment name="Test">
      <TimeOfDay dateTime="2026-01-01T12:00:00"/>
      <Weather cloudState="free"><Precipitation precipitationType="{weather}" intensity="0"/>
      <Fog visualRange="1200"/></Weather></Environment>''',
    )
    asset = build_catalog(
        [
            AssetFile("opaque.xosc", source.encode()),
            AssetFile("minimal.xodr", (fixture / "minimal.xodr").read_bytes()),
        ]
    )[0]
    asset.classification = {"function_type": function}
    return asset


def requirement(**edits):
    structure = {
        "tested_function": "AEB",
        "road_class": "直道",
        "ego_actions": ["匀速行驶"],
        "participants": [
            {
                "kind": "乘用车",
                "bearing": "正前方",
                "facing": "同向",
                "actions": ["匀速行驶"],
            }
        ],
        "params": {
            "ego_speed_kph": 36,
            "target_speeds_kph": [36],
            "weather": "晴天",
            "time_of_day": "日间",
        },
    }
    structure.update(edits)
    # Deliberately stale text/flat fields: the approved structure is authoritative.
    return ScenePackage(
        "REQ",
        "Opaque requirement",
        "A vehicle drives ahead.",
        road_types=["交叉口"],
        parameters={"ego_speed_kph": 80},
        structure=structure,
    )


def search(package, *assets):
    return OpenXIndex(list(assets), HashingEncoder(32)).search(
        "", query=scene_package_to_query(package), top_k=len(assets)
    )


def test_review_scope_distinguishes_known_interaction_from_missing_structure():
    partial = search(requirement(lane_marking="实线"), authored_asset())[0]
    assert partial.reuse_level == "review" and partial.review_kind == "partial"
    incomplete = requirement(participants=[{"kind": "未知", "bearing": "未知方位", "facing": "未知", "actions": []}])
    undecidable = search(incomplete, authored_asset())[0]
    assert undecidable.reuse_level == "review" and undecidable.review_kind == "undecidable"
    text = OpenXIndex([authored_asset()], HashingEncoder(32)).search("vehicle ahead")[0]
    assert text.reuse_level == "review" and text.review_kind == "recall"


def test_structured_facts_override_stale_flat_fields_and_text():
    result = search(requirement(), authored_asset())[0]
    assert result.reuse_level == "direct", result.differences
    assert result.scenario_score == 1
    edited = requirement(
        participants=[
            {"kind": "行人", "bearing": "右前方", "facing": "横向", "actions": ["静止"]}
        ]
    )
    assert scene_package_to_query(requirement()) != scene_package_to_query(edited)
    assert search(edited, authored_asset())[0].reuse_level == "new_build"


def test_braking_requirement_does_not_match_cruising_target():
    package = requirement(
        participants=[
            {
                "kind": "乘用车",
                "bearing": "正前方",
                "facing": "同向",
                "actions": ["刹停"],
            }
        ],
        params={},
    )
    results = search(
        package,
        authored_asset(),
        replace(authored_asset(final_speed=0), asset_id="stop"),
    )
    assert results[0].asset.asset_id == "stop"
    assert results[0].reuse_level == "direct"
    assert results[1].reuse_level != "direct"


@pytest.mark.parametrize(
    "edits,category",
    [
        ({"tested_function": "ACC"}, "function"),
        ({"road_class": "交叉口"}, "road"),
        ({"params": {"target_speeds_kph": [72]}}, "parameter"),
        ({"params": {"weather": "雨天"}}, "environment"),
        ({"params": {"time_of_day": "夜间"}}, "environment"),
    ],
)
def test_typed_constraints_change_the_decision(edits, category):
    result = search(requirement(**edits), authored_asset())[0]
    assert result.reuse_level != "direct"
    assert any(item.category == category for item in result.differences)


def test_unknown_topology_requests_review_instead_of_inventing_mismatch():
    asset = authored_asset()
    asset.bundle.scenario.positions = []
    result = search(requirement(), asset)[0]
    assert result.reuse_level == "review"
    assert not any(item.blocking for item in result.differences)


def test_empty_typed_structure_is_not_a_proof_of_direct_reuse():
    result = search(
        requirement(
            road_class="未知",
            tested_function="未知",
            ego_actions=[],
            participants=[],
            params={},
        ),
        authored_asset(),
    )[0]
    assert result.reuse_level == "review"


def test_structural_recall_text_has_no_asset_name_and_saved_labels_invalidate_index(
    tmp_path,
):
    from openx_workbench.retrieval import asset_structure_text

    asset = authored_asset()
    assert asset.title not in asset_structure_text(asset)
    index = OpenXIndex([asset], HashingEncoder(32))
    path = tmp_path / "index.json"
    index.save(path)
    asset.classification = {"function_type": "ACC"}
    with pytest.raises(ValueError, match="changed"):
        OpenXIndex.load(path, [asset], HashingEncoder(32))
    with pytest.raises(ValueError, match="changed"):
        index.save(path)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), -1])
def test_invalid_numeric_requirements_are_rejected(value):
    with pytest.raises(ValueError, match="finite"):
        scene_package_to_query(requirement(params={"target_speeds_kph": [value]}))


def test_extra_target_action_prevents_direct_reuse():
    from openx_workbench.models import ActionIR

    asset = authored_asset()
    asset.bundle.scenario.actions.append(
        ActionIR("Extra", "LaneChangeAction", "Target")
    )
    assert search(requirement(), asset)[0].reuse_level == "modify"


def test_action_ownership_and_initial_speed_are_not_inferred():
    asset = authored_asset(final_speed=0)
    for action in asset.bundle.scenario.actions:
        if action.phase == "story":
            action.actor = "Ego"
    package = requirement(
        participants=[
            {
                "kind": "乘用车",
                "bearing": "正前方",
                "facing": "同向",
                "actions": ["刹停"],
            }
        ],
        params={},
    )
    result = search(package, asset)[0]
    assert result.reuse_level != "direct"
    asset.bundle.scenario.actions = [
        item for item in asset.bundle.scenario.actions if item.kind != "SpeedAction"
    ]
    result = search(requirement(), asset)[0]
    # No speed is read, so none is invented: it stays an open item to confirm, never a match.
    assert result.reuse_level in {"modify", "major_modify"}
    assert any(item.category == "parameter" and not item.verified for item in result.differences)


def test_missing_environment_is_confirmed_while_unsupported_road_constraints_request_review():
    asset = authored_asset()
    asset.bundle.scenario.environment = {}
    result = search(requirement(), asset)[0]
    assert result.reuse_level == "modify"
    assert [item.tier for item in result.differences if not item.verified] == ["adjustable"] * 2
    assert (
        search(requirement(lane_marking="实线"), authored_asset())[0].reuse_level
        == "review"
    )


def test_participant_multiplicity_and_order_are_preserved():
    participant = requirement().structure["participants"][0]
    result = search(
        requirement(participants=[participant, participant]), authored_asset()
    )[0]
    assert result.reuse_level == "new_build"


def test_opposite_position_and_junction_cannot_be_direct():
    asset = authored_asset()
    target = next(
        item for item in asset.bundle.scenario.positions if item.actor == "Target"
    )
    target.attributes["x"] = "-20"
    assert search(requirement(), asset)[0].reuse_level == "new_build"
    asset = authored_asset()
    asset.bundle.road.junction_count = 1
    assert search(requirement(), asset)[0].reuse_level == "modify"


def _signature(text):
    kind, rest = text.split("@")
    bearing, facing, actions = rest.split(":")
    return ParticipantSignature(kind, bearing, facing, tuple(actions.split("+")))


def _blocking(requested, candidates):
    differences = participant_differences(
        tuple(map(_signature, requested)), tuple(map(_signature, candidates))
    )
    return sum(item.blocking for item in differences), differences


def test_participants_are_paired_for_the_fewest_blocking_differences():
    # Key order puts the pedestrian first; pairing it first used up the matching vehicle.
    count, differences = _blocking(
        ["pedestrian@alongside_left:crossing:static", "vehicle@front_same_lane:same:cruise"],
        ["vehicle@front_same_lane:same:cruise", "vehicle@rear_same_lane:same:cruise"],
    )
    assert count == 1
    assert [(item.requested, item.candidate) for item in differences] == [
        ("pedestrian@alongside_left:crossing:static", "vehicle@rear_same_lane:same:cruise")
    ]
    count, differences = _blocking(
        ["pedestrian@alongside_left:crossing:static", "vehicle@front_same_lane:same:cruise"],
        ["vehicle@front_same_lane:same:cruise"],
    )
    assert count == 1 and differences[0].action == "add participant"
    assert differences[0].requested.startswith("pedestrian")


def test_a_moving_participant_further_ahead_or_behind_is_retimed_not_rebuilt():
    # A standard describes the interaction (right alongside), an asset where it starts (right behind).
    count, differences = _blocking(["vehicle@alongside_right:same:cruise"], ["vehicle@rear_right:same:cruise"])
    assert count == 0
    assert [(item.category, item.action, item.tier) for item in differences] == [
        ("placement", "move start position or retime trigger", "adjustable")]
    # Doing something else as well, the ego's own lane, or standing still: another interaction.
    assert _blocking(["vehicle@rear_left:same:cruise"], ["vehicle@front_left:same:cruise+lane_change"])[0] == 1
    assert _blocking(["vehicle@front_same_lane:same:cruise"], ["vehicle@rear_same_lane:same:cruise"])[0] == 1
    assert _blocking(["vehicle@front_right:same:static"], ["vehicle@rear_right:same:static"])[0] == 1


def test_a_standing_participant_facing_another_way_is_turned():
    count, differences = _blocking(["vehicle@front_same_lane:crossing:static"], ["vehicle@front_same_lane:same:static"])
    assert count == 0 and [item.action for item in differences] == ["turn standing participant"]
    assert _blocking(["vehicle@front_same_lane:crossing:cruise"], ["vehicle@front_same_lane:same:cruise"])[0] == 1


def test_keeping_a_distance_is_how_a_moving_participant_drives_along():
    # A lead car that keeps its distance to the ego, then brakes: the requested hard stop, cruising before it.
    assert _blocking(["vehicle@front_same_lane:same:stop"], ["vehicle@front_same_lane:same:following+stop"]) == (0, [])
    assert _blocking(["vehicle@front_same_lane:same:cruise"], ["vehicle@front_same_lane:same:following"]) == (0, [])
    # Requested to stand still, or to follow, it stays a behavior of its own.
    count, differences = _blocking(["vehicle@front_same_lane:same:static"], ["vehicle@front_same_lane:same:following"])
    assert count == 0 and [item.action for item in differences] == ["modify participant behavior"]
    _, differences = _blocking(["vehicle@front_same_lane:same:following"], ["vehicle@front_same_lane:same:cruise"])
    assert [item.action for item in differences] == ["modify participant behavior"]


def test_a_behavior_the_requirement_does_not_name_is_left_open():
    _, differences = _blocking(["vehicle@front_same_lane:same:unknown"], ["vehicle@front_same_lane:same:following+stop"])
    assert [item.category for item in differences] == ["participant_topology"]


def test_a_scenery_group_stands_for_every_requested_obstacle_there():
    requested = (_signature("obstacle@front_same_lane:crossing:static"),) * 2
    scenery = tuple(map(_signature, ["obstacle@front_left:unknown:static", "obstacle@front_same_lane:unknown:static"]))
    assert participant_differences(requested, (), scenery) == []


def test_pairing_prefers_the_cheaper_change_among_equally_blocking_pairings():
    count, differences = _blocking(
        ["vehicle@front_same_lane:same:stop", "vehicle@front_same_lane:same:cruise"],
        ["vehicle@front_same_lane:same:cruise", "vehicle@front_same_lane:same:stop"],
    )
    assert count == 0 and differences == []


def test_large_participant_sets_are_paired_optimally():
    # Eight requested participants: too many to enumerate, solved as an assignment problem.
    requested = ["pedestrian@alongside_left:crossing:static"] + [
        f"vehicle@{bearing}:same:cruise"
        for bearing in ("front_same_lane", "front_left", "front_right", "rear_same_lane",
                        "rear_left", "rear_right", "alongside_right")
    ]
    candidates = requested[1:] + ["vehicle@rear_same_lane:opposite:cruise"]
    count, differences = _blocking(requested, candidates)
    assert count == 1
    assert [item.requested for item in differences if item.blocking] == [requested[0]]


def test_assignment_solver_agrees_with_enumeration():
    import random

    from openx_workbench import reuse_structured

    vocabulary = (("vehicle", "pedestrian", "unknown"), ("front_same_lane", "rear_left", "unknown"),
                  ("same", "crossing", "unknown"), ("cruise", "static", "stop", "unknown"))
    generator = random.Random(7)

    drawn = ((), ("bearing",), ("facing",), ("bearing", "facing"))

    def draw(count):
        return tuple(ParticipantSignature(*(generator.choice(options) for options in vocabulary[:3]),
                                          (generator.choice(vocabulary[3]),), from_figure=generator.choice(drawn))
                     for _ in range(count))

    def total(requested, candidates, pairing):
        differences = [item for expected, column in zip(requested, pairing) for item in
                       reuse_structured._pair_differences(expected, candidates[column] if column is not None else None)]
        differences += [reuse_structured._extra_difference(actual) for column, actual in enumerate(candidates)
                        if column not in pairing]
        blocking, cost, figure, unverified = reuse_structured._score(differences)
        return blocking, round(cost, 6), round(figure, 6), unverified

    for _ in range(300):
        requested, candidates = draw(generator.randint(1, 5)), draw(generator.randint(0, 5))
        table = [[reuse_structured._score(reuse_structured._pair_differences(e, a)) for a in candidates]
                 for e in requested]
        absent = [reuse_structured._score(reuse_structured._pair_differences(e, None)) for e in requested]
        extra = [reuse_structured._score([reuse_structured._extra_difference(a)]) for a in candidates]
        enumerated = reuse_structured._enumerate(table, absent, extra)
        assigned = reuse_structured._assign(table, absent, extra)
        assert total(requested, candidates, assigned) == total(requested, candidates, enumerated)


DRAWN = {"source": "图", "quote": "图1", "reason": "画在主车右前方"}


def test_a_fact_drawn_in_a_figure_aids_ranking_but_never_decides_reuse():
    car = {"kind": "乘用车", "bearing": "右前方", "facing": "同向", "actions": ["匀速行驶"]}
    ahead, right = authored_asset(), replace(authored_asset(target_y=-3.5), asset_id="right")
    # Written in the text, a car ahead on the right is another interaction than one in the ego's lane.
    written = search(requirement(participants=[{**car, "evidence": {"bearing": {"source": "原文", "quote": "右前方"}}}]),
                     ahead, right)
    assert [(item.asset.asset_id, item.reuse_level) for item in written] == [("right", "direct"), (ahead.asset_id, "new_build")]
    # Drawn only, it is checked against the figure: the verdict rests on the text, the figure ranks.
    drawn = search(requirement(participants=[{**car, "evidence": {"bearing": DRAWN}}]), ahead, right)
    assert [(item.asset.asset_id, item.reuse_level) for item in drawn] == [("right", "direct"), (ahead.asset_id, "direct")]
    assert drawn[0].differences == ()
    assert [(item.category, item.tier, item.blocking, item.verified) for item in drawn[1].differences] == [
        ("figure", "figure", False, False)]
    assert drawn[1].estimated_change_cost == 0


def test_an_ego_lane_drawn_in_a_figure_is_checked_against_it():
    written = search(requirement(ego_lane="最右侧车道"), authored_asset())[0]
    assert written.reuse_level == "modify"
    assert [(item.category, item.requested, item.tier) for item in written.differences] == [
        ("unverified", "ego_lane=最右侧车道", "adjustable")]
    drawn = search(requirement(ego_lane="最右侧车道", evidence={"ego_lane": DRAWN}), authored_asset())[0]
    assert drawn.reuse_level == "direct"
    assert [(item.category, item.requested, item.candidate) for item in drawn.differences] == [
        ("figure", "ego_lane=最右侧车道", "not compared")]


def _bound(text, speed):
    return replace(_signature(text), speed_kph=speed)


def test_speeds_bound_to_participants_follow_the_pairing():
    front, rear = "vehicle@front_same_lane:same:cruise", "vehicle@rear_left:same:cruise"
    candidates = (_bound(front, 50), _bound(rear, 80))
    assert participant_differences((_bound(front, 50), _bound(rear, 80)), candidates) == []
    swapped = participant_differences((_bound(front, 80), _bound(rear, 50)), candidates)
    assert [(item.category, item.candidate, item.verified) for item in swapped] == [
        ("parameter", "speed=50 km/h", True), ("parameter", "speed=80 km/h", True)]
    # Identical participants are paired by speed, not by position.
    assert participant_differences((_bound(front, 80), _bound(front, 50)), (_bound(front, 50), _bound(front, 80))) == []
    unread = participant_differences((_bound(front, 50),), (_signature(front),))
    assert [(item.candidate, item.verified) for item in unread] == [("not extracted", False)]


def test_requirement_speeds_bind_to_participants_or_fall_back_to_the_list():
    participant = requirement().structure["participants"][0]
    bound = search(requirement(participants=[{**participant, "speed_kph": 36}], params={}), authored_asset())[0]
    assert bound.reuse_level == "direct"
    assert not [item for item in bound.differences if item.category == "parameter"]
    wrong = search(requirement(participants=[{**participant, "speed_kph": 50}]), authored_asset())[0]
    assert wrong.reuse_level == "modify"
    assert [item.requested for item in wrong.differences] == [
        "vehicle@front_same_lane:same:cruise speed=50 km/h"]


def test_an_unbound_speed_list_counts_duplicates_only_when_it_has_one_speed_per_participant():
    from openx_workbench.reuse_differences import target_speed_differences

    assert target_speed_differences((0.0,), (0.0, 0.0), participants=2) == []
    assert target_speed_differences((30.0, 30.0), (30.0,), participants=2)
    assert target_speed_differences((30.0,), (30.0, 30.0), participants=1)


def test_participant_speed_is_optional_in_the_stored_structure():
    from openx_workbench.pdf_v2.scene_schemas import SceneStructure, parse_scene_structure

    stored = requirement().structure
    assert SceneStructure.model_validate(stored).model_dump(mode="json")["participants"] == [
        {**stored["participants"][0], "age": "未知"}]
    with pytest.raises(ValueError):
        SceneStructure.model_validate({**stored, "participants": [{**stored["participants"][0], "speed_kph": -1}]})
    dropped = set()
    parsed = parse_scene_structure({"participants": [
        {"kind": "乘用车", "speed_kph": "20"}, {"kind": "行人", "speed_kph": "fast"},
        {"kind": "行人", "speed_kph": -3}]}, dropped)
    assert [item.speed_kph for item in parsed.participants] == [20.0, None, None]
    assert dropped == {"participant_speed='fast'", "participant_speed=-3"}


def _lanes(asset, same, total, markings):
    asset.bundle.road.lanes_same_direction, asset.bundle.road.lanes_total = same, total
    asset.bundle.road.lane_markings = markings
    return asset


def _road_differences(package, asset):
    return [(item.requested, item.verified) for item in search(package, asset)[0].differences if item.category == "road"]


def test_lane_count_is_a_lower_bound_read_in_the_stated_direction():
    def lanes(count, direction):
        return requirement(params={**requirement().structure["params"], "lane_count": count, "lane_direction": direction})

    asset = _lanes(authored_asset(), 2, 4, ["broken", "solid"])
    assert _road_differences(lanes(2, "单向"), asset) == []
    assert _road_differences(lanes(4, "双向"), asset) == []
    assert _road_differences(lanes(1, "双向"), asset) == []  # 双向单车道: one lane each way
    assert _road_differences(lanes(3, "单向"), asset) == [("at least 3 lanes in one direction", True)]
    assert search(lanes(3, "单向"), asset)[0].reuse_level == "modify"
    # The count of an unstated direction is checked against both directions together.
    assert _road_differences(lanes(4, "未知"), asset) == []


def test_lane_lines_are_matched_by_presence_and_unknown_when_unread():
    asset = _lanes(authored_asset(), 2, 4, ["broken"])
    assert _road_differences(requirement(lane_marking="虚线"), asset) == []
    assert _road_differences(requirement(lane_marking="实线"), asset) == [("solid lane line", True)]
    unread = _lanes(authored_asset(), 2, 4, [])
    assert _road_differences(requirement(lane_marking="实线"), unread) == [("solid lane line", False)]
    assert search(requirement(lane_marking="实线"), unread)[0].reuse_level == "review"


def test_driving_lanes_and_lines_are_read_from_opendrive():
    from openx_workbench.parser import parse_xodr

    road = parse_xodr("""<OpenDRIVE><header/><road id="1" length="100"><lanes><laneSection s="0">
      <left><lane id="2" type="sidewalk"/><lane id="1" type="driving"><roadMark type="broken"/></lane></left>
      <center><lane id="0" type="none"><roadMark type="solid solid"/></lane></center>
      <right><lane id="-1" type="driving"><roadMark type="broken"/></lane>
        <lane id="-2" type="driving"><roadMark type="solid"/></lane><lane id="-3" type="shoulder"/></right>
      </laneSection></lanes></road></OpenDRIVE>""")
    assert (road.lanes_same_direction, road.lanes_total, road.lane_markings) == (2, 3, ["broken", "solid"])


def test_a_requirement_without_participants_is_never_reused_as_is():
    asset = authored_asset()
    misuse = requirement(participants=[], tested_function="未知", test_intent="误作用试验")
    result = search(misuse, asset)[0]
    assert result.reuse_level == "review"
    assert {item.category for item in result.differences if not item.verified and item.tier == "core"} >= {"story"}
    # Even testing the same function, a story with no participant proves nothing.
    assert search(requirement(participants=[]), asset)[0].reuse_level == "review"


def test_a_driver_intervention_test_needs_an_asset_with_driver_inputs():
    result = search(requirement(test_intent="驾驶员干预试验"), authored_asset())[0]
    assert result.reuse_level == "new_build"
    assert [item.requested for item in result.differences if item.blocking] == ["driver_intervention"]


def test_the_tested_function_is_a_setting_not_a_rebuild():
    asset = authored_asset(function="AEB")
    switched = search(requirement(tested_function="FCW"), asset)[0]
    assert switched.reuse_level == "modify"
    assert [(item.category, item.blocking, item.tier) for item in switched.differences
            if item.category == "function"] == [("function", False, "adjustable")]
    unknown = search(requirement(), authored_asset(function="未知"))[0]
    assert unknown.reuse_level == "modify"
    assert any(item.category == "function" and not item.verified for item in unknown.differences)


def test_a_parking_requirement_needs_a_parking_asset():
    result = search(requirement(parking_operation="泊入"), authored_asset())[0]
    assert result.reuse_level == "new_build"


def test_either_or_participants_need_one_of_them():
    car, tricycle, walker = ({"kind": kind, "bearing": "正前方", "facing": "同向", "actions": ["匀速行驶"],
                              "alternative_group": "A"} for kind in ("乘用车", "三轮车", "行人"))
    result = search(requirement(participants=[tricycle, car, walker]), authored_asset())[0]
    assert result.reuse_level == "direct", result.differences
    assert [(item.category, item.candidate, item.tier) for item in result.differences] == [
        ("variant", "vehicle@front_same_lane:same:cruise", "note")]
    # Listed side by side, all three take part.
    together = [{key: value for key, value in item.items() if key != "alternative_group"} for item in (car, tricycle, walker)]
    assert search(requirement(participants=together), authored_asset())[0].reuse_level == "new_build"


def test_the_age_of_an_alternative_left_out_is_no_longer_required():
    from openx_workbench.reuse_structured import compare_structure

    adult, kid = ({"kind": "行人", "bearing": "正前方", "facing": "同向", "actions": ["匀速行驶"], "age": age,
                   "alternative_group": "A"} for age in ("成人", "儿童"))
    query = scene_package_to_query(requirement(participants=[adult, kid]))
    assert sorted(query.unverified) == ["participant age=儿童", "participant age=成人"]
    assert [item.requested for item in compare_structure(query, authored_asset())
            if item.requested.startswith("participant age")] == ["participant age=成人"]


def test_traffic_lights_and_speed_limit_signs_come_from_the_road_file():
    def road(limits=(), lights=0, missing=False):
        asset = authored_asset()
        asset.bundle.road.speed_limits_kph = list(limits)
        asset.bundle.road.furniture = {"traffic_light": lights} if lights else {}
        if missing:
            asset.bundle.road.file_missing, asset.bundle.road.inferred_features = True, ["straight"]
        return asset

    lights = requirement(traffic_controls=["交通信号灯"])
    assert _road_differences(lights, road(lights=4)) == []
    assert _road_differences(lights, road()) == [("traffic_light", True)]
    assert search(lights, road())[0].reuse_level == "modify"
    assert _road_differences(lights, road(missing=True)) == [("traffic_light", False)]

    def limits(*values):
        return requirement(traffic_controls=["限速标志"],
                           params={**requirement().structure["params"], "speed_limits_kph": list(values)})

    assert _road_differences(limits(60), road([40, 60, 80])) == []
    assert _road_differences(limits(100, 80), road([60, 80])) == []  # alternatives: any one will do
    assert [(item.candidate, item.cost) for item in search(limits(50), road([40, 60]))[0].differences
            if item.category == "road"] == [("speed_limit=40/60 km/h", 0.5)]
    assert _road_differences(limits(60), road()) == [("speed_limit=60 km/h", True)]
    assert _road_differences(requirement(traffic_controls=["限速标志"]), road([30])) == []


def test_round_c_fields_are_optional_in_the_stored_structure():
    from openx_workbench.pdf_v2.scene_schemas import SceneStructure, parse_scene_structure

    dumped = SceneStructure.model_validate(requirement().structure).model_dump(mode="json")
    assert not {"ego_turn", "traffic_controls"} & set(dumped) and "speed_limits_kph" not in dumped["params"]
    assert "alternative_group" not in dumped["participants"][0]
    dropped = set()
    parsed = parse_scene_structure({
        "ego_turn": "左转", "traffic_controls": ["交通信号灯", "红绿灯"], "params": {"speed_limits_kph": [80, "60", 0, "x"]},
        "participants": [{"kind": "乘用车", "alternative_group": "A"}, {"kind": "行人", "alternative_group": " "}]}, dropped)
    assert (parsed.ego_turn, parsed.traffic_controls, parsed.params.speed_limits_kph) == ("左转", ("交通信号灯",), (60.0, 80.0))
    assert [item.alternative_group for item in parsed.participants] == ["A", None]
    assert dropped == {"traffic_control=红绿灯", "speed_limit='x'"}
