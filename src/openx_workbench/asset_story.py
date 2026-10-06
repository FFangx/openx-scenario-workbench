"""A readable account of what an asset's scenario does, for a model or a person reviewing a match.

The structural comparison reads typed facts; a reviewer also needs what they leave out: the order of
events and what starts them, the ego's speeds over time, the commands, the props by model and lane,
where the driver's closing brake fires, what the run is scored by. Ported from ScenarioManager's
scene context (a blind structure-only judgement recovered 62 of 64 scenario categories from it).
Every line is read from the files; nothing comes from the asset's name, and what cannot be read is
left out rather than guessed.
"""

from __future__ import annotations

import math

from .catalog import OpenXAsset
from .models import ActionIR, ParseBundle, TriggerIR
from .reuse_facts import _entity_kind, bundle_participant_signatures, bundle_scenery_signatures
from .scene_facts import (
    DISCARDED_EVENTS,
    _preset,
    _world_pose,
    actions_of,
    asset_environment,
    command_facts,
    driver_overrides,
    ego_curve_radius,
    environment_events,
    lateral_direction,
    named_conditions,
    occlusions,
    route_turn,
    scenery_summary,
    scoring_criteria,
)

_RULES = {"greaterthan": ">", "greaterorequal": ">=", "lessthan": "<", "lessorequal": "<=", "equalto": "=",
          "notequalto": "!="}
EVENT_LIMIT = 12  # events listed; longer stories are cut, with the count kept


def _value(number: float | None) -> str:
    return f"{number:g}" if number is not None else "?"


def _kph(mps: float | None) -> str:
    return f"{mps * 3.6:.0f}" if mps is not None else "?"


def _trigger_text(trigger: TriggerIR, events: set[str]) -> str:
    rule = _RULES.get((trigger.rule or "").casefold(), "")
    attributes = trigger.attributes
    kind = trigger.kind
    if kind == "SimulationTimeCondition":
        return f"time {rule or '>'} {_value(trigger.value)} s"
    if kind == "StoryboardElementStateCondition":
        # Authoring tools often name acts and maneuvers by ID: only an event's name says anything.
        reference = attributes.get("storyboardElementRef", "")
        return f"after {reference if reference in events else 'an earlier element'} {attributes.get('state', '')}".strip()
    if kind == "TimeToCollisionCondition":
        return f"TTC {rule} {_value(trigger.value)} s"
    if kind in {"RelativeDistanceCondition", "DistanceCondition"}:
        return f"distance {rule} {_value(trigger.value)} m"
    if kind == "SpeedCondition":
        return f"speed {rule} {_kph(trigger.value)} km/h"
    if kind == "TraveledDistanceCondition":
        return f"travelled {_value(trigger.value)} m"
    if kind == "StandStillCondition":
        return f"standstill {_value(trigger.value)} s"
    if kind == "UserDefinedValueCondition":
        return f"check {attributes.get('name', '?')}"
    if kind == "ReachPositionCondition":
        return "reaches a position"
    return kind.removesuffix("Condition")


def _starts(bundle: ParseBundle, event_path: str) -> str:
    events = {event.get("name", "") for event in bundle.scenario.events}
    texts = [_trigger_text(trigger, events) for trigger in bundle.scenario.triggers
             if trigger.scope == "StartTrigger" and trigger.event_path == event_path]
    return " & ".join(dict.fromkeys(texts))


def _ego_start(bundle: ParseBundle) -> tuple[float, float, float] | None:
    ego = next((item for item in bundle.scenario.positions if (item.actor or "").casefold() == "ego"), None)
    return _world_pose(ego, bundle.road_geometry) if ego is not None else None


def _speeds(bundle: ParseBundle) -> str:
    """The ego's speed targets in file order (story events need not run in that order)."""
    steps = []
    for action in actions_of(bundle, "ego"):
        if (action.element or action.kind) != "SpeedAction":
            continue
        target = f"{_kph(action.target_value)} km/h" if action.target_value is not None else "relative"
        shape = "" if (action.shape or "linear").casefold() == "linear" else f" [{action.shape}]"
        label = "init" if action.phase == "init" else (action.event_name or "story")
        steps.append(f"{label} {target}{shape}")
    return " -> ".join(steps)


def _closing_brake(bundle: ParseBundle, brake: list[ActionIR]) -> str:
    """Where the driver's closing brake fires, as a distance from the ego's start: AEB tests close
    within about 100 m, lane-keeping and pilot tests after about 1 km."""
    start = _ego_start(bundle)
    for action in brake:
        for trigger in bundle.scenario.triggers:
            place = trigger.position
            if trigger.event_path != action.event_path or place.get("kind") != "WorldPosition" or start is None:
                continue
            try:
                return f"{math.hypot(float(place['x']) - start[0], float(place['y']) - start[1]):.0f} m after the ego's start"
            except (KeyError, ValueError):
                continue
    return "present, distance not read"


def _road(asset: OpenXAsset) -> list[str]:
    bundle, road = asset.bundle, asset.bundle.road
    if road.file_missing:
        return [f"road: file missing (map {road.name or '?'}; read from the map name as "
                f"{', '.join(road.inferred_features) or 'unknown'})"]
    shape = ["junction"] if road.junction_count else []
    shape += [name for name, present in (("straight", "line" in road.geometry_types),
                                         ("curved", set(road.geometry_types) & {"arc", "spiral", "paramPoly3"}))
              if present]
    line = f"road: {', '.join(shape) or 'unknown'}, {road.total_length:.0f} m"
    if road.lanes_total:
        line += f"; driving lanes {road.lanes_same_direction} one way, {road.lanes_total} in total"
    if road.lane_markings:
        line += f"; lines {', '.join(road.lane_markings)}"
    lines = [line]
    radius = ego_curve_radius(bundle)
    if radius:
        lines.append(f"curve ahead of the ego: R{radius:g}")
    signs = []
    if road.speed_limits_kph:
        signs.append("speed limit signs " + "/".join(f"{value:g}" for value in road.speed_limits_kph) + " km/h")
    signs += [f"{name.replace('_', ' ')} x{count}" for name, count in road.furniture.items()]
    if signs:
        lines.append("along the road: " + ", ".join(signs))
    return lines


def _environment(bundle: ParseBundle) -> list[str]:
    environment = asset_environment(bundle)
    parts = [str(environment[key]) for key in ("time_of_day", "weather") if key in environment]
    if "fog_visibility_m" in environment and environment.get("weather") == "fog":
        parts.append(f"visibility {_value(environment['fog_visibility_m'])} m")
    clock = _preset(bundle.source_case).get("time")
    if clock:
        parts.append(f"preset clock {clock}")
    lines = [f"environment: {', '.join(parts)}"] if parts else []
    changes = environment_events(bundle)
    if changes:
        lines.append("environment changes: " + "; ".join(
            f"{name} -> " + ", ".join(f"{key}={value}" for key, value in reading.items())
            for name, reading in changes))
    return lines


def _ego(bundle: ParseBundle) -> list[str]:
    facts = command_facts(bundle)
    lines = []
    speeds = _speeds(bundle)
    if speeds:
        lines.append(f"ego speeds: {speeds}")
    commands = list(dict.fromkeys(action.command for action in actions_of(bundle, "ego") if action.command))
    if commands:
        lines.append("ego commands: " + "; ".join(commands)
                     + (f" (function {facts['function']})" if facts["function"] else ""))
    overrides = driver_overrides(bundle)
    if overrides:
        lines.append("driver inputs: " + ", ".join(f"{name}={value}" for name, value in overrides.items()))
    moves = []
    side = lateral_direction(bundle)
    if side:
        moves.append(f"moves {side}")
    turn = route_turn(bundle)
    if turn:
        moves.append(f"route {turn}" if turn == "straight" else f"route turns {turn}")
    if facts["parking"]:
        moves.append(facts["parking"].replace("_", " "))
    if moves:
        lines.append("ego maneuvers: " + ", ".join(moves))
    brake = [action for action in actions_of(bundle, "ego")
             if (action.command or "").casefold().replace(" ", "").startswith("brakeposition")]
    lines.append("closing brake: " + (_closing_brake(bundle, brake) if brake else "none"))
    return lines


def _participants(bundle: ParseBundle) -> list[str]:
    models = {entity.name.casefold(): entity.model for entity in bundle.scenario.entities}
    described = []
    for item in bundle_participant_signatures(bundle, semantic=True):
        text = f"{item.kind} {item.bearing}, facing {item.facing}, {'+'.join(item.actions)}"
        if item.speed_kph:
            text += f" {item.speed_kph:.0f} km/h"
        model = models.get(item.actor.casefold())
        details = [f"model {model}"] if model else []
        details += list(item.traits)
        if item.background:
            details.append("background")
        described.append(text + (f" ({', '.join(details)})" if details else ""))
    lines = [f"participants ({len(described)}): " + ("; ".join(described) if described else "none")]
    props = scenery_summary(bundle)
    if props["models"]:
        where = ", ".join(item.bearing for item in bundle_scenery_signatures(bundle) if item.bearing != "unknown")
        lines.append("props: " + ", ".join(f"{model} x{count}" for model, count in props["models"].items())
                     + (f" in {', '.join(f'{lane} x{count}' for lane, count in props['lanes'].items())}" if props["lanes"] else "")
                     + (f"; standing {where}" if where else ""))
    hidden = occlusions(bundle, _entity_kind)
    if hidden:
        lines.append("occlusion: " + ", ".join(f"{blocker} hides {target}" for blocker, target in sorted(hidden)))
    return lines


def _events(bundle: ParseBundle) -> list[str]:
    events = [event for event in bundle.scenario.events if event.get("name") not in DISCARDED_EVENTS]
    if not events:
        return []
    shown = [f"{event.get('name', '?')}" + (f" [{starts}]" if (starts := _starts(bundle, event['source_path'])) else "")
             for event in events[:EVENT_LIMIT]]
    more = f" (+{len(events) - EVENT_LIMIT} more)" if len(events) > EVENT_LIMIT else ""
    return [f"events in file order: {'; '.join(shown)}{more}"]


def asset_story(asset: OpenXAsset) -> str:
    """The asset described line by line: road, environment, ego, participants, events, scoring."""
    bundle = asset.bundle
    lines = [*_road(asset), *_environment(bundle), *_ego(bundle), *_participants(bundle), *_events(bundle)]
    checks = named_conditions(bundle)
    if checks:
        lines.append("named checks: " + ", ".join(checks))
    scoring = scoring_criteria(bundle)
    if scoring:
        lines.append("scored by: " + "; ".join(scoring))
    return "\n".join(lines)
