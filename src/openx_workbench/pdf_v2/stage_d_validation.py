"""Adapted ScenarioManager V2 core; see docs/PDF_MIGRATION.md."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import SectionTree
from .scene_schemas import SceneFirstExtraction

STAGE_D_VERSION = "stage-d-v1"

Severity = Literal["critical", "high", "medium", "info"]

DEFAULT_MAX_UNCOVERED_RATIO = 0.95

DEFAULT_MAX_SCENE_NODE_SHARE = 0.40

DEFAULT_MAX_UNANCHORED_NUMBERS = 0

_STORY_NUMBER_RE = re.compile(
    r"(\d+(?:\.\d+)?)\s*(km/h|m/s2|m/s²|m/s|km|cm|mm|ms|m|s|%|°)(?![A-Za-z/])",
    re.IGNORECASE,
)

_SOURCE_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?")

def _normalize_number(text: str) -> str:
    value = float(text)
    return str(int(value)) if value.is_integer() else str(value)

class ValidationIssue(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: str = Field(min_length=1)
    severity: Severity
    detail: str = Field(min_length=1)
    scene_id: str | None = None
    node_ids: tuple[str, ...] = ()

class StageDReport(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    stage_d_version: Literal["stage-d-v1"] = STAGE_D_VERSION
    standard: str = Field(min_length=1)
    scene_count: int = Field(ge=0)
    covered_node_count: int = Field(ge=0)
    uncovered_node_count: int = Field(ge=0)
    uncovered_ratio: float = Field(ge=0.0, le=1.0)
    max_scene_node_share: float = Field(ge=0.0, le=1.0)
    issues: tuple[ValidationIssue, ...] = ()

    @property
    def verdict(self) -> Literal["pass", "needs_review", "fail"]:

        severities = {issue.severity for issue in self.issues}
        if "critical" in severities:
            return "fail"
        if "high" in severities:
            return "needs_review"
        return "pass"

def _check_hallucinations(extraction: SceneFirstExtraction) -> list[ValidationIssue]:

    if not extraction.rejected_node_ids:
        return []
    return [
        ValidationIssue(
            code="hallucinated_node_id",
            severity="high",
            detail=(
                f"模型引用了 {len(extraction.rejected_node_ids)} 个章节树中不存在的 "
                "node_id，已剔除；需确认是否连带丢失了真实内容"
            ),
            node_ids=extraction.rejected_node_ids,
        )
    ]

def _check_scene_overlap(extraction: SceneFirstExtraction) -> list[ValidationIssue]:

    issues: list[ValidationIssue] = []
    owner_by_node: dict[str, str] = {}
    for scene in extraction.scenes:
        for node_id in scene.declared_member_node_ids:
            previous = owner_by_node.get(node_id)
            if previous is not None and previous != scene.scene_id:
                issues.append(
                    ValidationIssue(
                        code="scene_member_overlap",
                        severity="high",
                        detail=f"节点被 {previous} 与 {scene.scene_id} 同时声明为场景本体",
                        scene_id=scene.scene_id,
                        node_ids=(node_id,),
                    )
                )
            else:
                owner_by_node[node_id] = scene.scene_id
    return issues

def _check_empty_scenes(
    extraction: SceneFirstExtraction,
    text_by_node: dict[str, str],
) -> list[ValidationIssue]:

    issues: list[ValidationIssue] = []
    for scene in extraction.scenes:
        body = "".join(text_by_node.get(node_id, "") for node_id in scene.node_ids).strip()
        if not body:
            issues.append(
                ValidationIssue(
                    code="empty_scene",
                    severity="high",
                    detail="场景覆盖的全部节点均无正文，无法交给搭建师",
                    scene_id=scene.scene_id,
                    node_ids=scene.node_ids[:5],
                )
            )
    return issues

def _check_story_anchoring(
    extraction: SceneFirstExtraction,
    text_by_node: dict[str, str],
    max_unanchored: int,
) -> list[ValidationIssue]:

    issues: list[ValidationIssue] = []
    for scene in extraction.scenes:
        source = "".join(text_by_node.get(node_id, "") for node_id in scene.node_ids)
        source_numbers = {
            _normalize_number(match.group(0))
            for match in _SOURCE_NUMBER_RE.finditer(source)
        }
        unanchored = sorted(
            {
                f"{match.group(1)}{match.group(2)}"
                for match in _STORY_NUMBER_RE.finditer(scene.story)
                if _normalize_number(match.group(1)) not in source_numbers
            }
        )
        if len(unanchored) > max_unanchored:
            issues.append(
                ValidationIssue(
                    code="story_unanchored_number",
                    severity="high",
                    detail=f"场景描述中的数值在原文找不到：{'、'.join(unanchored)}",
                    scene_id=scene.scene_id,
                )
            )
    return issues

def _check_oversized_scene(
    extraction: SceneFirstExtraction,
    total_nodes: int,
    max_share: float,
) -> tuple[list[ValidationIssue], float]:

    issues: list[ValidationIssue] = []
    largest = 0.0
    for scene in extraction.scenes:
        share = len(scene.node_ids) / total_nodes if total_nodes else 0.0
        largest = max(largest, share)
        if share > max_share:
            issues.append(
                ValidationIssue(
                    code="oversized_scene",
                    severity="high",
                    detail=(
                        f"单个场景覆盖了全文 {share:.0%} 的章节，疑似粒度过粗"
                        "（复核项数会被人为压低但未真正确认）"
                    ),
                    scene_id=scene.scene_id,
                )
            )
    return issues, largest

def _check_granularity_spread(extraction: SceneFirstExtraction, tree: SectionTree) -> list[ValidationIssue]:

    level_by_node = {node.node_id: node.level for node in tree.nodes}
    levels = sorted({level_by_node.get(s.anchor_node_id, 0) for s in extraction.scenes})
    if len(levels) <= 1:
        return []
    if max(levels) - min(levels) < 3:
        return []
    return [
        ValidationIssue(
            code="anchor_granularity_spread",
            severity="info",
            detail=f"场景锚点分布在第 {levels} 层，粒度跨度较大，建议人工确认是否一致",
        )
    ]

def _check_structure_flagged_anchors(
    extraction: SceneFirstExtraction,
    flagged_node_ids: frozenset[str],
) -> list[ValidationIssue]:

    hits = [s for s in extraction.scenes if s.anchor_node_id in flagged_node_ids]
    return [
        ValidationIssue(
            code="anchor_on_flagged_structure",
            severity="high",
            detail="场景锚点落在解析器标记的可疑节点上（可能是表格行或伪标题），结构需先修复",
            scene_id=scene.scene_id,
            node_ids=(scene.anchor_node_id,),
        )
        for scene in hits
    ]

def validate_scene_extraction(
    extraction: SceneFirstExtraction,
    tree: SectionTree,
    *,
    text_by_node: dict[str, str],
    flagged_node_ids: frozenset[str] = frozenset(),
    max_uncovered_ratio: float = DEFAULT_MAX_UNCOVERED_RATIO,
    max_scene_node_share: float = DEFAULT_MAX_SCENE_NODE_SHARE,
    max_unanchored_numbers: int = DEFAULT_MAX_UNANCHORED_NUMBERS,
) -> StageDReport:

    issues: list[ValidationIssue] = []
    issues.extend(_check_hallucinations(extraction))
    issues.extend(_check_scene_overlap(extraction))
    issues.extend(_check_empty_scenes(extraction, text_by_node))
    issues.extend(_check_story_anchoring(extraction, text_by_node, max_unanchored_numbers))
    issues.extend(_check_structure_flagged_anchors(extraction, flagged_node_ids))
    issues.extend(_check_granularity_spread(extraction, tree))

    substantive = {
        node.node_id for node in tree.nodes if text_by_node.get(node.node_id, "").strip()
    }
    accounted = extraction.covered_node_ids | set(extraction.document_context_node_ids)
    uncovered = substantive - accounted
    uncovered_ratio = len(uncovered) / len(substantive) if substantive else 0.0
    if uncovered_ratio > max_uncovered_ratio:
        issues.append(
            ValidationIssue(
                code="extraction_produced_almost_nothing",
                severity="critical",
                detail=(
                    f"{uncovered_ratio:.0%} 的有正文章节无人认领（上限 "
                    f"{max_uncovered_ratio:.0%}），疑似整份抽取失败而非内容本身不含场景"
                ),
                node_ids=tuple(sorted(uncovered)[:20]),
            )
        )

    oversized, largest_share = _check_oversized_scene(
        extraction, len(tree.nodes), max_scene_node_share
    )
    issues.extend(oversized)

    return StageDReport(
        standard=extraction.standard,
        scene_count=len(extraction.scenes),
        covered_node_count=len(extraction.covered_node_ids),
        uncovered_node_count=len(uncovered),
        uncovered_ratio=round(uncovered_ratio, 4),
        max_scene_node_share=round(largest_share, 4),
        issues=tuple(issues),
    )
