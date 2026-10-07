"""Reuse verdict of one requirement against one asset.

A typed requirement (an approved PDF scene structure) is compared structurally
(reuse_structured); anything else by keywords (reuse_legacy). Asset facts come
from reuse_facts, the numbers behind both from reuse_policy.
"""

from __future__ import annotations

from . import reuse_policy as policy
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


LEVELS = ("direct", "modify", "major_modify", "review", "new_build")


def classify_reuse_level(differences: tuple[ReuseDifference, ...]) -> str:
    """One of LEVELS: blocking differences make a new build, an unverified core fact a
    review, and changes a modification, a major one from MAJOR_MODIFY_COST.

    Unverified adjustable facts (a speed, the weather) are confirmed while making the
    changes, so they make a modification rather than a review. Notes and figure checks
    never count: the verdict rests on the requirement's text.
    """
    if any(item.blocking for item in differences):
        return "new_build"
    if any(not item.verified and item.tier == policy.TIER_CORE for item in differences):
        return "review"
    if all(item.tier in _ASIDE for item in differences):
        return "direct"
    return "major_modify" if change_cost(differences) >= policy.MAJOR_MODIFY_COST else "modify"


_ASIDE = (policy.TIER_NOTE, policy.TIER_FIGURE)


def change_cost(differences: tuple[ReuseDifference, ...]) -> float:
    """The summed cost of everything to change or confirm; notes and figure checks cost nothing."""
    return round(sum(item.cost for item in differences if item.tier not in _ASIDE), 3)


def figure_cost(differences: tuple[ReuseDifference, ...]) -> float:
    """The summed cost of the facts drawn in a figure that the asset does not show: it ranks
    candidates of equal change cost, never decides one."""
    return round(sum(item.cost for item in differences if item.tier == policy.TIER_FIGURE), 3)
