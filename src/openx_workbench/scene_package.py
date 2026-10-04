from __future__ import annotations

import re
import json
import math
from dataclasses import dataclass, field, replace


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
class ParticipantSignature:
    """One non-ego participant as matching sees it: kind, ego-relative bearing and facing, behaviors.

    `actor` names the asset entity it was read from (empty for a requirement). Neither it nor the
    speed is part of the signature's identity. Any component may be "unknown".
    """

    kind: str
    bearing: str
    facing: str
    actions: tuple[str, ...]
    actor: str = field(default="", compare=False)
    # Initial speed of this participant, compared after pairing; None when not stated or not read.
    speed_kph: float | None = field(default=None, compare=False)

    def __post_init__(self) -> None:
        if not self.actions:
            # A participant without recorded actions stands still.
            object.__setattr__(self, "actions", ("static",))

    def key(self) -> str:
        """Canonical text form, e.g. ``vehicle@front_same_lane:same:cruise``; part of the index vectors."""
        return f"{self.kind}@{self.bearing}:{self.facing}:{'+'.join(self.actions)}"

    @property
    def has_unknown(self) -> bool:
        return "unknown" in (self.kind, self.bearing, self.facing, *self.actions)


@dataclass(frozen=True, slots=True)
class RetrievalQuery:
    text: str
    scenario_families: frozenset[str] = frozenset()
    participant_signatures: tuple[ParticipantSignature, ...] = ()
    participant_relations: frozenset[str] = frozenset()
    entity_kinds: frozenset[str] = frozenset()
    action_kinds: frozenset[str] = frozenset()
    trigger_kinds: frozenset[str] = frozenset()
    road_features: frozenset[str] = frozenset()
    parameters: tuple[tuple[str, float], ...] = ()
    evidence: tuple[EvidenceRef, ...] = ()
    structured: bool = False
    tested_function: str = ""
    ego_actions: frozenset[str] = frozenset()
    target_speeds_kph: tuple[float, ...] = ()
    environment: tuple[tuple[str, str], ...] = ()
    unverified: tuple[str, ...] = ()


STRUCTURE_KINDS = {
    "乘用车": "vehicle",
    "卡车": "truck",
    "客车": "bus",
    "厢式车": "van",
    "挂车": "trailer",
    "摩托车": "motorcycle",
    "两轮车": "cyclist",
    "三轮车": "tricycle",
    "行人": "pedestrian",
    "障碍物": "obstacle",
    "未知": "unknown",
}
STRUCTURE_ACTIONS = {
    "静止": "static",
    "匀速行驶": "cruise",
    "变速": "speed_change",
    "刹停": "stop",
    "变道": "lane_change",
    "定距跟车": "following",
    "倒车": "reverse",
    "被测系统控制": "system_control",
    "未知": "unknown",
}
STRUCTURE_BEARINGS = dict(
    zip(
        (
            "正前方",
            "正后方",
            "并排同车道",
            "左前方",
            "左后方",
            "左并排",
            "右前方",
            "右后方",
            "右并排",
            "未知方位",
        ),
        (
            "front_same_lane",
            "rear_same_lane",
            "alongside_same_lane",
            "front_left",
            "rear_left",
            "alongside_left",
            "front_right",
            "rear_right",
            "alongside_right",
            "unknown",
        ),
    )
)
STRUCTURE_FACING = {
    "同向": "same",
    "对向": "opposite",
    "横向": "crossing",
    "未知": "unknown",
}
STRUCTURE_ROADS = {
    "直道": "straight",
    "弯道": "curve",
    "交叉口": "junction",
    "高速路": "motorway",
}
STRUCTURE_TRIGGERS = {
    "TTC": "ttc",
    "相对距离": "distance",
    "绝对距离": "distance",
    "车头时距": "headway",
}


def query_structure_text(query: RetrievalQuery) -> str:
    """Name-free canonical text shared by requirement and asset recall routes."""
    return json.dumps(
        {
            "function": query.tested_function,
            "participants": sorted(item.key() for item in query.participant_signatures),
            "ego_actions": sorted(query.ego_actions),
            "road": sorted(query.road_features),
            "triggers": sorted(query.trigger_kinds),
            "params": query.parameters,
            "target_speeds": query.target_speeds_kph,
            "environment": query.environment,
        },
        ensure_ascii=False,
        sort_keys=True,
    )


def _structured_query(package: ScenePackage) -> RetrievalQuery:
    from .pdf_v2.scene_schemas import SceneStructure

    structure = SceneStructure.model_validate(package.structure).model_dump(mode="json")
    params = structure["params"]
    for key, value in params.items():
        numbers = value if key == "target_speeds_kph" else [value]
        if any(
            isinstance(number, (int, float))
            and (not math.isfinite(number) or number < 0)
            for number in numbers
        ):
            raise ValueError(f"{key} must contain finite nonnegative values.")
    participants = structure["participants"]
    speeds = [participant.get("speed_kph") for participant in participants]
    signatures = []
    unverified = []
    for participant, speed in zip(participants, speeds):
        signatures.append(
            ParticipantSignature(
                kind=STRUCTURE_KINDS[participant["kind"]],
                bearing=STRUCTURE_BEARINGS[participant["bearing"]],
                facing=STRUCTURE_FACING[participant["facing"]],
                # A requirement that names no behavior leaves it open, unlike an asset.
                actions=tuple(sorted(STRUCTURE_ACTIONS[item] for item in participant["actions"]))
                or ("unknown",),
                speed_kph=float(speed) if speed is not None else None,
            )
        )
        if participant["age"] != "未知":
            unverified.append("participant age=" + participant["age"])
    numeric = tuple(
        (target, float(params[source]))
        for source, target in (
            ("ego_speed_kph", "ego_speed_kph"),
            ("ttc_value", "ttc_s"),
            ("fog_visibility_m", "fog_visibility_m"),
        )
        if params[source] is not None
    )
    environment = tuple(
        (key, mapping[params[key]])
        for key, mapping in (
            (
                "weather",
                {
                    "晴天": "dry",
                    "雨天": "rain",
                    "雪天": "snow",
                    "雾天": "fog",
                    "沙尘": "dust",
                },
            ),
            ("time_of_day", {"日间": "day", "夜间": "night"}),
        )
        if params[key] in mapping
    )
    # Keep unsupported declared requirements visible in the verdict. They must
    # never disappear just because the XML reader does not yet understand them.
    for key in (
        "relations",
        "venue_features",
        "lane_marking",
        "parking_operation",
        "test_intent",
    ):
        if structure[key] and structure[key] != "未知":
            unverified.append(f"{key}={structure[key]}")
    for key in (
        "lateral_direction",
        "curve_radius_m",
        "lane_count",
        "lane_direction",
        "end_condition",
    ):
        if params[key] is not None and params[key] != "未知":
            unverified.append(f"{key}={params[key]}")
    road = structure["road_class"]
    if road != "未知" and road not in STRUCTURE_ROADS:
        unverified.append("road_class=" + road)
    for trigger in structure["semantic_triggers"]:
        if trigger not in STRUCTURE_TRIGGERS:
            unverified.append("trigger=" + trigger)
    query = RetrievalQuery(
        text=" ".join((package.title, package.preferred_text)),
        structured=True,
        participant_signatures=tuple(sorted(signatures, key=ParticipantSignature.key)),
        road_features=frozenset([STRUCTURE_ROADS[road]])
        if road in STRUCTURE_ROADS
        else frozenset(),
        trigger_kinds=frozenset(
            STRUCTURE_TRIGGERS[item]
            for item in structure["semantic_triggers"]
            if item in STRUCTURE_TRIGGERS
        ),
        parameters=tuple(sorted(numeric)),
        evidence=tuple(package.evidence),
        tested_function=structure["tested_function"]
        if structure["tested_function"] != "未知"
        else "",
        ego_actions=frozenset(
            STRUCTURE_ACTIONS[item]
            for item in structure["ego_actions"]
            if item != "未知"
        ),
        # Speeds bound to participants replace the unbound list; either way duplicates count.
        target_speeds_kph=tuple(sorted(float(speed) for speed in speeds if speed is not None))
        if any(speed is not None for speed in speeds)
        else tuple(sorted(params["target_speeds_kph"])),
        environment=environment,
        unverified=tuple(unverified),
    )
    if not any(
        (
            query.participant_signatures,
            query.road_features,
            query.parameters,
            query.tested_function,
            query.ego_actions,
            query.target_speeds_kph,
            query.environment,
            query.trigger_kinds,
            query.unverified,
        )
    ):
        query = replace(query, unverified=("no extracted structural requirements",))
    return query


_ENTITY_TERMS = {
    "vehicle": ("vehicle", "car", "机动车", "车辆", "汽车", "目标车", "前车"),
    "motorcycle": ("ptw", "motorcycle", "motorbike", "motorcyclist", "摩托车"),
    "pedestrian": ("pedestrian", "行人"),
    "cyclist": ("cyclist", "bicycle", "自行车", "骑行者"),
}
_ACTION_TERMS = {
    "lane_change": (
        "lane change",
        "lane-change",
        "lanechange",
        "cut in",
        "cut-in",
        "换道",
        "切入",
    ),
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
    if package.structure:
        return _structured_query(package)
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


def synchronize_structure(package: ScenePackage) -> ScenePackage:
    """Derive compatibility fields from the same facts used by matching."""
    if not package.structure:
        return package
    query = _structured_query(package)
    package.entities = sorted({signature.kind for signature in query.participant_signatures})
    package.actions = sorted(
        query.ego_actions
        | {action for signature in query.participant_signatures for action in signature.actions}
    )
    package.triggers = sorted(query.trigger_kinds)
    package.road_types = sorted(query.road_features)
    package.parameters = dict(query.parameters)
    package.weather = (
        [dict(query.environment)["weather"]]
        if "weather" in dict(query.environment)
        else []
    )
    package.time_of_day = (
        [dict(query.environment)["time_of_day"]]
        if "time_of_day" in dict(query.environment)
        else []
    )
    package.classification.update(
        function=package.structure.get("tested_function", "未知"),
        road_type=package.structure.get("road_class", "未知"),
        intent=package.structure.get("test_intent", "未知"),
    )
    return package


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
