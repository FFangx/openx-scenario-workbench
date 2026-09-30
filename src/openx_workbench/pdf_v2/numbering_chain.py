"""Adapted ScenarioManager V2 core; see docs/PDF_MIGRATION.md."""
from __future__ import annotations

import re
from typing import NamedTuple

from .models import StructureFlag

MAX_SIBLING_GAP = 5

MAX_NUMBERING_DEPTH = 6

MAX_SEGMENT_VALUE = 999

_CJK_RE = re.compile(r"[\u4e00-\u9fff]")

_LATIN_TITLE_RE = re.compile(r"^[A-Za-z]{2,}(?:[ \t]+[A-Za-z]{2,})+\.?$")

_STRICT_NUMBERING_RE = re.compile(
    r"^(\d{1,3}|[A-Z])((?:[.．]\d{1,3})*)[.．]?(?=\s|$)"
)

class ParsedNumbering(NamedTuple):

    namespace: str
    parts: tuple[int, ...]
    remainder: str
    first_line_remainder: str = ""

def parse_numbering(text: str) -> ParsedNumbering | None:

    normalized = " ".join((text or "").split())
    match = _STRICT_NUMBERING_RE.match(normalized)
    if match is None:
        return None
    head, tail = match.group(1), match.group(2)
    raw_segments = [seg for seg in re.split(r"[.．]", tail) if seg]

    if head.isdigit():
        namespace = "main"
        raw_all = [head, *raw_segments]
    else:
        if not raw_segments:
            return None
        namespace = f"annex-{head}"
        raw_all = raw_segments

    if len(raw_all) > MAX_NUMBERING_DEPTH:
        return None
    parts: list[int] = []
    for segment in raw_all:
        if len(segment) > 1 and segment.startswith("0"):
            return None
        value = int(segment)
        if value > MAX_SEGMENT_VALUE:
            return None
        parts.append(value)
    if parts[0] == 0:
        return None

    remainder = normalized[match.end():].strip(" .．_-、:：")

    first_line = (text or "").splitlines()[0] if (text or "").strip() else ""
    line_match = _STRICT_NUMBERING_RE.match(first_line.strip())
    first_line_remainder = (
        first_line.strip()[line_match.end():].strip(" .．_-、:：")
        if line_match is not None
        else ""
    )
    return ParsedNumbering(
        namespace=namespace,
        parts=tuple(parts),
        remainder=remainder,
        first_line_remainder=first_line_remainder,
    )

def classify_junk_shape(
    numbering: ParsedNumbering,
    *,
    latin_document: bool = False,
) -> str | None:

    if not numbering.remainder:
        return "bare_number"
    if _CJK_RE.search(numbering.remainder):
        return None
    if latin_document:
        return None

    if _LATIN_TITLE_RE.match(numbering.first_line_remainder):
        return None
    return "no_cjk_remainder"

def _transition_legal(last: tuple[int, ...] | None, cand: tuple[int, ...]) -> bool:

    if last is None:
        return len(cand) <= 3 and all(value == 1 for value in cand[1:])

    if (
        len(cand) == len(last) + 1
        and cand[: len(last)] == last
        and 1 <= cand[-1] <= MAX_SIBLING_GAP
    ):
        return True

    for j in range(1, min(len(cand), len(last)) + 1):
        if cand[: j - 1] != last[: j - 1]:
            break
        gap = cand[j - 1] - last[j - 1]
        if 1 <= gap <= MAX_SIBLING_GAP and all(v == 1 for v in cand[j:]):
            return True
    return False

class HeadingCandidate(NamedTuple):

    block_id: str
    page_number: int
    text: str
    outline_hit: bool
    in_table: bool

class ChainDecision(NamedTuple):

    block_id: str
    accepted: bool
    flag: StructureFlag | None

class _ChainState:

    def __init__(self) -> None:
        self.last: dict[str, tuple[int, ...] | None] = {}
        self.accepted: dict[str, set[tuple[int, ...]]] = {}

    def lookup(self, namespace: str) -> tuple[tuple[int, ...] | None, set[tuple[int, ...]]]:
        return self.last.get(namespace), self.accepted.setdefault(namespace, set())

    def advance(self, numbering: ParsedNumbering) -> None:
        self.last[numbering.namespace] = numbering.parts
        self.accepted.setdefault(numbering.namespace, set()).add(numbering.parts)

def _flag(candidate: HeadingCandidate, kind: str, detail: str) -> StructureFlag:
    return StructureFlag(
        block_id=candidate.block_id,
        page_number=candidate.page_number,
        kind=kind,
        detail=detail[:200],
    )

def decode_headings(
    candidates: list[HeadingCandidate],
    *,
    latin_document: bool = False,
) -> tuple[dict[str, bool], tuple[StructureFlag, ...]]:

    state = _ChainState()
    decisions: dict[str, bool] = {}
    flags: list[StructureFlag] = []

    for candidate in candidates:
        numbering = parse_numbering(candidate.text)

        if candidate.outline_hit:
            decisions[candidate.block_id] = True
            if numbering is not None:
                last, accepted = state.lookup(numbering.namespace)
                if numbering.parts in accepted:
                    pass
                else:
                    if last is not None and not _transition_legal(last, numbering.parts):
                        flags.append(_flag(candidate, "numbering_discontinuity",
                                           f"outline anchor {candidate.text[:50]}"))
                    state.advance(numbering)
            continue

        if numbering is None:
            if _CJK_RE.search(candidate.text):

                decisions[candidate.block_id] = True
            else:

                decisions[candidate.block_id] = False
                flags.append(_flag(candidate, "invalid_numbering_rejected",
                                   candidate.text[:50]))
            continue

        last, accepted = state.lookup(numbering.namespace)
        is_duplicate = numbering.parts in accepted
        is_legal = (not is_duplicate) and _transition_legal(last, numbering.parts)
        junk_reason = classify_junk_shape(numbering, latin_document=latin_document)

        if junk_reason is None:
            decisions[candidate.block_id] = True
            if candidate.in_table:
                flags.append(_flag(candidate, "heading_inside_table",
                                   candidate.text[:50]))
            if is_duplicate:
                flags.append(_flag(candidate, "duplicate_heading",
                                   candidate.text[:50]))

            elif is_legal:
                state.advance(numbering)
            else:
                flags.append(_flag(candidate, "numbering_discontinuity",
                                   candidate.text[:50]))
                state.advance(numbering)
            continue

        if candidate.in_table:
            decisions[candidate.block_id] = False
            flags.append(_flag(candidate, "table_row_heading_rejected",
                               f"{junk_reason}: {candidate.text[:50]}"))
        elif is_duplicate:
            decisions[candidate.block_id] = False
            flags.append(_flag(candidate, "duplicate_junk_heading_rejected",
                               f"{junk_reason}: {candidate.text[:50]}"))
        elif is_legal:

            decisions[candidate.block_id] = True
            state.advance(numbering)
            if junk_reason == "bare_number":
                flags.append(_flag(candidate, "bare_heading_accepted",
                                   candidate.text[:50]))
        else:
            decisions[candidate.block_id] = False
            flags.append(_flag(candidate, "chain_rejected",
                               f"{junk_reason}: {candidate.text[:50]}"))

    return decisions, tuple(flags)
