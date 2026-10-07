from __future__ import annotations

import hashlib
import json
import math
import re
import statistics
import sys
from array import array
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from .atomic_write import write_bytes
from .catalog import OpenXAsset
from .models import ParseBundle
from . import reuse_policy as policy
from .reuse import change_cost, classify_reuse_level, compare_query_to_asset, figure_cost
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
INDEX_SCHEMA_VERSION = 3  # 3: binary float64 vectors instead of JSON numbers


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
    ]
    if road.file_missing:
        parts += ["road file missing", " ".join(road.inferred_features)]
        return " ".join(parts)
    parts += [
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
        self,
        assets: list[OpenXAsset],
        encoder: TextEncoder | None = None,
        *,
        fingerprint: str | None = None,
    ) -> None:
        """`fingerprint` is the caller's `catalog_fingerprint(assets)`, when it already has it."""
        self.assets = assets
        self.encoder = encoder or HashingEncoder()
        self.structures = [asset_structure_query(asset) for asset in assets]
        self.fingerprint = fingerprint or catalog_fingerprint(assets)
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
        """One header line of JSON, then every vector as little-endian float64 (names first, then structures)."""
        if catalog_fingerprint(self.assets) != self.fingerprint:
            raise ValueError(
                "The asset facts or classifications changed; rebuild the index."
            )
        header = {
            "schema_version": INDEX_SCHEMA_VERSION,
            "encoder_id": self.encoder.encoder_id,
            "asset_ids": [asset.asset_id for asset in self.assets],
            "catalog_fingerprint": self.fingerprint,
            "dimensions": len(self.vectors[0]) if self.vectors else 0,
        }
        values = array("d", (value for rows in (self.vectors, self.structure_vectors) for row in rows for value in row))
        if sys.byteorder == "big":
            values.byteswap()
        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes(path, json.dumps(header, separators=(",", ":")).encode() + b"\n" + values.tobytes())

    @classmethod
    def load(
        cls,
        path: Path,
        assets: list[OpenXAsset],
        encoder: TextEncoder | None = None,
        *,
        fingerprint: str | None = None,
    ) -> OpenXIndex:
        selected_encoder = encoder or HashingEncoder()
        header, _, data = path.read_bytes().partition(b"\n")
        payload = json.loads(header)
        if payload.get("schema_version") != INDEX_SCHEMA_VERSION:
            raise ValueError("Unsupported index schema version.")
        if payload.get("encoder_id") != selected_encoder.encoder_id:
            raise ValueError("The saved index uses a different encoder.")
        if payload.get("asset_ids") != [asset.asset_id for asset in assets]:
            raise ValueError("The asset catalog changed; rebuild the index.")
        if payload.get("catalog_fingerprint") != (fingerprint or catalog_fingerprint(assets)):
            raise ValueError(
                "The asset facts or classifications changed; rebuild the index."
            )
        dimensions = payload["dimensions"]
        values = array("d")
        values.frombytes(data)
        if sys.byteorder == "big":
            values.byteswap()
        if not isinstance(dimensions, int) or len(values) != 2 * len(assets) * dimensions:
            raise ValueError("The stored vectors do not match the asset catalog.")
        rows = [tuple(values[start:start + dimensions]) for start in range(0, len(values), dimensions or 1)]
        index = cls.__new__(cls)
        index.assets = assets
        index.encoder = selected_encoder
        index.fingerprint = payload["catalog_fingerprint"]
        index.structures = [asset_structure_query(asset) for asset in assets]
        index.vectors = rows[:len(assets)]
        index.structure_vectors = rows[len(assets):]
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
        return self._search_vectors(self.encoder.encode(text), query, top_k)

    def search_many(self, queries: list[RetrievalQuery], top_k: int = 5) -> list[list[RetrievalResult]]:
        if top_k <= 0 or not self.assets:
            return [[] for _ in queries]
        vectors = self.encoder.encode_many([query.text for query in queries])
        if len(vectors) != len(queries):
            raise ValueError("The embedding model returned an unexpected vector count.")
        return [self._search_vectors(vector, query, top_k) for vector, query in zip(vectors, queries)]

    def _search_vectors(self, query_vector, query, top_k):
        if query is None:
            return [
                RetrievalResult(
                    asset=self.assets[index],
                    score=round(max(0.0, min(1.0, similarity)), 4),
                    vector_score=round(similarity, 4),
                    scenario_score=0.0,
                    road_score=0.0,
                    reuse_level="review",
                    reasons=_reasons(None, self.assets[index].bundle),
                    review_kind="recall",
                )
                for index, similarity in self.recall(query_vector, min(len(self.assets), top_k))
            ]
        # Every asset is compared structurally and scored; only the returned ones are explained.
        similarity = dict(self.recall(query_vector, len(self.assets)))
        similarities = [similarity[index] for index in range(len(self.assets))]
        differences = [
            compare_query_to_asset(query, asset, candidate_structure=self.structures[index])
            for index, asset in enumerate(self.assets)
        ]
        parts = [
            (
                _scenario_query_score(query, asset.bundle, self.structures[index]),
                _road_query_score(query, asset.bundle),
            )
            for index, asset in enumerate(self.assets)
        ]
        scores = [
            round(max(0.0, min(1.0, policy.WEIGHT_SEMANTIC * similarities[index]
                               + policy.WEIGHT_SCENARIO * scenario + policy.WEIGHT_ROAD * road)), 4)
            for index, (scenario, road) in enumerate(parts)
        ]
        ranked = []
        for index in rank_candidates(differences, similarities, scores)[:top_k]:
            level = classify_reuse_level(differences[index])
            ranked.append(
                RetrievalResult(
                    asset=self.assets[index],
                    score=scores[index],
                    vector_score=round(similarities[index], 4),
                    scenario_score=round(parts[index][0], 4),
                    road_score=round(parts[index][1], 4),
                    reuse_level=level,
                    reasons=_reasons(query, self.assets[index].bundle, self.structures[index]),
                    differences=differences[index],
                    review_kind=review_kind(query, self.structures[index]) if level == "review" else "",
                    estimated_change_cost=change_cost(differences[index]),
                )
            )
        return ranked


def rank_candidates(
    differences: list[tuple[ReuseDifference, ...]], similarities: list[float], scores: list[float]
) -> list[int]:
    """Two-stage order of a structured query's candidates, as indices into the arguments.

    Structure decides the verdict and leads: direct and modify candidates come first,
    cheapest first (a major modification is close to a new build and does not lead). Review candidates within NAME_TIE_COST of
    the cheapest one are structurally tied; among them a standout name or text match
    (similarity NAME_STANDOUT_Z standard deviations above the library mean) goes first.
    Then come the remaining standout matches among the NAME_RECALL most similar assets,
    whatever their verdict, fewest blocking differences first. Everything else keeps
    the structural order: blocking differences, change cost, the facts drawn in a figure
    it does not show, then score. When no
    candidate is verified or reviewable, every one is a new build and structure alone
    picks the closest base.
    """
    count = len(differences)
    blocking = [sum(item.blocking for item in items) for items in differences]
    costs = [change_cost(items) for items in differences]
    figures = [figure_cost(items) for items in differences]
    levels = [classify_reuse_level(items) for items in differences]
    structural = sorted(range(count), key=lambda index: (blocking[index], costs[index], figures[index], -scores[index]))
    mean, spread = statistics.fmean(similarities), statistics.pstdev(similarities)
    standout = {
        index for index in range(count)
        if spread > 0 and (similarities[index] - mean) / spread >= policy.NAME_STANDOUT_Z
    }
    # A major modification is close to a new build: it does not outrank a reviewable candidate.
    verified = [index for index in structural if levels[index] in ("direct", "modify")]
    review = [index for index in structural if levels[index] == "review"]
    tied = [index for index in review if costs[index] <= costs[review[0]] + policy.NAME_TIE_COST]
    # Stable: candidates without a standout name keep their structural order.
    tied.sort(key=lambda index: (0, -similarities[index]) if index in standout else (1, 0.0))
    placed = {*verified, *tied}
    by_name = sorted(range(count), key=lambda index: -similarities[index])[:policy.NAME_RECALL] if placed else []
    named = sorted(
        (index for index in by_name if index in standout and index not in placed),
        key=lambda index: (blocking[index], -similarities[index]),
    )
    placed.update(named)
    return verified + tied + named + [index for index in structural if index not in placed]


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
