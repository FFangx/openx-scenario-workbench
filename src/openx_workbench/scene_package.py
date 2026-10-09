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


def clause_text(title: str, body: str) -> str:
    """A clause as a person reads it: its heading line, then its body. A one-sentence clause, a list
    item or a clause made only of sub-clauses is all heading."""
    title, body = (title or "").strip(), (body or "").strip()
    if not title or title in body:
        return body
    return f"{title}\n{body}" if body else title


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
    # Takes no part in the test (scene_facts.background_participants): an asset's parked cars or
    # bystanders. Left over, it costs little; it can still stand for a requested participant.
    background: bool = field(default=False, compare=False)
    # What an asset's 3D model shows beyond its category (scene_facts.model_traits): a child, a
    # tricycle authored as a car. Evidence that confirms a requirement, never a conflict.
    traits: tuple[str, ...] = field(default=(), compare=False)
    # Which way it faces relative to the ego once the ego's routing has turned it (an asset whose
    # ego turns at a junction; empty otherwise). A requirement may describe either moment: people
    # crossing the road the ego turns into walk the ego's starting way.
    turned_facing: str = field(default="", compare=False)
    # A requirement's alternatives share a label: one of them takes part in a run (a car, a tricycle
    # or a pedestrian stands ahead). Empty: always there. Only a requirement has it.
    alternative: str = field(default="", compare=False)
    # A requirement's stated pedestrian age (儿童 / 成人), kept among `unverified` until an asset
    # shows it; carried here so an alternative left out takes its age along.
    age: str = field(default="", compare=False)
    # Which of "bearing" and "facing" a requirement read from a figure rather than its text: an
    # aid to ranking, never a conflict (reuse_policy.TIER_FIGURE). Only a requirement has it.
    from_figure: tuple[str, ...] = field(default=(), compare=False)

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
    # Scenery props (cones, barriers) grouped by position: they can stand for a
    # requested obstacle but are not participants. Only an asset has them.
    scenery_signatures: tuple[ParticipantSignature, ...] = ()
    # (occluder kind, occluded kind) pairs, e.g. ("vehicle", "pedestrian").
    occlusions: frozenset[tuple[str, str]] = frozenset()
    # A driver-intervention test (driver inputs override the system); None: not stated.
    driver_intervention: bool | None = None
    # The driver asks the system for a lane change or confirms one (scene_facts.driver_requests).
    # Only an asset has it.
    driver_request: bool = False
    parking_operation: str = ""  # park_in / park_out
    # Lanes the road must offer at least: "same_direction" (单向 N) or "total" (双向 N, or
    # a count whose direction is not stated). A lower bound: one more lane never hurts a test.
    lane_count: int | None = None
    lane_count_scope: str = ""
    lane_marking: str = ""  # "solid" / "broken": the road must have such a line
    # The kind of test an asset's named checks show (an accelerator, see scene_facts.condition_facts);
    # a requirement keeps its declared intent among `unverified` until an asset confirms it.
    test_intent: str = ""
    # Which way an asset's ego moves sideways (scene_facts.lateral_direction), likewise confirming.
    lateral_direction: str = ""
    # Radius of the curve: a requirement's stated one (also kept among `unverified` until an
    # asset's road states its own), an asset's first curve ahead of the ego.
    curve_radius_m: float | None = None
    # Where an asset's ego drives beyond the road shape (scene_facts.in_tunnel), likewise confirming.
    venue_features: frozenset[str] = frozenset()
    # Which way the ego leaves the junction or roundabout: "straight" / "left" / "right" / "u_turn";
    # empty when not stated (requirement) or not readable (asset, scene_facts.ego_turn).
    ego_turn: str = ""
    # Traffic control a requirement's test relies on ("traffic_light" / "speed_limit") and the
    # speed-limit values it sets up (several: alternatives). The asset side is its road file.
    traffic_controls: frozenset[str] = frozenset()
    speed_limits_kph: tuple[float, ...] = ()
    # Which of its direction's lanes a requirement's ego drives in (最左侧车道 / 最右侧车道 / 中间车道).
    ego_lane: str = ""
    # The requirement's scene facts ("ego_turn", "ego_lane") read from a figure rather than its text.
    figure_facts: frozenset[str] = frozenset()


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
    "偏离车道": "lane_departure",
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
STRUCTURE_LANE_MARKINGS = {"实线": "solid", "虚线": "broken"}
STRUCTURE_PARKING = {"泊入": "park_in", "泊出": "park_out"}
STRUCTURE_INTENTS = {"激活边界试验": "activation_boundary"}
STRUCTURE_AGES = {"儿童": "child"}
STRUCTURE_LATERAL = {"左": "left", "右": "right"}
STRUCTURE_VENUES = {"隧道": "tunnel"}
STRUCTURE_TURNS = {"直行": "straight", "左转": "left", "右转": "right", "掉头": "u_turn"}
STRUCTURE_TRAFFIC_CONTROLS = {"交通信号灯": "traffic_light", "限速标志": "speed_limit"}
STRUCTURE_TRIGGERS = {
    "TTC": "ttc",
    "相对距离": "distance",
    "绝对距离": "distance",
    "车头时距": "headway",
}


def query_structure_text(query: RetrievalQuery) -> str:
    """Name-free canonical text shared by requirement and asset recall routes."""
    content = {
        "function": query.tested_function,
        # Scenery reads as the obstacles a requirement names.
        "participants": sorted(item.key() for item in (*query.participant_signatures, *query.scenery_signatures)),
        "ego_actions": sorted(query.ego_actions),
        "road": sorted(query.road_features),
        "triggers": sorted(query.trigger_kinds),
        "params": query.parameters,
        "target_speeds": query.target_speeds_kph,
        "environment": query.environment,
    }
    if query.occlusions:
        content["occlusions"] = sorted(f"{blocker}>{target}" for blocker, target in query.occlusions)
    if query.driver_intervention:
        content["driver_intervention"] = True
    if query.parking_operation:
        content["parking"] = query.parking_operation
    return json.dumps(content, ensure_ascii=False, sort_keys=True)


def _from_figure(item: dict, fields: tuple[str, ...]) -> tuple[str, ...]:
    """The fields the extraction read from a figure; a person's edit of a field drops its evidence."""
    evidence = item.get("evidence") or {}
    return tuple(name for name in fields if (evidence.get(name) or {}).get("source") == "图")


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
                alternative=participant.get("alternative_group") or "",
                age=participant["age"] if participant["age"] != "未知" else "",
                from_figure=_from_figure(participant, ("bearing", "facing")),
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
    occlusions = frozenset(
        (STRUCTURE_KINDS[item["subject"]], STRUCTURE_KINDS[item["object"]])
        for item in structure["relations"] if item["relation"] == "遮挡"
    )
    # A driver-intervention test is read from the asset's driver-input overrides;
    # the other intents (functional, false activation, boundary) are not.
    intervention = structure["test_intent"] == "驾驶员干预试验"
    # Keep unsupported declared requirements visible in the verdict. They must
    # never disappear just because the XML reader does not yet understand them.
    venues = structure["venue_features"]
    if venues and venues != "未知":
        # One item per venue, so an asset can confirm each (a tunnel by its lighting).
        unverified.extend(f"venue_features={item}" for item in ([venues] if isinstance(venues, str) else venues))
    lane_marking = STRUCTURE_LANE_MARKINGS.get(structure["lane_marking"] or "", "")
    if structure["lane_marking"] and structure["lane_marking"] != "未知" and not lane_marking:
        unverified.append(f"lane_marking={structure['lane_marking']}")
    lane_count = params["lane_count"]
    # 单向 N counts one direction; 双向 N both (SM's reading: an odd 双向 N, as in 双向单车道,
    # means N each way). The lane direction alone is no requirement: it only scopes the count.
    lane_scope = ""
    if isinstance(lane_count, (int, float)) and lane_count >= 1:
        lane_count = int(lane_count)
        if params["lane_direction"] == "单向":
            lane_scope = "same_direction"
        elif params["lane_direction"] == "双向" and lane_count % 2:
            lane_scope = "same_direction"
        else:
            lane_scope = "total"
    else:
        lane_count = None
    if structure["test_intent"] not in {"未知", "驾驶员干预试验"}:
        unverified.append(f"test_intent={structure['test_intent']}")
    # Which of its direction's lanes the ego drives in; an asset's start lane is not compared yet.
    # Read from a figure, it is checked against the figure instead (reuse_structured).
    figure_facts = frozenset(_from_figure(structure, ("ego_turn", "ego_lane")))
    ego_lane = structure.get("ego_lane", "未知")
    if ego_lane != "未知" and "ego_lane" not in figure_facts:
        unverified.append(f"ego_lane={ego_lane}")
    for key in (
        "lateral_direction",
        "curve_radius_m",
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
        occlusions=occlusions,
        driver_intervention=True if intervention else (False if structure["test_intent"] != "未知" else None),
        parking_operation=STRUCTURE_PARKING.get(structure["parking_operation"], ""),
        lane_count=lane_count,
        lane_count_scope=lane_scope,
        lane_marking=lane_marking,
        curve_radius_m=params["curve_radius_m"],
        ego_turn=STRUCTURE_TURNS.get(structure.get("ego_turn", ""), ""),
        traffic_controls=frozenset(STRUCTURE_TRAFFIC_CONTROLS[item] for item in structure.get("traffic_controls", ())),
        speed_limits_kph=tuple(params.get("speed_limits_kph", ())),
        ego_lane=ego_lane if ego_lane != "未知" else "",
        figure_facts=figure_facts,
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
            query.occlusions,
            query.driver_intervention,
            query.parking_operation,
            query.lane_count,
            query.lane_marking,
            query.ego_turn,
            query.traffic_controls,
            query.speed_limits_kph,
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
