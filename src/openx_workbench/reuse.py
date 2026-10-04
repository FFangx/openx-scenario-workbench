from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass

from .catalog import OpenXAsset
from .models import ParseBundle
from .reuse_geometry import _adjacent_lane, _bearing, _relative_facing, _relative_offset
from .scene_package import (
    RetrievalQuery,
    canonical_features,
    canonical_scenario_families,
)


@dataclass(frozen=True, slots=True)
class ReuseDifference:
    category: str
    requested: str
    candidate: str
    action: str
    blocking: bool = False
    cost: float = 1.0
    verified: bool = True


@dataclass(frozen=True, slots=True)
class ParticipantSignature:
    actor: str
    kind: str
    bearing: str
    facing: str
    actions: tuple[str, ...]

    def key(self) -> str:
        actions = "+".join(self.actions) or "static"
        return f"{self.kind}@{self.bearing}:{self.facing}:{actions}"


def compare_query_to_asset(
    query: RetrievalQuery,
    asset: OpenXAsset,
    *,
    candidate_structure: RetrievalQuery | None = None,
) -> tuple[ReuseDifference, ...]:
    if query.structured:
        return _compare_structure(query, asset, candidate_structure)
    entities, actions, triggers, road_features = bundle_features(asset.bundle)
    differences: list[ReuseDifference] = [
        ReuseDifference("parameter_resolution", "resolved scenario parameters", item["detail"],
                        "resolve parameter before confirming reuse", verified=False)
        for item in asset.bundle.scenario.parameter_issues
    ]
    candidate_families = bundle_scenario_families(asset.bundle)
    participant_families = {"car_to_car", "car_to_ptw", "car_to_vru"}
    for family in sorted(query.scenario_families - candidate_families):
        # Broad participant classes and maneuver labels are separate dimensions.
        # An absent label is unknown, rather than evidence of incompatibility.
        comparable = {
            item
            for item in candidate_families
            if (item in participant_families) == (family in participant_families)
        }
        differences.append(
            ReuseDifference(
                "scenario",
                family,
                ", ".join(sorted(comparable)) if comparable else "unknown",
                "build a different scenario family"
                if comparable
                else "verify candidate scenario family",
                blocking=bool(comparable),
                cost=10.0 if comparable else 2.0,
            )
        )
    participant_differences = _missing_participants(
        query.participant_signatures,
        tuple(item.key() for item in bundle_participant_signatures(asset.bundle)),
    )
    differences.extend(participant_differences)
    differences.extend(
        _missing(
            "entity",
            query.entity_kinds,
            entities,
            "add or replace entity",
            blocking=True,
            cost=6.0,
        )
    )
    if not any(
        item.category == "participant_topology" for item in participant_differences
    ):
        differences.extend(
            _missing(
                "relation",
                query.participant_relations,
                bundle_participant_relations(asset.bundle),
                "adjust participant placement",
                cost=2.0,
            )
        )
    differences.extend(
        _missing(
            "action",
            query.action_kinds,
            actions,
            "modify storyboard action",
            cost=2.0,
        )
    )
    differences.extend(
        _missing(
            "trigger",
            query.trigger_kinds,
            triggers,
            "modify start trigger",
            cost=1.5,
        )
    )
    differences.extend(
        _missing(
            "road",
            query.road_features,
            road_features,
            "select or modify OpenDRIVE",
            cost=1.0,
        )
    )
    differences.extend(
        _parameter_differences(query.parameters, bundle_parameters(asset.bundle))
    )
    return tuple(differences)


def bundle_scenario_families(bundle: ParseBundle) -> set[str]:
    scenario = bundle.scenario
    return canonical_scenario_families(scenario.name or scenario.description or "")


def actor_actions(bundle: ParseBundle, actor: str) -> set[str]:
    """Distinguish an initialization speed from subsequent speed events."""
    actions = [
        item
        for item in bundle.scenario.actions
        if actor.casefold()
        in {name.strip().casefold() for name in (item.actor or "").split(",")}
    ]
    result = {
        "lane_change"
        for item in actions
        if item.kind == "LaneChangeAction" and item.phase == "story"
    }
    if any(
        item.phase == "story" and item.kind not in {"SpeedAction", "LaneChangeAction"}
        for item in actions
    ):
        result.add("unknown")
    initial = [
        item.target_value
        for item in actions
        if item.kind == "SpeedAction" and item.phase == "init"
    ]
    events = [
        item.target_value
        for item in actions
        if item.kind == "SpeedAction" and item.phase == "story"
    ]
    if not initial or any(
        value is None or not math.isfinite(value) for value in initial + events
    ):
        result.add("unknown")
        return result
    current = initial[-1]
    if len(set(initial)) != 1:
        result.add("unknown")
        return result
    if current < 0:
        result.add("reverse")
    elif all(abs(value - current) <= 0.01 for value in events):
        result.add("static" if current == 0 else "cruise")
    elif current > 0 and events == [0]:
        result.add("stop")
    else:
        result.add("speed_change")
        if len(events) > 1:
            result.add("unknown")
    return result


def asset_structure_query(asset: OpenXAsset) -> RetrievalQuery:
    bundle = asset.bundle
    _, _, triggers, roads = bundle_features(bundle)
    roads = (
        {"junction"}
        if "junction" in roads
        else ({"curve"} if "curve" in roads else roads)
    )
    speeds = [
        item.target_value * 3.6
        for item in bundle.scenario.actions
        if item.kind == "SpeedAction"
        and item.phase == "init"
        and item.target_value is not None
        and item.actor
        and item.actor.casefold() != "ego"
    ]
    return RetrievalQuery(
        text="",
        structured=True,
        tested_function=asset.classification.get("function_type", ""),
        participant_signatures=tuple(
            item.key() for item in bundle_participant_signatures(bundle, semantic=True)
        ),
        ego_actions=frozenset(actor_actions(bundle, "ego")),
        trigger_kinds=frozenset(triggers),
        road_features=frozenset(roads),
        parameters=tuple(
            (key, values[0])
            for key, values in sorted(
                bundle_parameters(bundle, initial_only=True).items()
            )
            if values
        ),
        target_speeds_kph=tuple(sorted(set(speeds))),
        environment=tuple(
            (key, str(value))
            for key, value in sorted(bundle.scenario.environment.items())
            if key in {"weather", "time_of_day"}
        ),
        unverified=tuple(
            f"{item['path']} @{item['attribute']}: {item['detail']}"
            for item in bundle.scenario.parameter_issues
        ),
    )


def _signature_parts(value: str) -> tuple[str, str, str, set[str]]:
    kind_bearing, facing, actions = value.split(":", 2)
    kind, bearing = kind_bearing.split("@", 1)
    return kind, bearing, facing, set(actions.split("+"))


def _structured_participants(
    requested: tuple[str, ...], candidates: tuple[str, ...]
) -> list[ReuseDifference]:
    remaining = list(candidates)
    result = []
    for signature in requested:
        expected = _signature_parts(signature)

        def compatibility(value):
            actual = _signature_parts(value)
            mismatches = sum(
                left != right and "unknown" not in {left, right}
                for left, right in zip(expected[:3], actual[:3])
            )
            known_actions = expected[3] - {"unknown"}
            missing_actions = known_actions - actual[3]
            if actual[3] == {"stop"} and known_actions == {"speed_change"}:
                missing_actions = set()
            return (
                mismatches,
                bool(missing_actions and "unknown" not in actual[3]),
                sum(item == "unknown" for item in actual[:3])
                + ("unknown" in actual[3]),
                value,
            )

        # One-to-one matching preserves participant multiplicity. Favor the
        # fewest known conflicts; an unknown component never proves conflict.
        if not remaining:
            result.append(
                ReuseDifference(
                    "participant_signature",
                    signature,
                    "missing",
                    "add participant",
                    True,
                    8,
                )
            )
            continue
        selected = min(remaining, key=compatibility)
        remaining.remove(selected)
        mismatch, action_mismatch, _, _ = compatibility(selected)
        actual = _signature_parts(selected)
        if mismatch:
            result.append(
                ReuseDifference(
                    "participant_signature",
                    signature,
                    selected,
                    "rebuild participant interaction",
                    True,
                    8,
                )
            )
        elif action_mismatch:
            result.append(
                ReuseDifference(
                    "action", signature, selected, "modify participant behavior", cost=2
                )
            )
        else:
            extra_actions = actual[3] - expected[3] - {"unknown"}
            if actual[3] == {"stop"} and expected[3] == {"speed_change"}:
                extra_actions = set()
            if extra_actions:
                result.append(
                    ReuseDifference(
                        "action",
                        signature,
                        selected,
                        "remove additional participant behavior",
                        cost=2,
                    )
                )
        if not mismatch and (
            "unknown" in expected[:3]
            or "unknown" in actual[:3]
            or "unknown" in expected[3]
            or "unknown" in actual[3]
        ):
            result.append(
                ReuseDifference(
                    "participant_topology",
                    signature,
                    selected,
                    "verify participant facts",
                    cost=2,
                    verified=False,
                )
            )
    for signature in remaining:
        result.append(
            ReuseDifference(
                "participant_signature",
                "no additional participant",
                signature,
                "remove extra participant",
                cost=3,
            )
        )
    return result


def _compare_structure(
    query: RetrievalQuery, asset: OpenXAsset, candidate: RetrievalQuery | None = None
) -> tuple[ReuseDifference, ...]:
    candidate = candidate or asset_structure_query(asset)
    differences = (
        _structured_participants(
            query.participant_signatures, candidate.participant_signatures
        )
        if query.participant_signatures
        else []
    )
    for value in candidate.unverified:
        differences.append(ReuseDifference(
            "parameter_resolution", "resolved scenario parameters", value,
            "resolve parameter before confirming reuse", verified=False,
        ))
    for value in query.unverified:
        differences.append(
            ReuseDifference(
                "unverified",
                value,
                "not extracted",
                "verify declared requirement",
                verified=False,
            )
        )
    if query.tested_function:
        actual = candidate.tested_function
        if actual in {"", "未知", "unknown"}:
            differences.append(
                ReuseDifference(
                    "function",
                    query.tested_function,
                    "unknown",
                    "confirm tested function",
                    verified=False,
                )
            )
        elif actual != query.tested_function:
            differences.append(
                ReuseDifference(
                    "function",
                    query.tested_function,
                    actual,
                    "change tested function",
                    True,
                    10,
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
        _missing(
            "road",
            query.road_features - {"motorway"},
            set(candidate.road_features),
            "select or modify OpenDRIVE",
        )
    )
    differences.extend(
        _missing(
            "trigger",
            query.trigger_kinds,
            set(candidate.trigger_kinds),
            "modify start trigger",
            cost=1.5,
        )
    )
    if query.ego_actions:
        missing = query.ego_actions - candidate.ego_actions
        if missing or (candidate.ego_actions - query.ego_actions - {"unknown"}):
            differences.append(
                ReuseDifference(
                    "ego_action",
                    ",".join(sorted(query.ego_actions)),
                    ",".join(sorted(candidate.ego_actions)),
                    "verify ego behavior"
                    if "unknown" in candidate.ego_actions
                    else "modify ego behavior",
                    cost=2,
                    verified="unknown" not in candidate.ego_actions,
                )
            )
    values = bundle_parameters(asset.bundle, initial_only=True)
    visibility = asset.bundle.scenario.environment.get("fog_visibility_m")
    if isinstance(visibility, (float, int)):
        values["fog_visibility_m"] = (float(visibility),)
    for difference in _parameter_differences(query.parameters, values):
        from dataclasses import replace

        differences.append(
            replace(difference, verified=difference.candidate != "not extracted")
        )
    if query.target_speeds_kph:
        actual = candidate.target_speeds_kph
        if len(query.target_speeds_kph) != len(actual) or any(
            abs(left - right) > 0.5
            for left, right in zip(query.target_speeds_kph, actual)
        ):
            differences.append(
                ReuseDifference(
                    "parameter",
                    f"target speeds={query.target_speeds_kph}",
                    str(actual) if actual else "not extracted",
                    "set target initial speeds",
                    cost=0.5,
                    verified=bool(actual),
                )
            )
    environment = dict(candidate.environment)
    for key, expected in query.environment:
        actual = environment.get(key)
        if actual != expected:
            differences.append(
                ReuseDifference(
                    "environment",
                    f"{key}={expected}",
                    actual or "unknown",
                    "verify or change environment",
                    cost=0.5,
                    verified=actual is not None,
                )
            )
    return tuple(differences)


def bundle_parameters(
    bundle: ParseBundle, *, initial_only: bool = False
) -> dict[str, tuple[float, ...]]:
    values: dict[str, list[float]] = {}
    for trigger in bundle.scenario.triggers:
        if trigger.value is None:
            continue
        if trigger.kind == "TimeToCollisionCondition":
            values.setdefault("ttc_s", []).append(trigger.value)
        elif trigger.kind in {"RelativeDistanceCondition", "DistanceCondition"}:
            values.setdefault("distance_m", []).append(trigger.value)

    ego_speeds = [
        action.target_value * 3.6
        for action in bundle.scenario.actions
        if action.actor
        and action.actor.casefold() == "ego"
        and action.target_value is not None
        and (action.target_value >= 0 if initial_only else action.target_value > 0)
        and (action.phase == "init" if initial_only else True)
    ]
    if ego_speeds:
        values["ego_speed_kph"] = [ego_speeds[0]]
    return {
        name: tuple(sorted(set(round(value, 4) for value in candidates)))
        for name, candidates in values.items()
    }


def bundle_participant_signatures(
    bundle: ParseBundle, *, semantic: bool = False
) -> tuple[ParticipantSignature, ...]:
    scenario = bundle.scenario
    positions = {
        item.actor.casefold(): item for item in scenario.positions if item.actor
    }
    ego = positions.get("ego")
    actions: dict[str, set[str]] = {}
    for action in scenario.actions:
        action_kinds = canonical_features(action.kind)[1]
        for actor in (name.strip() for name in (action.actor or "").split(",")):
            if actor:
                actions.setdefault(actor.casefold(), set()).update(action_kinds)

    signatures: list[ParticipantSignature] = []
    for entity in scenario.entities:
        actor = entity.name.casefold()
        if actor == "ego":
            continue
        target = positions.get(actor)
        offset = (
            _relative_offset(ego, target, bundle.road_geometry)
            if ego is not None and target is not None
            else None
        )
        signatures.append(
            ParticipantSignature(
                actor=entity.name,
                kind=_participant_kind(entity.kind, entity.category),
                bearing=_bearing(*offset) if offset is not None else "unknown",
                facing=(
                    _relative_facing(ego, target, bundle.road_geometry)
                    if ego is not None and target is not None
                    else "unknown"
                ),
                actions=tuple(
                    sorted(
                        actor_actions(bundle, actor)
                        if semantic
                        else actions.get(actor, set())
                    )
                ),
            )
        )
    return tuple(sorted(signatures, key=lambda item: item.key()))


def bundle_participant_relations(bundle: ParseBundle) -> set[str]:
    positions = {
        item.actor.casefold(): item for item in bundle.scenario.positions if item.actor
    }
    ego = positions.get("ego")
    if ego is None:
        return set()

    relations: set[str] = set()
    for actor, target in positions.items():
        if actor == "ego":
            continue
        forward_left = _relative_offset(ego, target, bundle.road_geometry)
        if forward_left is None:
            continue
        forward, left = forward_left
        if forward > 5.0:
            relations.add("front")
        elif forward < -5.0:
            relations.add("rear")
        if left > 1.5:
            relations.add("left")
        elif left < -1.5:
            relations.add("right")
        if _adjacent_lane(ego, target):
            relations.add("adjacent_lane")
    return relations


def _participant_kind(kind: str, category: str | None) -> str:
    text = f"{kind} {category or ''}".casefold()
    if any(term in text for term in ("motorbike", "motorcycle", "ptw")):
        return "motorcycle"
    if any(term in text for term in ("bicycle", "cyclist")):
        return "cyclist"
    if kind == "pedestrian":
        return "pedestrian"
    if kind == "miscobject":
        return "obstacle"
    if category in {"truck", "bus", "van", "trailer"}:
        return category
    return "vehicle" if kind == "vehicle" else kind


def classify_reuse_level(differences: tuple[ReuseDifference, ...]) -> str:
    if not differences:
        return "direct"
    if any(item.blocking for item in differences):
        return "new_build"
    if any(not item.verified for item in differences):
        return "review"
    return "modify"


def change_cost(differences: tuple[ReuseDifference, ...]) -> float:
    return round(sum(item.cost for item in differences), 3)


def bundle_features(
    bundle: ParseBundle,
) -> tuple[set[str], set[str], set[str], set[str]]:
    scenario = bundle.scenario
    road = bundle.road
    candidate_text = " ".join(
        [
            scenario.name or "",
            scenario.description or "",
            " ".join(item.kind for item in scenario.entities),
            " ".join(filter(None, (item.category for item in scenario.entities))),
            " ".join(item.kind for item in scenario.actions),
            " ".join(item.kind for item in scenario.triggers),
        ]
    )
    entities, actions, triggers, _ = canonical_features(candidate_text)
    road_features: set[str] = set()
    if "line" in road.geometry_types:
        road_features.add("straight")
    if set(road.geometry_types) & {"arc", "spiral", "poly3", "paramPoly3"}:
        road_features.add("curve")
    if road.junction_count:
        road_features.add("junction")
    return entities, actions, triggers, road_features


def _parameter_differences(
    requested: tuple[tuple[str, float], ...],
    candidate: dict[str, tuple[float, ...]],
) -> list[ReuseDifference]:
    tolerances = {"ttc_s": 0.05, "distance_m": 0.1, "ego_speed_kph": 0.5}
    differences: list[ReuseDifference] = []
    for name, expected in requested:
        values = candidate.get(name, ())
        if not values:
            differences.append(
                ReuseDifference(
                    "parameter",
                    f"{name}={expected:g}",
                    "not extracted",
                    "verify and set parameter in XOSC",
                    cost=0.5,
                )
            )
            continue
        closest = min(values, key=lambda value: abs(value - expected))
        if abs(closest - expected) > tolerances.get(name, 0.0):
            differences.append(
                ReuseDifference(
                    "parameter",
                    f"{name}={expected:g}",
                    f"{name}={closest:g}",
                    "set parameter in XOSC",
                    cost=0.5,
                )
            )
    return differences


def _missing(
    category: str,
    requested: frozenset[str],
    candidate: set[str],
    action: str,
    *,
    blocking: bool = False,
    cost: float = 1.0,
) -> list[ReuseDifference]:
    return [
        ReuseDifference(category, value, "missing", action, blocking, cost)
        for value in sorted(requested - candidate)
    ]


def _missing_participants(
    requested: tuple[str, ...],
    candidate: tuple[str, ...],
) -> list[ReuseDifference]:
    remaining = Counter(candidate)
    unresolved: list[str] = []
    for signature in requested:
        if remaining[signature]:
            remaining[signature] -= 1
        else:
            unresolved.append(signature)

    differences: list[ReuseDifference] = []
    for signature in unresolved:
        coarse = _participant_coarse_key(signature)
        fallback = next(
            (
                candidate_signature
                for candidate_signature, count in remaining.items()
                if count
                and _participant_coarse_key(candidate_signature) == coarse
                and (
                    _participant_topology_unknown(signature)
                    or _participant_topology_unknown(candidate_signature)
                )
            ),
            None,
        )
        if fallback is not None:
            remaining[fallback] -= 1
            differences.append(
                ReuseDifference(
                    "participant_topology",
                    signature,
                    fallback,
                    "verify participant placement and facing",
                    cost=2.0,
                )
            )
        else:
            differences.append(
                ReuseDifference(
                    "participant_signature",
                    signature,
                    "missing",
                    "rebuild participant interaction",
                    blocking=True,
                    cost=8.0,
                )
            )
    return differences


def _participant_coarse_key(signature: str) -> tuple[str, str]:
    identity, _, actions = signature.partition(":")
    kind, _, _ = identity.partition("@")
    _, _, actions = actions.partition(":")
    return kind, actions


def _participant_topology_unknown(signature: str) -> bool:
    identity, _, remainder = signature.partition(":")
    _, _, bearing = identity.partition("@")
    facing, _, _ = remainder.partition(":")
    return bearing == "unknown" or facing == "unknown"
