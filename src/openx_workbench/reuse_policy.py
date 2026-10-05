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
COST_FUNCTION = 10  # the candidate tests a different function (AEB vs ACC)
COST_PARTICIPANT = 8  # a required participant is missing or interacts differently
COST_ENTITY = 6  # legacy keywords: a required entity class is absent
COST_EXTRA_PARTICIPANT = 3  # the candidate has a participant the requirement does not
COST_UNKNOWN_FAMILY = 2  # the candidate's scenario family cannot be read
COST_BEHAVIOR = 2  # change one participant's or the ego's storyboard behavior
COST_VERIFY_PARTICIPANT = 2  # participant facts must be checked by hand
COST_RELATION = 2  # legacy keywords: move a participant (front/left/adjacent lane)
COST_TRIGGER = 1.5  # change a start trigger
COST_ROAD = 1.0  # select or modify the OpenDRIVE road
COST_PARAMETER = 0.5  # set one numeric parameter, speed or environment value

# Verified, non-blocking changes costing at least this much are a "major modification": the
# candidate is still reusable, but close to a new build. A behavior change plus removing an extra
# participant (2 + 3) reaches it; on the benchmark every labelled "modify" stays below 4.
MAJOR_MODIFY_COST = 5.0

# ---------- ego-relative geometry ----------
# Where a participant sits relative to the ego vehicle (reuse_geometry).

ALONGSIDE_M = 5.0  # |longitudinal offset| up to this is "alongside", beyond it front/rear
SAME_LANE_M = 1.5  # |lateral offset| up to this is the same lane, beyond it left/right
LANE_WIDTH_M = 3.5  # assumed lane width when only lane IDs are known
FACING_SAME_MAX = math.pi / 6  # heading difference up to 30° faces the same way
FACING_OPPOSITE_MIN = 5 * math.pi / 6  # from 150° faces the opposite way; between: crossing

# ---------- value tolerances ----------
# Absolute tolerance within which an extracted value satisfies a requirement.

PARAMETER_TOLERANCE = {"ttc_s": 0.05, "distance_m": 0.1, "ego_speed_kph": 0.5}
TARGET_SPEED_TOLERANCE_KPH = 0.5
MOVING_SPEED_MPS = 0.3  # speeds up to this (about 1 km/h) are standstill; targets are compared to 0.1 m/s

# ---------- ranking ----------
# Candidates are ordered by (blocking differences, change cost, -score). The score
# only orders candidates inside one structural bucket and for free-text search.

WEIGHT_SEMANTIC = 0.55  # encoder similarity of requirement and asset text
WEIGHT_SCENARIO = 0.30  # overlap of participants, behaviors, triggers and function
WEIGHT_ROAD = 0.15  # overlap of road features
REASON_SCENARIO_MIN = 0.66  # scenario overlap shown as "scenario structure match"
REASON_ROAD_MIN = 0.75  # road overlap shown as "road structure match"
RECALL_MIN = 100  # semantic recall size for a structured query: max(RECALL_MIN, top_k * RECALL_FACTOR)
RECALL_FACTOR = 20
STRUCTURE_RECALL = 50  # extra candidates recalled through the structure-text vectors
