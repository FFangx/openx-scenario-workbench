from __future__ import annotations

import re
from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class EvidenceRef:
    source_pdf: str
    section_id: str
    page_start: int
    page_end: int
    source_text: str


@dataclass(slots=True)
class ScenePackage:
    package_id: str
    title: str
    preferred_text: str
    source_standard: str = ""
    evidence: list[EvidenceRef] = field(default_factory=list)
    road_types: list[str] = field(default_factory=list)
    weather: list[str] = field(default_factory=list)
    time_of_day: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    actions: list[str] = field(default_factory=list)
    triggers: list[str] = field(default_factory=list)
    parameters: dict[str, float] = field(default_factory=dict)
    classification: dict = field(default_factory=dict)
    structure: dict = field(default_factory=dict)
    extraction: dict = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    text: str
    scenario_families: frozenset[str] = frozenset()
    participant_signatures: tuple[str, ...] = ()
    participant_relations: frozenset[str] = frozenset()
    entity_kinds: frozenset[str] = frozenset()
    action_kinds: frozenset[str] = frozenset()
    trigger_kinds: frozenset[str] = frozenset()
    road_features: frozenset[str] = frozenset()
    parameters: tuple[tuple[str, float], ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()


_ENTITY_TERMS = {
    "vehicle": ("vehicle", "car", "机动车", "车辆", "汽车", "目标车", "前车"),
    "motorcycle": ("ptw", "motorcycle", "motorbike", "motorcyclist", "摩托车"),
    "pedestrian": ("pedestrian", "行人"),
    "cyclist": ("cyclist", "bicycle", "自行车", "骑行者"),
}
_ACTION_TERMS = {
    "lane_change": ("lane change", "lane-change", "lanechange", "cut in", "cut-in", "换道", "切入"),
    "braking": ("brake", "braking", "deceler", "制动", "减速"),
    "speed": ("accelerat", "speed", "加速", "车速", "速度"),
    "crossing": ("crossing", "cross", "横穿", "穿行"),
}
_TRIGGER_TERMS = {
    "ttc": ("ttc", "time to collision", "timetocollision", "碰撞时间"),
    "distance": ("distance", "距离", "间距"),
    "headway": ("time headway", "headway", "时距"),
}
_ROAD_TERMS = {
    "straight": ("straight", "直道", "直线"),
    "curve": ("curve", "curved", "bend", "弯道", "曲线"),
    "junction": ("junction", "intersection", "交叉口", "路口"),
    "motorway": ("motorway", "highway", "高速公路", "高速"),
}
_SCENARIO_FAMILY_TERMS = {
    "unresponsive_driver": ("unresponsive driver", "indirect sensing 80km/h"),
    "car_to_car": ("car-to-car", "car to car", "ccrs", "ccrm", "ccrb"),
    "car_to_ptw": ("car-to-ptw", "car to ptw", "cmrs", "cmrm", "cmrb"),
    "car_to_vru": ("car-to-vru", "car to vru", "cbla", "cpla"),
    "overtaking_lane_change": (
        "lane change with overtaking vehicle",
        "overtaking vehicle",
        "overtaking intentional",
    ),
}
_RELATION_TERMS = {
    "front": ("in front of", "ahead of", "前方", "前车"),
    "rear": ("behind", "from the rear", "后方", "后车"),
    "left": ("left side", "left lane", "左侧", "左车道"),
    "right": ("right side", "right lane", "右侧", "右车道"),
    "adjacent_lane": ("adjacent lane", "neighbouring lane", "相邻车道"),
}


def scene_package_to_query(package: ScenePackage) -> RetrievalQuery:
    text = " ".join(
        part
        for part in (
            package.title,
            package.preferred_text,
            " ".join(package.entities),
            " ".join(package.actions),
            " ".join(package.triggers),
            " ".join(package.road_types),
        )
        if part
    )
    return RetrievalQuery(
        text=text,
        scenario_families=frozenset(canonical_scenario_families(package.title)),
        participant_relations=frozenset(canonical_participant_relations(text)),
        entity_kinds=frozenset(_canonical_terms(text, _ENTITY_TERMS)),
        action_kinds=frozenset(_canonical_terms(text, _ACTION_TERMS)),
        trigger_kinds=frozenset(_canonical_terms(text, _TRIGGER_TERMS)),
        road_features=frozenset(_canonical_terms(text, _ROAD_TERMS)),
        parameters=tuple(sorted(package.parameters.items())),
        evidence=tuple(package.evidence),
    )


def canonical_scenario_families(text: str) -> set[str]:
    return _canonical_terms(text, _SCENARIO_FAMILY_TERMS)


def canonical_participant_relations(text: str) -> set[str]:
    return _canonical_terms(text, _RELATION_TERMS)


def extract_parameters(text: str) -> dict[str, float]:
    patterns = {
        "ttc_s": r"\bTTC\s*(?:=|≤|<|为|不大于)?\s*(\d+(?:\.\d+)?)\s*s\b",
        "ego_speed_kph": r"(?:ego|主车|自车)[^。；;\n]{0,24}?(\d+(?:\.\d+)?)\s*km/h",
        "distance_m": r"(?:distance|距离|间距)[^。；;\n]{0,16}?(\d+(?:\.\d+)?)\s*m\b",
    }
    values: dict[str, float] = {}
    for name, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            values[name] = float(match.group(1))
    return values


def canonical_features(text: str) -> tuple[set[str], set[str], set[str], set[str]]:
    return (
        _canonical_terms(text, _ENTITY_TERMS),
        _canonical_terms(text, _ACTION_TERMS),
        _canonical_terms(text, _TRIGGER_TERMS),
        _canonical_terms(text, _ROAD_TERMS),
    )


def _canonical_terms(text: str, vocabulary: dict[str, tuple[str, ...]]) -> set[str]:
    normalized = text.casefold()
    return {
        canonical
        for canonical, terms in vocabulary.items()
        if any(term.casefold() in normalized for term in terms)
    }
