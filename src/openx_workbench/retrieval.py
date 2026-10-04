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
from . import reuse_policy as policy
from .reuse import change_cost, classify_reuse_level, compare_query_to_asset
from .reuse_differences import ReuseDifference
from .reuse_facts import (
    asset_structure_query,
    bundle_features,
    bundle_participant_relations,
    bundle_participant_signatures,
    bundle_scenario_families,
)
from .scene_package import RetrievalQuery, query_structure_text


TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_]+|[\u4e00-\u9fff]{1,4}|\d+(?:\.\d+)?")
DEFAULT_BGE_MODEL = "BAAI/bge-m3"
INDEX_SCHEMA_VERSION = 2


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
    review_kind: str = ""

    @property
    def standard_checks(self):
        from .schema_validation import standard_gate
        return standard_gate(self.asset.bundle.validation)

    @property
    def confirmation_level(self):
        return "review" if self.reuse_level == "direct" and not self.standard_checks["passed"] else self.reuse_level

    @property
    def confirmation_review_kind(self):
        return "standards" if self.confirmation_level != self.reuse_level else self.review_kind


def review_kind(query: RetrievalQuery | None, candidate: RetrievalQuery) -> str:
    """Describe evidence coverage without changing the four verdicts or ranking."""
    if query is None:
        return "recall"
    if query.structured:
        participants_known = bool(query.participant_signatures and candidate.participant_signatures) and not any(
            signature.has_unknown for signature in (*query.participant_signatures, *candidate.participant_signatures)
        )
        ego_known = bool(query.ego_actions and candidate.ego_actions) and "unknown" not in (
            query.ego_actions | candidate.ego_actions
        )
        core_known = participants_known if query.participant_signatures else ego_known
        return "partial" if core_known else "undecidable"
    return "partial" if query.entity_kinds or query.action_kinds else "undecidable"


def asset_text(asset: OpenXAsset) -> str:
    scenario = asset.bundle.scenario
    road = asset.bundle.road
    parts = [
        asset.title,
        " ".join(str(value) for _, value in sorted(asset.classification.items())),
        scenario.description or "",
        " ".join(entity.name for entity in scenario.entities),
        " ".join(filter(None, (entity.category for entity in scenario.entities))),
        " ".join(action.kind for action in scenario.actions),
        " ".join(trigger.kind for trigger in scenario.triggers),
        f"roads {len(road.road_ids)} length {road.total_length} lanes {road.lane_count}",
        " ".join(f"lane_{name} {count}" for name, count in road.lane_types.items()),
        " ".join(
            f"geometry_{name} {count}" for name, count in road.geometry_types.items()
        ),
        f"junctions {road.junction_count} signals {road.signal_count} objects {road.object_count}",
    ]
    return " ".join(parts)


def asset_structure_text(asset: OpenXAsset) -> str:
    return query_structure_text(asset_structure_query(asset))


def catalog_fingerprint(assets: list[OpenXAsset]) -> str:
    # IDs identify immutable files; reviewed labels and parser semantics also
    # affect recall and must invalidate both disk and session caches.
    content = [
        (
            asset.asset_id,
            asset_text(asset),
            asset_structure_text(asset),
            {key: value for key, value in asset.bundle.to_dict().items() if key != "validation"},
            asset.bundle.validation,
        )
        for asset in assets
    ]
    return hashlib.sha256(
        json.dumps(content, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


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
        except OSError as exc:
            raise RuntimeError(
                "BGE-M3 runtime could not load. Check the PyTorch installation; see docs/REUSE_ALIGNMENT.md."
            ) from exc
        try:
            self.model = SentenceTransformer(model_name)
        except (OSError, RuntimeError) as exc:
            raise RuntimeError("BGE-M3 could not load. Check its local cache or download connection. "
                               "You can explicitly select the Hashing baseline in retrieval settings.") from exc
        self.encoder_id = f"sentence-transformers:{model_name}"

    def encode(self, text: str) -> tuple[float, ...]:
        return self.encode_many([text])[0]

    def encode_many(self, texts: list[str]) -> list[tuple[float, ...]]:
        if not texts:
            return []
        unique_texts = list(dict.fromkeys(texts))
        encoded = {}
        # M3 pads a batch to its longest input. Real SIM assets can contain
        # thousands of tokens; keep those out of the short-text batch so one
        # complex case cannot exhaust desktop memory. Preserve complete text.
        for lower, upper, batch_size in ((0, 512, 64), (512, 2048, 8), (2048, math.inf, 1)):
            group = [text for text in unique_texts if lower < len(text) <= upper or (lower == 0 and not text)]
            if not group:
                continue
            vectors = self.model.encode(group, batch_size=batch_size,
                                        normalize_embeddings=True, show_progress_bar=False)
            if len(vectors) != len(group):
                raise ValueError("The embedding model returned an unexpected vector count.")
            encoded.update({text: tuple(float(value) for value in vector)
                            for text, vector in zip(group, vectors)})
        return [encoded[text] for text in texts]


def build_encoder(name: str) -> TextEncoder:
    if name == "hashing":
        return HashingEncoder()
    if name == "bge":
        return SentenceTransformerEncoder()
    raise ValueError(f"Unknown encoder: {name}")


class OpenXIndex:
    def __init__(
        self, assets: list[OpenXAsset], encoder: TextEncoder | None = None
    ) -> None:
        self.assets = assets
        self.encoder = encoder or HashingEncoder()
        self.structures = [asset_structure_query(asset) for asset in assets]
        self.fingerprint = catalog_fingerprint(assets)
        self.vectors = self.encoder.encode_many([asset_text(asset) for asset in assets])
        self.structure_vectors = self.encoder.encode_many(
            [query_structure_text(structure) for structure in self.structures]
        )
        self._build_recall()

    def _build_recall(self) -> None:
        if (
            self.vectors
            and self.structure_vectors
            and len(self.vectors[0]) != len(self.structure_vectors[0])
        ):
            raise ValueError("Name and structure vector dimensions differ.")
        self._faiss = self._vector_index(self.vectors)
        self._structure_faiss = self._vector_index(self.structure_vectors)
        self.recall_backend = "faiss-flat-ip" if self._faiss is not None else "exact"

    def _vector_index(self, vectors):
        if not vectors:
            if self.assets:
                raise ValueError("The stored vectors do not match the asset catalog.")
            return None
        dimensions = len(vectors[0])
        if (
            not dimensions
            or len(vectors) != len(self.assets)
            or any(
                len(row) != dimensions or any(not math.isfinite(value) for value in row)
                for row in vectors
            )
        ):
            raise ValueError("The stored vectors do not match the asset catalog.")
        try:
            import faiss
            import numpy as np
        except ImportError:
            return None
        matrix = np.asarray(vectors, dtype="float32")
        if matrix.ndim != 2 or matrix.shape[0] != len(self.assets):
            raise ValueError("The stored vectors do not match the asset catalog.")
        index = faiss.IndexFlatIP(matrix.shape[1])
        index.add(matrix)
        return index

    def recall(
        self, query_vector: tuple[float, ...], count: int, *, structure=False
    ) -> list[tuple[int, float]]:
        vectors = self.structure_vectors if structure else self.vectors
        index = self._structure_faiss if structure else self._faiss
        if vectors and len(query_vector) != len(vectors[0]):
            raise ValueError("Query and index vector dimensions differ.")
        if index is not None:
            import numpy as np

            vector = np.asarray([query_vector], dtype="float32")
            scores, indices = index.search(vector, count)
            return [
                (int(index), float(score))
                for index, score in zip(indices[0], scores[0])
                if index >= 0
            ]
        ranked = [
            (index, sum(left * right for left, right in zip(query_vector, vector)))
            for index, vector in enumerate(vectors)
        ]
        return sorted(ranked, key=lambda item: (-item[1], item[0]))[:count]

    def save(self, path: Path) -> None:
        if catalog_fingerprint(self.assets) != self.fingerprint:
            raise ValueError(
                "The asset facts or classifications changed; rebuild the index."
            )
        payload = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "encoder_id": self.encoder.encoder_id,
            "asset_ids": [asset.asset_id for asset in self.assets],
            "catalog_fingerprint": self.fingerprint,
            "vectors": self.vectors,
            "structure_vectors": self.structure_vectors,
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
        if payload.get("catalog_fingerprint") != catalog_fingerprint(assets):
            raise ValueError(
                "The asset facts or classifications changed; rebuild the index."
            )
        index = cls.__new__(cls)
        index.assets = assets
        index.encoder = selected_encoder
        index.fingerprint = payload["catalog_fingerprint"]
        index.structures = [asset_structure_query(asset) for asset in assets]
        index.vectors = [
            tuple(float(value) for value in row) for row in payload["vectors"]
        ]
        index.structure_vectors = [
            tuple(float(value) for value in row) for row in payload["structure_vectors"]
        ]
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
        structure_vector = self.encoder.encode(query_structure_text(query)) if query else None
        return self._search_vectors(query_vector, structure_vector, query, top_k)

    def search_many(self, queries: list[RetrievalQuery], top_k: int = 5) -> list[list[RetrievalResult]]:
        if top_k <= 0 or not self.assets:
            return [[] for _ in queries]
        texts = [text for query in queries for text in (query.text, query_structure_text(query))]
        vectors = self.encoder.encode_many(texts)
        if len(vectors) != len(texts):
            raise ValueError("The embedding model returned an unexpected vector count.")
        return [self._search_vectors(vectors[2 * i], vectors[2 * i + 1], query, top_k)
                for i, query in enumerate(queries)]

    def _search_vectors(self, query_vector, structure_vector, query, top_k):
        ranked: list[RetrievalResult] = []
        recall_size = (
            min(len(self.assets), max(policy.RECALL_MIN, top_k * policy.RECALL_FACTOR))
            if query
            else min(len(self.assets), top_k)
        )
        recalled = dict(self.recall(query_vector, recall_size))
        if query:
            for index, _ in self.recall(
                structure_vector, min(len(self.assets), policy.STRUCTURE_RECALL), structure=True
            ):
                if index not in recalled:
                    recalled[index] = sum(
                        left * right
                        for left, right in zip(query_vector, self.vectors[index])
                    )
        differences_by_index = {}
        if query:
            # Structural compatibility is the primary ordering contract. Include
            # its best buckets even when semantic recall misses them, keeping
            # ties so semantic scores can still decide within a structural bucket.
            differences_by_index = {
                index: compare_query_to_asset(
                    query, asset, candidate_structure=self.structures[index]
                )
                for index, asset in enumerate(self.assets)
            }
            structural_keys = {
                index: (
                    sum(item.blocking for item in differences),
                    change_cost(differences),
                )
                for index, differences in differences_by_index.items()
            }
            cutoff = sorted(structural_keys.values())[min(top_k, len(self.assets)) - 1]
            for index, key in structural_keys.items():
                if key <= cutoff and index not in recalled:
                    recalled[index] = sum(
                        left * right
                        for left, right in zip(query_vector, self.vectors[index])
                    )
        for asset_index, vector_score in recalled.items():
            asset = self.assets[asset_index]
            scenario_score = (
                _scenario_query_score(query, asset.bundle, self.structures[asset_index])
                if query
                else 0.0
            )
            road_score = _road_query_score(query, asset.bundle) if query else 0.0
            if query:
                score = (
                    policy.WEIGHT_SEMANTIC * vector_score
                    + policy.WEIGHT_SCENARIO * scenario_score
                    + policy.WEIGHT_ROAD * road_score
                )
            else:
                score = vector_score
            score = round(max(0.0, min(1.0, score)), 4)
            differences = differences_by_index[asset_index] if query else ()
            reuse_level = (
                classify_reuse_level(differences) if query is not None else "review"
            )
            ranked.append(
                RetrievalResult(
                    asset=asset,
                    score=score,
                    vector_score=round(vector_score, 4),
                    scenario_score=round(scenario_score, 4),
                    road_score=round(road_score, 4),
                    reuse_level=reuse_level,
                    reasons=_reasons(query, asset.bundle, self.structures[asset_index]),
                    differences=differences,
                    review_kind=review_kind(query, self.structures[asset_index]) if reuse_level == "review" else "",
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
        participant_signatures=bundle_participant_signatures(bundle),
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


def _scenario_query_score(
    query: RetrievalQuery,
    candidate: ParseBundle,
    structure: RetrievalQuery | None = None,
) -> float:
    if query.structured and structure is not None:
        comparisons = [
            (set(query.participant_signatures), set(structure.participant_signatures)),
            (set(query.ego_actions), set(structure.ego_actions)),
            (set(query.trigger_kinds), set(structure.trigger_kinds)),
            (
                {query.tested_function} if query.tested_function else set(),
                {structure.tested_function} if structure.tested_function else set(),
            ),
        ]
        active = [
            _overlap(requested, actual)
            for requested, actual in comparisons
            if requested
        ]
        return sum(active) / len(active) if active else 0.0
    entities, actions, triggers, _ = bundle_features(candidate)
    families = bundle_scenario_families(candidate)
    participant_signatures = set(bundle_participant_signatures(candidate))
    relations = bundle_participant_relations(candidate)
    comparisons = [
        _overlap(set(query.scenario_families), families),
        _overlap(set(query.participant_signatures), participant_signatures),
        _overlap(set(query.participant_relations), relations),
        _overlap(set(query.entity_kinds), entities),
        _overlap(set(query.action_kinds), actions),
        _overlap(set(query.trigger_kinds), triggers),
    ]
    active = [
        score
        for requested, score in zip(
            (
                query.scenario_families,
                query.participant_signatures,
                query.participant_relations,
                query.entity_kinds,
                query.action_kinds,
                query.trigger_kinds,
            ),
            comparisons,
        )
        if requested
    ]
    return sum(active) / len(active) if active else 0.0


def _road_query_score(query: RetrievalQuery, candidate: ParseBundle) -> float:
    if not query.road_features:
        return 0.0
    _, _, _, candidate_features = bundle_features(candidate)
    return _overlap(set(query.road_features), candidate_features)


def _reasons(
    query: RetrievalQuery | None,
    candidate: ParseBundle,
    structure: RetrievalQuery | None = None,
) -> tuple[str, ...]:
    if query is None:
        return ("vector_text_match",)
    reasons = []
    if _scenario_query_score(query, candidate, structure) >= policy.REASON_SCENARIO_MIN:
        reasons.append("scenario_structure_match")
    if _road_query_score(query, candidate) >= policy.REASON_ROAD_MIN:
        reasons.append("road_structure_match")
    return tuple(reasons or ["partial_match"])
