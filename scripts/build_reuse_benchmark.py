"""Render the authored reuse benchmark library from its specification.

examples/reuse-benchmark/benchmark.json is the single source: each asset entry
describes the ego vehicle, its participants and the environment. This script
writes the matching OpenSCENARIO files to assets/ and the two OpenDRIVE roads
to roads/. tests/test_reuse_benchmark.py fails when the committed files drift
from the specification.

    python scripts/build_reuse_benchmark.py [--check]
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "examples" / "reuse-benchmark"

ROADS = {
    "straight": ("straight-2x2.xodr", "Straight two-lane-per-direction road",
                 '<geometry s="0" x="0" y="0" hdg="0" length="500"><line/></geometry>', 500),
    "curve": ("curve-2x2.xodr", "Curved two-lane-per-direction road (R = 250 m)",
              '<geometry s="0" x="0" y="0" hdg="0" length="20"><line/></geometry>'
              '<geometry s="20" x="20" y="0" hdg="0" length="380"><arc curvature="0.004"/></geometry>', 400),
}

# Bounding boxes and dimensions are plausible authored values, not measured vehicles.
ENTITIES = {
    "car": ('<Vehicle name="{name}" vehicleCategory="car">', (4.5, 1.8, 1.5)),
    "truck": ('<Vehicle name="{name}" vehicleCategory="truck">', (9.0, 2.5, 3.5)),
    "motorbike": ('<Vehicle name="{name}" vehicleCategory="motorbike">', (2.1, 0.8, 1.4)),
    "bicycle": ('<Vehicle name="{name}" vehicleCategory="bicycle">', (1.8, 0.6, 1.7)),
    "pedestrian": ('<Pedestrian name="{name}" model="adult" mass="75" pedestrianCategory="pedestrian">',
                   (0.5, 0.6, 1.8)),
}
EGO_S = 20.0


def road_xml(kind: str) -> str:
    name, title, geometry, length = ROADS[kind]
    lane = '<lane id="{id}" type="driving" level="false"><width sOffset="0" a="3.5" b="0" c="0" d="0"/></lane>'
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<OpenDRIVE>\n"
        f'  <header revMajor="1" revMinor="7" name="{title}" version="1.00" date="2026-10-04"/>\n'
        f'  <road name="{title}" length="{length}" id="1" junction="-1">\n'
        f"    <planView>{geometry}</planView>\n"
        '    <lanes><laneSection s="0">'
        f"<left>{lane.format(id=2)}{lane.format(id=1)}</left>"
        '<center><lane id="0" type="none" level="false"/></center>'
        f"<right>{lane.format(id=-1)}{lane.format(id=-2)}</right>"
        "</laneSection></lanes>\n"
        "  </road>\n"
        "</OpenDRIVE>\n"
    )


def _entity(name: str, kind: str) -> str:
    opening, (length, width, height) = ENTITIES[kind]
    closing = "</Pedestrian>" if kind == "pedestrian" else "</Vehicle>"
    box = (f'<BoundingBox><Center x="{length / 2 - 1:g}" y="0" z="{height / 2:g}"/>'
           f'<Dimensions width="{width:g}" length="{length:g}" height="{height:g}"/></BoundingBox>')
    return f'    <ScenarioObject name="{name}">{opening.format(name=name)}{box}{closing}</ScenarioObject>\n'


def _position(lane: int, s: float, heading: float) -> str:
    return (f'<Position><LanePosition roadId="1" laneId="{lane}" s="{s:g}" offset="0">'
            f'<Orientation type="relative" h="{heading:.4f}"/></LanePosition></Position>')


def _speed(kph: float) -> str:
    return (f'<LongitudinalAction><SpeedAction><SpeedActionDynamics dynamicsShape="step" value="0" '
            f'dynamicsDimension="time"/><SpeedActionTarget><AbsoluteTargetSpeed value="{kph / 3.6:.4f}"/>'
            "</SpeedActionTarget></SpeedAction></LongitudinalAction>")


def _init(name: str, lane: int | None, s: float, heading: float, kph: float) -> str:
    # lane None leaves the start position undeclared, as in a library asset whose placement is incomplete.
    teleport = (f"<PrivateAction><TeleportAction>{_position(lane, s, heading)}</TeleportAction></PrivateAction>"
                if lane is not None else "")
    return f'<Private entityRef="{name}">{teleport}<PrivateAction>{_speed(kph)}</PrivateAction></Private>'



def _event(name: str, index: int, step: dict) -> str:
    if step["type"] == "stop":
        action = (f'<LongitudinalAction><SpeedAction><SpeedActionDynamics dynamicsShape="linear" '
                  f'value="{step.get("decel", 4)}" dynamicsDimension="rate"/><SpeedActionTarget>'
                  '<AbsoluteTargetSpeed value="0"/></SpeedActionTarget></SpeedAction></LongitudinalAction>')
    elif step["type"] == "lane_change":
        action = ('<LateralAction><LaneChangeAction><LaneChangeActionDynamics dynamicsShape="sinusoidal" '
                  'value="3" dynamicsDimension="time"/><LaneChangeTarget>'
                  f'<AbsoluteTargetLane value="{step["to"]}"/></LaneChangeTarget></LaneChangeAction></LateralAction>')
    else:
        raise ValueError(f"Unknown story step {step['type']}")
    return (f'<Event name="{name}-{step["type"]}-{index}" priority="overwrite"><Action name="{step["type"]}">'
            f"<PrivateAction>{action}</PrivateAction></Action><StartTrigger><ConditionGroup>"
            f'<Condition name="at-{step.get("at", 2)}s" delay="0" conditionEdge="rising"><ByValueCondition>'
            f'<SimulationTimeCondition value="{step.get("at", 2)}" rule="greaterThan"/></ByValueCondition>'
            "</Condition></ConditionGroup></StartTrigger></Event>")


def scenario_xml(asset: dict) -> str:
    road_file = ROADS[asset["road"]][0]
    targets = asset["participants"]
    entities = _entity("Ego", "car") + "".join(_entity(item["name"], item["type"]) for item in targets)
    init = _init("Ego", asset.get("ego_lane", -1), EGO_S, 0.0, asset["ego_kph"]) + "".join(
        _init(item["name"], item["lane"], EGO_S + item["ds"], math.radians(item.get("heading_deg", 0)), item["kph"])
        for item in targets
    )
    groups = "".join(
        f'<ManeuverGroup name="{item["name"]}-group" maximumExecutionCount="1">'
        f'<Actors selectTriggeringEntities="false"><EntityRef entityRef="{item["name"]}"/></Actors>'
        f'<Maneuver name="{item["name"]}-maneuver">'
        + "".join(_event(item["name"], index, step) for index, step in enumerate(item["story"], 1))
        + "</Maneuver></ManeuverGroup>"
        for item in targets
        if item.get("story")
    )
    story = (
        '<Story name="Story"><Act name="Act">' + groups
        + '<StartTrigger><ConditionGroup><Condition name="act-start" delay="0" conditionEdge="rising">'
        '<ByValueCondition><SimulationTimeCondition value="0" rule="greaterThan"/></ByValueCondition>'
        "</Condition></ConditionGroup></StartTrigger></Act></Story>"
        if groups
        else ""
    )
    weather = asset.get("weather", "dry")
    precipitation = (f'<Precipitation precipitationType="{weather}" precipitationIntensity="0" intensity="0"/>'
                     if weather == "dry" else
                     f'<Precipitation precipitationType="{weather}" intensity="0.6"/>')
    return (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        "<OpenSCENARIO>\n"
        f'  <FileHeader revMajor="1" revMinor="2" date="2026-10-04T00:00:00" description="{asset["title"]}" '
        'author="OpenX Scenario Workbench reuse benchmark (authored)"/>\n'
        f'  <RoadNetwork><LogicFile filepath="../roads/{road_file}"/></RoadNetwork>\n'
        "  <Entities>\n" + entities + "  </Entities>\n"
        f'  <Environment name="Environment"><TimeOfDay animation="false" dateTime="2026-06-01T{asset.get("hour", 12):02d}:00:00"/>'
        f'<Weather cloudState="free">{precipitation}<Fog visualRange="{asset.get("visibility_m", 1200)}"/></Weather>'
        "<RoadCondition frictionScaleFactor=\"1.0\"/></Environment>\n"
        "  <Storyboard>\n"
        f"    <Init><Actions>{init}</Actions></Init>\n"
        f"    {story}\n"
        '    <StopTrigger><ConditionGroup><Condition name="end" delay="0" conditionEdge="rising"><ByValueCondition>'
        '<SimulationTimeCondition value="20" rule="greaterThan"/></ByValueCondition></Condition></ConditionGroup>'
        "</StopTrigger>\n"
        "  </Storyboard>\n"
        "</OpenSCENARIO>\n"
    )


def rendered(spec: dict) -> dict[str, str]:
    files = {f"roads/{name}": road_xml(kind) for kind, (name, *_rest) in ROADS.items()}
    files.update({f"assets/{asset['id']}.xosc": scenario_xml(asset) for asset in spec["assets"]})
    return files


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--check", action="store_true", help="only report files that differ from the specification")
    args = parser.parse_args()
    spec = json.loads((ROOT / "benchmark.json").read_text(encoding="utf-8"))
    stale = []
    for relative, content in rendered(spec).items():
        path = ROOT / relative
        if not path.exists() or path.read_bytes() != content.encode("utf-8"):
            stale.append(relative)
            if not args.check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_bytes(content.encode("utf-8"))
    print(("stale: " if args.check else "written: ") + (", ".join(stale) or "none"))
    return 1 if args.check and stale else 0


if __name__ == "__main__":
    sys.exit(main())
