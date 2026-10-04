"""Reuse verdict of one requirement against one asset.

A typed requirement (an approved PDF scene structure) is compared structurally
(reuse_structured); anything else by keywords (reuse_legacy). Asset facts come
from reuse_facts, the numbers behind both from reuse_policy.
"""

from __future__ import annotations

from .catalog import OpenXAsset
from .reuse_differences import ReuseDifference
from .reuse_legacy import compare_keywords
from .reuse_structured import compare_structure
from .scene_package import RetrievalQuery


def compare_query_to_asset(
    query: RetrievalQuery,
    asset: OpenXAsset,
    *,
    candidate_structure: RetrievalQuery | None = None,
) -> tuple[ReuseDifference, ...]:
    """Every difference to close before `asset` meets `query`.

    `candidate_structure` is the asset's precomputed `asset_structure_query`.
    """
    if query.structured:
        return compare_structure(query, asset, candidate_structure)
    return compare_keywords(query, asset)


def classify_reuse_level(differences: tuple[ReuseDifference, ...]) -> str:
    if not differences:
        return "direct"
    if any(item.blocking for item in differences):
        return "new_build"
    if any(not item.verified for item in differences):
        return "review"
    return "modify"


def change_cost(differences: tuple[ReuseDifference, ...]) -> float:
    return round(sum(item.cost for item in differences), 3)
