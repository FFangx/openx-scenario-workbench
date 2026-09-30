"""Adapted ScenarioManager V2 core; see docs/PDF_MIGRATION.md."""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Sequence

from .heading import extract_section_id
from .models import EvidenceSpan, OutlineEntry, ParsedBlock, ParsedDocument, SectionNode, SectionTree

@dataclass(frozen=True)
class _HeadingEvent:
    block_index: int
    level: int
    title: str
    page_number: int
    section_id: str

@dataclass
class _MutableNode:
    node_id: str
    section_id: str
    title: str
    level: int
    page_start: int
    page_end: int
    heading_block_id: str
    block_ids: list[str] = field(default_factory=list)
    parent_id: str | None = None
    child_ids: list[str] = field(default_factory=list)

def _normalize_title(title: str) -> str:
    without_markdown = re.sub(r"^#+\s*", "", title or "")
    return re.sub(r"\s+", " ", without_markdown.replace("**", "").strip())

def _section_id_from_title(title: str) -> str:
    normalized_title = _normalize_title(title)
    section_id = extract_section_id(normalized_title)
    if section_id == normalized_title[:20]:
        return ""
    return section_id.replace("．", ".").upper()

def _section_depth(section_id: str) -> int:
    normalized = section_id.replace("．", ".").strip(".")
    return len(normalized.split(".")) if normalized else 1

def _events_from_outline(
    document: ParsedDocument,
    outline: Sequence[OutlineEntry],
) -> list[_HeadingEvent]:
    events: list[_HeadingEvent] = []
    search_start = 0
    for entry in outline:
        normalized_title = _normalize_title(entry.title)
        entry_section_id = _section_id_from_title(normalized_title)
        matching_index = next(
            (
                index
                for index in range(search_start, len(document.blocks))
                if document.blocks[index].block_type == "heading"
                and document.blocks[index].page_number == entry.page_number
                and (
                    _normalize_title(document.blocks[index].text) == normalized_title
                    or (
                        entry_section_id
                        and _section_id_from_title(document.blocks[index].text)
                        == entry_section_id
                    )
                )
            ),
            -1,
        )
        if matching_index < 0:
            continue
        search_start = matching_index + 1
        block_title = _normalize_title(document.blocks[matching_index].text)
        events.append(
            _HeadingEvent(
                block_index=matching_index,
                level=entry.level,
                title=block_title,
                page_number=entry.page_number,
                section_id=_section_id_from_title(block_title),
            )
        )
    return events

def _events_from_heading_blocks(document: ParsedDocument) -> list[_HeadingEvent]:
    events: list[_HeadingEvent] = []
    for index, block in enumerate(document.blocks):
        if block.block_type != "heading":
            continue
        title = _normalize_title(block.text)
        section_id = _section_id_from_title(title)
        events.append(
            _HeadingEvent(
                block_index=index,
                level=block.heading_level or _section_depth(section_id),
                title=title,
                page_number=block.page_number,
                section_id=section_id,
            )
        )
    return events

def _make_node_id(event: _HeadingEvent, ordinal: int, used_ids: set[str]) -> str:
    base = event.section_id or f"section-{ordinal}"
    node_id = base
    suffix = 2
    while node_id in used_ids:
        node_id = f"{base}#{suffix}"
        suffix += 1
    return node_id

def build_section_tree(
    document: ParsedDocument,
    *,
    outline: Sequence[OutlineEntry] | None = None,
) -> SectionTree:

    heading_events = _events_from_heading_blocks(document)
    if outline:
        outline_events = {
            event.block_index: event
            for event in _events_from_outline(document, outline)
        }
        events = [
            outline_events.get(event.block_index, event)
            for event in heading_events
        ]
    else:
        events = heading_events
    if not events:
        return SectionTree(nodes=(), root_ids=())

    mutable_nodes: list[_MutableNode] = []
    used_ids: set[str] = set()
    stack: list[_MutableNode] = []

    for ordinal, event in enumerate(events, start=1):
        next_block_index = events[ordinal].block_index if ordinal < len(events) else len(document.blocks)
        body_blocks = tuple(
            block
            for block in document.blocks[event.block_index + 1:next_block_index]
            if block.block_type != "heading"
        )
        page_start = body_blocks[0].page_number if body_blocks else event.page_number
        page_end = body_blocks[-1].page_number if body_blocks else event.page_number
        node_id = _make_node_id(event, ordinal, used_ids)
        used_ids.add(node_id)

        while stack and stack[-1].level >= event.level:
            stack.pop()
        parent = stack[-1] if stack else None
        node = _MutableNode(
            node_id=node_id,
            section_id=event.section_id,
            title=event.title,
            level=event.level,
            page_start=page_start,
            page_end=page_end,
            heading_block_id=document.blocks[event.block_index].block_id,
            block_ids=[block.block_id for block in body_blocks],
            parent_id=parent.node_id if parent else None,
        )
        if parent is not None:
            parent.child_ids.append(node_id)
        mutable_nodes.append(node)
        stack.append(node)

    nodes = tuple(
        SectionNode(
            node_id=node.node_id,
            section_id=node.section_id,
            title=node.title,
            level=node.level,
            page_start=node.page_start,
            page_end=node.page_end,
            heading_block_id=node.heading_block_id,
            block_ids=tuple(node.block_ids),
            parent_id=node.parent_id,
            child_ids=tuple(node.child_ids),
        )
        for node in mutable_nodes
    )
    root_ids = tuple(node.node_id for node in nodes if node.parent_id is None)
    return SectionTree(nodes=nodes, root_ids=root_ids)

def validate_evidence_span(span: EvidenceSpan, document: ParsedDocument) -> bool:

    block = next((item for item in document.blocks if item.block_id == span.block_id), None)
    if block is None or block.page_number != span.page_number:
        return False
    if span.char_end > len(block.text):
        return False
    if block.text[span.char_start:span.char_end] != span.text:
        return False
    block_x0, block_y0, block_x1, block_y1 = block.bbox
    span_x0, span_y0, span_x1, span_y1 = span.bbox
    return (
        block_x0 <= span_x0 <= span_x1 <= block_x1
        and block_y0 <= span_y0 <= span_y1 <= block_y1
    )
