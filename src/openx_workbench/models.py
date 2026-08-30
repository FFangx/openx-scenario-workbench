from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class EntityIR:
    name: str
    kind: str
    category: str | None = None


@dataclass(slots=True)
class ActionIR:
    name: str
    kind: str
    actor: str | None = None
    target_value: float | None = None


@dataclass(slots=True)
class TriggerIR:
    scope: str
    condition_name: str
    kind: str
    delay: float | None = None
    edge: str | None = None


@dataclass(slots=True)
class PositionIR:
    kind: str
    attributes: dict[str, str] = field(default_factory=dict)


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


@dataclass(slots=True)
class RoadIR:
    name: str | None = None
    revision: str | None = None
    road_ids: list[str] = field(default_factory=list)
    lane_count: int = 0
    junction_count: int = 0
    signal_count: int = 0
    object_count: int = 0


@dataclass(slots=True)
class ParseBundle:
    scenario: ScenarioIR
    road: RoadIR
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
