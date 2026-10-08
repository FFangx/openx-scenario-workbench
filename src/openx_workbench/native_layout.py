"""Conservative PP-DocLayoutV2 overlay on immutable native PDF evidence."""
from __future__ import annotations

import hashlib
import math
import os
import re
from pathlib import Path

from .pdf_ocr import WorkerPool, ocr_identity, run_pdf_sidecar
from .pdf_v2.models import StructureFlag
from .pdf_v2.numbering_chain import parse_numbering
from .pdf_v2.parser import decode_document_headings

LAYOUT_VERSION = "native-layout-v1"
_TITLE_LABELS = {"doc_title", "document_title", "paragraph_title", "section_header"}
# Layout processes at once, across every PDF being extracted. Each peaks near 2 GB; twelve
# pages took 50 s in one process, 30 s in two and 26 s in three.
WORKERS = WorkerPool(max(1, min(3, (os.cpu_count() or 1) // 4)))


def layout_identity(root=None):
    identity = ocr_identity(root)
    return {**identity, "engine": LAYOUT_VERSION, "model": "PP-DocLayoutV2",
        "worker_sha256": hashlib.sha256(Path(__file__).with_name("layout_worker.py").read_bytes()).hexdigest()}


def _finite_number(value):
    return not isinstance(value, bool) and isinstance(value, (float, int)) and math.isfinite(value)


def parse_layout_pages(payload, expected_pages):
    if not isinstance(payload, dict):
        raise ValueError("Layout result is invalid")
    pages = payload.get("pages")
    if (not isinstance(pages, list) or len(pages) != len(expected_pages)
            or [p.get("number") for p in pages if isinstance(p, dict)] != list(expected_pages)):
        raise ValueError("Layout page coverage is incomplete or duplicated")
    regions = []
    for page in pages:
        dimensions = [page.get(key) for key in ("width", "height", "image_width", "image_height")]
        if any(not _finite_number(v) or v <= 0 for v in dimensions):
            raise ValueError("Layout page dimensions are invalid")
        width, height, iw, ih = dimensions
        if not isinstance(page.get("regions"), list):
            raise ValueError("Layout regions are missing")
        for raw in page["regions"]:
            if not isinstance(raw, dict) or not isinstance(raw.get("label"), str):
                raise ValueError("Layout region is invalid")
            box, score = raw.get("bbox"), raw.get("score")
            if not _finite_number(score) or not 0 <= score <= 1:
                raise ValueError("Layout confidence is invalid")
            if not isinstance(box, list) or len(box) != 4 or any(not _finite_number(v) for v in box):
                raise ValueError("Layout bounding box is invalid")
            x0, y0, x1, y1 = box
            if not (0 <= x0 < x1 <= iw and 0 <= y0 < y1 <= ih):
                raise ValueError("Layout bounding box is outside its page")
            regions.append({"page_number": page["number"], "label": raw["label"], "score": score,
                "bbox": (x0 * width / iw, y0 * height / ih, x1 * width / iw, y1 * height / ih)})
    return regions


def _iou(a, b):
    area = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - area
    return area / union if union > 0 else 0


def _overlaps_native(a, b):
    area = max(0, min(a[2], b[2]) - max(a[0], b[0])) * max(0, min(a[3], b[3]) - max(a[1], b[1]))
    native_area = (a[2] - a[0]) * (a[3] - a[1])
    return native_area > 0 and area / native_area >= .3


def overlay_native_headings(document, regions, *, outline=(), audit=None):
    """Only unambiguous numbered titles may promote an existing native block."""
    matches = {}
    for region in regions:
        if region["label"] not in _TITLE_LABELS or region["score"] < .5:
            continue
        candidates = [b for b in document.blocks if b.source == "native_text"
            and b.page_number == region["page_number"] and _overlaps_native(b.bbox, region["bbox"])]
        if len(candidates) == 1 and _iou(candidates[0].bbox, region["bbox"]) >= .5:
            matches.setdefault(candidates[0].block_id, []).append(region)
    blocks, flags, promoted = [], [], []
    for block in document.blocks:
        predictions = matches.get(block.block_id, [])
        numbering = parse_numbering(block.text)
        if (len(predictions) == 1 and block.block_type == "paragraph" and numbering and numbering.remainder
                and len(block.text) <= 120 and not re.search(r"\.{3,}|…{2,}", block.text)):
            block = block.model_copy(update={"block_type": "heading", "heading_level": len(numbering.parts)})
            promoted.append(block.block_id)
        elif len(predictions) > 1:
            flags.append(StructureFlag(block_id=block.block_id, page_number=block.page_number,
                kind="layout_heading_ambiguous", detail="Multiple visual title regions; original block retained."))
        blocks.append(block)
    blocks, chain_flags = decode_document_headings(blocks, document.page_count, outline)
    accepted = {b.block_id for b in blocks if b.block_type == "heading"}
    for block in blocks:
        if block.block_id in promoted and block.block_id in accepted:
            flags.append(StructureFlag(block_id=block.block_id, page_number=block.page_number,
                kind="layout_heading_promoted", detail="Visual numbered title; native text and coordinates retained. Review source."))
    all_flags = { (f.block_id, f.kind, f.detail): f for f in (*document.structure_flags, *flags, *chain_flags)}
    return document.model_copy(update={"blocks": tuple(blocks), "structure_flags": tuple(all_flags.values()),
        "preprocessing": {**document.preprocessing, "native_layout": {**(audit or {}),
            "promoted_block_ids": [bid for bid in promoted if bid in accepted]}}})


def rescue_native_structure(path, document, *, outline=(), root=None, progress=None):
    pages = sorted({b.page_number for b in document.blocks if b.source == "native_text"})
    if not pages:
        return document
    regions, audit = run_pdf_sidecar(path, pages, root=root, progress=progress,
        identity=layout_identity(root), worker="layout_worker.py", parse_pages=parse_layout_pages,
        cache_name="layout", message="本机版面模型正在复核章节标题 / Reviewing native chapter headings locally",
        timeout=min(600, 60 + 20 * len(pages)), pool=WORKERS)
    return overlay_native_headings(document, regions, outline=outline, audit=audit)
