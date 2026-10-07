"""Keyword comparison for requirements without an approved structure (legacy scenes, asset-to-asset).

Requested entities, actions, triggers and road features come from keywords in the
text; participants are compared by exact signature with a coarse fallback.
"""

from __future__ import annotations

from collections import Counter

from . import reuse_policy as policy
from .catalog import OpenXAsset
from .reuse_differences import ReuseDifference, missing, parameter_differences
from .reuse_facts import (
    bundle_features,
    bundle_parameters,
    bundle_participant_relations,
    bundle_participant_signatures,
    bundle_scenario_families,
)
from .scene_package import ParticipantSignature, RetrievalQuery

PARTICIPANT_FAMILIES = {"car_to_car", "car_to_ptw", "car_to_vru"}


def compare_keywords(query: RetrievalQuery, asset: OpenXAsset) -> tuple[ReuseDifference, ...]:
    entities, actions, triggers, road_features = bundle_features(asset.bundle)
    differences: list[ReuseDifference] = [
        ReuseDifference("parameter_resolution", "resolved scenario parameters", item["detail"],
                        "resolve parameter before confirming reuse", verified=False)
        for item in asset.bundle.scenario.parameter_issues
    ]
    candidate_families = bundle_scenario_families(asset.bundle)
    for family in sorted(query.scenario_families - candidate_families):
        # Broad participant classes and maneuver labels are separate dimensions.
        # An absent label is unknown, rather than evidence of incompatibility.
        comparable = {
            item
            for item in candidate_families
            if (item in PARTICIPANT_FAMILIES) == (family in PARTICIPANT_FAMILIES)
        }
        differences.append(
            ReuseDifference(
                "scenario",
                family,
                ", ".join(sorted(comparable)) if comparable else "unknown",
                "build a different scenario family"
                if comparable
                else "verify candidate scenario family",
                blocking=bool(comparable),
                cost=policy.COST_SCENARIO_FAMILY if comparable else policy.COST_UNKNOWN_FAMILY,
            )
        )
    participant_differences = _missing_participants(
        query.participant_signatures, bundle_participant_signatures(asset.bundle)
    )
    differences.extend(participant_differences)
    differences.extend(
        missing("entity", query.entity_kinds, entities, "add or replace entity", blocking=True,
                cost=policy.COST_ENTITY)
    )
    if not any(item.category == "participant_topology" for item in participant_differences):
        differences.extend(
            missing("relation", query.participant_relations, bundle_participant_relations(asset.bundle),
                    "adjust participant placement", cost=policy.COST_RELATION)
        )
    differences.extend(
        missing("action", query.action_kinds, actions, "modify storyboard action", cost=policy.COST_BEHAVIOR)
    )
    differences.extend(
        missing("trigger", query.trigger_kinds, triggers, "modify start trigger", cost=policy.COST_TRIGGER)
    )
    differences.extend(
        missing("road", query.road_features, road_features, "select or modify OpenDRIVE", cost=policy.COST_ROAD)
    )
    differences.extend(parameter_differences(query.parameters, bundle_parameters(asset.bundle)))
    return tuple(differences)


def _missing_participants(
    requested: tuple[ParticipantSignature, ...],
    candidate: tuple[ParticipantSignature, ...],
) -> list[ReuseDifference]:
    remaining = Counter(candidate)
    unresolved: list[ParticipantSignature] = []
    for signature in requested:
        if remaining[signature]:
            remaining[signature] -= 1
        else:
            unresolved.append(signature)

    differences: list[ReuseDifference] = []
    for signature in unresolved:
        fallback = next(
            (
                candidate_signature
                for candidate_signature, count in remaining.items()
                if count
                and _coarse(candidate_signature) == _coarse(signature)
                and (_topology_unknown(signature) or _topology_unknown(candidate_signature))
            ),
            None,
        )
        if fallback is not None:
            remaining[fallback] -= 1
            differences.append(
                ReuseDifference(
                    "participant_topology",
                    signature.key(),
                    fallback.key(),
                    "verify participant placement and facing",
                    cost=policy.COST_VERIFY_PARTICIPANT,
                )
            )
        else:
            differences.append(
                ReuseDifference(
                    "participant_signature",
                    signature.key(),
                    "missing",
                    "rebuild participant interaction",
                    blocking=True,
                    cost=policy.COST_PARTICIPANT,
                )
            )
    return differences


def _coarse(signature: ParticipantSignature) -> tuple[str, tuple[str, ...]]:
    return signature.kind, signature.actions


def _topology_unknown(signature: ParticipantSignature) -> bool:
    return signature.bearing == "unknown" or signature.facing == "unknown"
