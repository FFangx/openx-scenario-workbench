from __future__ import annotations

import re
from dataclasses import dataclass

from .scene_package import (
    EvidenceRef,
    ScenePackage,
    canonical_features,
    extract_parameters,
)


@dataclass(frozen=True, slots=True)
class PdfPage:
    number: int
    text: str


@dataclass(slots=True)
class DocumentSection:
    section_id: str
    title: str
    text: str
    page_start: int
    page_end: int


_HEADING_RE = re.compile(
    r"^(?P<section>(?:\d+(?:\.\d+){1,5}|[A-Z][.．]\d+(?:\.\d+)*))\s*[、.．]?\s*(?P<title>.+)$"
)
_SCENE_SIGNALS = (
    "scenario",
    "test vehicle",
    "target vehicle",
    "pedestrian",
    "ttc",
    "lane change",
    "cut-in",
    "场景",
    "测试车辆",
    "目标车辆",
    "目标车",
    "行人",
    "换道",
    "切入",
    "制动",
    "碰撞时间",
)


def extract_scene_packages_from_pdf(
    pdf_data: bytes,
    source_pdf: str,
    source_standard: str = "",
) -> list[ScenePackage]:
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError("PDF support requires the 'pdf' optional dependency.") from exc

    with pymupdf.open(stream=pdf_data, filetype="pdf") as document:
        pages = [PdfPage(index + 1, page.get_text("text")) for index, page in enumerate(document)]
    return extract_scene_packages_from_pages(pages, source_pdf, source_standard)


def extract_scene_packages_from_pages(
    pages: list[PdfPage],
    source_pdf: str,
    source_standard: str = "",
) -> list[ScenePackage]:
    packages: list[ScenePackage] = []
    for section in split_sections(pages):
        searchable = f"{section.title}\n{section.text}"
        if not _is_scene_section(searchable):
            continue
        entity_kinds, action_kinds, trigger_kinds, road_features = canonical_features(searchable)
        evidence = EvidenceRef(
            source_pdf=source_pdf,
            section_id=section.section_id,
            page_start=section.page_start,
            page_end=section.page_end,
            source_text=section.text.strip(),
        )
        package_id = f"{source_standard or 'PDF'}_{section.section_id}"
        packages.append(
            ScenePackage(
                package_id=package_id,
                title=section.title,
                preferred_text=section.text.strip(),
                source_standard=source_standard,
                evidence=[evidence],
                road_types=sorted(road_features),
                entities=sorted(entity_kinds),
                actions=sorted(action_kinds),
                triggers=sorted(trigger_kinds),
                parameters=extract_parameters(searchable),
            )
        )
    return packages


def split_sections(pages: list[PdfPage]) -> list[DocumentSection]:
    sections: list[DocumentSection] = []
    current: DocumentSection | None = None

    for page in pages:
        for raw_line in page.text.splitlines():
            line = raw_line.strip()
            if not line:
                continue
            heading = _HEADING_RE.match(line)
            if heading:
                if current:
                    sections.append(current)
                current = DocumentSection(
                    section_id=heading.group("section"),
                    title=heading.group("title").strip(),
                    text="",
                    page_start=page.number,
                    page_end=page.number,
                )
            elif current:
                current.text = f"{current.text}\n{line}".strip()
                current.page_end = page.number

    if current:
        sections.append(current)

    merged: dict[str, DocumentSection] = {}
    for section in sections:
        existing = merged.get(section.section_id)
        if existing is None:
            merged[section.section_id] = section
            continue
        existing.text = f"{existing.text}\n{section.text}".strip()
        existing.page_start = min(existing.page_start, section.page_start)
        existing.page_end = max(existing.page_end, section.page_end)
        if len(section.title) > len(existing.title):
            existing.title = section.title
    return list(merged.values())


def _is_scene_section(text: str) -> bool:
    normalized = text.casefold()
    return sum(signal in normalized for signal in _SCENE_SIGNALS) >= 2
