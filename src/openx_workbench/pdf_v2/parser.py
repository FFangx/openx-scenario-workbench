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

def _native_tables(page, page_number):
    """Preserve cell/row boundaries instead of flattening columns into prose."""
    from ..pdf_tables import native_table_html

    blocks, flags = [], []
    try:
        tables = page.find_tables().tables
        for index, table in enumerate(tables):
            rows = table.extract()
            if not rows or not any(cell for row in rows for cell in row):
                continue
            block_id = f"p{page_number}-table{index}"
            html, review_kind = native_table_html(table, rows)
            blocks.append(ParsedBlock(block_id=block_id, page_number=page_number,
                                      bbox=tuple(table.bbox), text=html, block_type="table"))
            if review_kind:
                flags.append(StructureFlag(block_id=block_id, page_number=page_number,
                    kind=review_kind, detail="Detected spans retained; review source. No missing values are filled in."
                    if review_kind == "table_merged_cells" else "Ambiguous cell geometry; extracted slots retained without inferred spans or values."))
    except Exception:
        # Retain native text if table detection fails, with an explicit audit.
        flags.append(StructureFlag(block_id=f"p{page_number}-table-detection", page_number=page_number,
                                   kind="table_detection_failed", detail="Native text retained; table layout was not reconstructed."))
    return blocks, flags

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
    ocr: bool = False,
    root=None,
    progress=None,
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


        blocks: list[ParsedBlock] = []
        table_flags = []
        preprocessing = {}
        ocr_pages = []
        if ocr:
            for number, page in enumerate(pdf_document, 1):
                # A native footer on an image-only page must not suppress OCR.
                images = [pymupdf_rect for image in page.get_images() for pymupdf_rect in page.get_image_rects(image[0])]
                large_image = any(rect.width * rect.height >= page.rect.width * page.rect.height * .5 for rect in images)
                if large_image or (len(_normalize_text(page_texts[number - 1])) < _MIN_NATIVE_TEXT_CHARS_PER_PAGE and images):
                    ocr_pages.append(number)
            if document_type != "born_digital" and not ocr_pages and not any(text.strip() for text in page_texts):
                raise ValueError("OCR: PDF contains no readable text or page images")
            if ocr_pages:
                from ..pdf_ocr import recognize_pdf_pages
                ocr_blocks, preprocessing = recognize_pdf_pages(source_path, ocr_pages, root=root, progress=progress)
                blocks.extend(ocr_blocks)

        for page_index, page in enumerate(pdf_document, start=1):
            if page_index in ocr_pages:
                continue
            page_dict = page.get_text("dict")
            table_blocks, page_flags = _native_tables(page, page_index)
            table_flags.extend(page_flags)
            table_bboxes = [block.bbox for block in table_blocks]
            page_blocks: list[ParsedBlock] = list(table_blocks)
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
                if _block_in_table(bbox, table_bboxes):
                    continue
                block_id = f"p{page_index}-b{block_index}"
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

        blocks.sort(key=lambda block: (block.page_number, block.bbox[1], block.bbox[0], block.block_id))
        structure_flags = tuple(table_flags)
        if decoder == "chain":
            blocks, chain_flags = decode_document_headings(blocks, pdf_document.page_count, outline,
                latin_document=_is_latin_document([b.text for b in blocks] if ocr_pages else page_texts))
            structure_flags += chain_flags

        return (
            ParsedDocument(
                source_pdf=source_path.name,
                parser="pymupdf",
                document_type=document_type,
                page_count=pdf_document.page_count,
                blocks=tuple(blocks),
                structure_flags=structure_flags,
                preprocessing=preprocessing,
            ),
            outline,
        )


def decode_document_headings(blocks, page_count, outline=(), *, latin_document=None):
    """Use one TOC and numbering gate for native, OCR and layout candidates."""
    toc_pages = _detect_toc_pages(blocks, page_count)
    toc_flags = tuple(StructureFlag(block_id=b.block_id, page_number=b.page_number,
        kind="toc_page_heading_rejected", detail=_normalize_text(b.text)[:50])
        for b in blocks if b.heading_level is not None and b.page_number in toc_pages)
    rejected = {flag.block_id for flag in toc_flags}
    outline_hits = {(entry.page_number, _normalize_text(entry.title)) for entry in outline}
    candidates = [HeadingCandidate(b.block_id, b.page_number, b.text,
        (b.page_number, _normalize_text(b.text)) in outline_hits, False)
        for b in blocks if b.heading_level is not None and b.block_id not in rejected]
    if latin_document is None:
        latin_document = _is_latin_document([b.text for b in blocks])
    decisions, chain_flags = decode_headings(candidates, latin_document=latin_document)
    blocks = [b.model_copy(update={"block_type": "paragraph", "heading_level": None})
        if b.block_id in rejected or decisions.get(b.block_id) is False else b for b in blocks]
    return blocks, (*toc_flags, *chain_flags)
