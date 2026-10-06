"""Adapted ScenarioManager V2 core; see docs/PDF_MIGRATION.md."""
from __future__ import annotations

import math
import re
from collections.abc import Mapping
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .models import SectionTree

SCENE_FIRST_VERSION = "scene-first-v1"

SceneActor = Literal[
    "ego",
    "target_vehicle",
    "vru",
    "static_object",
    "occluder",
    "traffic_element",
    "other",
]

NodeOrigin = Literal["declared_member", "declared_shared", "expanded"]

RoadClass = Literal[
    "直道", "弯道", "交叉口", "环岛", "停车场", "匝道合流", "高速路", "未知",
]

ParticipantKind = Literal[
    "乘用车", "卡车", "客车", "厢式车", "挂车", "摩托车", "两轮车", "三轮车",
    "行人", "障碍物", "未知",
]

Bearing = Literal[
    "正前方", "正后方", "并排同车道",
    "左前方", "左后方", "左并排",
    "右前方", "右后方", "右并排",
    "未知方位",
]

Facing = Literal["同向", "对向", "横向", "未知"]

ParticipantAction = Literal["静止", "匀速行驶", "变速", "刹停", "变道", "定距跟车"]

EgoAction = Literal[
    "匀速行驶", "变速", "刹停", "变道", "定距跟车", "倒车", "被测系统控制", "未知",
]

RelationKind = Literal["遮挡"]

SemanticTrigger = Literal[
    "TTC", "相对距离", "绝对距离", "车头时距", "速度", "相对速度",
]

Weather = Literal["晴天", "雨天", "雾天", "雪天", "沙尘", "未知"]
TimeOfDay = Literal["日间", "夜间", "未知"]

PedestrianAge = Literal["儿童", "成人", "未知"]

VenueFeature = Literal["隧道", "收费站", "服务区"]

LaneMarking = Literal["实线", "虚线", "未知"]

ParkingOperation = Literal["泊入", "泊出", "未知"]

TestIntent = Literal["功能试验", "误作用试验", "激活边界试验", "驾驶员干预试验", "未知"]

LateralDirection = Literal["左", "右", "未知"]

LaneDirection = Literal["单向", "双向", "未知"]

# Which way the ego leaves a junction or roundabout.
EgoTurn = Literal["直行", "左转", "右转", "掉头", "未知"]

# Traffic control whose presence the test relies on (a traffic-light test, a speed-limit test).
TrafficControl = Literal["交通信号灯", "限速标志"]

TestedFunction = Literal[

    "NOA", "AEB", "ACC", "LSS", "APA", "FCW",
    "BSM", "ALCA", "RCTA", "LDW", "LDP", "TSA",

    "LKA", "ELK", "AVP", "ISL", "DFM", "DAM", "DOW",
    "未知",
]

_ACTION_TO_SIGNATURE: dict[str, tuple[str, ...]] = {"静止": ()}

class SceneParticipant(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)

    kind: ParticipantKind
    bearing: Bearing = "未知方位"
    facing: Facing = "未知"
    actions: tuple[ParticipantAction, ...] = ()

    age: PedestrianAge = "未知"
    # This participant's own initial speed. Optional, and left out of the stored structure when
    # unset, so revisions saved before it existed read back unchanged.
    speed_kph: float | None = Field(default=None, ge=0, allow_inf_nan=False, exclude_if=lambda value: value is None)
    # Participants sharing a label are alternatives, one of which takes part in a run ("a car, a
    # tricycle or a pedestrian stands ahead"). Optional and left out when unset, like the speed.
    alternative_group: str | None = Field(default=None, min_length=1, max_length=16,
                                          exclude_if=lambda value: value is None)

    def signature_actions(self) -> tuple[str, ...]:

        out: set[str] = set()
        for action in self.actions:
            out.update(_ACTION_TO_SIGNATURE.get(action, (action,)))
        return tuple(sorted(out))

class SceneRelation(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)

    subject: ParticipantKind
    relation: RelationKind
    object: ParticipantKind

class SceneParams(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)

    ego_speed_kph: float | None = None
    target_speeds_kph: tuple[float, ...] = ()
    weather: Weather = "未知"
    time_of_day: TimeOfDay = "未知"
    ttc_value: float | None = None

    lateral_direction: LateralDirection = "未知"
    curve_radius_m: float | None = None

    lane_count: float | None = None
    lane_direction: LaneDirection = "未知"

    fog_visibility_m: float | None = None
    # Speed-limit sign values the test sets up; several are alternatives (chosen by the set speed).
    # Left out of the stored structure when empty, so earlier revisions read back unchanged.
    speed_limits_kph: tuple[float, ...] = Field(default=(), exclude_if=lambda value: not value)

    end_condition: str | None = None

class SceneStructure(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid", json_schema_serialization_defaults_required=True)

    road_class: RoadClass = "未知"

    tested_function: TestedFunction = "未知"

    tested_function_raw: str | None = None
    ego_actions: tuple[EgoAction, ...] = ()
    participants: tuple[SceneParticipant, ...] = ()
    relations: tuple[SceneRelation, ...] = ()
    semantic_triggers: tuple[SemanticTrigger, ...] = ()

    venue_features: tuple[VenueFeature, ...] = ()
    lane_marking: LaneMarking = "未知"
    parking_operation: ParkingOperation = "未知"
    test_intent: TestIntent = "未知"
    # Left out of the stored structure at their defaults, so earlier revisions read back unchanged.
    ego_turn: EgoTurn = Field(default="未知", exclude_if=lambda value: value == "未知")
    traffic_controls: tuple[TrafficControl, ...] = Field(default=(), exclude_if=lambda value: not value)
    params: SceneParams = SceneParams()

class ProposedScene(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    name: str = Field(min_length=1)

    story: str = Field(min_length=1)
    actors: tuple[SceneActor, ...] = ()
    anchor_node_id: str = Field(min_length=1)
    member_node_ids: tuple[str, ...] = ()

    shared_container_node_ids: tuple[str, ...] = ()
    confidence: float = Field(ge=0.0, le=1.0)

    structure: SceneStructure | None = None

class SceneProposal(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    proposal_version: Literal["scene-first-v1"] = SCENE_FIRST_VERSION
    scenes: tuple[ProposedScene, ...] = ()

    document_config_node_ids: tuple[str, ...] = ()

    rejected_node_ids: tuple[str, ...] = ()

    redirected_node_ids: tuple[tuple[str, str], ...] = ()

    rejected_structure_values: tuple[str, ...] = ()

class ResolvedScene(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    scene_version: Literal["scene-first-v1"] = SCENE_FIRST_VERSION
    scene_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    story: str = Field(min_length=1)
    actors: tuple[SceneActor, ...] = ()
    anchor_node_id: str = Field(min_length=1)
    confidence: float = Field(ge=0.0, le=1.0)

    structure: SceneStructure | None = None

    declared_member_node_ids: tuple[str, ...] = ()

    declared_shared_node_ids: tuple[str, ...] = ()

    expansion_added_node_ids: tuple[str, ...] = ()

    node_ids: tuple[str, ...]

    @model_validator(mode="after")
    def _validate_closure(self) -> "ResolvedScene":

        declared = set(self.declared_member_node_ids) | set(self.declared_shared_node_ids)
        expected = declared | set(self.expansion_added_node_ids)
        if set(self.node_ids) != expected:
            raise ValueError("node_ids must equal declared members/shared plus expansion")
        if declared & set(self.expansion_added_node_ids):
            raise ValueError("expansion_added_node_ids must not overlap declared node ids")
        if self.anchor_node_id not in set(self.node_ids):
            raise ValueError("anchor_node_id must be part of the scene node set")
        return self

class SceneFirstExtraction(BaseModel):

    model_config = ConfigDict(frozen=True, extra="forbid")

    extraction_version: Literal["scene-first-v1"] = SCENE_FIRST_VERSION
    standard: str = Field(min_length=1)
    heading_decoder: str = Field(min_length=1)
    scenes: tuple[ResolvedScene, ...] = ()

    document_context_node_ids: tuple[str, ...] = ()

    rejected_node_ids: tuple[str, ...] = ()

    @model_validator(mode="after")
    def _validate_scene_ids_unique(self) -> "SceneFirstExtraction":
        scene_ids = [scene.scene_id for scene in self.scenes]
        if len(scene_ids) != len(set(scene_ids)):
            raise ValueError("scene_id must be unique within an extraction")
        return self

    @property
    def covered_node_ids(self) -> frozenset[str]:

        return frozenset(
            node_id for scene in self.scenes for node_id in scene.node_ids
        )

def normalize_node_id(value: object) -> str:

    text = str(value or "").strip()
    if "]" in text:
        text = text.split("]", 1)[0]
    return text.strip().strip("[]").strip()

_CLAUSE_LEAD_NUMBER_RE = re.compile(
    r"(?:^|(?<=[\n\r\u3002\uff1b;]))[^\S\n\r]*"
    r"([A-Za-z]?\d+(?:\.\d+)+)(?![\d])"
    r"(?=\s*[^\s.\uff0e\u3002\uff1b;\u3001])"
)

def build_buried_clause_index(
    text_by_node: Mapping[str, str],
    known_node_ids: frozenset[str],
) -> dict[str, str]:

    index: dict[str, str] = {}
    for node_id, text in text_by_node.items():
        if not text:
            continue
        for match in _CLAUSE_LEAD_NUMBER_RE.finditer(text):
            clause = normalize_node_id(match.group(1))
            if not clause or clause in known_node_ids or clause in index:
                continue
            index[clause] = node_id
    return index

def _literal_values(annotation: object) -> frozenset[str]:

    return frozenset(get_args(annotation))

_ROAD_CLASS_VALUES = _literal_values(RoadClass)
_TESTED_FUNCTION_VALUES = _literal_values(TestedFunction)
_KIND_VALUES = _literal_values(ParticipantKind)
_BEARING_VALUES = _literal_values(Bearing)
_FACING_VALUES = _literal_values(Facing)
_PARTICIPANT_ACTION_VALUES = _literal_values(ParticipantAction)
_EGO_ACTION_VALUES = _literal_values(EgoAction)
_RELATION_VALUES = _literal_values(RelationKind)
_TRIGGER_VALUES = _literal_values(SemanticTrigger)
_WEATHER_VALUES = _literal_values(Weather)
_TIME_VALUES = _literal_values(TimeOfDay)
_AGE_VALUES = _literal_values(PedestrianAge)
_VENUE_VALUES = _literal_values(VenueFeature)
_LANE_MARKING_VALUES = _literal_values(LaneMarking)
_PARKING_OP_VALUES = _literal_values(ParkingOperation)
_TEST_INTENT_VALUES = _literal_values(TestIntent)
_LATERAL_DIR_VALUES = _literal_values(LateralDirection)
_LANE_DIR_VALUES = _literal_values(LaneDirection)
_EGO_TURN_VALUES = _literal_values(EgoTurn)
_TRAFFIC_CONTROL_VALUES = _literal_values(TrafficControl)

def parse_scene_structure(raw: object, dropped: set[str]) -> SceneStructure | None:

    if not isinstance(raw, dict):
        return None

    def _pick(value: object, allowed: frozenset[str], field: str, default: str) -> str:
        text = str(value or "").strip()
        if not text:
            return default
        if text in allowed:
            return text
        dropped.add(f"{field}={text}")
        return default

    def _pick_many(values: object, allowed: frozenset[str], field: str) -> tuple[str, ...]:
        out: list[str] = []
        for item in values or ():
            text = str(item or "").strip()
            if not text:
                continue
            if text in allowed:
                if text not in out:
                    out.append(text)
            else:
                dropped.add(f"{field}={text}")
        return tuple(out)

    def _number(value: object, field: str) -> float | None:
        if value is None or value == "":
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            dropped.add(f"{field}={value!r}")
            return None

    def _speed(value: object, field: str = "participant_speed") -> float | None:
        speed = _number(value, field)
        if speed is not None and not (math.isfinite(speed) and speed >= 0):
            dropped.add(f"{field}={value!r}")
            return None
        return speed

    def _group(value: object) -> str | None:
        text = str(value or "").strip()
        if len(text) > 16:
            dropped.add(f"alternative_group={text}")
            return None
        return text or None

    participants: list[SceneParticipant] = []
    for item in raw.get("participants") or ():
        if not isinstance(item, dict):
            continue
        kind = _pick(item.get("kind"), _KIND_VALUES, "kind", "未知")
        participants.append(
            SceneParticipant(
                kind=kind,
                bearing=_pick(item.get("bearing"), _BEARING_VALUES, "bearing", "未知方位"),
                facing=_pick(item.get("facing"), _FACING_VALUES, "facing", "未知"),
                actions=_pick_many(item.get("actions"), _PARTICIPANT_ACTION_VALUES, "action"),
                age=_pick(item.get("age"), _AGE_VALUES, "age", "未知"),
                speed_kph=_speed(item.get("speed_kph")),
                alternative_group=_group(item.get("alternative_group")),
            )
        )

    relations: list[SceneRelation] = []
    for item in raw.get("relations") or ():

        if isinstance(item, dict):
            triple = (item.get("subject"), item.get("relation"), item.get("object"))
        elif isinstance(item, (list, tuple)) and len(item) == 3:
            triple = tuple(item)
        else:
            continue
        subject = _pick(triple[0], _KIND_VALUES, "relation.subject", "")
        relation = _pick(triple[1], _RELATION_VALUES, "relation.kind", "")
        obj = _pick(triple[2], _KIND_VALUES, "relation.object", "")
        if not (subject and relation and obj):
            continue
        relations.append(
            SceneRelation(subject=subject, relation=relation, object=obj)
        )

    params_raw = raw.get("params") if isinstance(raw.get("params"), dict) else {}
    target_speeds = tuple(
        speed for speed in (
            _number(item, "target_speed") for item in (params_raw.get("target_speeds_kph") or ())
        ) if speed is not None
    )
    end_condition_raw = str(params_raw.get("end_condition") or "").strip()
    params = SceneParams(
        ego_speed_kph=_number(params_raw.get("ego_speed_kph"), "ego_speed"),
        target_speeds_kph=target_speeds,
        weather=_pick(params_raw.get("weather"), _WEATHER_VALUES, "weather", "未知"),
        time_of_day=_pick(params_raw.get("time_of_day"), _TIME_VALUES, "time_of_day", "未知"),
        ttc_value=_number(params_raw.get("ttc_value"), "ttc"),
        lateral_direction=_pick(params_raw.get("lateral_direction"), _LATERAL_DIR_VALUES, "lateral_direction", "未知"),
        curve_radius_m=_number(params_raw.get("curve_radius_m"), "curve_radius"),
        lane_count=_number(params_raw.get("lane_count"), "lane_count"),
        lane_direction=_pick(params_raw.get("lane_direction"), _LANE_DIR_VALUES, "lane_direction", "未知"),
        fog_visibility_m=_number(params_raw.get("fog_visibility_m"), "fog_visibility"),
        speed_limits_kph=tuple(sorted({
            limit for limit in (_speed(item, "speed_limit") for item in (params_raw.get("speed_limits_kph") or ()))
            if limit
        })),

        end_condition=end_condition_raw[:120] or None,
    )

    return SceneStructure(
        road_class=_pick(raw.get("road_class"), _ROAD_CLASS_VALUES, "road_class", "未知"),

        tested_function=_pick(
            raw.get("tested_function"), _TESTED_FUNCTION_VALUES, "tested_function", "未知"),

        tested_function_raw=str(raw.get("tested_function_raw") or "").strip()[:120] or None,
        ego_actions=_pick_many(raw.get("ego_actions"), _EGO_ACTION_VALUES, "ego_action"),
        participants=tuple(participants),
        relations=tuple(relations),
        semantic_triggers=_pick_many(raw.get("semantic_triggers"), _TRIGGER_VALUES, "trigger"),
        venue_features=_pick_many(raw.get("venue_features"), _VENUE_VALUES, "venue"),
        lane_marking=_pick(raw.get("lane_marking"), _LANE_MARKING_VALUES, "lane_marking", "未知"),
        parking_operation=_pick(raw.get("parking_operation"), _PARKING_OP_VALUES, "parking_operation", "未知"),
        test_intent=_pick(raw.get("test_intent"), _TEST_INTENT_VALUES, "test_intent", "未知"),
        ego_turn=_pick(raw.get("ego_turn"), _EGO_TURN_VALUES, "ego_turn", "未知"),
        traffic_controls=_pick_many(raw.get("traffic_controls"), _TRAFFIC_CONTROL_VALUES, "traffic_control"),
        params=params,
    )

def parse_scene_proposal(
    raw: dict,
    *,
    known_node_ids: frozenset[str],
    buried_clause_owners: Mapping[str, str] | None = None,
) -> SceneProposal:

    rejected: set[str] = set()
    dropped_structure: set[str] = set()
    redirected: dict[str, str] = {}
    buried = buried_clause_owners or {}

    def _resolve(node_id: str) -> str:

        owner = buried.get(node_id)
        if owner and owner in known_node_ids:
            redirected[node_id] = owner
            return owner
        rejected.add(node_id)
        return ""

    def _filter(values: object) -> tuple[str, ...]:

        kept: list[str] = []
        for value in values or ():
            node_id = normalize_node_id(value)
            if not node_id:
                continue
            if node_id not in known_node_ids:
                node_id = _resolve(node_id)
                if not node_id:
                    continue
            if node_id not in kept:
                kept.append(node_id)
        return tuple(kept)

    scenes: list[ProposedScene] = []
    for entry in raw.get("scenes") or ():
        if not isinstance(entry, dict):
            continue
        anchor = normalize_node_id(entry.get("anchor_node_id"))
        if anchor and anchor not in known_node_ids:

            anchor = _resolve(anchor)
        if not anchor:
            continue
        actors = tuple(
            actor
            for actor in (entry.get("actors") or ())
            if actor in {
                "ego", "target_vehicle", "vru", "static_object",
                "occluder", "traffic_element", "other",
            }
        )
        scenes.append(
            ProposedScene(
                name=str(entry.get("name") or anchor),
                story=str(entry.get("story") or "").strip() or "(未提供场景描述)",
                actors=actors,
                anchor_node_id=anchor,
                member_node_ids=_filter(entry.get("member_node_ids")),
                shared_container_node_ids=_filter(entry.get("shared_container_node_ids")),
                confidence=float(entry.get("confidence") or 0.0),
                structure=parse_scene_structure(entry.get("structure"), dropped_structure),
            )
        )

    return SceneProposal(
        scenes=tuple(scenes),
        document_config_node_ids=_filter(raw.get("shared_config_node_ids")),
        rejected_node_ids=tuple(sorted(rejected)),
        redirected_node_ids=tuple(sorted(redirected.items())),
        rejected_structure_values=tuple(sorted(dropped_structure)),
    )

def expand_subtrees(
    node_ids: frozenset[str],
    child_ids_by_node: dict[str, tuple[str, ...]],
) -> frozenset[str]:

    expanded: set[str] = set()
    stack = list(node_ids)
    while stack:
        current = stack.pop()
        if current in expanded:
            continue
        expanded.add(current)
        stack.extend(child_ids_by_node.get(current, ()))
    return frozenset(expanded)

def resolve_scenes(
    proposal: SceneProposal,
    tree: SectionTree,
    *,
    standard: str,
    heading_decoder: str,
) -> SceneFirstExtraction:

    child_ids_by_node = {node.node_id: node.child_ids for node in tree.nodes}
    document_order = {node.node_id: index for index, node in enumerate(tree.nodes)}

    def _ordered(values: frozenset[str]) -> tuple[str, ...]:

        return tuple(sorted(values, key=lambda n: document_order.get(n, len(document_order))))

    scenes: list[ResolvedScene] = []
    for index, proposed in enumerate(proposal.scenes, start=1):
        declared_members = frozenset(proposed.member_node_ids) | {proposed.anchor_node_id}
        declared_shared = frozenset(proposed.shared_container_node_ids) - declared_members
        declared = declared_members | declared_shared
        expanded = expand_subtrees(declared, child_ids_by_node)

        expanded &= frozenset(child_ids_by_node)
        added = expanded - declared

        scenes.append(
            ResolvedScene(
                scene_id=f"scene-{index:03d}-{proposed.anchor_node_id}",
                name=proposed.name,
                story=proposed.story,
                actors=proposed.actors,
                anchor_node_id=proposed.anchor_node_id,
                confidence=proposed.confidence,
                structure=proposed.structure,
                declared_member_node_ids=_ordered(declared_members),
                declared_shared_node_ids=_ordered(declared_shared),
                expansion_added_node_ids=_ordered(added),
                node_ids=_ordered(declared | added),
            )
        )

    return SceneFirstExtraction(
        standard=standard,
        heading_decoder=heading_decoder,
        scenes=tuple(scenes),
        document_context_node_ids=_ordered(frozenset(proposal.document_config_node_ids)),
        rejected_node_ids=proposal.rejected_node_ids,
    )
