"""Ego-relative participant geometry for reuse comparison.

Where a participant sits and which way it faces relative to the ego vehicle, from OpenSCENARIO
positions and OpenDRIVE reference lines.
"""

from __future__ import annotations

import math

from .models import PositionIR
from .road_geometry import RoadReferenceLine


def _bearing(forward: float, left: float) -> str:
    if forward > 5.0:
        longitudinal = "front"
    elif forward < -5.0:
        longitudinal = "rear"
    else:
        longitudinal = "alongside"
    if abs(left) <= 1.5:
        return f"{longitudinal}_same_lane"
    return f"{longitudinal}_{'left' if left > 0 else 'right'}"


def _relative_facing(
    ego: PositionIR,
    target: PositionIR,
    roads: dict[str, RoadReferenceLine],
) -> str:
    if target.kind == "RelativeObjectPosition":
        relative = _number(target.orientation, "h")
        if relative is None:
            return "same"
        if target.orientation.get("type") == "absolute":
            ego_heading = _ego_heading(ego, roads)
            if ego_heading is None:
                return "unknown"
            relative -= ego_heading
        return _facing(relative)

    road_id = ego.attributes.get("roadId") or target.attributes.get("roadId")
    road = roads.get(road_id or "")
    if road is not None:
        ego_coordinates = _road_coordinates(ego, road)
        target_coordinates = _road_coordinates(target, road)
        if ego_coordinates is not None and target_coordinates is not None:
            ego_s, _ = ego_coordinates
            target_s, _ = target_coordinates
            ego_heading = _heading_on_road(ego, road, ego_s)
            target_heading = _heading_on_road(target, road, target_s)
            ego_reference = road.heading_at(ego_s)
            target_reference = road.heading_at(target_s)
            if None not in (
                ego_heading,
                target_heading,
                ego_reference,
                target_reference,
            ):
                ego_deviation = _wrap(ego_heading - ego_reference)
                target_deviation = _wrap(target_heading - target_reference)
                return _facing(target_deviation - ego_deviation)

    ego_heading = _ego_heading(ego, roads)
    target_heading = _position_heading(target, None)
    if ego_heading is None or target_heading is None:
        return "unknown"
    return _facing(target_heading - ego_heading)


def _heading_on_road(
    position: PositionIR,
    road: RoadReferenceLine,
    s: float,
) -> float | None:
    reference = road.heading_at(s)
    heading = _position_heading(position, reference)
    if heading is not None:
        return heading
    lane_id = _integer(position.attributes, "laneId")
    if lane_id is None or reference is None:
        return None
    return reference if lane_id < 0 else reference + math.pi


def _facing(angle: float) -> str:
    delta = abs(_wrap(angle))
    if delta <= math.pi / 6:
        return "same"
    if delta >= 5 * math.pi / 6:
        return "opposite"
    return "crossing"


def _wrap(angle: float) -> float:
    return (angle + math.pi) % (2 * math.pi) - math.pi


def _number(attributes: dict[str, str], name: str) -> float | None:
    try:
        return float(attributes[name])
    except (KeyError, TypeError, ValueError):
        return None


def _relative_offset(
    ego: PositionIR,
    target: PositionIR,
    roads: dict[str, RoadReferenceLine],
) -> tuple[float, float] | None:
    if (
        target.kind == "RelativeObjectPosition"
        and target.attributes.get("entityRef", "").casefold() == "ego"
    ):
        dx = _number(target.attributes, "dx")
        dy = _number(target.attributes, "dy")
        return (dx, dy) if dx is not None and dy is not None else None

    if target.attributes.get("entityRef", "").casefold() == "ego":
        if target.kind == "RelativeWorldPosition":
            dx = _number(target.attributes, "dx")
            dy = _number(target.attributes, "dy")
            heading = _ego_heading(ego, roads)
            if dx is not None and dy is not None and heading is not None:
                return (
                    dx * math.cos(heading) + dy * math.sin(heading),
                    -dx * math.sin(heading) + dy * math.cos(heading),
                )
        if target.kind == "RelativeRoadPosition":
            ds = _number(target.attributes, "ds")
            dt = _number(target.attributes, "dt")
            direction = _ego_road_direction(ego, roads)
            if ds is not None and dt is not None and direction is not None:
                return ds * direction, dt * direction
        if target.kind == "RelativeLanePosition":
            ds = _number(target.attributes, "ds")
            lane_delta = _number(target.attributes, "dLane")
            offset = _number(target.attributes, "offset") or 0.0
            direction = _ego_road_direction(ego, roads)
            if ds is not None and lane_delta is not None and direction is not None:
                return ds * direction, (lane_delta * 3.5 + offset) * direction

    road_offset = _road_relative_offset(ego, target, roads)
    if road_offset is not None:
        return road_offset

    if ego.kind == target.kind == "WorldPosition":
        ex = _number(ego.attributes, "x")
        ey = _number(ego.attributes, "y")
        heading = _number(ego.attributes, "h") or 0.0
        tx = _number(target.attributes, "x")
        ty = _number(target.attributes, "y")
        if None in {ex, ey, tx, ty}:
            return None
        dx, dy = tx - ex, ty - ey
        return (
            dx * math.cos(heading) + dy * math.sin(heading),
            -dx * math.sin(heading) + dy * math.cos(heading),
        )
    return None


def _ego_heading(
    ego: PositionIR,
    roads: dict[str, RoadReferenceLine],
) -> float | None:
    road_id = ego.attributes.get("roadId")
    road = roads.get(road_id or "")
    s = _number(ego.attributes, "s")
    reference_heading = (
        road.heading_at(s) if road is not None and s is not None else None
    )
    return _position_heading(ego, reference_heading)


def _ego_road_direction(
    ego: PositionIR,
    roads: dict[str, RoadReferenceLine],
) -> float | None:
    road_id = ego.attributes.get("roadId")
    road = roads.get(road_id or "")
    s = _number(ego.attributes, "s")
    if road is not None and s is not None:
        return _travel_direction(ego, road, s)
    lane_id = _integer(ego.attributes, "laneId")
    if lane_id is not None and lane_id != 0:
        return 1.0 if lane_id < 0 else -1.0
    return None


def _road_relative_offset(
    ego: PositionIR,
    target: PositionIR,
    roads: dict[str, RoadReferenceLine],
) -> tuple[float, float] | None:
    road_id = ego.attributes.get("roadId") or target.attributes.get("roadId")
    road = roads.get(road_id or "")
    if road is None:
        return _lane_position_fallback(ego, target)

    ego_coordinates = _road_coordinates(ego, road)
    target_coordinates = _road_coordinates(target, road)
    if ego_coordinates is None or target_coordinates is None:
        return _lane_position_fallback(ego, target)
    ego_s, ego_t = ego_coordinates
    target_s, target_t = target_coordinates
    direction = _travel_direction(ego, road, ego_s)
    if direction is None:
        return None
    return (
        (target_s - ego_s) * direction,
        (target_t - ego_t) * direction,
    )


def _road_coordinates(
    position: PositionIR,
    road: RoadReferenceLine,
) -> tuple[float, float] | None:
    if position.kind == "RoadPosition":
        if position.attributes.get("roadId") != road.road_id:
            return None
        s = _number(position.attributes, "s")
        t = _number(position.attributes, "t")
        return (s, t) if s is not None and t is not None else None
    if position.kind == "LanePosition":
        if position.attributes.get("roadId") != road.road_id:
            return None
        s = _number(position.attributes, "s")
        lane_id = _integer(position.attributes, "laneId")
        offset = _number(position.attributes, "offset") or 0.0
        if s is None or lane_id is None:
            return None
        section = next(
            (item for item in reversed(road.lane_sections) if item.s <= s),
            None,
        )
        lateral = section.lateral_offset(lane_id, s) if section else None
        return (s, lateral + offset) if lateral is not None else None
    if position.kind == "WorldPosition":
        x = _number(position.attributes, "x")
        y = _number(position.attributes, "y")
        return road.road_from_world(x, y) if x is not None and y is not None else None
    return None


def _travel_direction(
    position: PositionIR,
    road: RoadReferenceLine,
    s: float,
) -> float | None:
    reference_heading = road.heading_at(s)
    heading = _position_heading(position, reference_heading)
    if heading is not None and reference_heading is not None:
        delta = (heading - reference_heading + math.pi) % (2 * math.pi) - math.pi
        return 1.0 if abs(delta) < math.pi / 2 else -1.0
    lane_id = _integer(position.attributes, "laneId")
    if lane_id is not None and lane_id != 0:
        return 1.0 if lane_id < 0 else -1.0
    return None


def _position_heading(
    position: PositionIR,
    reference_heading: float | None,
) -> float | None:
    heading = _number(position.attributes, "h")
    if heading is not None:
        return heading
    heading = _number(position.orientation, "h")
    if heading is None:
        return None
    if position.orientation.get("type") == "relative" and reference_heading is not None:
        return reference_heading + heading
    return heading


def _lane_position_fallback(
    ego: PositionIR,
    target: PositionIR,
) -> tuple[float, float] | None:
    if ego.kind != "LanePosition" or target.kind != "LanePosition":
        return None
    if ego.attributes.get("roadId") != target.attributes.get("roadId"):
        return None
    ego_s = _number(ego.attributes, "s")
    target_s = _number(target.attributes, "s")
    ego_lane = _integer(ego.attributes, "laneId")
    target_lane = _integer(target.attributes, "laneId")
    if any(value is None for value in (ego_s, target_s, ego_lane, target_lane)):
        return None
    direction = 1.0 if ego_lane < 0 else -1.0
    return (
        (target_s - ego_s) * direction,
        (target_lane - ego_lane) * 3.5 * direction,
    )


def _integer(attributes: dict[str, str], name: str) -> int | None:
    try:
        return int(attributes[name])
    except (KeyError, TypeError, ValueError):
        return None


def _adjacent_lane(ego: PositionIR, target: PositionIR) -> bool:
    if (
        target.kind == "RelativeLanePosition"
        and target.attributes.get("entityRef", "").casefold() == "ego"
    ):
        lane_delta = _integer(target.attributes, "dLane")
        return lane_delta is not None and abs(lane_delta) == 1
    if ego.kind != "LanePosition" or target.kind != "LanePosition":
        return False
    if ego.attributes.get("roadId") != target.attributes.get("roadId"):
        return False
    ego_lane = _number(ego.attributes, "laneId")
    target_lane = _number(target.attributes, "laneId")
    return (
        ego_lane is not None
        and target_lane is not None
        and abs(ego_lane - target_lane) == 1
    )
