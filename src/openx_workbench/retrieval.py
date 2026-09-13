from __future__ import annotations

import hashlib
import math
import re
from collections import Counter
from dataclasses import dataclass

from .catalog import OpenXAsset
from .models import ParseBundle
from .reuse import ReuseDifference, bundle_features, compare_query_to_asset
from .scene_package import RetrievalQuery


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]+|[\u4e00-\u9fff]{1,4}|\d+(?:\.\d+)?")


@dataclass(frozen=True, slots=True)
class RetrievalResult:
    asset: OpenXAsset
    score: float
    vector_score: float
    scenario_score: float
    road_score: float
    reuse_level: str
    reasons: tuple[str, ...]
    differences: tuple[ReuseDifference, ...] = ()


def asset_text(asset: OpenXAsset) -> str:
    scenario = asset.bundle.scenario
    road = asset.bundle.road
    parts = [
        asset.title,
        scenario.description or "",
        " ".join(entity.name for entity in scenario.entities),
        " ".join(filter(None, (entity.category for entity in scenario.entities))),
        " ".join(action.kind for action in scenario.actions),
        " ".join(trigger.kind for trigger in scenario.triggers),
        f"roads {len(road.road_ids)} length {road.total_length} lanes {road.lane_count}",
        " ".join(f"lane_{name} {count}" for name, count in road.lane_types.items()),
        " ".join(f"geometry_{name} {count}" for name, count in road.geometry_types.items()),
        f"junctions {road.junction_count} signals {road.signal_count} objects {road.object_count}",
    ]
    return " ".join(parts)


class HashingEncoder:
    """Small dependency-free vector encoder for the local MVP index."""

    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions

    def encode(self, text: str) -> tuple[float, ...]:
        counts: Counter[int] = Counter()
        for token in TOKEN_RE.findall(text.casefold()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            counts[int.from_bytes(digest) % self.dimensions] += 1
        norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
        return tuple(counts.get(index, 0) / norm for index in range(self.dimensions))


class OpenXIndex:
    def __init__(self, assets: list[OpenXAsset], encoder: HashingEncoder | None = None) -> None:
        self.assets = assets
        self.encoder = encoder or HashingEncoder()
        self.vectors = [self.encoder.encode(asset_text(asset)) for asset in assets]

    def search(
        self,
        text: str,
        query_bundle: ParseBundle | None = None,
        query: RetrievalQuery | None = None,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        if query is None and query_bundle is not None:
            query = bundle_to_query(query_bundle)
        if query is not None:
            text = query.text
        query_vector = self.encoder.encode(text)
        ranked: list[RetrievalResult] = []

        for asset, vector in zip(self.assets, self.vectors):
            vector_score = sum(left * right for left, right in zip(query_vector, vector))
            scenario_score = _scenario_query_score(query, asset.bundle) if query else 0.0
            road_score = _road_query_score(query, asset.bundle) if query else 0.0
            if query:
                score = 0.55 * vector_score + 0.30 * scenario_score + 0.15 * road_score
            else:
                score = vector_score
            score = round(max(0.0, min(1.0, score)), 4)
            differences = compare_query_to_asset(query, asset) if query else ()
            reuse_level = _reuse_level(score, structured=query is not None)
            if reuse_level == "direct" and differences:
                reuse_level = "modify"
            ranked.append(
                RetrievalResult(
                    asset=asset,
                    score=score,
                    vector_score=round(vector_score, 4),
                    scenario_score=round(scenario_score, 4),
                    road_score=round(road_score, 4),
                    reuse_level=reuse_level,
                    reasons=_reasons(query, asset.bundle),
                    differences=differences,
                )
            )
        return sorted(ranked, key=lambda item: item.score, reverse=True)[:top_k]


def bundle_query_text(bundle: ParseBundle) -> str:
    scenario = bundle.scenario
    return " ".join(
        [
            scenario.name or "",
            scenario.description or "",
            " ".join(entity.name for entity in scenario.entities),
            " ".join(action.kind for action in scenario.actions),
            " ".join(trigger.kind for trigger in scenario.triggers),
        ]
    )


def bundle_to_query(bundle: ParseBundle) -> RetrievalQuery:
    text = bundle_query_text(bundle)
    entities, actions, triggers, road_terms = bundle_features(bundle)
    return RetrievalQuery(
        text=text,
        entity_kinds=frozenset(entities),
        action_kinds=frozenset(actions),
        trigger_kinds=frozenset(triggers),
        road_features=frozenset(road_terms),
    )


def _overlap(left: set[str], right: set[str]) -> float:
    if not left:
        return 0.0
    return len(left & right) / len(left)


def _scenario_query_score(query: RetrievalQuery, candidate: ParseBundle) -> float:
    entities, actions, triggers, _ = bundle_features(candidate)
    comparisons = [
        _overlap(set(query.entity_kinds), entities),
        _overlap(set(query.action_kinds), actions),
        _overlap(set(query.trigger_kinds), triggers),
    ]
    active = [score for requested, score in zip(
        (query.entity_kinds, query.action_kinds, query.trigger_kinds), comparisons
    ) if requested]
    return sum(active) / len(active) if active else 0.0


def _road_query_score(query: RetrievalQuery, candidate: ParseBundle) -> float:
    if not query.road_features:
        return 0.0
    _, _, _, candidate_features = bundle_features(candidate)
    return _overlap(set(query.road_features), candidate_features)


def _reuse_level(score: float, structured: bool) -> str:
    direct_threshold = 0.8 if structured else 0.55
    modify_threshold = 0.45 if structured else 0.25
    if score >= direct_threshold:
        return "direct"
    if score >= modify_threshold:
        return "modify"
    return "new_build"


def _reasons(query: RetrievalQuery | None, candidate: ParseBundle) -> tuple[str, ...]:
    if query is None:
        return ("vector_text_match",)
    reasons = []
    if _scenario_query_score(query, candidate) >= 0.66:
        reasons.append("scenario_structure_match")
    if _road_query_score(query, candidate) >= 0.75:
        reasons.append("road_structure_match")
    return tuple(reasons or ["partial_match"])
