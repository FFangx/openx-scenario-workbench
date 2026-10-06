"""Every tunable number behind a reuse verdict and its ranking, in one place.

Changing a value here changes verdicts or ranking: rerun ``openx-ablation`` and
update docs/EVALUATION.md (see .impeccable/REACT_MIGRATION_HANDOFF.md, section 13).
"""

from __future__ import annotations

import math

# ---------- modification cost ----------
# Rough engineering effort of closing one difference, in arbitrary units. Within a
# reuse level, candidates are ranked by the summed cost (fewest blocking
# differences first). Integral values stay ints: they are serialized into traces.

COST_SCENARIO_FAMILY = 10  # a different scenario family (car-to-car vs car-to-VRU)
COST_FUNCTION = 2  # switch the tested function and its scoring (AEB vs FCW); the story is unchanged
COST_PARTICIPANT = 8  # a required participant is missing or interacts differently
COST_ENTITY = 6  # legacy keywords: a required entity class is absent
COST_EXTRA_PARTICIPANT = 3  # the candidate has a participant the requirement does not
COST_BACKGROUND_PARTICIPANT = 0.25  # per group of left-over background participants (parked cars)
COST_UNKNOWN_FAMILY = 2  # the candidate's scenario family cannot be read
COST_BEHAVIOR = 2  # change one participant's or the ego's storyboard behavior
COST_VERIFY_PARTICIPANT = 2  # participant facts must be checked by hand
COST_RELATION = 2  # legacy keywords: move a participant (front/left/adjacent lane)
COST_TRIGGER = 1.5  # change a start trigger
COST_PLACEMENT = 1.5  # move a moving participant's start or retime its trigger; turn a standing one
COST_ROAD = 1.0  # select or modify the OpenDRIVE road
COST_PARAMETER = 0.5  # set one numeric parameter, speed or environment value

# ---------- difference tiers ----------
# Which differences decide reuse. Core facts make up the scenario's story and its road
# (who is there, what they do, what is tested, which road); an unverified core fact keeps a
# candidate in review. Adjustable facts (speeds, TTC, triggers, environment) are edited while
# reusing; an unverified one is listed to confirm during the change, not a reason for review.
# Notes (test intent, end condition) describe the evaluation, not the scenario: listed, never
# compared. Mirrors the ScenarioManager layering of 2026-07-27 (story > map > parameters).

TIER_CORE, TIER_ADJUSTABLE, TIER_NOTE = "core", "adjustable", "note"
# An unresolved parameter reference in the asset ("parameter_resolution") stays core: what the
# file does at all is unclear until it is resolved.
TIER_BY_CATEGORY = {
    "function": TIER_ADJUSTABLE,  # a setting of the reuse, rarely in the file (2026-10-05)
    "background_participant": TIER_ADJUSTABLE,  # kept or removed while reusing, like scenery
    "parameter": TIER_ADJUSTABLE,
    "trigger": TIER_ADJUSTABLE,
    "placement": TIER_ADJUSTABLE,  # where a moving participant starts, which way a standing one faces
    "environment": TIER_ADJUSTABLE,
}
# Requirement items the comparison cannot check yet ("unverified"), by "key=value", then by key.
# Only a functional test intent is a note: a misuse or activation-boundary test is another kind
# of test, which an asset does not show, so it stays core.
TIER_BY_REQUIREMENT = {
    "lateral_direction": TIER_ADJUSTABLE,
    "ego_action=lane_change": TIER_ADJUSTABLE,  # under system control the system changes lanes itself
    "ego_action=system_control": TIER_ADJUSTABLE,  # switched on while reusing, often not in the file
    "trigger": TIER_ADJUSTABLE,
    "test_intent=功能试验": TIER_NOTE,
    "end_condition": TIER_NOTE,
}


def difference_tier(category: str, requested: str) -> str:
    """The tier of a difference; anything not listed is core, the safe default."""
    if category == "unverified":
        return TIER_BY_REQUIREMENT.get(requested, TIER_BY_REQUIREMENT.get(requested.split("=", 1)[0], TIER_CORE))
    return TIER_BY_CATEGORY.get(category, TIER_CORE)


# Verified, non-blocking changes costing at least this much are a "major modification": the
# candidate is still reusable, but close to a new build. A behavior change plus removing an extra
# participant (2 + 3) reaches it; on the benchmark every labelled "modify" stays below 4.
MAJOR_MODIFY_COST = 5.0

# ---------- ego-relative geometry ----------
# Where a participant sits relative to the ego vehicle (reuse_geometry).

ALONGSIDE_M = 5.0  # |longitudinal offset| up to this is "alongside", beyond it front/rear
SAME_LANE_M = 1.5  # |lateral offset| up to this is the same lane, beyond it left/right
LANE_WIDTH_M = 3.5  # assumed lane width when only lane IDs are known
EGO_WIDTH_M = 2.0  # assumed ego width when its BoundingBox is not declared
HIDDEN_SHARE = 0.8  # a standing participant covering this share of another's width hides it
FACING_SAME_MAX = math.pi / 6  # heading difference up to 30° faces the same way
FACING_OPPOSITE_MIN = 5 * math.pi / 6  # from 150° faces the opposite way; between: crossing

# ---------- value tolerances ----------
# Absolute tolerance within which an extracted value satisfies a requirement.

PARAMETER_TOLERANCE = {"ttc_s": 0.05, "distance_m": 0.1, "ego_speed_kph": 0.5}
TARGET_SPEED_TOLERANCE_KPH = 0.5
# Relative: a road drawn as R251 serves an R250 test; R250 and R500 test variants stay apart.
CURVE_RADIUS_TOLERANCE = 0.1
MOVING_SPEED_MPS = 0.3  # speeds up to this (about 1 km/h) are standstill; targets are compared to 0.1 m/s

# ---------- ranking ----------
# Two stages (retrieval.rank_candidates): structure decides the verdict and puts
# verified candidates first; among structurally tied review candidates a standout
# name or text match leads; then the other standout matches; then the rest by
# (blocking differences, change cost, -score). The score also orders free-text search.

WEIGHT_SEMANTIC = 0.55  # encoder similarity of requirement and asset text
WEIGHT_SCENARIO = 0.30  # overlap of participants, behaviors, triggers and function
WEIGHT_ROAD = 0.15  # overlap of road features
REASON_SCENARIO_MIN = 0.66  # scenario overlap shown as "scenario structure match"
REASON_ROAD_MIN = 0.75  # road overlap shown as "road structure match"
# Review candidates costing at most this much more than the cheapest review candidate are
# structurally tied (one road change, or two parameters).
NAME_TIE_COST = 1.0
# A name or text similarity this many standard deviations above the library mean is a
# standout match. Relative, so it holds for any encoder; libraries under 8 assets cannot
# reach it and keep the structural order. Tuned on a private real-standard evaluation
# (2026-10-05): with names it lifts BGE-M3 R@1, with opaque names it leaves R@1 unchanged.
NAME_STANDOUT_Z = 2.5
NAME_RECALL = 10  # standout matches among this many most similar assets are recalled
