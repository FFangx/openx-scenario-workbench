"""Adapted ScenarioManager V2 core; see docs/PDF_MIGRATION.md."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import SectionNode, SectionTree

SHARED_PREFILTER_VERSION = "shared-container-prefilter-v1"

SHARED_CONTAINER_KEYWORDS: tuple[str, ...] = (
    "结束条件",
    "试验要求",
    "试验步骤",
    "试验方法",
    "试验实施",
    "实施方法",
    "注意事项",
    "有效性",
    "判断方法",
    "判定",
    "通用要求",
)

DEFAULT_LOOKBACK_SIBLINGS = 6

PrefilterSignal = Literal["self_title", "ancestor_title", "preceding_sibling_title"]

class SharedContainerCandidate(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    prefilter_version: Literal["shared-container-prefilter-v1"] = (
        SHARED_PREFILTER_VERSION
    )
    node_id: str = Field(min_length=1)

    signal: PrefilterSignal

    matched_keyword: str = Field(min_length=1)

    signal_node_id: str = Field(min_length=1)

    sibling_distance: int | None = Field(default=None, ge=1)

def _match_keyword(title: str) -> str | None:

    for keyword in SHARED_CONTAINER_KEYWORDS:
        if keyword in title:
            return keyword
    return None

def _sibling_sequence(
    node: SectionNode,
    node_by_id: dict[str, SectionNode],
    tree: SectionTree,
) -> tuple[str, ...]:

    if node.parent_id is None:
        return tree.root_ids
    parent = node_by_id.get(node.parent_id)
    return parent.child_ids if parent is not None else ()

def prefilter_shared_containers(
    tree: SectionTree,
    *,
    excluded_node_ids: frozenset[str] = frozenset(),
    lookback_siblings: int = DEFAULT_LOOKBACK_SIBLINGS,
) -> tuple[SharedContainerCandidate, ...]:

    node_by_id = {node.node_id: node for node in tree.nodes}

    keyword_by_id = {
        node.node_id: _match_keyword(node.title) for node in tree.nodes
    }

    candidates: list[SharedContainerCandidate] = []
    for node in tree.nodes:
        if node.node_id in excluded_node_ids:
            continue

        own = keyword_by_id[node.node_id]
        if own is not None:
            candidates.append(
                SharedContainerCandidate(
                    node_id=node.node_id,
                    signal="self_title",
                    matched_keyword=own,
                    signal_node_id=node.node_id,
                )
            )
            continue

        ancestor_hit: tuple[str, str] | None = None
        cursor = node.parent_id
        while cursor is not None:
            hit = keyword_by_id.get(cursor)
            if hit is not None:
                ancestor_hit = (cursor, hit)
                break
            parent_node = node_by_id.get(cursor)
            cursor = parent_node.parent_id if parent_node is not None else None
        if ancestor_hit is not None:
            candidates.append(
                SharedContainerCandidate(
                    node_id=node.node_id,
                    signal="ancestor_title",
                    matched_keyword=ancestor_hit[1],
                    signal_node_id=ancestor_hit[0],
                )
            )
            continue

        if lookback_siblings <= 0:
            continue
        siblings = _sibling_sequence(node, node_by_id, tree)
        if node.node_id not in siblings:
            continue
        index = siblings.index(node.node_id)
        window = siblings[max(0, index - lookback_siblings) : index]

        for distance, sibling_id in enumerate(reversed(window), start=1):
            hit = keyword_by_id.get(sibling_id)
            if hit is None:
                continue
            candidates.append(
                SharedContainerCandidate(
                    node_id=node.node_id,
                    signal="preceding_sibling_title",
                    matched_keyword=hit,
                    signal_node_id=sibling_id,
                    sibling_distance=distance,
                )
            )
            break

    return tuple(candidates)

def exclude_subtrees(
    tree: SectionTree,
    root_node_ids: frozenset[str],
) -> frozenset[str]:

    node_by_id = {node.node_id: node for node in tree.nodes}
    collected: set[str] = set()
    stack = [node_id for node_id in root_node_ids if node_id in node_by_id]
    while stack:
        current = stack.pop()
        if current in collected:
            continue
        collected.add(current)
        stack.extend(node_by_id[current].child_ids)
    return frozenset(collected)
