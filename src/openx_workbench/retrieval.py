from __future__ import annotations

import hashlib
import json
import math
import re
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .catalog import OpenXAsset
from .models import ParseBundle
from .reuse import (
    ReuseDifference,
    bundle_features,
    bundle_participant_relations,
    bundle_participant_signatures,
    bundle_scenario_families,
    change_cost,
    classify_reuse_level,
    compare_query_to_asset,
)
from .scene_package import RetrievalQuery


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]+|[\u4e00-\u9fff]{1,4}|\d+(?:\.\d+)?")
DEFAULT_BGE_MODEL = "BAAI/bge-small-zh-v1.5"
INDEX_SCHEMA_VERSION = 1


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
    estimated_change_cost: float | None = None


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
        self.encoder_id = f"hashing-blake2b-{dimensions}"

    def encode(self, text: str) -> tuple[float, ...]:
        counts: Counter[int] = Counter()
        for token in TOKEN_RE.findall(text.casefold()):
            digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8).digest()
            counts[int.from_bytes(digest, byteorder="big") % self.dimensions] += 1
        norm = math.sqrt(sum(value * value for value in counts.values())) or 1.0
        return tuple(counts.get(index, 0) / norm for index in range(self.dimensions))

    def encode_many(self, texts: list[str]) -> list[tuple[float, ...]]:
        return [self.encode(text) for text in texts]


class TextEncoder(Protocol):
    encoder_id: str

    def encode(self, text: str) -> tuple[float, ...]: ...

    def encode_many(self, texts: list[str]) -> list[tuple[float, ...]]: ...


class SentenceTransformerEncoder:
    def __init__(self, model_name: str = DEFAULT_BGE_MODEL) -> None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise RuntimeError(
                "Semantic retrieval requires: pip install 'openx-scenario-workbench[semantic]'"
            ) from exc
        self.model = SentenceTransformer(model_name)
        self.encoder_id = f"sentence-transformers:{model_name}"

    def encode(self, text: str) -> tuple[float, ...]:
        return self.encode_many([text])[0]

    def encode_many(self, texts: list[str]) -> list[tuple[float, ...]]:
        vectors = self.model.encode(
            texts,
            batch_size=64,
            normalize_embeddings=True,
            show_progress_bar=False,
        )
        return [tuple(float(value) for value in vector) for vector in vectors]


def build_encoder(name: str) -> TextEncoder:
    if name == "hashing":
        return HashingEncoder()
    if name == "bge":
        return SentenceTransformerEncoder()
    raise ValueError(f"Unknown encoder: {name}")


class OpenXIndex:
    def __init__(self, assets: list[OpenXAsset], encoder: TextEncoder | None = None) -> None:
        self.assets = assets
        self.encoder = encoder or HashingEncoder()
        self.vectors = self.encoder.encode_many([asset_text(asset) for asset in assets])
        self._build_recall()

    def _build_recall(self) -> None:
        self._faiss = None
        self.recall_backend = "exact"
        if not self.vectors:
            return
        try:
            import faiss
            import numpy as np
        except ImportError:
            return
        matrix = np.asarray(self.vectors, dtype="float32")
        if matrix.ndim != 2 or matrix.shape[0] != len(self.assets):
            raise ValueError("The stored vectors do not match the asset catalog.")
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        self._faiss = index
        self.recall_backend = "faiss-flat-ip"

    def _recall(self, query_vector: tuple[float, ...], count: int) -> list[tuple[int, float]]:
        if self._faiss is not None:
            import numpy as np
            vector = np.asarray([query_vector], dtype="float32")
            scores, indices = self._faiss.search(vector, count)
            return [(int(index), float(score)) for index, score in zip(indices[0], scores[0])
                    if index >= 0]
        ranked = [(index, sum(left * right for left, right in zip(query_vector, vector)))
                  for index, vector in enumerate(self.vectors)]
        return sorted(ranked, key=lambda item: (-item[1], item[0]))[:count]

    def save(self, path: Path) -> None:
        payload = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "encoder_id": self.encoder.encoder_id,
            "asset_ids": [asset.asset_id for asset in self.assets],
            "vectors": self.vectors,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, separators=(",", ":")), encoding="utf-8")

    @classmethod
    def load(
        cls,
        path: Path,
        assets: list[OpenXAsset],
        encoder: TextEncoder | None = None,
    ) -> OpenXIndex:
        selected_encoder = encoder or HashingEncoder()
        payload = json.loads(path.read_text(encoding="utf-8"))
        if payload.get("schema_version") != INDEX_SCHEMA_VERSION:
            raise ValueError("Unsupported index schema version.")
        if payload.get("encoder_id") != selected_encoder.encoder_id:
            raise ValueError("The saved index uses a different encoder.")
        if payload.get("asset_ids") != [asset.asset_id for asset in assets]:
            raise ValueError("The asset catalog changed; rebuild the index.")
        index = cls.__new__(cls)
        index.assets = assets
        index.encoder = selected_encoder
        index.vectors = [tuple(float(value) for value in row) for row in payload["vectors"]]
        index._build_recall()
        return index

    def search(
        self,
        text: str,
        query_bundle: ParseBundle | None = None,
        query: RetrievalQuery | None = None,
        top_k: int = 5,
    ) -> list[RetrievalResult]:
        if top_k <= 0 or not self.assets:
            return []
        if query is None and query_bundle is not None:
            query = bundle_to_query(query_bundle)
        if query is not None:
            text = query.text
        query_vector = self.encoder.encode(text)
        ranked: list[RetrievalResult] = []
        recall_size = min(len(self.assets), max(100, top_k * 20)) if query else min(len(self.assets), top_k)
        recalled = dict(self._recall(query_vector, recall_size))
        differences_by_index = {}
        if query:
            # Structural compatibility is the primary ordering contract. Include
            # its best buckets even when semantic recall misses them, keeping
            # ties so semantic scores can still decide within a structural bucket.
            differences_by_index = {index: compare_query_to_asset(query, asset)
                                    for index, asset in enumerate(self.assets)}
            structural_keys = {index: (sum(item.blocking for item in differences), change_cost(differences))
                               for index, differences in differences_by_index.items()}
            cutoff = sorted(structural_keys.values())[min(top_k, len(self.assets)) - 1]
            for index, key in structural_keys.items():
                if key <= cutoff and index not in recalled:
                    recalled[index] = sum(left * right for left, right in zip(query_vector, self.vectors[index]))
        for asset_index, vector_score in recalled.items():
            asset = self.assets[asset_index]
            scenario_score = _scenario_query_score(query, asset.bundle) if query else 0.0
            road_score = _road_query_score(query, asset.bundle) if query else 0.0
            if query:
                score = 0.55 * vector_score + 0.30 * scenario_score + 0.15 * road_score
            else:
                score = vector_score
            score = round(max(0.0, min(1.0, score)), 4)
            differences = differences_by_index[asset_index] if query else ()
            reuse_level = classify_reuse_level(differences) if query is not None else "review"
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
                    estimated_change_cost=(
                        change_cost(differences) if query is not None else None
                    ),
                )
            )
        if query is None:
            return sorted(ranked, key=lambda item: item.score, reverse=True)[:top_k]
        return sorted(
            ranked,
            key=lambda item: (
                sum(difference.blocking for difference in item.differences),
                change_cost(item.differences),
                -item.score,
            ),
        )[:top_k]


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
        scenario_families=frozenset(bundle_scenario_families(bundle)),
        participant_signatures=tuple(
            item.key() for item in bundle_participant_signatures(bundle)
        ),
        participant_relations=frozenset(bundle_participant_relations(bundle)),
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
    families = bundle_scenario_families(candidate)
    participant_signatures = {
        item.key() for item in bundle_participant_signatures(candidate)
    }
    relations = bundle_participant_relations(candidate)
    comparisons = [
        _overlap(set(query.scenario_families), families),
        _overlap(set(query.participant_signatures), participant_signatures),
        _overlap(set(query.participant_relations), relations),
        _overlap(set(query.entity_kinds), entities),
        _overlap(set(query.action_kinds), actions),
        _overlap(set(query.trigger_kinds), triggers),
    ]
    active = [score for requested, score in zip(
        (
            query.scenario_families,
            query.participant_signatures,
            query.participant_relations,
            query.entity_kinds,
            query.action_kinds,
            query.trigger_kinds,
        ),
        comparisons,
    ) if requested]
    return sum(active) / len(active) if active else 0.0


def _road_query_score(query: RetrievalQuery, candidate: ParseBundle) -> float:
    if not query.road_features:
        return 0.0
    _, _, _, candidate_features = bundle_features(candidate)
    return _overlap(set(query.road_features), candidate_features)


def _reasons(query: RetrievalQuery | None, candidate: ParseBundle) -> tuple[str, ...]:
    if query is None:
        return ("vector_text_match",)
    reasons = []
    if _scenario_query_score(query, candidate) >= 0.66:
        reasons.append("scenario_structure_match")
    if _road_query_score(query, candidate) >= 0.75:
        reasons.append("road_structure_match")
    return tuple(reasons or ["partial_match"])
