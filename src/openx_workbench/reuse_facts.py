"""Facts read from a parsed asset for reuse comparison: participants, behaviors, parameters, road."""

from __future__ import annotations

from . import reuse_policy as policy
from .catalog import OpenXAsset
from .models import EntityIR, ParseBundle
from .reuse_geometry import _adjacent_lane, _bearing, _relative_facing, _relative_offset
from .scene_facts import (
    ROUTE_TURN_MIN,
    actor_behaviors,
    asset_environment,
    background_participants,
    command_facts,
    condition_facts,
    driver_overrides,
    driver_requests,
    ego_curve_radius,
    ego_turn,
    in_tunnel,
    is_scenery,
    lateral_direction,
    lateral_speeds,
    model_traits,
    occlusions,
    route_turn_angle,
    scene_speed_mps,
)
from .scene_package import (
    ParticipantSignature,
    RetrievalQuery,
    canonical_features,
    canonical_scenario_families,
)


def bundle_scenario_families(bundle: ParseBundle) -> set[str]:
    scenario = bundle.scenario
    return canonical_scenario_families(scenario.name or scenario.description or "")


def actor_speed_kph(bundle: ParseBundle, actor: str) -> float | None:
    """The speed the actor reaches in the scenario (see scene_facts.scene_speed_mps)."""
    value = scene_speed_mps(bundle, actor)
    return value * 3.6 if value is not None else None


def actor_actions(bundle: ParseBundle, actor: str) -> set[str]:
    """The actor's behaviors in the typed requirement vocabulary (see scene_facts.actor_behaviors)."""
    return actor_behaviors(bundle, actor)


def asset_tested_function(asset: OpenXAsset) -> str:
    """An accepted classification, else the function a simulator command switches on."""
    accepted = asset.classification.get("function_type", "")
    if accepted and accepted != "未知":
        return accepted
    return command_facts(asset.bundle)["function"]


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
    ego = command_facts(bundle)
    checks = condition_facts(bundle)
    return RetrievalQuery(
        text="",
        structured=True,
        tested_function=asset_tested_function(asset),
        participant_signatures=participants,
        scenery_signatures=bundle_scenery_signatures(bundle),
        occlusions=occlusions(bundle, _entity_kind),
        driver_intervention=bool(driver_overrides(bundle)),
        driver_request=bool(driver_requests(bundle)),
        parking_operation=ego["parking"],
        ego_actions=frozenset(actor_actions(bundle, "ego")),
        trigger_kinds=frozenset(triggers),
        road_features=frozenset(roads),
        parameters=tuple(
            (key, values[0])
            for key, values in sorted(bundle_parameters(bundle).items())
            if values
        ),
        target_speeds_kph=tuple(sorted(item.speed_kph for item in participants if item.speed_kph is not None)),
        environment=tuple(
            (key, str(value))
            for key, value in sorted(asset_environment(bundle).items())
            if key in {"weather", "time_of_day"}
        ),
        unverified=tuple(
            f"{item['path']} @{item['attribute']}: {item['detail']}"
            for item in bundle.scenario.parameter_issues
        ),
        test_intent="activation_boundary" if checks["activation_boundary"] else "",
        lateral_direction=lateral_direction(bundle),
        lateral_speeds_mps=lateral_speeds(bundle, "ego", actor_speed_kph(bundle, "ego")),
        curve_radius_m=ego_curve_radius(bundle),
        venue_features=frozenset({"tunnel"}) if in_tunnel(bundle) else frozenset(),
        ego_turn=ego_turn(bundle),
    )


def bundle_parameters(bundle: ParseBundle) -> dict[str, tuple[float, ...]]:
    values: dict[str, list[float]] = {}
    for trigger in bundle.scenario.triggers:
        if trigger.value is None:
            continue
        if trigger.kind == "TimeToCollisionCondition":
            values.setdefault("ttc_s", []).append(trigger.value)
        elif trigger.kind in {"RelativeDistanceCondition", "DistanceCondition"}:
            values.setdefault("distance_m", []).append(trigger.value)

    ego_speed = actor_speed_kph(bundle, "ego")
    if ego_speed is not None:
        values["ego_speed_kph"] = [ego_speed]
    return {
        name: tuple(sorted(set(round(value, 4) for value in candidates)))
        for name, candidates in values.items()
    }


def bundle_participant_signatures(
    bundle: ParseBundle, *, semantic: bool = False, scenery: bool = False
) -> tuple[ParticipantSignature, ...]:
    """Non-ego traffic participants in key order; with `scenery`, the scenery props instead.

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
    background = background_participants(bundle) if not scenery else frozenset()
    turn = route_turn_angle(bundle) if not scenery else None
    turns = turn is not None and abs(turn) >= ROUTE_TURN_MIN

    signatures: list[ParticipantSignature] = []
    for entity in scenario.entities:
        actor = entity.name.casefold()
        if actor == "ego" or is_scenery(entity) != scenery:
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
                # A prop has no direction of travel: its model's heading is not a fact.
                facing=(
                    _relative_facing(ego, target, bundle.road_geometry)
                    if ego is not None and target is not None and not scenery
                    else "unknown"
                ),
                actions=tuple(
                    sorted(
                        actor_actions(bundle, actor)
                        if semantic
                        else actions.get(actor, set())
                    )
                ),
                speed_kph=actor_speed_kph(bundle, actor),
                background=actor in background,
                traits=model_traits(entity),
                turned_facing=(
                    _relative_facing(ego, target, bundle.road_geometry, turn)
                    if turns and ego is not None and target is not None
                    else ""
                ),
            )
        )
    return tuple(sorted(signatures, key=ParticipantSignature.key))


def bundle_scenery_signatures(bundle: ParseBundle) -> tuple[ParticipantSignature, ...]:
    """Scenery props grouped by where they stand: 27 cones ahead are one obstacle ahead.

    Props can stand for a requested obstacle, but are never extra participants.
    """
    return tuple(sorted(set(bundle_participant_signatures(bundle, semantic=True, scenery=True)),
                        key=ParticipantSignature.key))


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


def _entity_kind(entity: EntityIR) -> str:
    return _participant_kind(entity.kind, entity.category)


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
