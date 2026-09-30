"""Adapted ScenarioManager V2 core; see docs/PDF_MIGRATION.md."""
from __future__ import annotations

import re
from pathlib import Path

from .models import OutlineEntry, ParsedBlock, ParsedDocument, StructureFlag
from .numbering_chain import HeadingCandidate, decode_headings

_NUMBERED_HEADING_RE = re.compile(
    r"^(?:\d+|[A-Z])(?:[.．]\d+){0,5}[.．]?(?:\s+|$)",
    re.IGNORECASE,
)
_TOC_DOT_LEADER_RE = re.compile(r"\.{3,}|…{2,}")
_ATTACHMENT_HEADING_RE = re.compile(r"^附件\s*\d+\s+\S")
_HEADING_FONT_RE = re.compile(r"bold|black|hei", re.IGNORECASE)
_MIN_HEADING_FONT_SIZE = 12.0
_MIN_NATIVE_TEXT_CHARS_PER_PAGE = 20

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

_LATIN_DOCUMENT_CJK_RATIO = 0.02

_TOC_ENTRY_RE = re.compile(r"^\S.*?\s+(\d{1,3})$")

_MIN_TOC_ENTRIES_PER_PAGE = 4

_TOC_SCAN_HEAD_RATIO = 0.25
_TOC_SCAN_MIN_PAGES = 5

def _normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()

def _classify_document_type(page_texts: list[str]) -> str:
    text_page_count = sum(
        1
        for text in page_texts
        if len(_normalize_text(text)) >= _MIN_NATIVE_TEXT_CHARS_PER_PAGE
    )
    coverage = text_page_count / max(1, len(page_texts))
    if coverage >= 0.9:
        return "born_digital"
    if coverage <= 0.1:
        return "scanned"
    return "mixed"

def _is_latin_document(page_texts: list[str]) -> bool:

    total = 0
    cjk = 0
    for text in page_texts:
        stripped = "".join((text or "").split())
        total += len(stripped)
        cjk += sum(1 for ch in stripped if _CJK_RE.match(ch))
    if total == 0:
        return False
    return (cjk / total) < _LATIN_DOCUMENT_CJK_RATIO

def _detect_toc_pages(blocks: list[ParsedBlock], page_count: int) -> frozenset[int]:

    if page_count <= 0:
        return frozenset()
    scan_limit = max(_TOC_SCAN_MIN_PAGES, int(page_count * _TOC_SCAN_HEAD_RATIO))
    targets_by_page: dict[int, list[int]] = {}

    for block in blocks:
        if block.page_number > scan_limit:
            continue
        match = _TOC_ENTRY_RE.match(_normalize_text(block.text))
        if match is None:
            continue
        target = int(match.group(1))

        if block.page_number <= target <= page_count:
            targets_by_page.setdefault(block.page_number, []).append(target)

    return frozenset(
        page_number
        for page_number, targets in targets_by_page.items()
        if len(targets) >= _MIN_TOC_ENTRIES_PER_PAGE
        and all(a <= b for a, b in zip(targets, targets[1:]))
    )

def _read_outline(pdf_document: object) -> tuple[OutlineEntry, ...]:
    raw_outline = pdf_document.get_toc(simple=True) or []
    entries: list[OutlineEntry] = []
    for level, title, page_number in raw_outline:
        normalized_title = _normalize_text(str(title))
        if not normalized_title or int(page_number) < 1:
            continue
        if normalized_title.rstrip(".．").isdigit():
            continue
        entries.append(
            OutlineEntry(
                level=int(level),
                title=normalized_title,
                page_number=int(page_number),
            )
        )
    return tuple(entries)

def _block_text(raw_block: dict[str, object]) -> str:
    lines: list[str] = []
    for raw_line in raw_block.get("lines", []):
        spans = raw_line.get("spans", [])
        line_text = "".join(str(span.get("text", "")) for span in spans)
        if line_text.strip():
            lines.append(line_text.rstrip())
    return "\n".join(lines).strip()

def _has_heading_font_style(raw_block: dict[str, object]) -> bool:
    return any(
        float(span.get("size", 0.0)) >= _MIN_HEADING_FONT_SIZE
        or _HEADING_FONT_RE.search(str(span.get("font", ""))) is not None
        for raw_line in raw_block.get("lines", [])
        for span in raw_line.get("spans", [])
        if str(span.get("text", "")).strip()
    )

def _fallback_heading_level(
    text: str,
    raw_block: dict[str, object],
) -> int | None:
    normalized = _normalize_text(text)
    if len(normalized) > 120 or _TOC_DOT_LEADER_RE.search(normalized):
        return None
    if _ATTACHMENT_HEADING_RE.match(normalized):
        return 1 if _has_heading_font_style(raw_block) else None
    if not _NUMBERED_HEADING_RE.match(normalized):
        return None
    title_parts = normalized.split(maxsplit=1)
    section_id = title_parts[0].replace("．", ".").strip(".")
    heading_level = max(1, len(section_id.split(".")))
    if heading_level == 1 and (
        len(title_parts) < 2 or not _has_heading_font_style(raw_block)
    ):
        return None
    return heading_level

def _resolve_heading_decoder(heading_decoder: str | None) -> str:

    if heading_decoder is not None:
        value = heading_decoder.strip().lower()
    else:
        PDF_HEADING_DECODER = "chain"

        value = PDF_HEADING_DECODER
    return value if value in {"greedy", "chain"} else "greedy"

def _page_table_bboxes(page: object) -> list[tuple[float, float, float, float]]:

    try:
        return [tuple(map(float, table.bbox)) for table in page.find_tables().tables]
    except Exception:
        return []

def _block_in_table(bbox: tuple[float, ...], tables: list[tuple[float, float, float, float]]) -> bool:

    x0, y0, x1, y1 = bbox
    block_area = max(0.0, x1 - x0) * max(0.0, y1 - y0)
    if block_area <= 0.0:
        return False
    for tx0, ty0, tx1, ty1 in tables:
        overlap = max(0.0, min(x1, tx1) - max(x0, tx0)) * max(0.0, min(y1, ty1) - max(y0, ty0))
        if overlap / block_area >= 0.5:
            return True
    return False

def parse_pdf_structure(
    pdf_path: str | Path,
    *,
    heading_decoder: str | None = None,
) -> tuple[ParsedDocument, tuple[OutlineEntry, ...]]:

    import fitz

    decoder = _resolve_heading_decoder(heading_decoder)
    source_path = Path(pdf_path)
    with fitz.open(str(source_path)) as pdf_document:
        if pdf_document.page_count < 1:
            raise ValueError("PDF must contain at least one page")

        page_texts = [page.get_text("text") for page in pdf_document]
        document_type = _classify_document_type(page_texts)
        outline = _read_outline(pdf_document)
        outline_levels = {
            (entry.page_number, _normalize_text(entry.title)): entry.level
            for entry in outline
        }

        latin_document = _is_latin_document(page_texts) if decoder == "chain" else False

        blocks: list[ParsedBlock] = []

        candidate_meta: dict[str, tuple[bool, bool]] = {}
        for page_index, page in enumerate(pdf_document, start=1):
            page_dict = page.get_text("dict")
            table_bboxes = _page_table_bboxes(page) if decoder == "chain" else []
            page_blocks: list[ParsedBlock] = []
            for block_index, raw_block in enumerate(page_dict.get("blocks", [])):
                if raw_block.get("type") != 0:
                    continue
                text = _block_text(raw_block)
                if not text:
                    continue
                normalized_text = _normalize_text(text)
                outline_level = outline_levels.get((page_index, normalized_text))
                heading_level = outline_level
                if heading_level is None:
                    heading_level = _fallback_heading_level(text, raw_block)
                raw_bbox = raw_block.get("bbox", (0.0, 0.0, 0.0, 0.0))
                bbox = tuple(float(value) for value in raw_bbox)
                block_id = f"p{page_index}-b{block_index}"
                if decoder == "chain" and heading_level is not None:
                    candidate_meta[block_id] = (
                        outline_level is not None,
                        _block_in_table(bbox, table_bboxes),
                    )
                page_blocks.append(
                    ParsedBlock(
                        block_id=block_id,
                        page_number=page_index,
                        bbox=bbox,
                        text=text,
                        block_type="heading" if heading_level is not None else "paragraph",
                        heading_level=heading_level,
                        source="native_text",
                    )
                )
            blocks.extend(
                sorted(
                    page_blocks,
                    key=lambda block: (
                        block.bbox[1],
                        block.bbox[0],
                        block.block_id,
                    ),
                )
            )

        structure_flags: tuple[StructureFlag, ...] = ()
        if decoder == "chain":

            toc_pages = _detect_toc_pages(blocks, pdf_document.page_count)
            toc_flags = [
                StructureFlag(
                    block_id=block.block_id,
                    page_number=block.page_number,
                    kind="toc_page_heading_rejected",
                    detail=_normalize_text(block.text)[:50],
                )
                for block in blocks
                if block.block_id in candidate_meta and block.page_number in toc_pages
            ]
            if toc_flags:
                rejected_toc_ids = {flag.block_id for flag in toc_flags}
                blocks = [
                    block.model_copy(update={"block_type": "paragraph", "heading_level": None})
                    if block.block_id in rejected_toc_ids
                    else block
                    for block in blocks
                ]
                for block_id in rejected_toc_ids:
                    candidate_meta.pop(block_id, None)

            if candidate_meta:

                candidates = [
                    HeadingCandidate(
                        block_id=block.block_id,
                        page_number=block.page_number,
                        text=block.text,
                        outline_hit=candidate_meta[block.block_id][0],
                        in_table=candidate_meta[block.block_id][1],
                    )
                    for block in blocks
                    if block.block_id in candidate_meta
                ]
                decisions, chain_flags = decode_headings(
                    candidates, latin_document=latin_document
                )
                blocks = [
                    block.model_copy(update={"block_type": "paragraph", "heading_level": None})
                    if decisions.get(block.block_id) is False
                    else block
                    for block in blocks
                ]
                structure_flags = (*toc_flags, *chain_flags)
            else:
                structure_flags = tuple(toc_flags)

        return (
            ParsedDocument(
                source_pdf=source_path.name,
                parser="pymupdf",
                document_type=document_type,
                page_count=pdf_document.page_count,
                blocks=tuple(blocks),
                structure_flags=structure_flags,
            ),
            outline,
        )
