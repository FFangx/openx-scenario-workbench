"""Comparison of a typed requirement (an approved PDF scene structure) with an asset's structure."""

from __future__ import annotations

from dataclasses import replace
from itertools import permutations

from . import reuse_policy as policy
from .catalog import OpenXAsset
from .reuse_differences import (
    ReuseDifference,
    environment_differences,
    missing,
    parameter_differences,
    target_speed_differences,
)
from .reuse_facts import asset_structure_query, bundle_parameters
from .scene_package import ParticipantSignature, RetrievalQuery

ENUMERATION_LIMIT = 6  # up to 6! = 720 participant pairings are enumerated; beyond, solve the assignment problem


def compare_structure(
    query: RetrievalQuery, asset: OpenXAsset, candidate: RetrievalQuery | None = None
) -> tuple[ReuseDifference, ...]:
    candidate = candidate or asset_structure_query(asset)
    differences = (
        participant_differences(
            query.participant_signatures, candidate.participant_signatures
        )
        if query.participant_signatures
        else []
    )
    for value in candidate.unverified:
        differences.append(ReuseDifference(
            "parameter_resolution", "resolved scenario parameters", value,
            "resolve parameter before confirming reuse", verified=False,
        ))
    for value in query.unverified:
        differences.append(
            ReuseDifference(
                "unverified",
                value,
                "not extracted",
                "verify declared requirement",
                verified=False,
            )
        )
    if query.tested_function:
        actual = candidate.tested_function
        if actual in {"", "未知", "unknown"}:
            differences.append(
                ReuseDifference(
                    "function",
                    query.tested_function,
                    "unknown",
                    "confirm tested function",
                    verified=False,
                )
            )
        elif actual != query.tested_function:
            differences.append(
                ReuseDifference(
                    "function",
                    query.tested_function,
                    actual,
                    "change tested function",
                    True,
                    policy.COST_FUNCTION,
                )
            )
    if "motorway" in query.road_features:
        differences.append(
            ReuseDifference(
                "road",
                "motorway",
                "not extracted",
                "verify road classification",
                verified=False,
            )
        )
    differences.extend(
        missing(
            "road",
            query.road_features - {"motorway"},
            set(candidate.road_features),
            "select or modify OpenDRIVE",
            cost=policy.COST_ROAD,
        )
    )
    differences.extend(
        missing(
            "trigger",
            query.trigger_kinds,
            set(candidate.trigger_kinds),
            "modify start trigger",
            cost=policy.COST_TRIGGER,
        )
    )
    if query.ego_actions:
        absent = query.ego_actions - candidate.ego_actions
        if absent or (candidate.ego_actions - query.ego_actions - {"unknown"}):
            differences.append(
                ReuseDifference(
                    "ego_action",
                    ",".join(sorted(query.ego_actions)),
                    ",".join(sorted(candidate.ego_actions)),
                    "verify ego behavior"
                    if "unknown" in candidate.ego_actions
                    else "modify ego behavior",
                    cost=policy.COST_BEHAVIOR,
                    verified="unknown" not in candidate.ego_actions,
                )
            )
    values = bundle_parameters(asset.bundle, initial_only=True)
    visibility = asset.bundle.scenario.environment.get("fog_visibility_m")
    if isinstance(visibility, (float, int)):
        values["fog_visibility_m"] = (float(visibility),)
    # A parameter the XML reader cannot find is unverified rather than a known change.
    differences.extend(
        replace(difference, verified=difference.candidate != "not extracted")
        for difference in parameter_differences(query.parameters, values)
    )
    if not any(item.speed_kph is not None for item in query.participant_signatures):
        # Speeds not bound to participants (older revisions) are compared as a multiset.
        differences.extend(
            target_speed_differences(query.target_speeds_kph, candidate.target_speeds_kph,
                                     len(query.participant_signatures))
        )
    differences.extend(environment_differences(query.environment, candidate.environment))
    return tuple(differences)


def _conflicts(expected: ParticipantSignature, actual: ParticipantSignature) -> tuple[int, bool, int]:
    """(known identity conflicts, known behavior conflict, unknown components of `actual`).

    An unknown component never proves a conflict. A stop satisfies a requested speed change.
    """
    identity = zip(
        (expected.kind, expected.bearing, expected.facing),
        (actual.kind, actual.bearing, actual.facing),
    )
    mismatches = sum(left != right and "unknown" not in {left, right} for left, right in identity)
    known_actions = set(expected.actions) - {"unknown"}
    absent = known_actions - set(actual.actions)
    if set(actual.actions) == {"stop"} and known_actions == {"speed_change"}:
        absent = set()
    unknowns = sum(item == "unknown" for item in (actual.kind, actual.bearing, actual.facing)) + (
        "unknown" in actual.actions
    )
    return mismatches, bool(absent and "unknown" not in actual.actions), unknowns


def _pair_differences(expected: ParticipantSignature, actual: ParticipantSignature | None) -> list[ReuseDifference]:
    """What it takes to make candidate participant `actual` (None: absent) into the requested one."""
    signature = expected.key()
    if actual is None:
        return [ReuseDifference("participant_signature", signature, "missing", "add participant", True,
                                policy.COST_PARTICIPANT)]
    result = []
    mismatch, action_mismatch, _ = _conflicts(expected, actual)
    if mismatch:
        result.append(ReuseDifference("participant_signature", signature, actual.key(),
                                      "rebuild participant interaction", True, policy.COST_PARTICIPANT))
    elif action_mismatch:
        result.append(ReuseDifference("action", signature, actual.key(), "modify participant behavior",
                                      cost=policy.COST_BEHAVIOR))
    else:
        extra_actions = set(actual.actions) - set(expected.actions) - {"unknown"}
        if set(actual.actions) == {"stop"} and set(expected.actions) == {"speed_change"}:
            extra_actions = set()
        if extra_actions:
            result.append(ReuseDifference("action", signature, actual.key(), "remove additional participant behavior",
                                          cost=policy.COST_BEHAVIOR))
    if not mismatch and (expected.has_unknown or actual.has_unknown):
        result.append(ReuseDifference("participant_topology", signature, actual.key(), "verify participant facts",
                                      cost=policy.COST_VERIFY_PARTICIPANT, verified=False))
    if not mismatch and expected.speed_kph is not None:
        result.extend(_speed_difference(expected, actual))
    return result


def _speed_difference(expected: ParticipantSignature, actual: ParticipantSignature) -> list[ReuseDifference]:
    requested = f"{expected.key()} speed={expected.speed_kph:g} km/h"
    if actual.speed_kph is None:
        return [ReuseDifference("parameter", requested, "not extracted", "set participant initial speed",
                                cost=policy.COST_PARAMETER, verified=False)]
    if abs(actual.speed_kph - expected.speed_kph) > policy.TARGET_SPEED_TOLERANCE_KPH:
        return [ReuseDifference("parameter", requested, f"speed={actual.speed_kph:g} km/h",
                                "set participant initial speed", cost=policy.COST_PARAMETER)]
    return []


def _extra_difference(actual: ParticipantSignature) -> ReuseDifference:
    return ReuseDifference("participant_signature", "no additional participant", actual.key(),
                           "remove extra participant", cost=policy.COST_EXTRA_PARTICIPANT)


def _score(differences: list[ReuseDifference]) -> tuple[int, float, int]:
    """The ranking key of a set of differences (blocking count, then change cost), then unverified count."""
    return (sum(item.blocking for item in differences), sum(item.cost for item in differences),
            sum(not item.verified for item in differences))


def _pair(
    requested: tuple[ParticipantSignature, ...], candidates: tuple[ParticipantSignature, ...]
) -> list[int | None]:
    """The candidate index paired with each requested participant (None: none left).

    Pairing is one-to-one, so participant multiplicity counts. Among all pairings it picks the one
    whose differences rank best, the same order candidates are ranked by.
    """
    table = [[_score(_pair_differences(expected, actual)) for actual in candidates] for expected in requested]
    absent = [_score(_pair_differences(expected, None)) for expected in requested]
    extra = [_score([_extra_difference(actual)]) for actual in candidates]
    if max(len(requested), len(candidates)) <= ENUMERATION_LIMIT:
        return _enumerate(table, absent, extra)
    return _assign(table, absent, extra)



def _enumerate(table, absent, extra) -> list[int | None]:
    slots = [*range(len(extra)), *[None] * max(0, len(absent) - len(extra))]

    def rank(pairing):
        scores = [table[row][column] if column is not None else absent[row] for row, column in enumerate(pairing)]
        scores += [extra[column] for column in set(range(len(extra))) - set(pairing)]
        blocking, cost, unverified = (sum(values) for values in zip(*scores)) if scores else (0, 0, 0)
        # Ties keep candidates in key order, so the result does not depend on enumeration order.
        return blocking, round(cost, 6), unverified, [len(extra) if column is None else column for column in pairing]

    return list(min(set(permutations(slots, len(absent))), key=rank))


def _assign(table, absent, extra) -> list[int | None]:
    """Minimum-cost assignment (Hungarian method) on the scores folded into one exact integer."""

    def weight(score):
        blocking, cost, unverified = score
        return blocking * 10**9 + round(cost * 1000) * 100 + unverified

    rows, columns = len(absent), len(extra)
    size = max(rows, columns)
    matrix = [[weight(table[row][column]) if row < rows and column < columns
               else weight(absent[row]) if row < rows
               else weight(extra[column]) if column < columns else 0
               for column in range(size)] for row in range(size)]
    paired = _hungarian(matrix)
    return [paired[row] if paired[row] < columns else None for row in range(rows)]


def _hungarian(matrix: list[list[int]]) -> list[int]:
    """Column assigned to each row of a square cost matrix, minimizing the total (O(n^3) with potentials)."""
    size = len(matrix)
    row_potential, column_potential = [0] * (size + 1), [0] * (size + 1)
    owner = [0] * (size + 1)  # owner[column] = row (1-based; 0 = free)
    for row in range(1, size + 1):
        owner[0] = row
        column = 0
        best = [None] * (size + 1)
        previous = [0] * (size + 1)
        used = [False] * (size + 1)
        while owner[column]:
            used[column] = True
            current, delta, chosen = owner[column], None, 0
            for candidate in range(1, size + 1):
                if used[candidate]:
                    continue
                reduced = matrix[current - 1][candidate - 1] - row_potential[current] - column_potential[candidate]
                if best[candidate] is None or reduced < best[candidate]:
                    best[candidate], previous[candidate] = reduced, column
                if delta is None or best[candidate] < delta:
                    delta, chosen = best[candidate], candidate
            for candidate in range(size + 1):
                if used[candidate]:
                    row_potential[owner[candidate]] += delta
                    column_potential[candidate] -= delta
                else:
                    best[candidate] -= delta
            column = chosen
        while column:
            owner[column] = owner[previous[column]]
            column = previous[column]
    assigned = [0] * size
    for column in range(1, size + 1):
        assigned[owner[column] - 1] = column - 1
    return assigned


def participant_differences(
    requested: tuple[ParticipantSignature, ...], candidates: tuple[ParticipantSignature, ...]
) -> list[ReuseDifference]:
    pairing = _pair(requested, candidates)
    result = []
    for expected, column in zip(requested, pairing):
        result.extend(_pair_differences(expected, candidates[column] if column is not None else None))
    paired = set(pairing)
    result.extend(_extra_difference(actual) for column, actual in enumerate(candidates) if column not in paired)
    return result
