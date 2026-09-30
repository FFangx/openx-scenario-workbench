from __future__ import annotations

import math
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET


def _local(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local(child) == name]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in list(element) if _local(child) == name), None)


def _float(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value) if value is not None else default
    except ValueError:
        return default


@dataclass(frozen=True, slots=True)
class GeometrySegment:
    s: float
    x: float
    y: float
    heading: float
    length: float
    kind: str = "line"
    curvature: float = 0.0
    curvature_start: float = 0.0
    curvature_end: float = 0.0
    coefficients: tuple[float, ...] = ()
    normalized: bool = True

    def heading_at(self, s: float) -> float:
        ds = max(0.0, min(s - self.s, self.length))
        if self.kind == "arc":
            return self.heading + self.curvature * ds
        if self.kind == "spiral" and self.length > 0:
            rate = (self.curvature_end - self.curvature_start) / self.length
            return self.heading + self.curvature_start * ds + 0.5 * rate * ds * ds
        if self.kind == "paramPoly3":
            _, bu, cu, du, _, bv, cv, dv = self.coefficients
            p = ds / self.length if self.normalized and self.length > 0 else ds
            return self.heading + math.atan2(
                bv + 2 * cv * p + 3 * dv * p * p,
                bu + 2 * cu * p + 3 * du * p * p,
            )
        return self.heading

    def point_at(self, s: float) -> tuple[float, float]:
        ds = max(0.0, min(s - self.s, self.length))
        if self.kind == "line":
            return self._to_world(ds, 0.0)
        if self.kind == "arc" and abs(self.curvature) > 1e-12:
            angle = self.curvature * ds
            radius = 1.0 / self.curvature
            return self._to_world(radius * math.sin(angle), radius * (1 - math.cos(angle)))
        if self.kind == "paramPoly3":
            au, bu, cu, du, av, bv, cv, dv = self.coefficients
            p = ds / self.length if self.normalized and self.length > 0 else ds
            return self._to_world(
                au + bu * p + cu * p * p + du * p**3,
                av + bv * p + cv * p * p + dv * p**3,
            )

        x, y = self.x, self.y
        walked = 0.0
        while walked < ds:
            step = min(0.5, ds - walked)
            heading = self.heading_at(self.s + walked + step / 2)
            x += step * math.cos(heading)
            y += step * math.sin(heading)
            walked += step
        return x, y

    def _to_world(self, forward: float, left: float) -> tuple[float, float]:
        cosine, sine = math.cos(self.heading), math.sin(self.heading)
        return (
            self.x + forward * cosine - left * sine,
            self.y + forward * sine + left * cosine,
        )


@dataclass(frozen=True, slots=True)
class LaneWidth:
    s_offset: float
    a: float
    b: float
    c: float
    d: float

    def at(self, section_offset: float) -> float:
        value = max(0.0, section_offset - self.s_offset)
        return self.a + self.b * value + self.c * value**2 + self.d * value**3


@dataclass(frozen=True, slots=True)
class LaneSection:
    s: float
    widths: dict[int, tuple[LaneWidth, ...]]

    def lateral_offset(self, lane_id: int, s: float) -> float | None:
        if lane_id == 0:
            return 0.0
        section_offset = s - self.s
        step = 1 if lane_id > 0 else -1
        offset = 0.0
        for current in range(step, lane_id + step, step):
            entries = self.widths.get(current)
            if not entries:
                return None
            entry = next(
                (item for item in reversed(entries) if item.s_offset <= section_offset),
                entries[0],
            )
            width = entry.at(section_offset)
            offset += width / 2 if current == lane_id else width
        return offset if lane_id > 0 else -offset


@dataclass(slots=True)
class RoadReferenceLine:
    road_id: str
    length: float
    rule: str
    segments: list[GeometrySegment]
    lane_sections: list[LaneSection] = field(default_factory=list)

    def segment_at(self, s: float) -> GeometrySegment | None:
        return next((item for item in reversed(self.segments) if item.s <= s), None)

    def heading_at(self, s: float) -> float | None:
        segment = self.segment_at(s)
        return segment.heading_at(s) if segment else None

    def world_from_road(self, s: float, t: float) -> tuple[float, float, float] | None:
        segment = self.segment_at(s)
        if segment is None:
            return None
        x, y = segment.point_at(s)
        heading = segment.heading_at(s)
        return x - t * math.sin(heading), y + t * math.cos(heading), heading

    def world_from_lane(
        self,
        s: float,
        lane_id: int,
        offset: float = 0.0,
    ) -> tuple[float, float, float] | None:
        section = next(
            (item for item in reversed(self.lane_sections) if item.s <= s),
            None,
        )
        lateral = section.lateral_offset(lane_id, s) if section else None
        if lateral is None:
            return None
        return self.world_from_road(s, lateral + offset)

    def road_from_world(self, x: float, y: float) -> tuple[float, float] | None:
        if not self.segments:
            return None
        step = 5.0
        samples = max(2, int(self.length / step) + 1)
        best_s = min(
            (min(self.length, index * step) for index in range(samples)),
            key=lambda s: math.dist(self.segment_at(s).point_at(s), (x, y)),
        )
        fine_step = step / 20
        lower, upper = max(0.0, best_s - step), min(self.length, best_s + step)
        fine_samples = int((upper - lower) / fine_step) + 1
        best_s = min(
            (lower + index * fine_step for index in range(fine_samples)),
            key=lambda s: math.dist(self.segment_at(s).point_at(s), (x, y)),
        )
        segment = self.segment_at(best_s)
        px, py = segment.point_at(best_s)
        heading = segment.heading_at(best_s)
        distance = math.hypot(x - px, y - py)
        cross = math.cos(heading) * (y - py) - math.sin(heading) * (x - px)
        return best_s, math.copysign(distance, cross)


def parse_road_geometry(data: bytes | str) -> dict[str, RoadReferenceLine]:
    root = ET.fromstring(data)
    roads: dict[str, RoadReferenceLine] = {}
    for road in (element for element in root.iter() if _local(element) == "road"):
        segments: list[GeometrySegment] = []
        plan_view = _child(road, "planView")
        for geometry in _children(plan_view, "geometry") if plan_view is not None else []:
            kind = "line"
            curvature = curvature_start = curvature_end = 0.0
            coefficients: tuple[float, ...] = ()
            normalized = True
            if (arc := _child(geometry, "arc")) is not None:
                kind, curvature = "arc", _float(arc.get("curvature"))
            elif (spiral := _child(geometry, "spiral")) is not None:
                kind = "spiral"
                curvature_start = _float(spiral.get("curvStart"))
                curvature_end = _float(spiral.get("curvEnd"))
            elif (poly := _child(geometry, "paramPoly3")) is not None:
                kind = "paramPoly3"
                coefficients = tuple(
                    _float(poly.get(name))
                    for name in ("aU", "bU", "cU", "dU", "aV", "bV", "cV", "dV")
                )
                normalized = poly.get("pRange", "normalized") == "normalized"
            segments.append(GeometrySegment(
                _float(geometry.get("s")),
                _float(geometry.get("x")),
                _float(geometry.get("y")),
                _float(geometry.get("hdg")),
                _float(geometry.get("length")),
                kind,
                curvature,
                curvature_start,
                curvature_end,
                coefficients,
                normalized,
            ))

        lane_sections: list[LaneSection] = []
        lanes = _child(road, "lanes")
        for section in _children(lanes, "laneSection") if lanes is not None else []:
            widths: dict[int, tuple[LaneWidth, ...]] = {}
            for side_name in ("left", "right"):
                side = _child(section, side_name)
                for lane in _children(side, "lane") if side is not None else []:
                    lane_id = int(lane.get("id", "0"))
                    entries = tuple(sorted((
                        LaneWidth(
                            _float(width.get("sOffset")),
                            _float(width.get("a")),
                            _float(width.get("b")),
                            _float(width.get("c")),
                            _float(width.get("d")),
                        )
                        for width in _children(lane, "width")
                    ), key=lambda item: item.s_offset))
                    if entries:
                        widths[lane_id] = entries
            lane_sections.append(LaneSection(_float(section.get("s")), widths))

        road_id = road.get("id", "")
        roads[road_id] = RoadReferenceLine(
            road_id=road_id,
            length=_float(road.get("length")),
            rule=road.get("rule", ""),
            segments=sorted(segments, key=lambda item: item.s),
            lane_sections=sorted(lane_sections, key=lambda item: item.s),
        )
    return roads
