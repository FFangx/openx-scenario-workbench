"""Adapted ScenarioManager V2 core; see docs/PDF_MIGRATION.md."""
from __future__ import annotations

from .models import ParsedDocument, SectionTree, StructureIssue, StructureQualityReport

def assess_structure_quality(
    document: ParsedDocument,
    tree: SectionTree,
    *,
    max_section_chars: int = 12_000,
    max_section_pages: int = 4,
    min_block_coverage_rate: float = 0.8,
) -> StructureQualityReport:

    if max_section_chars < 1 or max_section_pages < 1:
        raise ValueError("section quality limits must be positive")
    if not 0.0 <= min_block_coverage_rate <= 1.0:
        raise ValueError("min_block_coverage_rate must be within [0, 1]")

    body_blocks = tuple(block for block in document.blocks if block.block_type != "heading")
    assigned_block_ids = {
        block_id
        for node in tree.nodes
        for block_id in node.block_ids
    }
    covered_count = sum(1 for block in body_blocks if block.block_id in assigned_block_ids)
    coverage = covered_count / len(body_blocks) if body_blocks else 1.0

    if not tree.nodes:
        return StructureQualityReport(
            section_count=0,
            block_coverage_rate=round(coverage, 4),
            requires_review=True,
            issues=(
                StructureIssue(
                    code="empty_section_tree",
                    message="未识别到章节树，禁止自动推断场景边界。",
                ),
            ),
        )

    block_by_id = {block.block_id: block for block in document.blocks}
    issues: list[StructureIssue] = []
    for node in tree.nodes:
        section_chars = sum(
            len(block_by_id[block_id].text)
            for block_id in node.block_ids
            if block_id in block_by_id
        )
        if section_chars > max_section_chars:
            issues.append(
                StructureIssue(
                    code="oversized_section",
                    node_id=node.node_id,
                    message=f"章节直属正文 {section_chars} 字符，可能存在标题漏识别。",
                )
            )
        page_span = node.page_end - node.page_start + 1
        if page_span > max_section_pages:
            issues.append(
                StructureIssue(
                    code="wide_page_span",
                    node_id=node.node_id,
                    message=f"章节跨越 {page_span} 页，需复核边界。",
                )
            )

    if coverage < min_block_coverage_rate:
        issues.append(
            StructureIssue(
                code="low_block_coverage",
                message=f"仅 {coverage:.1%} 的非标题文本块被章节树覆盖。",
            )
        )

    return StructureQualityReport(
        section_count=len(tree.nodes),
        block_coverage_rate=round(coverage, 4),
        requires_review=bool(issues),
        issues=tuple(issues),
    )
