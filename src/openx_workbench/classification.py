"""Version-scoped asset classification: labels read from the files by rules, or set by a reviewer."""
from __future__ import annotations

import json
import math
import re
import uuid
from typing import get_args

from .pdf_v2.scene_schemas import TestedFunction
from .pdf_store import PdfStore

FUNCTIONS = tuple(get_args(TestedFunction))
ROADS = ("直道", "弯道", "交叉口", "停车场", "环岛", "匝道", "未知")
# Road types read from a map name when the road file is missing (parser.map_road_features).
MAP_ROAD_LABELS = {"straight": "直道", "curve": "弯道", "junction": "交叉口", "parking": "停车场", "roundabout": "环岛"}
TARGETS = ("乘用车", "商用车", "两轮车", "行人", "骑行者", "障碍物", "动物")
# The functions of a lane support system (LSS); a title naming LSS and one of them tests that one.
LANE_SUPPORT = {"LDW", "LDP", "LKA", "ELK"}
# Raised whenever the rules change: labels from older rules are read again (outdated).
RULES_VERSION = 2
# The stretch ahead of the ego's start where the test happens: out to past the farthest place the
# scenario uses, and at least ROAD_AHEAD_M where it states no place (curves and junctions of the
# libraries' tests start 21-500 m ahead; a 120 km/h curve test's curve 330 m ahead).
ROAD_AHEAD_M = 250.0
PAST_REACH_M = 50.0  # the stretch reaches this far past the farthest place the scenario uses
RING_REACH_M = 30.0  # a junction or curve this close to a ring's edge belongs to the roundabout


def rule_labels(asset, file_name=""):
    """The labels the files state: the function the title names or a command switches on, the road the
    ego drives into, the participants and the action types."""
    from .scene_facts import command_function

    bundle = asset.bundle
    text = f"{asset.title} {bundle.scenario.description or ''} {file_name}"
    named = [fn for fn in FUNCTIONS if fn != "未知" and re.search(r"(?<![A-Za-z])" + re.escape(fn) + r"(?![A-Za-z])", text, re.I)]
    if set(named) & LANE_SUPPORT:
        named = [fn for fn in named if fn != "LSS"]  # "LSS__LDW_...": the lane-support function tested
    command = command_function(bundle)
    return {"function_type": named[0] if len(named) == 1 else (command if command in FUNCTIONS else "未知"),
            "label_road_type": _road_label(bundle),
            "label_target_type": _target_labels(asset),
            "label_actions": sorted({action.kind for action in bundle.scenario.actions}),
            "scenario_intent": bundle.scenario.description or asset.title}


def _road_label(bundle):
    """Parking when the ego parks, or reverses where parking spaces are drawn; else the first curve or
    junction on the stretch where the test happens, from the ego's start to past the farthest place
    the scenario uses (a roundabout when it is part of a ring); without a road file, the map's name."""
    from .road_geometry import roundabouts
    from .scene_facts import actor_behaviors, command_facts, ego_road_ahead, scenario_reach

    road = bundle.road
    if command_facts(bundle)["parking"] or ("reverse" in actor_behaviors(bundle, "ego") and road.furniture.get("parking_space")):
        return "停车场"
    if road.file_missing:
        return next((MAP_ROAD_LABELS[f] for f in road.inferred_features if f in MAP_ROAD_LABELS), "未知")
    ahead = ego_road_ahead(bundle, max(ROAD_AHEAD_M, scenario_reach(bundle) + PAST_REACH_M))
    if ahead is None:
        return "未知"
    if ahead.at and any(math.dist(ahead.at, (x, y)) <= radius + RING_REACH_M for x, y, radius in roundabouts(bundle.road_geometry)):
        return "环岛"
    return "交叉口" if ahead.junction else "弯道" if ahead.curve_radius else "直道"


def outdated(record):
    """Whether a version's labels are missing or come from older rules (or the retired model review);
    a reviewer's labels never are."""
    return record.get("status") != "manual_confirmed" and record.get("rules") != RULES_VERSION


def classify_asset(store, version):
    """The rule labels of a version, saved; a reviewer's confirmed labels stay final."""
    previous = read_classification(store, version)
    rule = rule_labels(store.load_asset(version), version.xosc_name)
    record = {"version_id": version.version_id, "rules": RULES_VERSION, "rule": rule, "final": rule,
              "status": "rule", "needs_review": False, "final_accepted": True, "differences": []}
    if previous.get("status") == "manual_confirmed":
        record.update(final=previous["final"], status="manual_confirmed",
                      differences=[key for key in rule if rule[key] != previous["final"].get(key)])
    _save(store, version, record)
    return record


def _target_labels(asset):
    from .reuse_facts import bundle_participant_signatures, bundle_scenery_signatures
    labels = {"pedestrian": "行人", "cyclist": "骑行者", "motorcycle": "两轮车",
              "vehicle": "乘用车", "truck": "商用车", "bus": "商用车", "van": "商用车",
              "trailer": "商用车", "obstacle": "障碍物"}
    return sorted({labels[item.kind] for item in (*bundle_participant_signatures(asset.bundle), *bundle_scenery_signatures(asset.bundle))
                   if item.kind in labels})


def read_classification(store, version):
    path = store.root / "assets" / version.asset_id / version.version_id / "classification.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


def _save(store, version, record):
    from datetime import datetime, timezone
    record["saved_at"] = datetime.now(timezone.utc).isoformat()
    folder = store.root / "assets" / version.asset_id / version.version_id
    PdfStore._write_json(folder / "classification_history" / (uuid.uuid4().hex + ".json"), record)
    PdfStore._write_json(folder / "classification.json", record)


def confirm_classification(store, version, final):
    if (final.get("function_type") not in FUNCTIONS or final.get("label_road_type") not in ROADS or
        not isinstance(final.get("label_target_type"), list) or any(value not in TARGETS for value in final["label_target_type"]) or
        not isinstance(final.get("label_actions"), list) or any(not isinstance(value, str) for value in final["label_actions"]) or
        not isinstance(final.get("scenario_intent"), str)):
        raise ValueError("Invalid classification.")
    record = read_classification(store, version) or classify_asset(store, version)
    record.update(final=final, status="manual_confirmed", needs_review=False, final_accepted=True,
                  differences=[key for key in record["rule"] if record["rule"][key] != final[key]])
    _save(store, version, record)
    return record
