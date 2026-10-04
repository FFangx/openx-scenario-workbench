"""Comparison of a typed requirement (an approved PDF scene structure) with an asset's structure."""

from __future__ import annotations

from dataclasses import replace

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
    differences.extend(
        target_speed_differences(query.target_speeds_kph, candidate.target_speeds_kph)
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


def _pair(
    requested: tuple[ParticipantSignature, ...], candidates: tuple[ParticipantSignature, ...]
) -> tuple[list[tuple[ParticipantSignature, ParticipantSignature | None]], list[ParticipantSignature]]:
    """One-to-one pairing, preserving participant multiplicity; returns the pairs and the unpaired candidates."""
    remaining = list(candidates)
    pairs = []
    for expected in requested:
        if not remaining:
            pairs.append((expected, None))
            continue
        selected = min(remaining, key=lambda actual: (*_conflicts(expected, actual), actual.key()))
        remaining.remove(selected)
        pairs.append((expected, selected))
    return pairs, remaining


def participant_differences(
    requested: tuple[ParticipantSignature, ...], candidates: tuple[ParticipantSignature, ...]
) -> list[ReuseDifference]:
    pairs, extra = _pair(requested, candidates)
    result = []
    for expected, actual in pairs:
        signature = expected.key()
        if actual is None:
            result.append(
                ReuseDifference(
                    "participant_signature", signature, "missing", "add participant", True,
                    policy.COST_PARTICIPANT,
                )
            )
            continue
        mismatch, action_mismatch, _ = _conflicts(expected, actual)
        if mismatch:
            result.append(
                ReuseDifference(
                    "participant_signature", signature, actual.key(), "rebuild participant interaction", True,
                    policy.COST_PARTICIPANT,
                )
            )
        elif action_mismatch:
            result.append(
                ReuseDifference(
                    "action", signature, actual.key(), "modify participant behavior", cost=policy.COST_BEHAVIOR
                )
            )
        else:
            extra_actions = set(actual.actions) - set(expected.actions) - {"unknown"}
            if set(actual.actions) == {"stop"} and set(expected.actions) == {"speed_change"}:
                extra_actions = set()
            if extra_actions:
                result.append(
                    ReuseDifference(
                        "action", signature, actual.key(), "remove additional participant behavior",
                        cost=policy.COST_BEHAVIOR,
                    )
                )
        if not mismatch and (expected.has_unknown or actual.has_unknown):
            result.append(
                ReuseDifference(
                    "participant_topology", signature, actual.key(), "verify participant facts",
                    cost=policy.COST_VERIFY_PARTICIPANT, verified=False,
                )
            )
    for actual in extra:
        result.append(
            ReuseDifference(
                "participant_signature", "no additional participant", actual.key(), "remove extra participant",
                cost=policy.COST_EXTRA_PARTICIPANT,
            )
        )
    return result
