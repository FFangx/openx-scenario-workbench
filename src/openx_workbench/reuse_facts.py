"""Facts read from a parsed asset for reuse comparison: participants, behaviors, parameters, road."""

from __future__ import annotations

import math

from . import reuse_policy as policy
from .catalog import OpenXAsset
from .models import ParseBundle
from .reuse_geometry import _adjacent_lane, _bearing, _relative_facing, _relative_offset
from .scene_package import (
    ParticipantSignature,
    RetrievalQuery,
    canonical_features,
    canonical_scenario_families,
)


def bundle_scenario_families(bundle: ParseBundle) -> set[str]:
    scenario = bundle.scenario
    return canonical_scenario_families(scenario.name or scenario.description or "")


def _actions_of(bundle: ParseBundle, actor: str) -> list:
    return [
        item
        for item in bundle.scenario.actions
        if actor.casefold()
        in {name.strip().casefold() for name in (item.actor or "").split(",")}
    ]


def actor_initial_speed_kph(bundle: ParseBundle, actor: str) -> float | None:
    """The actor's initialization speed, when the scenario sets exactly one."""
    values = {
        item.target_value
        for item in _actions_of(bundle, actor)
        if item.kind == "SpeedAction" and item.phase == "init"
    }
    if len(values) != 1:
        return None
    value = values.pop()
    return value * 3.6 if value is not None and math.isfinite(value) else None


def actor_actions(bundle: ParseBundle, actor: str) -> set[str]:
    """Distinguish an initialization speed from subsequent speed events."""
    actions = _actions_of(bundle, actor)
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
    elif all(abs(value - current) <= policy.CONSTANT_SPEED_TOLERANCE_MPS for value in events):
        result.add("static" if current == 0 else "cruise")
    elif current > 0 and events == [0]:
        result.add("stop")
    else:
        result.add("speed_change")
        if len(events) > 1:
            result.add("unknown")
    return result


def asset_structure_query(asset: OpenXAsset) -> RetrievalQuery:
    """The asset described in the same terms as a typed requirement."""
    bundle = asset.bundle
    _, _, triggers, roads = bundle_features(bundle)
    roads = (
        {"junction"}
        if "junction" in roads
        else ({"curve"} if "curve" in roads else roads)
    )
    participants = bundle_participant_signatures(bundle, semantic=True)
    return RetrievalQuery(
        text="",
        structured=True,
        tested_function=asset.classification.get("function_type", ""),
        participant_signatures=participants,
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
        target_speeds_kph=tuple(sorted(item.speed_kph for item in participants if item.speed_kph is not None)),
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
    """Non-ego participants in key order.

    `semantic` reads behaviors as the typed vocabulary (cruise, stop, ...) of a
    requirement; otherwise as keyword features of the action names.
    """
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
                speed_kph=actor_initial_speed_kph(bundle, actor),
            )
        )
    return tuple(sorted(signatures, key=ParticipantSignature.key))


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
        if forward > policy.ALONGSIDE_M:
            relations.add("front")
        elif forward < -policy.ALONGSIDE_M:
            relations.add("rear")
        if left > policy.SAME_LANE_M:
            relations.add("left")
        elif left < -policy.SAME_LANE_M:
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


def bundle_features(
    bundle: ParseBundle,
) -> tuple[set[str], set[str], set[str], set[str]]:
    """Keyword features (entities, actions, triggers, road) of the asset's names and geometry."""
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
    if road.file_missing:
        # No geometry to read: the map name is the only road evidence.
        return entities, actions, triggers, set(road.inferred_features)
    road_features: set[str] = set()
    if "line" in road.geometry_types:
        road_features.add("straight")
    if set(road.geometry_types) & {"arc", "spiral", "poly3", "paramPoly3"}:
        road_features.add("curve")
    if road.junction_count:
        road_features.add("junction")
    return entities, actions, triggers, road_features
