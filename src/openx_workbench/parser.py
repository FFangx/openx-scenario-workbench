from __future__ import annotations

from pathlib import PurePosixPath
from xml.etree import ElementTree as ET

from .models import ActionIR, EntityIR, ParseBundle, PositionIR, RoadIR, ScenarioIR, TriggerIR


def _local(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _all(root: ET.Element, name: str):
    return (element for element in root.iter() if _local(element) == name)


def _first(root: ET.Element, name: str) -> ET.Element | None:
    return next(_all(root, name), None)


def _float(value: str | None) -> float | None:
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


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


def _action(node: ET.Element, name: str, actor: str | None) -> ActionIR:
    kind_node = next((child for child in node.iter() if _local(child) in KNOWN_ACTIONS), None)
    speed = _first(node, "AbsoluteTargetSpeed")
    return ActionIR(
        name,
        _local(kind_node) if kind_node is not None else "Action",
        actor,
        _float(speed.get("value") if speed is not None else None),
    )


def parse_xosc(data: bytes | str) -> ScenarioIR:
    root = ET.fromstring(data)
    if _local(root) != "OpenSCENARIO":
        raise ValueError("Expected an OpenSCENARIO root element.")
    header = _first(root, "FileHeader")
    logic_file = _first(root, "LogicFile")
    scenario = ScenarioIR(
        name=header.get("description") if header is not None else None,
        description=header.get("description") if header is not None else None,
        author=header.get("author") if header is not None else None,
        revision=_revision(header),
        road_file=logic_file.get("filepath") if logic_file is not None else None,
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
            scenario.actions.append(_action(private_action, f"init_{index}", actor))

    # Story actions inherit their actors from the containing ManeuverGroup.
    for group in _all(root, "ManeuverGroup"):
        actors_node = _first(group, "Actors")
        actor_names = [node.get("entityRef", "") for node in _all(actors_node, "EntityRef")] if actors_node is not None else []
        actor = ", ".join(name for name in actor_names if name) or None
        for action in _all(group, "Action"):
            scenario.actions.append(_action(action, action.get("name", "unnamed"), actor))

    for action in _all(root, "GlobalAction"):
        parsed = _action(action, action.get("name", "global"), None)
        if parsed.kind == "Action":
            parsed.kind = "GlobalAction"
        scenario.actions.append(parsed)

    for scope in ("StartTrigger", "StopTrigger"):
        for trigger in _all(root, scope):
            for condition in _all(trigger, "Condition"):
                condition_types = [
                    _local(node)
                    for node in condition.iter()
                    if _local(node).endswith("Condition")
                    and _local(node) not in {"Condition", "ByValueCondition", "ByEntityCondition"}
                ]
                condition_kind = condition_types[-1] if condition_types else "Condition"
                scenario.triggers.append(TriggerIR(scope, condition.get("name", "unnamed"), condition_kind, _float(condition.get("delay")), condition.get("conditionEdge")))

    position_names = {"WorldPosition", "LanePosition", "RoadPosition", "RelativeWorldPosition", "RelativeLanePosition", "RelativeRoadPosition"}
    for node in root.iter():
        if _local(node) in position_names:
            scenario.positions.append(PositionIR(_local(node), dict(node.attrib)))
    return scenario


def parse_xodr(data: bytes | str) -> RoadIR:
    root = ET.fromstring(data)
    if _local(root) != "OpenDRIVE":
        raise ValueError("Expected an OpenDRIVE root element.")
    header = _first(root, "header")
    road_ids = [road.get("id", "") for road in _all(root, "road")]
    return RoadIR(
        name=header.get("name") if header is not None else None,
        revision=_revision(header),
        road_ids=road_ids,
        lane_count=sum(1 for _ in _all(root, "lane")),
        junction_count=sum(1 for _ in _all(root, "junction")),
        signal_count=sum(1 for _ in _all(root, "signal")),
        object_count=sum(1 for _ in _all(root, "object")),
    )


def parse_bundle(xosc_data: bytes | str, xodr_data: bytes | str, xodr_filename: str | None = None) -> ParseBundle:
    scenario = parse_xosc(xosc_data)
    road = parse_xodr(xodr_data)
    warnings: list[str] = []
    if scenario.road_file and xodr_filename:
        referenced = PurePosixPath(scenario.road_file.replace("\\", "/")).name.casefold()
        uploaded = PurePosixPath(xodr_filename.replace("\\", "/")).name.casefold()
        if referenced != uploaded:
            warnings.append("road_file_mismatch")
    if not scenario.entities:
        warnings.append("no_scenario_entities")
    if not road.road_ids:
        warnings.append("no_roads")
    return ParseBundle(scenario, road, warnings)
