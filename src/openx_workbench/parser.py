from __future__ import annotations

from collections import Counter
import math
from pathlib import PurePosixPath
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


def _action(node: ET.Element, name: str, actor: str | None, phase: str = "story") -> ActionIR:
    kind_node = next((child for child in node.iter() if _local(child) in KNOWN_ACTIONS), None)
    speed = _first(node, "AbsoluteTargetSpeed")
    return ActionIR(
        name,
        _local(kind_node) if kind_node is not None else "Action",
        actor,
        _float(speed.get("value") if speed is not None else None),
        phase,
    )


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
        kind, category = "reference", None
        for child in list(obj):
            child_name = _local(child)
            if child_name in {"Vehicle", "Pedestrian", "MiscObject"}:
                kind = child_name.lower()
                category = child.get("vehicleCategory") or child.get("pedestrianCategory") or child.get("miscObjectCategory")
                break
            if child_name == "CatalogReference":
                kind = "catalog_reference"
                category = child.get("catalogName")
                break
        scenario.entities.append(EntityIR(obj.get("name", "unnamed"), kind, category))

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
    # Multiple environments may change during playback. Only a single declared
    # environment is evidence for a constant requirement; otherwise leave unknown.
    environments = list(_all(root, "Environment"))
    if len(environments) == 1:
        environment = environments[0]
        precipitation = _first(environment, "Precipitation")
        fog = _first(environment, "Fog")
        clock = _first(environment, "TimeOfDay")
        if precipitation is not None:
            kind = precipitation.get("precipitationType")
            intensity = _float(precipitation.get("intensity"))
            if kind == "dry":
                scenario.environment["weather"] = "dry"
            elif kind in {"rain", "snow"} and intensity is not None and intensity >= 0:
                scenario.environment["weather"] = kind if intensity > 0 else "dry"
        visibility = _float(fog.get("visualRange")) if fog is not None else None
        if visibility is not None:
            scenario.environment["fog_visibility_m"] = visibility
            # Match ScenarioManager's coarse test-weather convention; retain
            # the raw range for requirements that specify exact visibility.
            if 0 < visibility <= 350 and scenario.environment.get("weather") in {None, "dry"}:
                scenario.environment["weather"] = "fog"
        if clock is not None:
            from datetime import datetime
            try:
                hour = datetime.fromisoformat(clock.get("dateTime", "").replace("Z", "+00:00")).hour
                scenario.environment["time_of_day"] = "day" if 6 <= hour < 18 else "night"
            except ValueError:
                pass
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


def parse_bundle(xosc_data: bytes | str, xodr_data: bytes | str, xodr_filename: str | None = None) -> ParseBundle:
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
    )
