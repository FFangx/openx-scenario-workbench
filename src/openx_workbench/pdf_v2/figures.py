"""Scene figures: the drawing above a figure caption, rendered for a model that reads images.

Standards often place a target only in a figure ("如图C.10所示"). The text parser keeps no figure,
only its caption ("图C.10 日间儿童目标横穿…示意图"), which sits under it. A figure is the page
region between its caption and the nearest body text above, cut to what is drawn there: vector
lines, pictures and their labels. Captions are read from the page as laid out, since a parser may
fold one into a table or a heading. Nothing here depends on one standard's layout.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Iterable

from .models import ParsedBlock, SectionTree

# A figure number: 图5, 图C.10, 图2-1, 图2- 6, 图 A.1 (the PDF may put spaces anywhere in it).
_NUMBER = r"([A-Z]?\s*[.．]?\s*\d+(?:\s*[.．\-－]\s*\d+)*)"
_CAPTION = re.compile(r"^图\s*" + _NUMBER + r"(?!\s*[.．\-－]?\s*\d)")
# A caption names the figure; a sentence that starts with a figure number refers to it.
_REFERRING = re.compile(r"^\s*(?:所示|为|是|给出|可见|[，,。；：])")
# A reference to a figure: 图 after punctuation, a line start or a word that points to it (如图5,
# 见图C.1, 按照图C.1、图C.2). After another word it ends one: 示意图 25 is a caption and its page
# number, GB 5768.4—2017中图B.4 a figure of another standard.
REFERENCE = re.compile(r"(?:(?<![一-鿿])|(?<=[如见照按和及与至或从]))图\s*" + _NUMBER)
_SPACE = re.compile(r"\s+")
_PAGE_SUFFIX = re.compile(r"\s+\d{1,4}$")
_LEGEND = re.compile(r"^(?:标引序号说明|说明|注\s*\d*)\s*[:：]")
_KEY = re.compile(r"^\S{1,8}\s*(?:——|—|--)")
_HEADING = re.compile(r"^(?:[A-Z]|\d+)(?:[.．]\d+)+\s+[一-鿿]")
_PAGE_NUMBER = re.compile(r"[-—\s]*\d{1,4}[-—\s]*")

CAPTION_CHARS = 100  # a caption is a title, not a paragraph
BODY_CHARS = 40  # text this long above a figure is running text, not a label in the drawing
INSIDE_SHARE = 0.6  # a picture or shape belongs to the figure when this much of it lies in the region
MAX_SIDE_PX = 1600
MAX_DPI = 200
PADDING = 4.0


@dataclass(frozen=True)
class Figure:
    """One figure: its number ("图C.10"), its caption line, where it is, the rendered PNG and the
    section it is in."""
    label: str
    caption: str
    page_number: int
    clip: tuple[float, float, float, float]
    png: bytes
    node_id: str | None = None


@dataclass(frozen=True)
class _Text:
    """A run of text on the page: a layout block, cut where a caption line starts or ends."""
    rect: tuple[float, float, float, float]
    text: str


def figure_label(number: str) -> str:
    """A figure number as one token: 图 C. 10 → 图C.10, 图2- 6 → 图2-6."""
    return "图" + _SPACE.sub("", number).replace("．", ".").replace("－", "-")


def caption_label(line: str) -> str | None:
    """The figure number of a caption line ("图C.10 日间…示意图"), or None for any other text: a
    title has no comma or full stop, a sentence about a figure has."""
    text = line.strip()
    match = _CAPTION.match(text)
    if not match or len(_SPACE.sub("", text)) > CAPTION_CHARS or "。" in text or "，" in text:
        return None
    if _REFERRING.match(text[match.end():]):
        return None
    return figure_label(match.group(1))


def referenced_labels(text: str) -> list[str]:
    """Figure numbers a text refers to, in order ("如图C.10所示" → 图C.10)."""
    return list(dict.fromkeys(figure_label(match.group(1)) for match in REFERENCE.finditer(text or "")))


def _page_texts(page, ocr_blocks: list[ParsedBlock]) -> list[_Text]:
    """The page's text as laid out; a scanned page's from its OCR blocks. A caption line is a
    run of its own, so the labels above it in the same layout block stay labels."""
    if ocr_blocks:
        return [_Text(block.bbox, block.text) for block in ocr_blocks]
    runs: list[_Text] = []
    for block in page.get_text("dict").get("blocks", []):
        if block.get("type") != 0:
            continue
        current: list[tuple[tuple[float, ...], str]] = []
        for line in block.get("lines", []):
            text = "".join(str(span.get("text", "")) for span in line.get("spans", [])).strip()
            if not text:
                continue
            if caption_label(text):
                if current:
                    runs.append(_join(current))
                runs.append(_Text(tuple(line["bbox"]), text))
                current = []
            else:
                current.append((tuple(line["bbox"]), text))
        if current:
            runs.append(_join(current))
    return runs


def _join(lines: list[tuple[tuple[float, ...], str]]) -> _Text:
    return _Text((min(box[0] for box, _ in lines), min(box[1] for box, _ in lines),
                  max(box[2] for box, _ in lines), max(box[3] for box, _ in lines)), "\n".join(text for _, text in lines))


def _legend(text: str) -> bool:
    """A figure's key between the drawing and its caption ("标引序号说明：", "c ——曲率", "注：")."""
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return bool(lines) and (bool(_LEGEND.match(lines[0])) or all(_KEY.match(line) for line in lines))


def _overlaps(first, second) -> bool:
    return first[0] < second[2] and second[0] < first[2] and first[1] < second[3] and second[1] < first[3]


def _body(run: _Text, furniture: set[str], headings: list[tuple]) -> bool:
    """Whether text above a caption ends the figure: running text, a heading, another caption or
    page furniture. Labels inside the drawing and its key do not."""
    text = _SPACE.sub("", run.text)
    if text in furniture or caption_label(run.text) or _HEADING.match(run.text.strip()):
        return True
    if any(_overlaps(run.rect, box) for box in headings):
        return True
    return not _legend(run.text) and ("。" in text or len(text) >= BODY_CHARS)


def _inside(rect, region, tolerance: float = 2.0) -> bool:
    return (rect.x0 >= region.x0 - tolerance and rect.x1 <= region.x1 + tolerance
            and rect.y0 >= region.y0 - tolerance and rect.y1 <= region.y1 + tolerance)


def _drawn_in(rect, region):
    """The part of a drawing or picture that belongs to the region: a line inside it, or a shape
    mostly inside it (a picture may carry a white margin over the text above); None otherwise."""
    if rect.width <= 0 or rect.height <= 0:
        return rect if _inside(rect, region) else None
    part = rect & region
    if part.is_empty or part.width * part.height < INSIDE_SHARE * rect.width * rect.height:
        return None
    return part


def _clip(page, caption: _Text, runs: list[_Text], stops: list[tuple], furniture: set[str],
          headings: list[tuple], scanned: bool):
    """The rectangle of the figure above a caption, or None when nothing is drawn there. `stops`
    are the parsed headings and tables of the page: a table wholly above the caption ends it."""
    import pymupdf

    above = [run for run in runs if run is not caption and run.rect[3] <= caption.rect[1] + 1]
    ends = [run.rect[3] for run in above if _body(run, furniture, headings)]
    ends += [box[3] for box in stops if box[3] <= caption.rect[1] + 1]
    # Below the text that ends the figure, clear of its descenders.
    region = pymupdf.Rect(page.rect.x0, max(ends, default=page.rect.y0 - 2) + 2, page.rect.x1, caption.rect[1])
    if region.height < 10:
        return None
    if scanned:
        drawn = [tuple(region)]  # a scanned page is one picture: the region is the figure
    else:
        shapes = [pymupdf.Rect(item["rect"]) for item in page.get_drawings()]
        shapes += [pymupdf.Rect(item["bbox"]) for item in page.get_image_info()]
        drawn = [tuple(part) for part in (_drawn_in(shape, region) for shape in shapes) if part is not None]
    if not drawn:
        return None
    labels = [run.rect for run in above if not _body(run, furniture, headings) and _inside(pymupdf.Rect(run.rect), region)]
    # A line is a rectangle without area, so the union is taken corner by corner.
    rects = [*drawn, *labels, caption.rect]
    clip = pymupdf.Rect(min(r[0] for r in rects) - PADDING, min(r[1] for r in rects) - PADDING,
                        max(r[2] for r in rects) + PADDING, max(r[3] for r in rects) + PADDING)
    # The margin never reaches over the text that ends the figure.
    clip &= pymupdf.Rect(page.rect.x0, region.y0, page.rect.x1, page.rect.y1)
    return clip if clip.height >= 20 and clip.width >= 20 else None


def _owners(blocks: list[ParsedBlock], tree: SectionTree | None) -> list[tuple[int, float, str]]:
    """Where each section's text starts and goes on, as (page, top, node) in reading order."""
    if tree is None:
        return []
    node_of = {block_id: node.node_id for node in tree.nodes
               for block_id in (node.heading_block_id, *node.block_ids) if block_id}
    return [(block.page_number, block.bbox[1], node_of[block.block_id]) for block in blocks if block.block_id in node_of]


def _owner(owners: list[tuple[int, float, str]], page_number: int, top: float) -> str | None:
    """The section a caption is in: that of the last text that starts before it."""
    found = None
    for page, y, node_id in owners:
        if (page, y) > (page_number, top + 1):
            break
        found = node_id
    return found


def find_figures(pdf_bytes: bytes, blocks: Iterable[ParsedBlock], tree: SectionTree | None = None) -> list[Figure]:
    """Every captioned figure of a document, rendered, in reading order, with the section it is in
    (given the section tree built from `blocks`)."""
    import pymupdf

    blocks = list(blocks)
    owners = sorted(_owners(blocks, tree), key=lambda item: (item[0], item[1]))
    by_page: dict[int, list[ParsedBlock]] = {}
    for block in blocks:
        by_page.setdefault(block.page_number, []).append(block)
    found: list[Figure] = []
    with pymupdf.open(stream=pdf_bytes, filetype="pdf") as pdf:
        pages = []
        for number, page in enumerate(pdf, 1):
            ocr = [block for block in by_page.get(number, []) if block.source == "ocr"]
            pages.append((page, _page_texts(page, ocr), bool(ocr)))
        # Running headers and footers: the same text on three pages or more, or a bare page number.
        counts = Counter(_SPACE.sub("", run.text) for _, runs, _ in pages for run in runs)
        furniture = {text for text, count in counts.items() if count >= 3 or _PAGE_NUMBER.fullmatch(text)}
        for number, (page, runs, scanned) in enumerate(pages, 1):
            parsed = by_page.get(number, [])
            headings = [block.bbox for block in parsed if block.block_type == "heading"]
            stops = [block.bbox for block in parsed if block.block_type in {"heading", "table"}]
            for run in runs:
                label = caption_label(run.text.splitlines()[0]) if run.text else None
                if label is None:
                    continue
                clip = _clip(page, run, runs, stops, furniture, headings, scanned)
                if clip is None:
                    continue
                dpi = max(72, min(MAX_DPI, int(MAX_SIDE_PX * 72 / max(clip.width, clip.height))))
                png = page.get_pixmap(clip=clip, dpi=dpi).tobytes("png")
                caption = _PAGE_SUFFIX.sub("", run.text.splitlines()[0].strip())
                found.append(Figure(label, caption, number, (clip.x0, clip.y0, clip.x1, clip.y1), png,
                                    _owner(owners, number, run.rect[1])))
    return found
