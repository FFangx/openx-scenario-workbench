"""Public, authored counterexamples for the PDF structure-to-decision contract."""

from dataclasses import replace
from pathlib import Path

import pytest

from openx_workbench.catalog import AssetFile, build_catalog
from openx_workbench.retrieval import HashingEncoder, OpenXIndex
from openx_workbench.reuse_structured import participant_differences
from openx_workbench.scene_package import ParticipantSignature, ScenePackage, scene_package_to_query


def authored_asset(*, speed=10, final_speed=10, function="AEB", weather="dry"):
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
      <WorldPosition x="20" y="0" h="0"/></Position></TeleportAction></PrivateAction>
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
    assert search(requirement(), asset)[0].reuse_level == "review"


def test_missing_environment_and_unsupported_constraints_request_review():
    asset = authored_asset()
    asset.bundle.scenario.environment = {}
    assert search(requirement(), asset)[0].reuse_level == "review"
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

    def draw(count):
        return tuple(ParticipantSignature(*(generator.choice(options) for options in vocabulary[:3]),
                                          (generator.choice(vocabulary[3]),)) for _ in range(count))

    def total(requested, candidates, pairing):
        differences = [item for expected, column in zip(requested, pairing) for item in
                       reuse_structured._pair_differences(expected, candidates[column] if column is not None else None)]
        differences += [reuse_structured._extra_difference(actual) for column, actual in enumerate(candidates)
                        if column not in pairing]
        blocking, cost, unverified = reuse_structured._score(differences)
        return blocking, round(cost, 6), unverified

    for _ in range(300):
        requested, candidates = draw(generator.randint(1, 5)), draw(generator.randint(0, 5))
        table = [[reuse_structured._score(reuse_structured._pair_differences(e, a)) for a in candidates]
                 for e in requested]
        absent = [reuse_structured._score(reuse_structured._pair_differences(e, None)) for e in requested]
        extra = [reuse_structured._score([reuse_structured._extra_difference(a)]) for a in candidates]
        enumerated = reuse_structured._enumerate(table, absent, extra)
        assigned = reuse_structured._assign(table, absent, extra)
        assert total(requested, candidates, assigned) == total(requested, candidates, enumerated)
