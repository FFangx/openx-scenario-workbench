from __future__ import annotations

from collections import Counter
import math
from pathlib import PurePosixPath
from typing import Any
from xml.etree import ElementTree as ET

from .models import ActionIR, EntityIR, ParseBundle, PositionIR, RoadIR, ScenarioIR, TriggerIR
from .road_geometry import parse_road_geometry
from .parameter_resolution import resolve_parameters
from .xml_values import local_name as _local, number


def _all(root: ET.Element, name: str):
    return (element for element in root.iter() if _local(element) == name)


def _first(root: ET.Element, name: str) -> ET.Element | None:
    return next(_all(root, name), None)


def _float(value: str | None) -> float | None:
    """Missing, non-numeric and non-finite values all read as None."""
    result = number(value)
    return result if result is not None and math.isfinite(result) else None


def _revision(header: ET.Element | None) -> str | None:
    if header is None:
        return None
    major = header.get("revMajor")
    minor = header.get("revMinor")
    return ".".join(part for part in (major, minor) if part is not None) or None


KNOWN_ACTIONS = {
    "SpeedAction", "LaneChangeAction", "LaneOffsetAction", "LateralDistanceAction",
    "TeleportAction", "RoutingAction", "EnvironmentAction", "TrafficSignalStateAction",
    "SynchronizeAction", "VisibilityAction", "ControllerAction",
}


# Elements that only group the action that does something.
_ACTION_WRAPPERS = {
    "Action", "PrivateAction", "GlobalAction", "UserDefinedAction", "LongitudinalAction",
    "LateralAction", "ControllerAction", "RoutingAction", "InfrastructureAction", "TrafficAction",
    "ParameterAction", "VariableAction", "AppearanceAction", "EntityAction",
}


def _action(node: ET.Element, name: str, actor: str | None, phase: str = "story") -> ActionIR:
    kind_node = next((child for child in node.iter() if _local(child) in KNOWN_ACTIONS), None)
    element = next((child for child in node.iter()
                    if _local(child).endswith("Action") and _local(child) not in _ACTION_WRAPPERS), None)
    speed = _first(node, "AbsoluteTargetSpeed")
    dynamics = _first(node, "SpeedActionDynamics")
    command = _first(node, "CustomCommandAction")
    return ActionIR(
        name,
        _local(kind_node) if kind_node is not None else "Action",
        actor,
        _float(speed.get("value") if speed is not None else None),
        phase,
        element=_local(element) if element is not None else "",
        shape=dynamics.get("dynamicsShape") if dynamics is not None else None,
        command=((command.text or command.get("content") or "").strip() or None) if command is not None else None,
        overrides=_overrides(node),
    )


def _overrides(node: ET.Element) -> dict[str, str]:
    """Active driver-input overrides: OpenSCENARIO 1.0 channels (Brake, Gear, ...) or 1.1+ Override*Action."""
    result: dict[str, str] = {}
    for override in _all(node, "OverrideControllerValueAction"):
        for channel in override:
            name = _local(channel).removeprefix("Override").removesuffix("Action")
            if channel.get("active", "").casefold() != "true":
                continue
            value = channel.get("value") or channel.get("number")
            if value is None:
                inner = next((item for item in channel.iter() if item is not channel and
                              (item.get("value") or item.get("number")) is not None), None)
                value = (inner.get("value") or inner.get("number")) if inner is not None else ""
            result[name] = value
    return result


def _environment_reading(environment: ET.Element) -> dict[str, str | float]:
    """Weather, time of day and fog range declared by one Environment."""
    reading: dict[str, str | float] = {}
    precipitation = _first(environment, "Precipitation")
    fog = _first(environment, "Fog")
    clock = _first(environment, "TimeOfDay")
    sun = _first(environment, "Sun")
    if precipitation is not None:
        kind = precipitation.get("precipitationType")
        intensity = _float(precipitation.get("intensity") or precipitation.get("precipitationIntensity"))
        if kind == "dry":
            reading["weather"] = "dry"
        elif kind in {"rain", "snow"} and intensity is not None and intensity >= 0:
            reading["weather"] = kind if intensity > 0 else "dry"
    visibility = _float(fog.get("visualRange")) if fog is not None else None
    if visibility is not None:
        reading["fog_visibility_m"] = visibility
        # Match ScenarioManager's coarse test-weather convention; retain
        # the raw range for requirements that specify exact visibility.
        if 0 < visibility <= 350 and reading.get("weather") in {None, "dry"}:
            reading["weather"] = "fog"
    if clock is not None:
        from datetime import datetime
        try:
            hour = datetime.fromisoformat(clock.get("dateTime", "").replace("Z", "+00:00")).hour
            reading["time_of_day"] = "day" if 6 <= hour < 18 else "night"
        except ValueError:
            pass
    if "time_of_day" not in reading and sun is not None:
        elevation = _float(sun.get("elevation"))
        if elevation is not None:
            reading["time_of_day"] = "day" if elevation > 0 else "night"
    return reading


def _merge_environments(readings: list[dict[str, str | float]]) -> dict[str, str | float]:
    """One environment from every declared one (initial and story changes).

    A story that turns rain or fog on is a rain or fog scenario. Conflicting
    readings (rain and fog, or day and night) stay unknown.
    """
    merged: dict[str, str | float] = {}
    weathers = {item["weather"] for item in readings if "weather" in item}
    adverse = weathers - {"dry"}
    if len(adverse) == 1:
        merged["weather"] = adverse.pop()
    elif weathers == {"dry"}:
        merged["weather"] = "dry"
    times = {item["time_of_day"] for item in readings if "time_of_day" in item}
    if len(times) == 1:
        merged["time_of_day"] = times.pop()
    ranges = [item["fog_visibility_m"] for item in readings if "fog_visibility_m" in item]
    if ranges:
        merged["fog_visibility_m"] = min(ranges)
    return merged


def parse_xosc(data: bytes | str) -> ScenarioIR:
    root = ET.fromstring(data)
    if _local(root) != "OpenSCENARIO":
        raise ValueError("Expected an OpenSCENARIO root element.")
    paths, parameters, parameter_issues, resolutions = resolve_parameters(root)
    for node in _all(root, "ParameterAction"):
        parameter_issues.append({"path": paths[node], "attribute": "parameterRef",
                                 "raw": node.get("parameterRef", ""),
                                 "detail": "dynamic parameter updates require execution review"})
    parents = {child: parent for parent in root.iter() for child in parent}

    def enclosing(node, tag):
        while node in parents:
            node = parents[node]
            if _local(node) == tag:
                return node
        return None

    def append_action(node, name, actor, phase="story"):
        if _first(node, "GlobalAction") is not None:
            actor = None
        action = _action(node, name, actor, phase)
        action.source_path = paths[node]
        event = enclosing(node, "Event")
        action.event_path = paths[event] if event is not None else ""
        action.event_name = event.get("name", "") if event is not None else ""
        scenario.actions.append(action)
    header = _first(root, "FileHeader")
    logic_file = _first(root, "LogicFile")
    scenario = ScenarioIR(
        name=header.get("description") if header is not None else None,
        description=header.get("description") if header is not None else None,
        author=header.get("author") if header is not None else None,
        revision=_revision(header),
        road_file=logic_file.get("filepath") if logic_file is not None else None,
        parameters=parameters, parameter_issues=parameter_issues,
        parameter_resolutions=resolutions,
    )

    for obj in _all(root, "ScenarioObject"):
        kind, category, model, width = "reference", None, None, None
        for child in list(obj):
            child_name = _local(child)
            if child_name in {"Vehicle", "Pedestrian", "MiscObject"}:
                kind = child_name.lower()
                category = child.get("vehicleCategory") or child.get("pedestrianCategory") or child.get("miscObjectCategory")
                properties = {item.get("name"): item.get("value") for item in _all(child, "Property")}
                model = properties.get("model") or child.get("model3d") or child.get("name")
                model = model if model and model != "default" else None
                dimensions = _first(child, "Dimensions")
                width = _float(dimensions.get("width")) if dimensions is not None else None
                break
            if child_name == "CatalogReference":
                kind = "catalog_reference"
                category = child.get("catalogName")
                break
        scenario.entities.append(EntityIR(obj.get("name", "unnamed"), kind, category, model, width))

    # Initialization actions are grouped under Private by entity.
    for private in _all(root, "Private"):
        actor = private.get("entityRef")
        for index, private_action in enumerate(_all(private, "PrivateAction"), start=1):
            append_action(private_action, f"init_{index}", actor, "init")

    # Story actions inherit their actors from the containing ManeuverGroup.
    for group in _all(root, "ManeuverGroup"):
        actors_node = _first(group, "Actors")
        actor_names = [node.get("entityRef", "") for node in _all(actors_node, "EntityRef")] if actors_node is not None else []
        actor = ", ".join(name for name in actor_names if name) or None
        for action in _all(group, "Action"):
            append_action(action, action.get("name", "unnamed"), actor)

    for action in _all(root, "GlobalAction"):
        if enclosing(action, "Action") is not None:
            continue  # Already parsed through its owning story Action.
        parsed = _action(action, action.get("name", "global"), None)
        parsed.phase = "init" if enclosing(action, "Init") is not None else "story"
        parsed.source_path = paths[action]
        if parsed.kind == "Action":
            parsed.kind = "GlobalAction"
        scenario.actions.append(parsed)

    for scope in ("StartTrigger", "StopTrigger"):
        for trigger in _all(root, scope):
            for condition in _all(trigger, "Condition"):
                condition_nodes = [
                    node
                    for node in condition.iter()
                    if _local(node).endswith("Condition")
                    and _local(node) not in {"Condition", "ByValueCondition", "ByEntityCondition"}
                ]
                condition_node = condition_nodes[-1] if condition_nodes else None
                condition_kind = _local(condition_node) if condition_node is not None else "Condition"
                scenario.triggers.append(TriggerIR(
                    scope=scope,
                    condition_name=condition.get("name", "unnamed"),
                    kind=condition_kind,
                    delay=_float(condition.get("delay")),
                    edge=condition.get("conditionEdge"),
                    value=_float(condition_node.get("value")) if condition_node is not None else None,
                    rule=condition_node.get("rule") if condition_node is not None else None,
                    entity_refs=tuple(
                        node.get("entityRef", "")
                        for node in _all(condition, "EntityRef")
                        if node.get("entityRef")
                    ),
                    source_path=paths[condition],
                    event_path=paths[event] if (event := enclosing(condition, "Event")) is not None else "",
                    attributes=dict(condition_node.attrib) if condition_node is not None else {},
                ))

    for event in _all(root, "Event"):
        path = paths[event]
        scenario.events.append({
            **event.attrib, "source_path": path,
            "maneuver_path": paths[maneuver] if (maneuver := enclosing(event, "Maneuver")) is not None else "",
            "actions": [action.source_path for action in scenario.actions if action.event_path == path],
            "conditions": [trigger.source_path for trigger in scenario.triggers if trigger.event_path == path],
        })

    position_names = {
        "WorldPosition", "LanePosition", "RoadPosition", "RelativeObjectPosition",
        "RelativeWorldPosition", "RelativeLanePosition", "RelativeRoadPosition",
    }
    for private in _all(root, "Private"):
        actor = private.get("entityRef")
        for node in private.iter():
            if _local(node) in position_names:
                scenario.positions.append(
                    PositionIR(
                        _local(node),
                        dict(node.attrib),
                        actor=actor,
                        orientation=(
                            dict(orientation.attrib)
                            if (orientation := _first(node, "Orientation")) is not None
                            else {}
                        ),
                    )
                )
    scenario.environment = _merge_environments(
        [_environment_reading(environment) for environment in _all(root, "Environment")])
    return scenario


def parse_xodr(data: bytes | str) -> RoadIR:
    root = ET.fromstring(data)
    if _local(root) != "OpenDRIVE":
        raise ValueError("Expected an OpenDRIVE root element.")
    header = _first(root, "header")
    roads = list(_all(root, "road"))
    road_ids = [road.get("id", "") for road in roads]
    lane_types = Counter(lane.get("type", "unknown") for lane in _all(root, "lane"))
    geometry_names = {"line", "arc", "spiral", "poly3", "paramPoly3"}
    geometry_types = Counter(
        _local(child)
        for geometry in _all(root, "geometry")
        for child in list(geometry)
        if _local(child) in geometry_names
    )
    return RoadIR(
        name=header.get("name") if header is not None else None,
        revision=_revision(header),
        road_ids=road_ids,
        total_length=round(sum(_float(road.get("length")) or 0.0 for road in roads), 3),
        lane_count=sum(lane_types.values()),
        lane_types=dict(sorted(lane_types.items())),
        geometry_types=dict(sorted(geometry_types.items())),
        junction_count=sum(1 for _ in _all(root, "junction")),
        signal_count=sum(1 for _ in _all(root, "signal")),
        object_count=sum(1 for _ in _all(root, "object")),
    )


# Map-name keywords of simulator built-in roads, checked in order: a "two-lane
# roundabout junction" is a roundabout, a "three-lane junction" a junction.
# Names that only count lanes ("ThreeLanes", "单向双车道") are the built-in
# straight multi-lane roads. "cross" is left out: "walkCross" is a crosswalk.
_MAP_ROAD_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("parking", ("park", "停车", "泊车", "库位")),
    ("roundabout", ("roundabout", "环岛", "环形")),
    ("junction", ("junction", "intersection", "路口")),
    ("curve", ("curve", "bend", "turn", "r=", "弯")),
    ("motorway", ("motorway", "highway", "高速")),
    ("straight", ("straight", "striaght", "直道", "直线", "lane", "车道")),
)


def map_road_features(*names: str | None) -> list[str]:
    """Road type named by a map whose OpenDRIVE file is unavailable; empty when the name says nothing."""
    text = " ".join(name for name in names if name).casefold()
    return next(([feature] for feature, keywords in _MAP_ROAD_RULES
                 if any(keyword in text for keyword in keywords)), [])


def parse_bundle_without_road(xosc_data: bytes | str, map_names: tuple[str, ...] = (),
                              source_case: dict[str, Any] | None = None) -> ParseBundle:
    """Parse a scenario whose road file is missing: matchable on its scenario, not previewable."""
    from .schema_validation import validate_xml
    scenario = parse_xosc(xosc_data)
    road = RoadIR(name=next((name for name in reversed(map_names) if name), None), file_missing=True,
                  inferred_features=map_road_features(*map_names))
    warnings = ["road_file_missing"]
    if scenario.parameter_issues:
        warnings.append("unresolved_scenario_parameters")
    if not scenario.entities:
        warnings.append("no_scenario_entities")
    return ParseBundle(
        scenario=scenario,
        road=road,
        warnings=warnings,
        validation={"scenario": validate_xml(xosc_data),
                    "road": {"status": "missing", "standard": "OpenDRIVE", "version": None, "issues": []}},
        source_case=dict(source_case or {}),
    )


def parse_bundle(xosc_data: bytes | str, xodr_data: bytes | str, xodr_filename: str | None = None,
                 source_case: dict[str, Any] | None = None) -> ParseBundle:
    from .schema_validation import validate_xml
    scenario = parse_xosc(xosc_data)
    road = parse_xodr(xodr_data)
    warnings: list[str] = []
    if scenario.parameter_issues:
        warnings.append("unresolved_scenario_parameters")
    if scenario.road_file and xodr_filename:
        referenced = PurePosixPath(scenario.road_file.replace("\\", "/")).name.casefold()
        uploaded = PurePosixPath(xodr_filename.replace("\\", "/")).name.casefold()
        if referenced != uploaded:
            warnings.append("road_file_mismatch")
    if not scenario.entities:
        warnings.append("no_scenario_entities")
    if not road.road_ids:
        warnings.append("no_roads")
    return ParseBundle(
        scenario=scenario,
        road=road,
        warnings=warnings,
        road_geometry=parse_road_geometry(xodr_data),
        validation={"scenario": validate_xml(xosc_data), "road": validate_xml(xodr_data)},
        source_case=dict(source_case or {}),
    )
