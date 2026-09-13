from __future__ import annotations

from dataclasses import dataclass

from .catalog import OpenXAsset
from .models import ParseBundle
from .scene_package import RetrievalQuery, canonical_features


@dataclass(frozen=True, slots=True)
class ReuseDifference:
    category: str
    requested: str
    candidate: str
    action: str


def compare_query_to_asset(
    query: RetrievalQuery,
    asset: OpenXAsset,
) -> tuple[ReuseDifference, ...]:
    entities, actions, triggers, road_features = bundle_features(asset.bundle)
    differences: list[ReuseDifference] = []
    differences.extend(_missing("entity", query.entity_kinds, entities, "add or replace entity"))
    differences.extend(_missing("action", query.action_kinds, actions, "modify storyboard action"))
    differences.extend(_missing("trigger", query.trigger_kinds, triggers, "modify start trigger"))
    differences.extend(_missing("road", query.road_features, road_features, "select or modify OpenDRIVE"))
    differences.extend(
        ReuseDifference("parameter", name, "not extracted", "verify and set parameter in XOSC")
        for name, _ in query.parameters
    )
    return tuple(differences)


def bundle_features(bundle: ParseBundle) -> tuple[set[str], set[str], set[str], set[str]]:
    scenario = bundle.scenario
    road = bundle.road
    candidate_text = " ".join(
        [
            scenario.name or "",
            scenario.description or "",
            " ".join(item.kind for item in scenario.entities),
            " ".join(filter(None, (item.category for item in scenario.entities))),
            " ".join(item.kind for item in scenario.actions),
            " ".join(item.kind for item in scenario.triggers),
        ]
    )
    entities, actions, triggers, _ = canonical_features(candidate_text)
    road_features: set[str] = set()
    if "line" in road.geometry_types:
        road_features.add("straight")
    if set(road.geometry_types) & {"arc", "spiral", "poly3", "paramPoly3"}:
        road_features.add("curve")
    if road.junction_count:
        road_features.add("junction")
    return entities, actions, triggers, road_features


def _missing(
    category: str,
    requested: frozenset[str],
    candidate: set[str],
    action: str,
) -> list[ReuseDifference]:
    return [
        ReuseDifference(category, value, "missing", action)
        for value in sorted(requested - candidate)
    ]
