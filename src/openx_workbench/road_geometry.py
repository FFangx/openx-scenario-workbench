from __future__ import annotations

import math
import statistics
from dataclasses import dataclass, field
from xml.etree import ElementTree as ET

from .xml_values import local_name as _local, number


def _children(element: ET.Element, name: str) -> list[ET.Element]:
    return [child for child in list(element) if _local(child) == name]


def _child(element: ET.Element, name: str) -> ET.Element | None:
    return next((child for child in list(element) if _local(child) == name), None)


def _float(value: str | None, default: float = 0.0) -> float:
    """Missing or non-numeric values read as `default`; geometry keeps non-finite values as given."""
    return number(value, default)


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
    junction: str = "-1"  # the junction this road connects through, "-1" for an ordinary road

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
            junction=road.get("junction", "-1"),
        )
    return roads


# ---------- the curve a vehicle drives into ----------
# Read from ScenarioManager libraries (ego_curve_radius): real test curves have radii of 15-833 m,
# while transition polynomials sample as 1174 m and more; parking-space connector arcs are under
# 19 m long, the shortest test curve 45 m. The gaps between them set both limits.
STRAIGHT_RADIUS_M = 1000.0  # a segment this flat or flatter is straight
MIN_CURVE_LENGTH_M = 30.0  # a shorter segment adjusts the alignment, it is no curve
JOIN_DISTANCE_M = 2.0  # road ends this close continue each other
LOCATE_DISTANCE_M = 30.0  # farther from every reference line, the vehicle is on no road of the file
ON_LINE_M = 1.0  # a point this far from where its (s, t) leads lies beyond the road's end, not beside it


def place_on(road: RoadReferenceLine, x: float, y: float) -> tuple[float, float] | None:
    """(s, t) of a point beside `road`'s reference line; None beyond either end or farther away
    than LOCATE_DISTANCE_M."""
    found = road.road_from_world(x, y)
    if found is None:
        return None
    s, t = found
    back = road.world_from_road(s, t)
    if abs(t) > LOCATE_DISTANCE_M or back is None or math.dist(back[:2], (x, y)) > ON_LINE_M:
        return None
    return s, t


def locate(roads: dict[str, RoadReferenceLine], x: float, y: float) -> tuple[RoadReferenceLine, float, float] | None:
    """The ordinary road (no junction connector) a point lies beside, the nearest reference line
    first, with the point's (s, t); None when it is beside none."""
    return min(((road, *found) for road in roads.values()
                if road.junction == "-1" and road.segments and (found := place_on(road, x, y))),
               key=lambda item: abs(item[2]), default=None)


def segment_radius(segment: GeometrySegment) -> float | None:
    """A segment's representative radius in metres; None for lines and spiral transitions
    (the arc they lead into is the curve)."""
    if segment.kind == "arc":
        return abs(1.0 / segment.curvature) if abs(segment.curvature) > 1e-9 else None
    if segment.kind == "paramPoly3" and segment.coefficients:
        _, bu, cu, du, _, bv, cv, dv = segment.coefficients
        radii = []
        for step in range(1, 10):  # p = 0.1 .. 0.9, away from the end points
            p = step / 10
            du_dp, dv_dp = bu + 2 * cu * p + 3 * du * p * p, bv + 2 * cv * p + 3 * dv * p * p
            denominator = (du_dp**2 + dv_dp**2) ** 1.5
            curvature = (du_dp * (2 * cv + 6 * dv * p) - dv_dp * (2 * cu + 6 * du * p)) / denominator if denominator > 1e-12 else 0.0
            if abs(curvature) > 1e-12:
                radii.append(abs(1.0 / curvature))
        return statistics.median(radii) if radii else None
    return None


def _first_curve(road: RoadReferenceLine, from_s: float | None, forward: bool) -> float | None:
    for segment in road.segments if forward else reversed(road.segments):
        if from_s is not None and (segment.s + segment.length < from_s if forward else segment.s > from_s):
            continue  # already behind the vehicle
        if segment.length < MIN_CURVE_LENGTH_M:
            continue
        radius = segment_radius(segment)
        if radius is not None and radius < STRAIGHT_RADIUS_M:
            return radius
    return None


def _ends(road: RoadReferenceLine) -> tuple[tuple[float, float], tuple[float, float]]:
    first, last = road.segments[0], road.segments[-1]
    return first.point_at(first.s), last.point_at(last.s + last.length)


def path_curve_radius(roads: dict[str, RoadReferenceLine], x: float, y: float, heading: float) -> float | None:
    """Radius of the first curve ahead of a vehicle at (x, y) heading `heading`, in metres.

    One map often holds several curves (R251 to R833 along one road), so the curve is the one the
    vehicle drives into, not the map's. Junction connectors (turning R32-R58, roundabout R2-R5)
    are no curve tests and are left out. The search follows the road the vehicle is on, then up to
    two roads joined to its end. None: no road found, or no curve ahead.
    """
    located = min(((road, *place) for road in roads.values()
                   if road.junction == "-1" and road.segments and (place := road.road_from_world(x, y))),
                  key=lambda item: abs(item[2]), default=None)
    if located is None or abs(located[2]) > LOCATE_DISTANCE_M:
        return None
    road, s, _ = located
    reference = road.heading_at(s)
    if reference is None:
        return None
    forward = abs(math.remainder(heading - reference, math.tau)) < math.pi / 2
    radius, visited = _first_curve(road, s, forward), {road.road_id}
    for _ in range(2):
        if radius is not None:
            break
        exit_point = _ends(road)[1 if forward else 0]
        joined = next(((other, start) for other in roads.values()
                       if other.road_id not in visited and other.junction == "-1" and other.segments
                       for start, end in (_ends(other),)
                       if math.dist(start, exit_point) < JOIN_DISTANCE_M or math.dist(end, exit_point) < JOIN_DISTANCE_M),
                      None)
        if joined is None:
            break
        road, forward = joined[0], math.dist(joined[1], exit_point) < JOIN_DISTANCE_M
        visited.add(road.road_id)
        radius = _first_curve(road, None, forward)
    return round(radius) if radius is not None else None


@dataclass(frozen=True, slots=True)
class RoadAhead:
    """The first feature ahead of a vehicle, how far ahead and where (x, y) it starts: a curve it
    enters, or a junction its road runs into; neither when the stretch looked at is straight."""
    curve_radius: float | None = None
    junction: bool = False
    distance: float | None = None
    at: tuple[float, float] | None = None


def road_ahead(roads: dict[str, RoadReferenceLine], x: float, y: float, heading: float,
               distance: float) -> RoadAhead | None:
    """The first curve or junction within `distance` metres ahead of a vehicle at (x, y) heading `heading`.

    Follows the road the vehicle is on and the ordinary roads joined to its end, as path_curve_radius
    does; a junction connector touching the end means the road runs into a junction. A curve is curved
    segments in a row, together MIN_CURVE_LENGTH_M or longer: authoring tools often draw one curve as
    many short polynomials. None: the vehicle is on no road of the file.
    """
    located = locate(roads, x, y)
    if located is None:
        return None
    road, position, _ = located
    reference = road.heading_at(position)
    if reference is None:
        return None
    forward = abs(math.remainder(heading - reference, math.tau)) < math.pi / 2
    walked, visited = 0.0, {road.road_id}
    curve_start, curve_at, curve_length, radii = 0.0, None, 0.0, []
    while True:
        for segment in road.segments if forward else reversed(road.segments):
            start, end = segment.s, segment.s + segment.length
            if (end < position) if forward else (start > position):
                continue  # already behind the vehicle
            ahead = walked + max(0.0, start - position if forward else position - end)
            radius = segment_radius(segment)
            if radius is None or radius >= STRAIGHT_RADIUS_M:
                curve_length, radii = 0.0, []
                if ahead > distance:
                    return RoadAhead()
                continue
            if not radii:
                if ahead > distance:
                    return RoadAhead()
                curve_start, curve_at = ahead, segment.point_at(start if forward else end)
            curve_length += segment.length
            radii.append(radius)
            if curve_length >= MIN_CURVE_LENGTH_M:
                return RoadAhead(curve_radius=round(min(radii)), distance=round(curve_start), at=curve_at)
        last = road.segments[-1]
        walked += (last.s + last.length - position) if forward else position - road.segments[0].s
        if walked > distance:
            return RoadAhead()
        exit_point = _ends(road)[1 if forward else 0]
        touching = [other for other in roads.values() if other.road_id not in visited and other.segments
                    and any(math.dist(end, exit_point) < JOIN_DISTANCE_M for end in _ends(other))]
        if any(other.junction != "-1" for other in touching):
            return RoadAhead(junction=True, distance=round(walked), at=exit_point)
        joined = next((other for other in touching if other.junction == "-1"), None)
        if joined is None:
            return RoadAhead()
        forward = math.dist(_ends(joined)[0], exit_point) < JOIN_DISTANCE_M
        road, position = joined, (joined.segments[0].s if forward else joined.segments[-1].s + joined.segments[-1].length)
        visited.add(road.road_id)


# ---------- roundabouts ----------
# OpenDRIVE has no roundabout element: a ring is drawn as tight curved roads and junction connectors
# around one centre (the libraries' R15 ring: four 60-degree roads, four junctions of 30-degree
# connectors). Turning connectors of an ordinary junction curve around different centres.
RING_RADIUS_M = 60.0  # a tighter curve may be a piece of a ring; wider rings are roads, not roundabouts
RING_TURN = math.radians(300)  # pieces around one centre turning together this far close a ring
RING_CENTRE_M = 3.0  # pieces whose centres lie this close (or within a quarter of the radius) share one


def _circle(points: list[tuple[float, float]]) -> tuple[float, float, float] | None:
    """Centre and radius of the circle through three points; None when they lie on a line."""
    (ax, ay), (bx, by), (cx, cy) = points
    d = 2 * (ax * (by - cy) + bx * (cy - ay) + cx * (ay - by))
    if abs(d) < 1e-9:
        return None
    ux = ((ax * ax + ay * ay) * (by - cy) + (bx * bx + by * by) * (cy - ay) + (cx * cx + cy * cy) * (ay - by)) / d
    uy = ((ax * ax + ay * ay) * (cx - bx) + (bx * bx + by * by) * (ax - cx) + (cx * cx + cy * cy) * (bx - ax)) / d
    return ux, uy, math.dist((ux, uy), (ax, ay))


def roundabouts(roads: dict[str, RoadReferenceLine]) -> list[tuple[float, float, float]]:
    """Centre (x, y) and radius of every ring in the file: tight curved roads or connectors turning
    the same way around one centre, together RING_TURN or more."""
    pieces = []
    for road in roads.values():
        if not road.segments:
            continue
        first, last = road.segments[0], road.segments[-1]
        start, end = first.s, last.s + last.length
        points = [road.world_from_road(s, 0.0) for s in (start, (start + end) / 2, end)]
        turn = math.remainder(last.heading_at(end) - first.heading_at(start), math.tau)
        circle = _circle([point[:2] for point in points]) if all(points) else None
        if circle is not None and circle[2] <= RING_RADIUS_M and abs(turn) >= math.radians(10):
            pieces.append((circle, turn))
    rings: list[list] = []  # [centre x, centre y, radius, turn, pieces]
    for (x, y, radius), turn in pieces:
        ring = next((ring for ring in rings if (ring[3] > 0) == (turn > 0)
                     and math.dist((ring[0], ring[1]), (x, y)) <= max(RING_CENTRE_M, radius / 4)), None)
        if ring is None:
            rings.append([x, y, radius, turn, 1])
        else:
            ring[3] += turn
            ring[4] += 1
    return [(x, y, radius) for x, y, radius, turn, count in rings if abs(turn) >= RING_TURN and count >= 3]

