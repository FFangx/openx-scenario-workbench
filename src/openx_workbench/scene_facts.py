"""Scenario facts that need interpretation beyond OpenSCENARIO element types.

What an authored scenario means is spread over details a type-by-type reading
misses: the speed a story accelerates to, simulator commands, driver-input
overrides, scenery props, environment presets kept outside the file. These rules
were worked out on ScenarioManager libraries (a blind structure-only judgement
recovered 62 of 64 scenario categories from these signals) and are re-derived
here on the parsed scenario, not on SIM JSON. Nothing here reads a scenario's name.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Any

from . import reuse_policy as policy
from .models import ActionIR, EntityIR, ParseBundle, PositionIR
from .reuse_geometry import _position_heading, _relative_offset
from .road_geometry import RoadAhead, path_curve_radius, road_ahead

# Events that only operate the simulation: TurnOff switches the system under test
# off when the scenario ends; just_for_test teleports and zeroes the ego. The
# driver's closing brake (BrakePosition) is kept: whether it exists and where it
# fires describe the scenario.
DISCARDED_EVENTS = frozenset({"TurnOff", "just_for_test"})

# Driver assistance functions switched on by a simulator command (EnableACC, ...).
_ENABLE = re.compile(r"Enable(ACC|AEB|APA|NOA|LSS|LKA|LDW|LDP|ALCA|DOW|BSM|RCTA|FCW|TSA)", re.IGNORECASE)
# Commands that make the system under test change lanes.
_LANE_CHANGE_COMMANDS = ("lanechangecmd", "lanechangereq", "驾驶员触发换道指令", "alcamode=")
# Commands that make the ego drift out of its lane without taking the next one (LaneOffset=left in a
# lane departure warning or keeping test): a lane departure, not a lane change.
_LANE_DEPARTURE_COMMANDS = ("laneoffset=",)
# A request to engage the system under test.
_ENGAGE_COMMANDS = ("sysengreq",)
# The driver asking the system under test for a lane change or confirming one it proposes.
_DRIVER_REQUEST_COMMANDS = ("lanechangereq", "lanechangeconfirm", "驾驶员触发换道指令")

# Elements whose meaning the behavior reading below covers.
_UNDERSTOOD = frozenset({
    "SpeedAction", "LaneChangeAction", "CustomCommandAction", "ActivateControllerAction",
    "AssignControllerAction", "OverrideControllerValueAction", "LongitudinalDistanceAction",
    "TeleportAction", "FollowTrajectoryAction", "AcquirePositionAction", "AssignRouteAction",
})
# Elements that only make sense while the entity moves, even without a speed.
_MOVING = frozenset({"LaneChangeAction", "LongitudinalDistanceAction", "FollowTrajectoryAction",
                     "AcquirePositionAction", "AssignRouteAction"})


def scene_actions(bundle: ParseBundle) -> list[ActionIR]:
    """Actions that describe the scenario, without simulation-control events."""
    return [action for action in bundle.scenario.actions if action.event_name not in DISCARDED_EVENTS]


def actions_of(bundle: ParseBundle, actor: str) -> list[ActionIR]:
    name = actor.casefold()
    return [action for action in scene_actions(bundle)
            if name in {item.strip().casefold() for item in (action.actor or "").split(",")}]


def _element(action: ActionIR) -> str:
    return action.element or action.kind


def is_scenery(entity: EntityIR) -> bool:
    """A MiscObject (cone, barrier, carton) is scenery, not a traffic participant."""
    return entity.kind == "miscobject"


# 3D model names are the authoring tool's convention (Child01, ACEA_Child01, Tricycle01 authored
# as a car), not OpenSCENARIO: an accelerator like EnableXXX. Present, strong evidence; absent or
# unfamiliar, nothing.
_MODEL_TRAITS = (("child", "child"), ("tricycle", "tricycle"))


def model_traits(entity: EntityIR) -> tuple[str, ...]:
    """What the entity's 3D model shows beyond its category: a child, a tricycle."""
    model = (entity.model or "").casefold()
    return tuple(trait for marker, trait in _MODEL_TRAITS if marker in model)


# ---------- speed ----------

def _speed_actions(bundle: ParseBundle, actor: str) -> list[ActionIR]:
    return [action for action in actions_of(bundle, actor) if _element(action) == "SpeedAction"]


def _absolute(action: ActionIR) -> bool:
    """A SpeedAction with an absolute target; a relative target (or an unresolved parameter) has none."""
    return action.target_value is not None and math.isfinite(action.target_value)


def scene_speed_mps(bundle: ParseBundle, actor: str) -> float | None:
    """The speed the actor reaches in the scenario: the highest absolute target of any SpeedAction.

    Initialization often sets 0 and the story accelerates (0 -> 80 km/h), so the
    initial value alone is not the scenario's speed. Story events need not run in
    document order, so the reading does not depend on it.
    """
    values = [action.target_value for action in _speed_actions(bundle, actor) if _absolute(action)]
    return max(values) if values else None


def speed_behaviour(bundle: ParseBundle, actor: str) -> str:
    """static, cruise, stop, speed_change, reverse, or unknown.

    * stop: a story SpeedAction with a transition (not a step) to standstill
      after the actor moved. A step to zero is a reset, not braking.
    * speed_change: more than one distinct non-zero target.
    * cruise: one non-zero target.
    """
    actions = actions_of(bundle, actor)
    speeds = [action for action in _speed_actions(bundle, actor) if _absolute(action)]
    values = [action.target_value for action in speeds]
    if any(value < -policy.MOVING_SPEED_MPS for value in values):
        return "reverse"
    cruise = max(values, default=0.0)
    # A story speed relative to another entity also means the actor moves.
    moving = cruise > policy.MOVING_SPEED_MPS or any(
        action.phase == "story" and (_element(action) in _MOVING or
                                     (_element(action) == "SpeedAction" and not _absolute(action)))
        for action in actions)
    if not moving:
        return "static"
    if any(action.phase == "story" and (action.shape or "").casefold() != "step"
           and action.target_value <= policy.MOVING_SPEED_MPS for action in speeds):
        return "stop"
    distinct = {round(value, 1) for value in values if value > policy.MOVING_SPEED_MPS}
    if not distinct:
        return "unknown"  # moves along a trajectory, a route or a relative speed, at no stated speed
    return "speed_change" if len(distinct) > 1 else "cruise"


# ---------- commands and driver inputs ----------

def commands(bundle: ParseBundle, actor: str) -> list[str]:
    return [action.command for action in actions_of(bundle, actor) if action.command]


def command_function(bundle: ParseBundle, actor: str = "ego") -> str:
    """The function a command switches on (EnableNOA -> NOA); empty when none does."""
    for command in commands(bundle, actor):
        match = _ENABLE.search(command.split(";")[0])
        if match:
            return match.group(1).upper()
    return ""


def command_facts(bundle: ParseBundle, actor: str = "ego") -> dict[str, Any]:
    """What the actor's simulator commands do."""
    texts = [command.casefold().replace(" ", "") for command in commands(bundle, actor)]
    parking = ""
    if any("enableapa" in text for text in texts):
        parking = "park_out" if any("parkingout" in text for text in texts) else "park_in"
    elif any("parkingout" in text for text in texts):
        parking = "park_out"
    return {
        "function": command_function(bundle, actor),
        "system_control": any(_ENABLE.search(text) or text.startswith(_ENGAGE_COMMANDS) for text in texts),
        "lane_change": any(marker in text for text in texts for marker in _LANE_CHANGE_COMMANDS),
        "lane_departure": any(marker in text for text in texts for marker in _LANE_DEPARTURE_COMMANDS),
        "parking": parking,
        "door_open": any("door=open" in text for text in texts),
        "brake": any(text.startswith("brakeposition") for text in texts),
    }


def driver_overrides(bundle: ParseBundle, actor: str = "ego") -> dict[str, str]:
    """Driver inputs the story takes over (Throttle, Brake, SteeringWheel, ParkingBrake, Clutch, Gear)."""
    result: dict[str, str] = {}
    for action in actions_of(bundle, actor):
        if action.phase == "story":
            result.update(action.overrides)
    return result


def driver_requests(bundle: ParseBundle, actor: str = "ego") -> list[str]:
    """The driver's commands to the system under test (a lane-change request or confirmation).

    The library's convention, an accelerator: a driver input when present, never required.
    """
    return [command for command in commands(bundle, actor)
            if any(marker in command.casefold().replace(" ", "") for marker in _DRIVER_REQUEST_COMMANDS)]


def _reverse_gear(bundle: ParseBundle, actor: str) -> bool:
    for action in actions_of(bundle, actor):
        gear = action.overrides.get("Gear")
        try:
            if gear is not None and float(gear) < 0:
                return True
        except ValueError:
            continue
    return False


def actor_behaviors(bundle: ParseBundle, actor: str) -> set[str]:
    """The actor's behaviors in the typed requirement vocabulary.

    The ego also changes lanes when the scenario waits on a named lane-change check (see
    condition_facts): a lane change the system under test makes leaves no action in the file.
    """
    actions = actions_of(bundle, actor)
    story = [action for action in actions if action.phase == "story"]
    facts = command_facts(bundle, actor)
    result: set[str] = set()
    checked = actor.casefold() == "ego" and condition_facts(bundle)["lane_change"]
    if facts["lane_change"] or checked or any(_element(action) == "LaneChangeAction" for action in story):
        result.add("lane_change")
    if facts["lane_departure"]:
        result.add("lane_departure")
    if facts["system_control"]:
        result.add("system_control")
    if any(_element(action) == "LongitudinalDistanceAction" for action in story):
        result.add("following")
    if _reverse_gear(bundle, actor):
        result.add("reverse")
    if any(_element(action) not in _UNDERSTOOD for action in story):
        result.add("unknown")
    behaviour = speed_behaviour(bundle, actor)
    if behaviour != "static" or not result:
        result.add(behaviour)
    return result


# ---------- lateral movement and route ----------

# Commands naming the side the system under test moves to (ALCAMode=left, LaneOffset=right):
# the library's convention, an accelerator.
_SIDE_COMMANDS = ("alcamode=", "laneoffset=")


def _start_lane(bundle: ParseBundle, actor: str) -> float | None:
    name = actor.casefold()
    return next((_number(position.attributes.get("laneId")) for position in bundle.scenario.positions
                 if (position.actor or "").casefold() == name and position.kind == "LanePosition"), None)


def lateral_direction(bundle: ParseBundle, actor: str = "ego") -> str:
    """Which way the actor moves sideways: "left", "right", or "" when not read or both ways.

    A relative target lane counts to the left of the actor's own driving direction when
    positive (OpenSCENARIO); an absolute one is read against the lane the actor starts in:
    lane IDs grow away from the reference line on both sides, so in right-hand traffic a
    lane nearer to it is to the left. A command naming the side counts too.
    """
    directions: set[str] = set()
    start = _start_lane(bundle, actor)
    for action in actions_of(bundle, actor):
        target, value = action.lane_target, _number(action.lane_target.get("value"))
        if target.get("kind") == "RelativeTargetLane" and target.get("entityRef", "").casefold() == actor.casefold():
            if value:
                directions.add("left" if value > 0 else "right")
        elif target.get("kind") == "AbsoluteTargetLane" and start and value and value * start > 0 and value != start:
            directions.add("left" if abs(value) < abs(start) else "right")
        text = (action.command or "").casefold().replace(" ", "")
        for marker in _SIDE_COMMANDS:
            side = text.split(marker, 1)[1] if marker in text else ""
            directions.update(item for item in ("left", "right") if side.startswith(item))
    return directions.pop() if len(directions) == 1 else ""


def _world_pose(position: PositionIR, roads: dict) -> tuple[float, float, float] | None:
    """World x, y and heading of a world, lane or road position (OpenSCENARIO's h defaults to 0)."""
    attributes = position.attributes
    if position.kind == "WorldPosition":
        x, y = _number(attributes.get("x")), _number(attributes.get("y"))
        return (x, y, _number(attributes.get("h")) or 0.0) if x is not None and y is not None else None
    road, s = roads.get(attributes.get("roadId", "")), _number(attributes.get("s"))
    lane = _number(attributes.get("laneId"))
    if road is None or s is None:
        return None
    if position.kind == "LanePosition" and lane is not None:
        pose = road.world_from_lane(s, int(lane), _number(attributes.get("offset")) or 0.0)
    elif position.kind == "RoadPosition":
        pose = road.world_from_road(s, _number(attributes.get("t")) or 0.0)
    else:
        return None
    if pose is None:
        return None
    x, y, reference = pose
    heading = _position_heading(position, reference)
    # Without a stated heading, a vehicle drives its lane's way: against the reference line on the left.
    return x, y, heading if heading is not None else reference + (math.pi if lane and lane > 0 else 0.0)


def ego_curve_radius(bundle: ParseBundle) -> float | None:
    """Radius of the first curve ahead of where the ego starts (road_geometry.path_curve_radius).

    None when the road file is missing, the start cannot be placed or no curve lies ahead.
    """
    ego = next((item for item in bundle.scenario.positions if (item.actor or "").casefold() == "ego"), None)
    pose = _world_pose(ego, bundle.road_geometry) if ego is not None else None
    return path_curve_radius(bundle.road_geometry, *pose) if pose is not None else None


def ego_road_ahead(bundle: ParseBundle, distance: float) -> RoadAhead | None:
    """The first curve or junction within `distance` metres ahead of where the ego starts
    (road_geometry.road_ahead); None when the start cannot be placed on the road file."""
    ego = next((item for item in bundle.scenario.positions if (item.actor or "").casefold() == "ego"), None)
    pose = _world_pose(ego, bundle.road_geometry) if ego is not None else None
    return road_ahead(bundle.road_geometry, *pose, distance) if pose is not None else None


def scenario_reach(bundle: ParseBundle) -> float:
    """How far (straight line, metres) from the ego's start the scenario uses a place: another
    participant's start, or a position a condition waits for (an event's, the scenario's end);
    0 when the start cannot be placed."""
    roads = bundle.road_geometry
    ego = next((item for item in bundle.scenario.positions if (item.actor or "").casefold() == "ego"), None)
    start = _world_pose(ego, roads) if ego is not None else None
    if start is None:
        return 0.0
    places = [item for item in bundle.scenario.positions if (item.actor or "").casefold() != "ego"]
    places += [PositionIR(trigger.position["kind"], trigger.position) for trigger in bundle.scenario.triggers
               if trigger.position.get("kind")]
    poses = [pose for place in places if (pose := _world_pose(place, roads)) is not None]
    return max((math.dist(start[:2], pose[:2]) for pose in poses), default=0.0)


ROUTE_TURN_MIN = math.pi / 4  # a routing that turns the actor less than this goes straight


def route_turn_angle(bundle: ParseBundle, actor: str = "ego") -> float | None:
    """How far the actor's routing turns it (radians, left positive), or None without a routing
    whose positions state headings.

    From the stated headings in order, from where the actor starts through its route waypoints,
    trajectory vertices or AcquirePosition target. Summing each step's change telescopes to the
    last heading minus the first, so one heading stated wrong in between (a vertex at 0 inside a
    curve) cancels out.
    """
    name = actor.casefold()
    start = next((_world_pose(position, bundle.road_geometry) for position in bundle.scenario.positions
                  if (position.actor or "").casefold() == name), None)
    for action in actions_of(bundle, actor):
        headings = [heading for waypoint in action.waypoints if (heading := _number(waypoint.get("h"))) is not None]
        if start is not None and headings:
            headings.insert(0, start[2])
        if len(headings) >= 2:
            return sum(math.remainder(after - before, math.tau) for before, after in zip(headings, headings[1:]))
    return None


U_TURN_MIN = 3 * math.pi / 4  # a routing that turns the actor at least this far turns it around


def route_turn(bundle: ParseBundle, actor: str = "ego") -> str:
    """Which way the actor's routing turns it: "left", "right", "u_turn", "straight", or "" when not read."""
    turn = route_turn_angle(bundle, actor)
    if turn is None:
        return ""
    if abs(turn) >= U_TURN_MIN:
        return "u_turn"
    return "left" if turn >= ROUTE_TURN_MIN else "right" if turn <= -ROUTE_TURN_MIN else "straight"


# Map-name road types (parser.map_road_features) with a junction to turn at; a parking area's aisles too.
_TURNING_PLACES = frozenset({"junction", "roundabout", "parking"})


def ego_turn(bundle: ParseBundle) -> str:
    """Which way the ego leaves a junction: "straight", "left", "right", "u_turn", or "" when not read.

    A road file without a junction leaves nowhere to turn: straight, whatever the routing says (the
    bend of a curve is no turn). Otherwise the routing decides (route_turn). Without a road file a
    routing outweighs the map name, which is only read for a road with nowhere to turn.
    """
    road = bundle.road
    if not road.file_missing and not road.junction_count:
        return "straight"
    turn = route_turn(bundle)
    if not turn and road.file_missing and road.inferred_features and not set(road.inferred_features) & _TURNING_PLACES:
        return "straight"
    return turn


# ---------- named conditions ----------

# A library's own named checks (UserDefinedValueCondition: Check_LaneChangeCompleted,
# Check_SysEngReq_Rejected, Trigger_HandsOff) are the authoring tool's convention, not
# OpenSCENARIO semantics, like EnableXXX: present, strong evidence; absent or unknown, nothing.
# Set-up and teardown every case of the tool waits on tell nothing.
_SIMULATION_CONDITIONS = frozenset({"egopreparecompleted", "endthecase"})
_LANE_CHANGE_CONDITIONS = ("lanechange",)
# Whether the system activates (at Vsmax, on request) or asks the driver to take over before
# rain or fog: the checks of an activation-boundary test.
_ACTIVATION_CONDITIONS = ("activated", "sysengreq_accepted", "sysengreq_rejected", "dca_before")


def named_conditions(bundle: ParseBundle) -> tuple[str, ...]:
    """Names of the user-defined conditions the scenario starts or stops on, in file order."""
    result: list[str] = []
    for trigger in bundle.scenario.triggers:
        name = trigger.attributes.get("name", "") if trigger.kind == "UserDefinedValueCondition" else ""
        if name and name.casefold() not in _SIMULATION_CONDITIONS and name not in result:
            result.append(name)
    return tuple(result)


def condition_facts(bundle: ParseBundle) -> dict[str, bool]:
    """What the named checks show about the test (the system under test is the ego)."""
    names = [name.casefold() for name in named_conditions(bundle)]
    return {
        "lane_change": any(marker in name for name in names for marker in _LANE_CHANGE_CONDITIONS),
        "activation_boundary": any(marker in name for name in names for marker in _ACTIVATION_CONDITIONS),
    }


# ---------- environment ----------

_PRESET_WEATHER = {"sunny": "dry", "cloudy": "dry", "overcast": "dry", "rainy": "rain", "snowy": "snow",
                   "foggy": "fog", "dusty": "dust"}


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def _preset(source_case: dict[str, Any]) -> dict[str, Any]:
    presets = [item for item in source_case.get("environments") or [] if isinstance(item, dict)]
    current = source_case.get("current_environment_id")
    return next((item for item in presets if current and item.get("id") == current), presets[0] if presets else {})


def preset_environment(source_case: dict[str, Any]) -> dict[str, str]:
    """Weather and time of day of the authoring tool's environment preset.

    Rain and snow amounts outrank the preset's category. The preset's fog value is
    a rendering level, not a visibility, and is not read.
    """
    preset = _preset(source_case)
    if not preset:
        return {}
    result: dict[str, str] = {}
    for key, weather in (("snow", "snow"), ("rain", "rain"), ("dust", "dust")):
        if (_number(preset.get(key)) or 0) > 0:
            result["weather"] = weather
            break
    else:
        category = _PRESET_WEATHER.get(str(preset.get("category") or "").casefold())
        if category:
            result["weather"] = category
    clock = str(preset.get("time") or "")
    hour = _number(clock.split(":")[0]) if ":" in clock else None
    if hour is None and _number(preset.get("timeOfDay")) is not None:
        hour = _number(preset.get("timeOfDay")) // 100
    if hour is not None:
        result["time_of_day"] = "day" if 6 <= hour < 18 else "night"
    return result


def asset_environment(bundle: ParseBundle) -> dict[str, str | float]:
    """Environment set in the scenario, completed from the authoring tool's preset."""
    return {**preset_environment(bundle.source_case), **bundle.scenario.environment}


def environment_events(bundle: ParseBundle) -> list[tuple[str, dict[str, str | float]]]:
    """The story's environment changes in file order, as (event name, reading): rain growing from
    10 to 70 mm/h, fog closing in to 25 m, day turning to night. The scenario's environment
    already merges them (asset_environment); the sequence describes the test."""
    return [(action.event_name or action.name, action.environment) for action in scene_actions(bundle)
            if action.phase == "story" and action.environment]


def in_tunnel(bundle: ParseBundle) -> bool:
    """The story turns the light to night and back to day: the ego drives through a tunnel, lit
    the way a library without tunnel roads simulates one. A night test turns once."""
    lighting = [reading["time_of_day"] for _, reading in environment_events(bundle) if reading.get("time_of_day")]
    return "night" in lighting and "day" in lighting[lighting.index("night") + 1:]


# ---------- scoring ----------

# Criteria every case of the authoring tool carries alike (a 600 s timeout; collision, switched
# on or off with no pattern across a library): they tell nothing about the test.
_DEFAULT_CRITERIA = frozenset({"timeout", "collision"})
_OPERATORS = {"gt": ">", "ge": ">=", "lt": "<", "le": "<=", "eq": "=", "ne": "!="}


def _condition_text(condition: dict[str, Any]) -> str:
    variable, value = condition.get("variable"), condition.get("value")
    if isinstance(value, dict):  # stopTrigger {red: true, vru: false}: the flags that are set
        value = "+".join(str(key) for key, flag in value.items() if flag is True) or "none"
    operator = _OPERATORS.get(str(condition.get("operator") or "").casefold(), "=")
    return f"{variable}{operator}{_scalar_text(value)}" if value is not None else str(variable)


def _scalar_text(value: Any) -> str:
    number = _number(value)
    return f"{number:g}" if number is not None and not isinstance(value, bool) else str(value)


def scoring_criteria(bundle: ParseBundle) -> tuple[str, ...]:
    """What the authoring tool scores a run by, beyond its defaults, in authoring order.

    The lateral distance to the lane line (dtlc>1.75) marks a lane-keeping or lane-change test,
    longitudinal acceleration limits (lonacc<-5) a following test, a red-light stop region
    (stopandgo: stopTrigger=red) a traffic-light test, leaving the road (offtrack) a lateral
    control test. A simulator's own scoring, not OpenSCENARIO: present, it tells what the test
    measures; absent, nothing.
    """
    result: list[str] = []
    for item in bundle.source_case.get("judgements") or []:
        kind = str(item.get("type") or "") if isinstance(item, dict) else ""
        if not kind or not item.get("enabled", True) or kind in _DEFAULT_CRITERIA:
            continue
        conditions = [_condition_text(condition) for condition in item.get("conditions") or []
                      if isinstance(condition, dict) and condition.get("variable")]
        text = ", ".join(conditions) if kind == "customized" else (
            f"{kind}: {', '.join(conditions)}" if conditions else kind)
        if text and text not in result:
            result.append(text)
    return tuple(result)


# ---------- scenery ----------

def scenery_summary(bundle: ParseBundle) -> dict[str, dict[str, int]]:
    """Scenery props counted by 3D model, and the lanes they stand in.

    The count is meaning: 154 barriers and 60 cones mark a construction zone, one
    carton in lane -2 is an obstacle to detect.
    """
    props = [entity for entity in bundle.scenario.entities if is_scenery(entity)]
    names = {entity.name.casefold() for entity in props}
    lanes = Counter(
        f"lane {position.attributes['laneId']}" for position in bundle.scenario.positions
        if (position.actor or "").casefold() in names and position.kind == "LanePosition"
        and position.attributes.get("laneId") is not None
    )
    return {
        "models": dict(Counter(entity.model or entity.category or "object" for entity in props).most_common()),
        "lanes": dict(lanes.most_common()),
    }


# ---------- occlusion ----------

def occlusions(bundle: ParseBundle, kind_of) -> frozenset[tuple[str, str]]:
    """(occluder kind, occluded kind) pairs: a nearer object covers the ego's line of sight.

    Read per instance before props are grouped. Props occluding props are scenery and
    not recorded.
    """
    return frozenset((kind_of(blocker), kind_of(target)) for blocker, target in _occluding(bundle))


def _occluding(bundle: ParseBundle) -> list[tuple[EntityIR, EntityIR]]:
    """(occluder, occluded) entity pairs. An occluder's angular width comes from its own
    BoundingBox; a moving target sweeps its line of sight from where it starts to the
    ego's path, so it counts as occluded if any part of that sweep is covered.
    """
    positions = {item.actor.casefold(): item for item in bundle.scenario.positions if item.actor}
    ego = positions.get("ego")
    if ego is None:
        return []
    placed = []
    for entity in bundle.scenario.entities:
        name = entity.name.casefold()
        if name == "ego" or name not in positions:
            continue
        offset = _relative_offset(ego, positions[name], bundle.road_geometry)
        if offset is None or offset[0] <= 0:
            continue
        moving = speed_behaviour(bundle, entity.name) not in {"static", "unknown"}
        placed.append((entity, offset, moving))
    result = []
    for blocker, (forward, left), _ in placed:
        if not blocker.width:
            continue
        distance = math.hypot(forward, left)
        angle, half_width = math.atan2(left, forward), math.atan2(blocker.width / 2, distance)
        for target, (target_forward, target_left), moving in placed:
            if target is blocker or (is_scenery(blocker) and is_scenery(target)):
                continue
            if math.hypot(target_forward, target_left) <= distance:
                continue
            near = math.atan2(target_left, target_forward)
            low, high = (min(near, 0.0), max(near, 0.0)) if moving else (near, near)
            if low <= angle + half_width and high >= angle - half_width:
                result.append((blocker, target))
    return result


# ---------- background participants ----------

def background_participants(bundle: ParseBundle) -> frozenset[str]:
    """Names (casefolded) of traffic participants that take no part in the test.

    A participant takes part when it moves (a speed set only in Init is enough), a
    trigger condition refers to it, it has a story action, it stands in the ego's path
    ahead, its position cannot be read, or it occludes a participant that takes part or
    a prop in the ego's path. Of a row in the path, what is hidden behind another such
    participant takes no part. The rest is background: the parked cars of a narrow passage, a VRU crowd standing by. When no
    participant takes part, the scenario has no lead to set a background against (a lone
    stationary car whose position on a curve the straight-line reading misses): none is.
    Structure only, never names.
    """
    scenario = bundle.scenario
    positions = {item.actor.casefold(): item for item in scenario.positions if item.actor}
    ego = positions.get("ego")
    # Triggering entities, and the entity a condition measures against (RelativeDistanceCondition).
    referenced = {name.casefold() for trigger in scenario.triggers
                  for name in (*trigger.entity_refs, trigger.attributes.get("entityRef", "")) if name}
    acting = {name.strip().casefold() for action in scene_actions(bundle) if action.phase == "story"
              for name in (action.actor or "").split(",")}
    candidates = {entity.name.casefold() for entity in scenario.entities
                  if entity.name.casefold() != "ego" and not is_scenery(entity)}
    props = {entity.name.casefold() for entity in scenario.entities if is_scenery(entity)}
    widths = {entity.name.casefold(): entity.width or 0.0 for entity in scenario.entities}
    ego_half_width = (widths.get("ego") or policy.EGO_WIDTH_M) / 2

    offsets = {name: _relative_offset(ego, positions[name], bundle.road_geometry)
               for name in candidates | props if ego is not None and name in positions}

    def in_path(name: str) -> bool:
        """Ahead, in the ego's lane or with its body reaching into the ego's width."""
        offset = offsets.get(name)
        if offset is None:
            return True
        lateral = abs(offset[1])
        return offset[0] > 0 and (lateral <= policy.SAME_LANE_M or lateral - widths[name] / 2 < ego_half_width)

    def span(name: str) -> tuple[float, float]:
        forward, left = offsets[name]
        angle, half = math.atan2(left, forward), math.atan2(widths[name] / 2, math.hypot(forward, left))
        return angle - half, angle + half

    def hides(blocker: str, target: str) -> bool:
        """A nearer participant covers most of the target's width (a thin pedestrian hides no car)."""
        if None in (offsets.get(blocker), offsets.get(target)) or not widths[target]:
            return False
        if math.hypot(*offsets[blocker]) >= math.hypot(*offsets[target]):
            return False
        (low, high), (target_low, target_high) = span(blocker), span(target)
        covered = min(high, target_high) - max(low, target_low)
        return covered >= policy.HIDDEN_SHARE * (target_high - target_low)

    moving = {entity.name.casefold() for entity in scenario.entities
              if entity.name.casefold() in candidates and speed_behaviour(bundle, entity.name) != "static"}
    active = {name for name in candidates if name in referenced or name in acting or name in moving}
    in_lane = {name for name in candidates - active if in_path(name)}
    hidden = {target for target in in_lane if any(hides(blocker, target) for blocker in in_lane - {target})}
    pairs = [(blocker.name.casefold(), target.name.casefold()) for blocker, target in _occluding(bundle)]
    relevant = active | (in_lane - hidden)
    targets = relevant | {name for name in props if in_path(name)}
    relevant |= {blocker for blocker, target in pairs if target in targets}
    return frozenset(candidates - relevant) if relevant & candidates else frozenset()
