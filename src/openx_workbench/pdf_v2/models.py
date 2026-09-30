"""Adapted ScenarioManager V2 core; see docs/PDF_MIGRATION.md."""
from __future__ import annotations

import hashlib
import json
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

BBox = tuple[float, float, float, float]

def _is_valid_bbox(bbox: BBox) -> bool:
    x0, y0, x1, y1 = bbox
    return x0 <= x1 and y0 <= y1

class ParsedBlock(BaseModel):

    model_config = ConfigDict(frozen=True)

    block_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    bbox: BBox
    text: str = Field(min_length=1)
    block_type: Literal["heading", "paragraph", "table", "image", "unknown"] = "paragraph"
    heading_level: int | None = Field(default=None, ge=1)
    source: Literal["native_text", "ocr"] = "native_text"
    @field_validator("text")
    @classmethod
    def _reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("text must not be blank")
        return value

    @field_validator("bbox")
    @classmethod
    def _validate_bbox(cls, value: BBox) -> BBox:
        if not _is_valid_bbox(value):
            raise ValueError("bbox must satisfy x0 <= x1 and y0 <= y1")
        return value

class StructureFlag(BaseModel):

    model_config = ConfigDict(frozen=True)

    block_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    kind: str = Field(min_length=1)
    detail: str = ""

class ParsedDocument(BaseModel):

    model_config = ConfigDict(frozen=True)

    source_pdf: str = Field(min_length=1)
    parser: str = Field(min_length=1)
    document_type: Literal["born_digital", "scanned", "mixed"]
    page_count: int = Field(ge=1)
    blocks: tuple[ParsedBlock, ...]

    structure_flags: tuple[StructureFlag, ...] = ()

    @model_validator(mode="after")
    def _validate_blocks(self) -> "ParsedDocument":
        block_ids = [block.block_id for block in self.blocks]
        if len(block_ids) != len(set(block_ids)):
            raise ValueError("block_id must be unique within a document")
        if any(block.page_number > self.page_count for block in self.blocks):
            raise ValueError("block page_number exceeds page_count")
        return self

class OutlineEntry(BaseModel):

    model_config = ConfigDict(frozen=True)

    level: int = Field(ge=1)
    title: str = Field(min_length=1)
    page_number: int = Field(ge=1)

class EvidenceSpan(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    block_id: str = Field(min_length=1)
    page_number: int = Field(ge=1)
    bbox: BBox
    text: str = Field(min_length=1)
    source: Literal["regex", "semantic_mapping", "manual"]
    char_start: int = Field(ge=0)
    char_end: int = Field(gt=0)

    @field_validator("text")
    @classmethod
    def _reject_blank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("evidence text must not be blank")
        return value

    @field_validator("bbox")
    @classmethod
    def _validate_bbox(cls, value: BBox) -> BBox:
        if not _is_valid_bbox(value):
            raise ValueError("bbox must satisfy x0 <= x1 and y0 <= y1")
        return value

    @model_validator(mode="after")
    def _validate_char_range(self) -> "EvidenceSpan":
        if self.char_end <= self.char_start:
            raise ValueError("char_end must be greater than char_start")
        return self

class NumericEvidence(BaseModel):

    model_config = ConfigDict(frozen=True)

    value: float
    unit: str = Field(min_length=1)
    quantity: Literal["speed", "time", "distance", "acceleration"]
    evidence: EvidenceSpan

class SectionNode(BaseModel):

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(min_length=1)
    section_id: str = ""
    title: str = Field(min_length=1)
    level: int = Field(ge=1)
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    heading_block_id: str | None = None
    block_ids: tuple[str, ...] = ()
    parent_id: str | None = None
    child_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_page_range(self) -> "SectionNode":
        if self.page_end < self.page_start:
            raise ValueError("page_end must be greater than or equal to page_start")
        return self

    @property
    def page_range(self) -> tuple[int, int]:
        return self.page_start, self.page_end

class SectionTree(BaseModel):

    model_config = ConfigDict(frozen=True)

    nodes: tuple[SectionNode, ...]
    root_ids: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_relationships(self) -> "SectionTree":
        node_by_id = {node.node_id: node for node in self.nodes}
        if len(node_by_id) != len(self.nodes):
            raise ValueError("node_id must be unique within a section tree")

        if any(root_id not in node_by_id for root_id in self.root_ids):
            raise ValueError("root_ids must reference existing nodes")

        expected_roots = tuple(node.node_id for node in self.nodes if node.parent_id is None)
        if self.root_ids != expected_roots:
            raise ValueError("root_ids must match nodes without parents in document order")

        for node in self.nodes:
            if node.parent_id is not None:
                parent = node_by_id.get(node.parent_id)
                if parent is None or node.node_id not in parent.child_ids:
                    raise ValueError("parent and child relationships must be reciprocal")
            for child_id in node.child_ids:
                child = node_by_id.get(child_id)
                if child is None or child.parent_id != node.node_id:
                    raise ValueError("parent and child relationships must be reciprocal")
        for node in self.nodes:
            visited = {node.node_id}
            parent_id = node.parent_id
            while parent_id is not None:
                if parent_id in visited:
                    raise ValueError("section tree parent relationships contain a cycle")
                visited.add(parent_id)
                parent_id = node_by_id[parent_id].parent_id
        return self

    def find_by_section_id(self, section_id: str) -> SectionNode | None:
        normalized = section_id.strip().upper()
        return next(
            (node for node in self.nodes if node.section_id.strip().upper() == normalized),
            None,
        )

class CandidateRegion(BaseModel):

    model_config = ConfigDict(frozen=True)

    region_id: str = Field(min_length=1)
    root_node_id: str = Field(min_length=1)
    node_ids: tuple[str, ...]
    reasons: tuple[str, ...]
    score: float = Field(ge=0.0, le=1.0)

class SceneRegion(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    region_version: Literal["scene-region-v1"] = "scene-region-v1"
    region_id: str = Field(min_length=1)
    root_node_id: str = Field(min_length=1)
    node_ids: tuple[str, ...]
    block_ids: tuple[str, ...]
    page_start: int = Field(ge=1)
    page_end: int = Field(ge=1)
    inherited_context_node_ids: tuple[str, ...] = ()
    shared_context_refs: tuple[str, ...] = ()
    candidate_reasons: tuple[str, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)
    boundary_source: Literal["section_subtree", "semantic_selection", "manual"]
    review_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_region(self) -> "SceneRegion":
        if self.root_node_id not in self.node_ids:
            raise ValueError("scene region root must be included in node_ids")
        if len(self.node_ids) != len(set(self.node_ids)):
            raise ValueError("scene region node_ids must be unique")
        if len(self.block_ids) != len(set(self.block_ids)):
            raise ValueError("scene region block_ids must be unique")
        if len(self.inherited_context_node_ids) != len(
            set(self.inherited_context_node_ids)
        ):
            raise ValueError("scene region context node IDs must be unique")
        if set(self.node_ids) & set(self.inherited_context_node_ids):
            raise ValueError("scene region context cannot overlap included nodes")
        if len(self.shared_context_refs) != len(set(self.shared_context_refs)):
            raise ValueError("scene region shared context refs must be unique")
        if self.page_end < self.page_start:
            raise ValueError("scene region page_end must not precede page_start")
        return self

    @property
    def page_range(self) -> tuple[int, int]:
        return self.page_start, self.page_end

OwnershipStatus = Literal["owned", "shared", "review"]
OwnershipReason = Literal[
    "selected_root",
    "existing_region_member",
    "unique_descendant",
    "common_ancestor",
    "numbered_family_context",
    "missing_relation",
    "block_collision",
]

class NodeDisposition(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    node_id: str = Field(min_length=1)
    status: OwnershipStatus
    owner_region_id: str | None = None
    shared_context_id: str | None = None
    proposed_region_ids: tuple[str, ...] = ()
    reason_code: OwnershipReason
    support_candidate_ids: tuple[str, ...] = ()

class SharedContext(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    context_id: str = Field(min_length=1)
    node_ids: tuple[str, ...]
    consumer_region_ids: tuple[str, ...]
    relation_anchor_node_id: str = Field(min_length=1)
    reason_code: Literal[
        "common_ancestor",
        "numbered_family_context",
        "delegated_to_nested_root",
    ]

class OwnershipReviewItem(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    review_id: str = Field(min_length=1)
    node_id: str = Field(min_length=1)
    proposed_region_ids: tuple[str, ...] = ()
    reason_code: Literal["missing_relation", "block_collision"]

class SceneOwnershipPlan(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    ownership_version: Literal["scene-ownership-v5", "scene-ownership-v6"] = (
        "scene-ownership-v6"
    )
    relevant_node_ids: tuple[str, ...]
    selected_root_ids: tuple[str, ...]
    regions: tuple[SceneRegion, ...]
    shared_contexts: tuple[SharedContext, ...]
    dispositions: tuple[NodeDisposition, ...]
    review_items: tuple[OwnershipReviewItem, ...]

    @model_validator(mode="after")
    def _validate_partition(self) -> "SceneOwnershipPlan":
        disposition_ids = tuple(item.node_id for item in self.dispositions)
        if len(disposition_ids) != len(set(disposition_ids)):
            raise ValueError("ownership dispositions must have unique node IDs")
        if set(disposition_ids) != set(self.relevant_node_ids):
            raise ValueError("ownership dispositions must partition relevant nodes")
        if tuple(region.root_node_id for region in self.regions) != self.selected_root_ids:
            raise ValueError("ownership regions must conserve selected roots")
        owned_blocks = [block_id for region in self.regions for block_id in region.block_ids]
        if len(owned_blocks) != len(set(owned_blocks)):
            raise ValueError("owned SceneRegion blocks must be disjoint")
        region_by_id = {region.region_id: region for region in self.regions}
        context_by_id = {
            context.context_id: context for context in self.shared_contexts
        }
        review_by_node = {item.node_id: item for item in self.review_items}
        for disposition in self.dispositions:
            if disposition.status == "owned":
                owner = region_by_id.get(disposition.owner_region_id or "")
                if owner is None or disposition.node_id not in owner.node_ids:
                    raise ValueError("owned disposition must reference its containing region")
                if disposition.shared_context_id is not None:
                    raise ValueError("owned disposition cannot reference shared context")
            elif disposition.status == "shared":
                context = context_by_id.get(disposition.shared_context_id or "")
                if context is None or disposition.node_id not in context.node_ids:
                    raise ValueError("shared disposition must reference its containing context")
                if disposition.owner_region_id is not None:
                    raise ValueError("shared disposition cannot define owner region")
                if set(disposition.proposed_region_ids) != set(context.consumer_region_ids):
                    raise ValueError("shared disposition consumers must match context")
            else:
                review = review_by_node.get(disposition.node_id)
                if review is None or review.reason_code != disposition.reason_code:
                    raise ValueError("review disposition must reference a matching review item")
                if disposition.owner_region_id is not None or disposition.shared_context_id is not None:
                    raise ValueError("review disposition cannot define owner or shared context")
        for region_id, region in region_by_id.items():
            expected_node_ids = {
                item.node_id
                for item in self.dispositions
                if item.status == "owned" and item.owner_region_id == region_id
            }
            if set(region.node_ids) != expected_node_ids:
                raise ValueError("region nodes must match owned dispositions")
        for context_id, context in context_by_id.items():
            expected_node_ids = {
                item.node_id
                for item in self.dispositions
                if item.status == "shared" and item.shared_context_id == context_id
            }
            if set(context.node_ids) != expected_node_ids:
                raise ValueError("shared context nodes must match shared dispositions")
            if not set(context.consumer_region_ids).issubset(region_by_id):
                raise ValueError("shared context references unknown consumers")
        context_ids = set(context_by_id)
        if any(
            reference not in context_ids
            for region in self.regions
            for reference in region.shared_context_refs
        ):
            raise ValueError("SceneRegion references unknown shared context")
        for region in self.regions:
            for reference in region.shared_context_refs:
                if region.region_id not in context_by_id[reference].consumer_region_ids:
                    raise ValueError("SceneRegion is not an authorized context consumer")
        for context in self.shared_contexts:
            for consumer_id in context.consumer_region_ids:
                if context.context_id not in region_by_id[consumer_id].shared_context_refs:
                    raise ValueError("shared context consumer must reference the context")
        if set(review_by_node) != {
            item.node_id for item in self.dispositions if item.status == "review"
        }:
            raise ValueError("review items must match review dispositions")
        return self

class SceneRegionEvidenceRecord(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    evidence_ref: str = Field(pattern=r"^numeric-evidence:[0-9a-f]{64}$")
    evidence: NumericEvidence

class SceneRegionSharedContextPayload(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    context_id: str = Field(min_length=1)
    node_ids: tuple[str, ...]
    block_ids: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    consumer_region_ids: tuple[str, ...]
    relation_anchor_node_id: str = Field(min_length=1)
    reason_code: str = Field(min_length=1)

class SceneRegionRequestEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    request_id: str = Field(min_length=1)
    root_node_id: str = Field(min_length=1)
    title: str = Field(min_length=1)
    owned_block_ids: tuple[str, ...]
    shared_context_refs: tuple[str, ...] = ()
    allowed_evidence_refs: tuple[str, ...] = ()

class SceneRegionRequestRegistry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    registry_version: Literal["scene-region-request-registry-v3"] = (
        "scene-region-request-registry-v3"
    )
    source_pdf: str = Field(min_length=1)
    source_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    ownership_sha256: str = Field(pattern=r"^[0-9a-f]{64}$")
    max_text_chars: int = Field(ge=1)
    evidence_records: tuple[SceneRegionEvidenceRecord, ...]
    shared_contexts: tuple[SceneRegionSharedContextPayload, ...]
    requests: tuple[SceneRegionRequestEntry, ...]

    @model_validator(mode="after")
    def _validate_references(self) -> "SceneRegionRequestRegistry":
        for record in self.evidence_records:
            expected_ref = "numeric-evidence:" + hashlib.sha256(
                json.dumps(
                    record.evidence.model_dump(mode="json"),
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ).encode("utf-8")
            ).hexdigest()
            if record.evidence_ref != expected_ref:
                raise ValueError("evidence ref does not match evidence content")
        evidence_refs = [record.evidence_ref for record in self.evidence_records]
        context_ids = [context.context_id for context in self.shared_contexts]
        request_ids = [request.request_id for request in self.requests]
        if len(evidence_refs) != len(set(evidence_refs)):
            raise ValueError("registry evidence refs must be unique")
        if len(context_ids) != len(set(context_ids)):
            raise ValueError("registry context IDs must be unique")
        if len(request_ids) != len(set(request_ids)):
            raise ValueError("registry request IDs must be unique")
        evidence_ref_set = set(evidence_refs)
        evidence_by_ref = {
            record.evidence_ref: record.evidence for record in self.evidence_records
        }
        context_by_id = {context.context_id: context for context in self.shared_contexts}
        for context in self.shared_contexts:
            if not set(context.evidence_refs).issubset(evidence_ref_set):
                raise ValueError("shared context references unknown evidence")
            expected_context_refs = {
                evidence_ref
                for evidence_ref, evidence in evidence_by_ref.items()
                if evidence.evidence.block_id in set(context.block_ids)
            }
            if set(context.evidence_refs) != expected_context_refs:
                raise ValueError("shared context evidence permission mismatch")
        owned_blocks = [
            block_id for request in self.requests for block_id in request.owned_block_ids
        ]
        if len(owned_blocks) != len(set(owned_blocks)):
            raise ValueError("registry request owned blocks must be disjoint")
        shared_blocks = {
            block_id for context in self.shared_contexts for block_id in context.block_ids
        }
        if set(owned_blocks) & shared_blocks:
            raise ValueError("registry owned and shared blocks must be disjoint")
        for request in self.requests:
            permitted_block_ids = set(request.owned_block_ids)
            for context_id in request.shared_context_refs:
                context = context_by_id.get(context_id)
                if context is None:
                    raise ValueError("request references unknown shared context")
                if request.request_id not in context.consumer_region_ids:
                    raise ValueError("request is not a declared shared-context consumer")
                permitted_block_ids.update(context.block_ids)
            expected_request_refs = tuple(
                record.evidence_ref
                for record in self.evidence_records
                if record.evidence.evidence.block_id in permitted_block_ids
            )
            if request.allowed_evidence_refs != expected_request_refs:
                raise ValueError("request evidence permission mismatch")
        return self

class StructureIssue(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    code: Literal[
        "empty_section_tree",
        "oversized_section",
        "wide_page_span",
        "low_block_coverage",
    ]
    node_id: str = ""
    message: str = Field(min_length=1)

class StructureQualityReport(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    section_count: int = Field(ge=0)
    block_coverage_rate: float = Field(ge=0.0, le=1.0)
    requires_review: bool
    issues: tuple[StructureIssue, ...]
