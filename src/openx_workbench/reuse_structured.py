"""Comparison of a typed requirement (an approved PDF scene structure) with an asset's structure."""

from __future__ import annotations

from collections import Counter
from dataclasses import replace
from itertools import islice, permutations, product

from . import reuse_policy as policy
from .catalog import OpenXAsset
from .reuse_differences import (
    ReuseDifference,
    environment_differences,
    missing,
    parameter_differences,
    target_speed_differences,
)
from .reuse_facts import asset_structure_query, bundle_parameters
from .scene_facts import asset_environment
from .scene_package import (
    STRUCTURE_AGES,
    STRUCTURE_INTENTS,
    STRUCTURE_LATERAL,
    STRUCTURE_VENUES,
    ParticipantSignature,
    RetrievalQuery,
)

ENUMERATION_LIMIT = 6  # up to 6! = 720 participant pairings are enumerated; beyond, solve the assignment problem
LONGITUDINAL = frozenset({"cruise", "speed_change", "stop", "following", "reverse"})  # the ego's speed behaviors
VARIANT_LIMIT = 64  # combinations of alternatives compared per asset; beyond, the first ones in key order


def compare_structure(
    query: RetrievalQuery, asset: OpenXAsset, candidate: RetrievalQuery | None = None
) -> tuple[ReuseDifference, ...]:
    """Every difference to close; with alternatives, for the one the asset serves best.

    A requirement may offer alternatives of which one takes part in a run ("a car, a tricycle or a
    pedestrian stands ahead"). An asset builds one of them: the others are neither missing nor its
    concern. Each combination is compared, the one ranking best kept, and a note names the choice.
    """
    candidate = candidate or asset_structure_query(asset)
    signatures = query.participant_signatures
    groups: dict[str, list[int]] = {}
    for index, item in enumerate(signatures):
        if item.alternative:
            groups.setdefault(item.alternative, []).append(index)
    groups = {label: members for label, members in groups.items() if len(members) > 1}
    if not groups:
        return _compare_structure(query, asset, candidate)
    compared = []
    for picks in islice(product(*groups.values()), VARIANT_LIMIT):
        left_out = {index for members in groups.values() for index in members} - set(picks)
        # The age of an alternative left out is no longer a requirement.
        ages = Counter(f"participant age={signatures[index].age}" for index in left_out if signatures[index].age)
        unverified = []
        for value in query.unverified:
            if ages[value] > 0:
                ages[value] -= 1
            else:
                unverified.append(value)
        variant = replace(query, participant_signatures=tuple(item for index, item in enumerate(signatures)
                                                              if index not in left_out), unverified=tuple(unverified))
        compared.append((_compare_structure(variant, asset, candidate), picks))
    differences, picks = min(compared, key=lambda item: _score(list(item[0])))
    notes = tuple(
        ReuseDifference("variant", " / ".join(signatures[index].key() for index in members),
                        signatures[pick].key(), "select or build the other alternatives", cost=0)
        for members, pick in zip(groups.values(), picks)
    )
    return differences + notes


def _compare_structure(query: RetrievalQuery, asset: OpenXAsset, candidate: RetrievalQuery) -> tuple[ReuseDifference, ...]:
    differences = (
        participant_differences(
            query.participant_signatures, candidate.participant_signatures, candidate.scenery_signatures
        )
        if query.participant_signatures
        else []
    )
    if not (query.participant_signatures or query.occlusions):
        # Information gate: with no participant or interaction stated, two near-empty stories
        # always "match", which proves nothing, even when both test the same function (a
        # traffic-light test matched a static-obstacle test that way). A person decides.
        differences.append(ReuseDifference(
            "story", "participants or interaction", "not stated in the requirement",
            "decide by hand whether this is the same test", verified=False,
        ))
    differences.extend(_occlusion_differences(query, candidate))
    differences.extend(_intent_differences(query, candidate))
    for value in candidate.unverified:
        differences.append(ReuseDifference(
            "parameter_resolution", "resolved scenario parameters", value,
            "resolve parameter before confirming reuse", verified=False,
        ))
    # The asset's named checks show the declared kind of test (an activation-boundary test), its ego
    # moves to the declared side, its 3D models show a declared child (once per participant shown),
    # its lighting shows a tunnel: confirmed. Anything else stays unverified; the requirement may
    # mean another participant's side, a tunnel may be built another way.
    confirmed = Counter({f"test_intent={label}": 1 for label, intent in STRUCTURE_INTENTS.items()
                         if intent == candidate.test_intent})
    confirmed.update(f"lateral_direction={label}" for label, side in STRUCTURE_LATERAL.items()
                     if side == candidate.lateral_direction)
    confirmed.update(f"venue_features={label}" for label, venue in STRUCTURE_VENUES.items()
                     if venue in candidate.venue_features)
    for label, trait in STRUCTURE_AGES.items():
        confirmed[f"participant age={label}"] = sum(trait in item.traits for item in candidate.participant_signatures)
    if query.curve_radius_m and candidate.curve_radius_m:
        # The asset's road states the radius of the curve ahead of the ego: no longer unverified.
        confirmed[f"curve_radius_m={query.curve_radius_m}"] += 1
        if abs(candidate.curve_radius_m - query.curve_radius_m) > policy.CURVE_RADIUS_TOLERANCE * query.curve_radius_m:
            differences.append(ReuseDifference(
                "road", f"curve radius {query.curve_radius_m:g} m", f"{candidate.curve_radius_m:g} m",
                "select or modify OpenDRIVE curve", cost=policy.COST_ROAD))
    for value in query.unverified:
        if confirmed[value] > 0:
            confirmed[value] -= 1
            continue
        differences.append(
            ReuseDifference(
                "unverified",
                value,
                "not extracted",
                "verify declared requirement",
                verified=False,
            )
        )
    if query.ego_lane and "ego_lane" in query.figure_facts:
        # An asset's start lane is not compared yet: a lane drawn in a figure is checked against it.
        differences.append(_figure_check(f"ego_lane={query.ego_lane}", "not compared"))
    if query.tested_function:
        actual = candidate.tested_function
        # The tested function is a setting of the reuse (which system is switched on, how it is
        # scored), not part of the scenario: a story built for AEB serves FCW as well. Many
        # libraries never write it into the file, so unknown is confirmed while reusing.
        if actual in {"", "未知", "unknown"}:
            differences.append(
                ReuseDifference(
                    "function",
                    query.tested_function,
                    "unknown",
                    "confirm tested function",
                    cost=policy.COST_PARAMETER,
                    verified=False,
                )
            )
        elif actual != query.tested_function:
            related = policy.related_functions(actual, query.tested_function)
            differences.append(
                ReuseDifference(
                    "function",
                    query.tested_function,
                    actual,
                    "switch to the related tested function" if related else "switch the tested function and its scoring",
                    cost=policy.COST_PARAMETER if related else policy.COST_FUNCTION,
                )
            )
    if "motorway" in query.road_features:
        differences.append(
            ReuseDifference(
                "road",
                "motorway",
                "not extracted",
                "verify road classification",
                verified=False,
            )
        )
    differences.extend(
        missing(
            "road",
            query.road_features - {"motorway"},
            set(candidate.road_features),
            "select or modify OpenDRIVE",
            cost=policy.COST_ROAD,
        )
    )
    differences.extend(_lane_differences(query, asset.bundle.road))
    differences.extend(_traffic_control_differences(query, asset.bundle.road))
    differences.extend(
        missing(
            "trigger",
            query.trigger_kinds,
            set(candidate.trigger_kinds),
            "modify start trigger",
            cost=policy.COST_TRIGGER,
        )
    )
    if query.ego_actions:
        # Whether the system under test drives is a setting of the reuse, like the tested function:
        # a requirement that does not say so asks for nothing else, and a library that never writes
        # its engage command into the file still drives with the system on. To confirm, never a change.
        controlled = {"system_control"}
        if controlled <= query.ego_actions - candidate.ego_actions:
            differences.append(ReuseDifference("unverified", "ego_action=system_control", "not in the file",
                                               "confirm the system under test drives", cost=policy.COST_PARAMETER,
                                               verified=False))
        absent = query.ego_actions - candidate.ego_actions - controlled
        # A system under test changes lanes by itself: its asset need not script the lane change
        # (a system-triggered lane change shows none). To confirm, at no cost; an asset that shows
        # one still scores higher.
        unscripted = absent & {"lane_change"} if "system_control" in query.ego_actions & candidate.ego_actions else set()
        absent -= unscripted
        if unscripted:
            differences.append(ReuseDifference("unverified", "ego_action=lane_change", "not scripted",
                                               "confirm the system changes lanes", cost=0, verified=False))
        extra = candidate.ego_actions - query.ego_actions - {"unknown"} - controlled
        # Driving at a steady speed is how an asset reads any ego that moves; a requirement that names
        # no longitudinal behavior (only a lane departure, or the system taking over) asks nothing of it.
        if not query.ego_actions & LONGITUDINAL:
            extra -= {"cruise"}
        if absent or extra:
            differences.append(
                ReuseDifference(
                    "ego_action",
                    ",".join(sorted(query.ego_actions)),
                    ",".join(sorted(candidate.ego_actions)),
                    "verify ego behavior"
                    if "unknown" in candidate.ego_actions
                    else "modify ego behavior",
                    cost=policy.COST_BEHAVIOR,
                    verified="unknown" not in candidate.ego_actions,
                )
            )
    differences.extend(_route_differences(query, candidate))
    differences.extend(_lateral_speed_differences(query, candidate))
    values = bundle_parameters(asset.bundle)
    visibility = asset_environment(asset.bundle).get("fog_visibility_m")
    if isinstance(visibility, (float, int)):
        values["fog_visibility_m"] = (float(visibility),)
    # A parameter the XML reader cannot find is unverified rather than a known change.
    differences.extend(
        replace(difference, verified=difference.candidate != "not extracted")
        for difference in parameter_differences(query.parameters, values)
    )
    if not any(item.speed_kph is not None for item in query.participant_signatures):
        # Speeds not bound to participants (older revisions) are compared as a multiset.
        differences.extend(
            target_speed_differences(query.target_speeds_kph, candidate.target_speeds_kph,
                                     len(query.participant_signatures))
        )
    differences.extend(environment_differences(query.environment, candidate.environment))
    return tuple(differences)


LANE_SCOPES = {"same_direction": "lanes in one direction", "total": "lanes in total"}


def _lane_differences(query: RetrievalQuery, road) -> list[ReuseDifference]:
    """The road's driving lanes and lane lines against the requirement, in three states.

    Enough lanes or the requested line present: no difference. Too few lanes or no such line on
    the map: a road change. Not readable (road file missing, no driving lanes, no lane lines):
    unverified, never a guess.
    """
    differences = []
    if query.lane_count is not None:
        requested = f"at least {query.lane_count} {LANE_SCOPES[query.lane_count_scope]}"
        actual = road.lanes_same_direction if query.lane_count_scope == "same_direction" else road.lanes_total
        if road.file_missing or not actual:
            differences.append(ReuseDifference("road", requested, "road file missing" if road.file_missing
                                               else "no driving lanes read", "verify lane count",
                                               cost=policy.COST_ROAD, verified=False))
        elif actual < query.lane_count:
            differences.append(ReuseDifference("road", requested, f"{actual} {LANE_SCOPES[query.lane_count_scope]}",
                                               "select a road with more lanes", cost=policy.COST_ROAD))
    if query.lane_marking:
        requested = f"{query.lane_marking} lane line"
        if road.file_missing or not road.lane_markings:
            differences.append(ReuseDifference("road", requested, "road file missing" if road.file_missing
                                               else "no lane lines read", "verify lane lines",
                                               cost=policy.COST_ROAD, verified=False))
        elif query.lane_marking not in road.lane_markings:
            differences.append(ReuseDifference("road", requested, "lines: " + ", ".join(road.lane_markings),
                                               "select or modify OpenDRIVE lane lines", cost=policy.COST_ROAD))
    return differences


def _traffic_control_differences(query: RetrievalQuery, road) -> list[ReuseDifference]:
    """Traffic lights and speed-limit signs the test relies on, from the road file, in three states.

    Present (a requested speed limit among the signed ones; of several requested, any one): no
    difference. Absent from a readable road: a road change, or a sign value to set. Road file missing:
    unverified, never a guess.
    """
    differences = []
    wanted = set(query.traffic_controls)
    if query.speed_limits_kph:
        wanted.discard("speed_limit")  # the values say it
        requested = "speed_limit=" + "/".join(f"{value:g}" for value in query.speed_limits_kph) + " km/h"
        tolerance = policy.PARAMETER_TOLERANCE["speed_limit_kph"]
        if road.file_missing:
            differences.append(ReuseDifference("road", requested, "road file missing", "verify speed limit signs",
                                               cost=policy.COST_ROAD, verified=False))
        elif not road.speed_limits_kph:
            differences.append(ReuseDifference("road", requested, "no speed limit sign",
                                               "add a speed limit sign to OpenDRIVE", cost=policy.COST_ROAD))
        elif not any(abs(asked - signed) <= tolerance
                     for asked in query.speed_limits_kph for signed in road.speed_limits_kph):
            differences.append(ReuseDifference(
                "road", requested, "speed_limit=" + "/".join(f"{value:g}" for value in road.speed_limits_kph) + " km/h",
                "set the speed limit sign value", cost=policy.COST_PARAMETER))
    present = {"speed_limit": bool(road.speed_limits_kph), "traffic_light": bool(road.furniture.get("traffic_light"))}
    for control in sorted(wanted):
        if road.file_missing:
            differences.append(ReuseDifference("road", control, "road file missing", "verify traffic control",
                                               cost=policy.COST_ROAD, verified=False))
        elif not present[control]:
            differences.append(ReuseDifference("road", control, f"no {control}", "add traffic control to OpenDRIVE",
                                               cost=policy.COST_ROAD))
    return differences


def _route_differences(query: RetrievalQuery, candidate: RetrievalQuery) -> list[ReuseDifference]:
    """The way the ego leaves the junction: another turn is a route to change in the same junction,
    an unread one is to verify (scene_facts.ego_turn reads one wherever the road leaves no choice)."""
    if not query.ego_turn or query.ego_turn == candidate.ego_turn:
        return []
    requested = f"ego_turn={query.ego_turn}"
    if "ego_turn" in query.figure_facts:
        return [_figure_check(requested, f"ego_turn={candidate.ego_turn}" if candidate.ego_turn else "not read")]
    if not candidate.ego_turn:
        return [ReuseDifference("ego_route", requested, "not read", "verify the ego's route",
                                cost=policy.COST_PARAMETER, verified=False)]
    return [ReuseDifference("ego_route", requested, f"ego_turn={candidate.ego_turn}", "change the ego's route",
                            cost=policy.COST_BEHAVIOR)]


def _lateral_speed_differences(query: RetrievalQuery, candidate: RetrievalQuery) -> list[ReuseDifference]:
    """Each stated lateral speed, or the stated range, against the speeds the asset scripts. An asset
    that scripts none (a drift left to the simulator, a lane change of another shape) is not compared:
    many libraries leave the speed to the test bench, so not reading it says nothing against the asset."""
    speeds = candidate.lateral_speeds_mps
    if not speeds:
        return []
    tolerance = policy.LATERAL_SPEED_TOLERANCE_MPS
    differences = []
    if query.lateral_speed_range_mps:
        low, high = query.lateral_speed_range_mps
        if not any(low - tolerance <= speed <= high + tolerance for speed in speeds):
            closest = min(speeds, key=lambda speed: min(abs(speed - low), abs(speed - high)))
            differences.append(ReuseDifference(
                "parameter", f"lateral_speed_mps={low:g}-{high:g}", f"lateral_speed_mps={closest:g}",
                "set parameter in XOSC", cost=policy.COST_PARAMETER))
    for value in query.lateral_speeds_mps:
        closest = min(speeds, key=lambda speed: abs(speed - value))
        if abs(closest - value) > tolerance:
            differences.append(ReuseDifference(
                "parameter", f"lateral_speed_mps={value:g}", f"lateral_speed_mps={closest:g}",
                "set parameter in XOSC", cost=policy.COST_PARAMETER))
    return differences


def _occlusion_differences(query: RetrievalQuery, candidate: RetrievalQuery) -> list[ReuseDifference]:
    placed = all(item.bearing != "unknown"
                 for item in (*candidate.participant_signatures, *candidate.scenery_signatures))
    return [
        ReuseDifference("relation", f"{blocker} occludes {target}", "not found",
                        "place an occluding participant", cost=policy.COST_RELATION, verified=placed)
        for blocker, target in sorted(query.occlusions - candidate.occlusions)
    ]


def _intent_differences(query: RetrievalQuery, candidate: RetrievalQuery) -> list[ReuseDifference]:
    differences = []
    # A driver's request to the system (a lane-change request or confirmation) is a driver input a
    # driver-intervention test can rest on when the ego is to change lanes, and also how a functional
    # test triggers the function ("驾驶员触发的换道" reads either way): it satisfies such an
    # intervention, and only the inputs that take over the controls (pedals, wheel) count against
    # a functional test.
    requested = bool(query.driver_intervention and candidate.driver_request and "lane_change" in query.ego_actions)
    actual = candidate.driver_intervention or requested
    if query.driver_intervention is not None and query.driver_intervention != actual:
        # Driver inputs are one action of the story (an override of the wheel or a pedal while the
        # system acts): adding or removing them changes one behavior. What a driver-intervention test
        # reuses is the run that makes the system act (the drift, the cut-in, the lane change).
        differences.append(ReuseDifference(
            "ego_action",
            "driver_intervention" if query.driver_intervention else "no driver_intervention",
            "driver_intervention" if actual else "no driver_intervention",
            "add driver input override" if query.driver_intervention else "remove driver input override",
            cost=policy.COST_BEHAVIOR,
        ))
    if query.parking_operation and query.parking_operation != candidate.parking_operation:
        # Parking in against parking out is a change; a driving scenario is no parking test at all.
        differences.append(ReuseDifference(
            "ego_action", query.parking_operation, candidate.parking_operation or "no parking",
            "change parking operation" if candidate.parking_operation else "build a parking test",
            blocking=not candidate.parking_operation,
            cost=policy.COST_BEHAVIOR if candidate.parking_operation else policy.COST_PARTICIPANT,
        ))
    return differences


def _static_obstacles(expected: ParticipantSignature, actual: ParticipantSignature) -> bool:
    """Both are standing obstacles: which way an obstacle faces is not compared."""
    return all(item.kind == "obstacle" and set(item.actions) == {"static"} for item in (expected, actual))


def _facing(signature: ParticipantSignature, other: ParticipantSignature) -> str:
    """The facing compared with `other`: either moment when the ego turns (turned_facing)."""
    if _static_obstacles(signature, other):
        return "any"
    return other.facing if signature.turned_facing and other.facing == signature.turned_facing else signature.facing


def _kind(signature: ParticipantSignature, other: ParticipantSignature) -> str:
    """The kind, or the other's kind when this one's 3D model shows it (a tricycle authored as a car)."""
    return other.kind if other.kind in signature.traits else signature.kind


def _moves(signature: ParticipantSignature) -> bool:
    return bool(set(signature.actions) - {"static", "unknown"})


def _side(bearing: str) -> str:
    return bearing.split("_", 1)[1] if "_" in bearing else ""


def _actions(actual: ParticipantSignature, expected: ParticipantSignature) -> set[str]:
    """`actual`'s behaviors as compared with `expected`'s.

    Keeping its distance to another (LongitudinalDistanceAction) is how a moving participant
    drives along until the test event: for a requirement that has it move otherwise, it is no
    behavior of its own, and it drives as a requested cruise does.
    """
    actions = set(actual.actions)
    if "following" in actions and "following" not in expected.actions and _moves(expected):
        actions.discard("following")
        actions |= {"cruise"} & set(expected.actions)
    return actions


def _retimed(expected: ParticipantSignature, actual: ParticipantSignature) -> bool:
    """Both move the same way on the same side of the ego, one further ahead or behind.

    Where a moving participant is depends on when it is looked at: a requirement describes the
    interaction (right alongside when the ego changes lanes), an asset where it starts (right
    behind, catching up). Moving its start or retiming its trigger, not another story. Doing
    something else as well is another interaction (a car cutting in from ahead does not overtake
    from behind), and the same lane stays apart (a lead car, a car closing in from behind).
    """
    return (expected.bearing != actual.bearing and set(expected.actions) == _actions(actual, expected)
            and _moves(expected) and _side(expected.bearing) == _side(actual.bearing) in {"left", "right"})


def _turned(expected: ParticipantSignature, actual: ParticipantSignature) -> bool:
    """Both stand still and face different known ways: one heading to set (a stopped car turned
    oblique, a child turned to the road). Near 30° the facing classes split noisily: an oblique car
    reads as crossing in a standard and as same-way in its asset."""
    return (set(expected.actions) == set(actual.actions) == {"static"} and not _static_obstacles(expected, actual)
            and expected.facing != _facing(actual, expected) and "unknown" not in {expected.facing, actual.facing})


def _figure_check(requested: str, candidate: str) -> ReuseDifference:
    """A fact the requirement's figure shows, not its text, that the asset does not show."""
    return ReuseDifference("figure", requested, candidate, "check against the figure",
                           cost=policy.COST_FIGURE, verified=False)


def _drawn(expected: ParticipantSignature, actual: ParticipantSignature) -> ParticipantSignature:
    """`expected` with each component it read from a figure taken from `actual` where both are
    known and differ: a figure aids ranking (_figure_check), it never makes a conflict or a change."""
    taken = {}
    if ("bearing" in expected.from_figure and expected.bearing != actual.bearing
            and "unknown" not in {expected.bearing, actual.bearing}):
        taken["bearing"] = actual.bearing
    shown = _facing(actual, expected)
    if ("facing" in expected.from_figure and _facing(expected, actual) != shown
            and "unknown" not in {expected.facing, shown}):
        taken["facing"] = shown
    return replace(expected, **taken) if taken else expected


def _placement(expected: ParticipantSignature, actual: ParticipantSignature) -> str:
    """The change that places `actual` like `expected` when that is all that differs, else ""."""
    if _retimed(expected, actual):
        return "move start position or retime trigger"
    return "turn standing participant" if _turned(expected, actual) else ""


def _conflicts(expected: ParticipantSignature, actual: ParticipantSignature) -> tuple[int, bool, int]:
    """(known identity conflicts, known behavior conflict, unknown components of `actual`).

    An unknown component never proves a conflict. A stop satisfies a requested speed change,
    keeping a distance a requested cruise (_actions). A difference in placement alone
    (_placement) is a change, not a conflict.
    """
    identity = zip(
        (expected.kind, actual.bearing if _retimed(expected, actual) else expected.bearing,
         actual.facing if _turned(expected, actual) else _facing(expected, actual)),
        (_kind(actual, expected), actual.bearing, _facing(actual, expected)),
    )
    mismatches = sum(left != right and "unknown" not in {left, right} for left, right in identity)
    known_actions = set(expected.actions) - {"unknown"}
    absent = known_actions - _actions(actual, expected)
    if set(actual.actions) == {"stop"} and known_actions == {"speed_change"}:
        absent = set()
    unknowns = sum(item == "unknown" for item in (actual.kind, actual.bearing, _facing(actual, expected))) + (
        "unknown" in actual.actions
    )
    return mismatches, bool(absent and "unknown" not in actual.actions), unknowns


def _pair_differences(expected: ParticipantSignature, actual: ParticipantSignature | None) -> list[ReuseDifference]:
    """What it takes to make candidate participant `actual` (None: absent) into the requested one."""
    signature = expected.key()
    if actual is None:
        return [ReuseDifference("participant_signature", signature, "missing", "add participant", True,
                                policy.COST_PARTICIPANT)]
    result = []
    compared = _drawn(expected, actual)
    mismatch, action_mismatch, _ = _conflicts(compared, actual)
    if mismatch:
        result.append(ReuseDifference("participant_signature", signature, actual.key(),
                                      "rebuild participant interaction", True, policy.COST_PARTICIPANT))
    elif action_mismatch:
        result.append(ReuseDifference("action", signature, actual.key(), "modify participant behavior",
                                      cost=policy.COST_BEHAVIOR))
    else:
        extra_actions = _actions(actual, expected) - set(expected.actions) - {"unknown"}
        # A stop is a speed change; a requirement that names no behavior leaves every one open.
        if set(actual.actions) == {"stop"} and set(expected.actions) == {"speed_change"} or "unknown" in expected.actions:
            extra_actions = set()
        if extra_actions:
            result.append(ReuseDifference("action", signature, actual.key(), "remove additional participant behavior",
                                          cost=policy.COST_BEHAVIOR))
    if not mismatch and (placement := _placement(compared, actual)):
        result.append(ReuseDifference("placement", signature, actual.key(), placement, cost=policy.COST_PLACEMENT))
    if not mismatch and any(
        "unknown" in (item.kind, item.bearing, _facing(item, other), *item.actions)
        for item, other in ((compared, actual), (actual, compared))
    ):
        result.append(ReuseDifference("participant_topology", signature, actual.key(), "verify participant facts",
                                      cost=policy.COST_VERIFY_PARTICIPANT, verified=False))
    if not mismatch and compared is not expected:
        result.append(_figure_check(signature, actual.key()))
    if not mismatch and expected.speed_kph is not None:
        result.extend(_speed_difference(expected, actual))
    return result


def _speed_difference(expected: ParticipantSignature, actual: ParticipantSignature) -> list[ReuseDifference]:
    requested = f"{expected.key()} speed={expected.speed_kph:g} km/h"
    if actual.speed_kph is None:
        return [ReuseDifference("parameter", requested, "not extracted", "set participant initial speed",
                                cost=policy.COST_PARAMETER, verified=False)]
    if abs(actual.speed_kph - expected.speed_kph) > policy.TARGET_SPEED_TOLERANCE_KPH:
        return [ReuseDifference("parameter", requested, f"speed={actual.speed_kph:g} km/h",
                                "set participant initial speed", cost=policy.COST_PARAMETER)]
    return []


def _extra_difference(actual: ParticipantSignature) -> ReuseDifference:
    return ReuseDifference("participant_signature", "no additional participant", actual.key(),
                           "remove extra participant", cost=policy.COST_EXTRA_PARTICIPANT)


def _background_differences(left_over: list[ParticipantSignature]) -> list[ReuseDifference]:
    """Left-over background participants, one low-cost difference per signature, as props are
    grouped: 34 parked cars along a narrow passage do not make the asset a major change."""
    counts = Counter(item.key() for item in left_over)
    return [ReuseDifference("background_participant", "no additional participant",
                            key if count == 1 else f"{count} × {key}", "keep or remove background participants",
                            cost=policy.COST_BACKGROUND_PARTICIPANT)
            for key, count in sorted(counts.items())]


def _score(differences: list[ReuseDifference]) -> tuple[int, float, float, int]:
    """The ranking key of a set of differences (blocking count, then change cost, then the facts
    drawn in a figure it does not show), then unverified count."""
    return (sum(item.blocking for item in differences),
            sum(item.cost for item in differences if item.tier != policy.TIER_FIGURE),
            sum(item.cost for item in differences if item.tier == policy.TIER_FIGURE),
            sum(not item.verified for item in differences))


def _pair(
    requested: tuple[ParticipantSignature, ...], candidates: tuple[ParticipantSignature, ...],
    scenery: int = 0,
) -> list[int | None]:
    """The candidate index paired with each requested participant (None: none left).

    Pairing is one-to-one, so participant multiplicity counts. Among all pairings it picks the one
    whose differences rank best, the same order candidates are ranked by. The last `scenery`
    candidates are scenery groups: they may stand for a requested participant, but cost nothing
    when left unpaired. Nor do background participants here: their low cost is per group.
    """
    table = [[_score(_pair_differences(expected, actual)) for actual in candidates] for expected in requested]
    absent = [_score(_pair_differences(expected, None)) for expected in requested]
    extra = [_score([_extra_difference(actual)]) if index < len(candidates) - scenery and not actual.background
             else (0, 0, 0, 0) for index, actual in enumerate(candidates)]
    if max(len(requested), len(candidates)) <= ENUMERATION_LIMIT:
        return _enumerate(table, absent, extra)
    return _assign(table, absent, extra)



def _enumerate(table, absent, extra) -> list[int | None]:
    slots = [*range(len(extra)), *[None] * max(0, len(absent) - len(extra))]

    def rank(pairing):
        scores = [table[row][column] if column is not None else absent[row] for row, column in enumerate(pairing)]
        scores += [extra[column] for column in set(range(len(extra))) - set(pairing)]
        blocking, cost, figure, unverified = (sum(values) for values in zip(*scores)) if scores else (0, 0, 0, 0)
        # Ties keep candidates in key order, so the result does not depend on enumeration order.
        return (blocking, round(cost, 6), round(figure, 6), unverified,
                [len(extra) if column is None else column for column in pairing])

    return list(min(set(permutations(slots, len(absent))), key=rank))


def _assign(table, absent, extra) -> list[int | None]:
    """Minimum-cost assignment (Hungarian method) on the scores folded into one exact integer."""

    def weight(score):
        blocking, cost, figure, unverified = score
        return blocking * 10**18 + round(cost * 1000) * 10**10 + round(figure * 1000) * 10**4 + unverified

    rows, columns = len(absent), len(extra)
    size = max(rows, columns)
    matrix = [[weight(table[row][column]) if row < rows and column < columns
               else weight(absent[row]) if row < rows
               else weight(extra[column]) if column < columns else 0
               for column in range(size)] for row in range(size)]
    paired = _hungarian(matrix)
    return [paired[row] if paired[row] < columns else None for row in range(rows)]


def _hungarian(matrix: list[list[int]]) -> list[int]:
    """Column assigned to each row of a square cost matrix, minimizing the total (O(n^3) with potentials)."""
    size = len(matrix)
    row_potential, column_potential = [0] * (size + 1), [0] * (size + 1)
    owner = [0] * (size + 1)  # owner[column] = row (1-based; 0 = free)
    for row in range(1, size + 1):
        owner[0] = row
        column = 0
        best = [None] * (size + 1)
        previous = [0] * (size + 1)
        used = [False] * (size + 1)
        while owner[column]:
            used[column] = True
            current, delta, chosen = owner[column], None, 0
            for candidate in range(1, size + 1):
                if used[candidate]:
                    continue
                reduced = matrix[current - 1][candidate - 1] - row_potential[current] - column_potential[candidate]
                if best[candidate] is None or reduced < best[candidate]:
                    best[candidate], previous[candidate] = reduced, column
                if delta is None or best[candidate] < delta:
                    delta, chosen = best[candidate], candidate
            for candidate in range(size + 1):
                if used[candidate]:
                    row_potential[owner[candidate]] += delta
                    column_potential[candidate] -= delta
                else:
                    best[candidate] -= delta
            column = chosen
        while column:
            owner[column] = owner[previous[column]]
            column = previous[column]
    assigned = [0] * size
    for column in range(1, size + 1):
        assigned[owner[column] - 1] = column - 1
    return assigned


def participant_differences(
    requested: tuple[ParticipantSignature, ...], candidates: tuple[ParticipantSignature, ...],
    scenery: tuple[ParticipantSignature, ...] = (),
) -> list[ReuseDifference]:
    # A scenery group is every prop standing there: it can stand for each requested obstacle
    # there (cones and barriers ahead are both the group ahead).
    copies = max(1, sum(item.kind == "obstacle" for item in requested))
    pool = (*candidates, *(item for item in scenery for _ in range(copies)))
    pairing = _pair(requested, pool, len(pool) - len(candidates))
    result = []
    for expected, column in zip(requested, pairing):
        result.extend(_pair_differences(expected, pool[column] if column is not None else None))
    paired = set(pairing)
    left_over = [actual for column, actual in enumerate(candidates) if column not in paired]
    result.extend(_extra_difference(actual) for actual in left_over if not actual.background)
    result.extend(_background_differences([actual for actual in left_over if actual.background]))
    return result
