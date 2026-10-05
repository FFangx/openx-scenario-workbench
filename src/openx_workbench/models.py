from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class EntityIR:
    name: str
    kind: str
    category: str | None = None
    # 3D model of the object (its `name` attribute or `model` property) and its
    # BoundingBox width in metres, when declared.
    model: str | None = None
    width: float | None = None


@dataclass(slots=True)
class ActionIR:
    name: str
    kind: str
    actor: str | None = None
    target_value: float | None = None
    phase: str = "story"
    source_path: str = ""
    event_path: str = ""
    # Innermost action element (e.g. CustomCommandAction, LongitudinalDistanceAction).
    element: str = ""
    event_name: str = ""
    # SpeedAction dynamicsShape (step, linear, ...).
    shape: str | None = None
    # CustomCommandAction text.
    command: str | None = None
    # Active OverrideControllerValueAction channels and their values (Brake, Gear, ...).
    overrides: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class TriggerIR:
    scope: str
    condition_name: str
    kind: str
    delay: float | None = None
    edge: str | None = None
    value: float | None = None
    rule: str | None = None
    entity_refs: tuple[str, ...] = ()
    source_path: str = ""
    event_path: str = ""
    attributes: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class PositionIR:
    kind: str
    attributes: dict[str, str] = field(default_factory=dict)
    actor: str | None = None
    orientation: dict[str, str] = field(default_factory=dict)


@dataclass(slots=True)
class ScenarioIR:
    name: str | None = None
    description: str | None = None
    author: str | None = None
    revision: str | None = None
    road_file: str | None = None
    entities: list[EntityIR] = field(default_factory=list)
    actions: list[ActionIR] = field(default_factory=list)
    triggers: list[TriggerIR] = field(default_factory=list)
    positions: list[PositionIR] = field(default_factory=list)
    environment: dict[str, str | float] = field(default_factory=dict)
    parameters: list[dict[str, str]] = field(default_factory=list)
    parameter_issues: list[dict[str, str]] = field(default_factory=list)
    parameter_resolutions: list[dict[str, str]] = field(default_factory=list)
    events: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class RoadIR:
    name: str | None = None
    revision: str | None = None
    road_ids: list[str] = field(default_factory=list)
    total_length: float = 0.0
    lane_count: int = 0
    lane_types: dict[str, int] = field(default_factory=dict)
    geometry_types: dict[str, int] = field(default_factory=dict)
    junction_count: int = 0
    signal_count: int = 0
    object_count: int = 0
    # Driving lanes only (see parser._lane_profile); 0 when none were read.
    lanes_same_direction: int = 0  # most driving lanes one direction offers on one cross-section
    lanes_total: int = 0  # most driving lanes of both directions on one cross-section
    lane_markings: list[str] = field(default_factory=list)  # "solid"/"broken" drawn on driving lanes
    # The referenced OpenDRIVE file is not available (e.g. a simulator's
    # built-in map). Only the map name is known; `inferred_features` are
    # road types read from that name, never from geometry.
    file_missing: bool = False
    inferred_features: list[str] = field(default_factory=list)


@dataclass(slots=True)
class ParseBundle:
    scenario: ScenarioIR
    road: RoadIR
    warnings: list[str] = field(default_factory=list)
    road_geometry: dict[str, Any] = field(default_factory=dict, repr=False)
    validation: dict[str, Any] = field(default_factory=dict)
    # Authoring-tool metadata outside the OpenSCENARIO file, such as a
    # ScenarioManager case's map and environment presets.
    source_case: dict[str, Any] = field(default_factory=dict, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario": asdict(self.scenario),
            "road": asdict(self.road),
            "warnings": list(self.warnings),
            "validation": self.validation,
        }
