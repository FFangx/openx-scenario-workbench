"""Ground a scene structure's spatial facts in the scene's own text (prompt v9 on).

Each spatial field (a participant's bearing, facing and either-or group; the ego's turn and lane)
names its source: stated, implied with a reason, or unknown. A fact keeps its value only when its
quote is found in the text the scene was extracted from; otherwise it reads as unknown and a person
is asked to check it. Contradictions are pointed out, never corrected. Where two independent
readings of the same text disagree, the fact reads as unknown.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .scene_schemas import FieldEvidence, SceneParticipant, SceneStructure

# The unknown value of each field that has one. An either-or group has none: unsupported, it is
# kept and marked, since reading the participants as alternatives is the tolerant reading.
UNKNOWN = {"bearing": "未知方位", "facing": "未知", "ego_turn": "未知", "ego_lane": "未知"}
PARTICIPANT_FIELDS = ("bearing", "facing", "alternative_group")
SCENE_FIELDS = ("ego_turn", "ego_lane")

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")
_ELLIPSIS = re.compile(r"…+|\.{3,}")
_WRAPPERS = "「」『』“”‘’\"'《》"


def normalize(text: str) -> str:
    """Text compared without markup, whitespace or width differences (a PDF breaks lines anywhere)."""
    return _SPACE.sub("", unicodedata.normalize("NFKC", _TAG.sub("", text)))


def quote_found(quote: str, normalized_source: str) -> bool:
    """Whether the quote's parts (split at an ellipsis) appear in the source in order."""
    parts = [normalize(part).strip(_WRAPPERS) for part in _ELLIPSIS.split(quote)]
    parts = [part for part in parts if part]
    position = 0
    for part in parts:
        found = normalized_source.find(part, position)
        if found < 0:
            return False
        position = found + len(part)
    return bool(parts)


def _unknown(field: str, value: object) -> bool:
    return value is None or value == UNKNOWN.get(field)


def _with_note(evidence: dict, field: str, note: str) -> dict:
    item = evidence.get(field) or FieldEvidence()
    review = f"{item.review}；{note}" if item.review and note not in item.review else (item.review or note)
    return {**evidence, field: item.model_copy(update={"review": review[:300]})}


def _problem(item: FieldEvidence | None, normalized_source: str) -> str:
    if item is None or item.source == "未知":
        return "没有原文依据"
    if not item.quote:
        return "没有引用原文"
    if item.source == "推出" and not item.reason:
        return "写了推出但没有理由"
    if not quote_found(item.quote, normalized_source):
        return "引句在本场景原文中找不到"
    return ""


def _ground_fields(values: dict, evidence: dict, fields: tuple[str, ...], source: str) -> tuple[dict, dict]:
    updates, kept = {}, {}
    for field in fields:
        value, item = values[field], evidence.get(field)
        if _unknown(field, value):
            continue  # nothing to ground; an unknown value needs no evidence
        problem = _problem(item, source)
        if not problem:
            kept[field] = item
        elif field in UNKNOWN:
            updates[field] = UNKNOWN[field]
            kept[field] = FieldEvidence(quote=item.quote if item else None,
                                        review=f"{problem}：原为「{value}」，已改为未知")
        else:
            kept[field] = (item or FieldEvidence()).model_copy(update={"review": f"任选组{problem}，请核对"})
    return updates, kept


def ground_structure(structure: SceneStructure, source_text: str) -> SceneStructure:
    """Keep the spatial facts whose quote the scene's own text contains; the rest read as unknown."""
    source = normalize(source_text)
    participants = []
    for participant in structure.participants:
        values = {field: getattr(participant, field) for field in PARTICIPANT_FIELDS}
        updates, evidence = _ground_fields(values, participant.evidence, PARTICIPANT_FIELDS, source)
        participants.append(participant.model_copy(update={**updates, "evidence": evidence}))
    values = {field: getattr(structure, field) for field in SCENE_FIELDS}
    updates, evidence = _ground_fields(values, structure.evidence, SCENE_FIELDS, source)
    return structure.model_copy(update={**updates, "participants": tuple(participants), "evidence": evidence})


def _side(bearing: str) -> str:
    return bearing[0] if bearing[:1] in {"左", "右"} else ""


def _static(participant: SceneParticipant) -> bool:
    return "静止" in participant.actions or participant.speed_kph == 0


def check_contradictions(structure: SceneStructure) -> SceneStructure:
    """Mark facts that contradict each other or the quoted wording; nothing is changed."""
    notes: list[list[str]] = [[] for _ in structure.participants]
    items = list(enumerate(structure.participants))
    # Standing participants quoting the same sentence stand where it says, alike.
    for index, participant in items:
        quote = (participant.evidence.get("bearing") or FieldEvidence()).quote
        if not quote or _unknown("bearing", participant.bearing) or not _static(participant):
            continue
        for other_index, other in items:
            other_quote = (other.evidence.get("bearing") or FieldEvidence()).quote
            if (other_index != index and other.kind == participant.kind and _static(other) and other_quote
                    and normalize(other_quote) == normalize(quote)
                    and not _unknown("bearing", other.bearing) and other.bearing != participant.bearing):
                notes[index].append(f"与另一个静止的{other.kind}引同一句原文，方位却是「{other.bearing}」")
    # The near side is the ego's right, the far side its left (right-hand traffic).
    for index, participant in items:
        quote = normalize((participant.evidence.get("bearing") or FieldEvidence()).quote or "")
        side = _side(participant.bearing)
        if side == "左" and "近端" in quote:
            notes[index].append("原文说近端（主车右侧），方位却在左侧")
        if side == "右" and "远端" in quote:
            notes[index].append("原文说远端（主车左侧），方位却在右侧")
    # An occluder hides what is behind it from the ego: both stand on the same side.
    for relation in structure.relations:
        blockers = {_side(p.bearing) for p in structure.participants if p.kind == relation.subject} - {""}
        hidden = [(i, _side(p.bearing)) for i, p in items if p.kind == relation.object]
        for index, side in hidden:
            if len(blockers) == 1 and side and side not in blockers:
                notes[index].append(f"遮挡它的{relation.subject}在另一侧")
    participants = tuple(
        participant.model_copy(update={"evidence": _with_note(participant.evidence, "bearing",
                                                              "矛盾：" + "；".join(found) + "，请核对")})
        if found else participant
        for participant, found in zip(structure.participants, notes))
    return structure.model_copy(update={"participants": participants})


def _pair(first: tuple[SceneParticipant, ...], second: tuple[SceneParticipant, ...]) -> list[int] | None:
    """For each participant of the first reading its counterpart in the second, or None when the
    two readings name different participants."""
    if Counter(p.kind for p in first) != Counter(p.kind for p in second):
        return None
    fields = ("bearing", "facing", "actions", "age", "speed_kph")
    free, pairing = set(range(len(second))), []
    for participant in first:
        best = max((index for index in free if second[index].kind == participant.kind),
                   key=lambda index: (sum(getattr(participant, field) == getattr(second[index], field)
                                          for field in fields), -index))
        free.discard(best)
        pairing.append(best)
    return pairing


def _groups(participants, order) -> frozenset:
    labels: dict[str, set[int]] = {}
    for position, index in enumerate(order):
        label = participants[index].alternative_group
        if label:
            labels.setdefault(label, set()).add(position)
    return frozenset(frozenset(members) for members in labels.values())


def _times(count: int) -> str:
    return {2: "两", 3: "三"}.get(count, str(count)) + "次读取"


def _vote(field: str, items: list) -> tuple[dict, dict | None]:
    """The value of `field` the readings agree on, from (value, evidence) per reading, the first
    reading's first: a known value more than half of them name stands, with that reading's evidence.
    Without one, a known first value reads as unknown; an unknown one stays as it is.
    Returns the update and the new evidence (None: unchanged)."""
    values = [getattr(item, field) for item in items]
    known = Counter(value for value in values if not _unknown(field, value))
    winner = next((value for value, count in known.items() if count * 2 > len(values)), None)
    if winner == values[0] or (winner is None and _unknown(field, values[0])):
        return {}, None
    if winner is not None:
        return {field: winner}, next(item.evidence.get(field) for item in items if getattr(item, field) == winner)
    shown = "/".join(f"「{value if not _unknown(field, value) else '未知'}」" for value in values)
    return {field: UNKNOWN[field]}, FieldEvidence(quote=(items[0].evidence.get(field) or FieldEvidence()).quote,
                                                  review=f"{_times(len(values))}不一致（{shown}），已改为未知")


def _apply(item, fields: tuple[str, ...], items: list):
    updates, evidence = {}, dict(item.evidence)
    for field in fields:
        change, chosen = _vote(field, items)
        updates.update(change)
        if chosen is not None:
            evidence[field] = chosen
        elif change:
            evidence.pop(field, None)
    return item.model_copy(update={**updates, "evidence": evidence}) if updates else item


def _kinds(structure: SceneStructure) -> str:
    kinds = Counter(p.kind for p in structure.participants)
    return "、".join(f"{kind}×{n}" if n > 1 else kind for kind, n in kinds.items()) or "无"


def reconcile_readings(readings: list[SceneStructure | None]) -> SceneStructure | None:
    """One structure from independent readings of the same text: a spatial fact stands where more
    than half of the readings agree on it, otherwise it reads as unknown.

    The other fields follow the first reading. A reading that names other participants cannot be
    compared one by one: it takes no part in their votes and a person is asked to check."""
    present = [reading for reading in readings if reading is not None]
    if len(present) < 2:
        return present[0] if present else None
    first, flags = present[0], list(present[0].review_flags)
    paired = []
    for other in present[1:]:
        pairing = _pair(first.participants, other.participants)
        if pairing is None:
            flags.append(f"{_times(len(present))}的参与者不一致（{_kinds(first)} / {_kinds(other)}），请核对")
        else:
            paired.append((other, pairing))
    participants = first.participants
    if paired:
        participants = tuple(
            _apply(participant, ("bearing", "facing"),
                   [participant, *(other.participants[pairing[index]] for other, pairing in paired)])
            for index, participant in enumerate(first.participants))
        groups = Counter([_groups(first.participants, range(len(first.participants))),
                          *(_groups(other.participants, pairing) for other, pairing in paired)])
        if groups[_groups(first.participants, range(len(first.participants)))] * 2 <= len(paired) + 1:
            flags.append(f"{_times(len(present))}的任选分组不一致，请核对")
    merged = _apply(first, SCENE_FIELDS, present)
    return merged.model_copy(update={"participants": participants, "review_flags": tuple(dict.fromkeys(flags))})


def reconcile(first: SceneStructure | None, second: SceneStructure | None) -> SceneStructure | None:
    """Two independent readings (reconcile_readings)."""
    return reconcile_readings([first, second])
