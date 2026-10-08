import math

import pytest

from openx_workbench.parser import parse_bundle
from openx_workbench.reuse_facts import (
    bundle_participant_relations,
    bundle_participant_signatures,
)
from openx_workbench.road_geometry import RoadAhead, parse_road_geometry, road_ahead, roundabouts


CURVED_ROAD = b"""<?xml version="1.0"?>
<OpenDRIVE>
  <header revMajor="1" revMinor="7" name="Curve"/>
  <road name="Curve" length="100" id="1" junction="-1" rule="RHT">
    <planView>
      <geometry s="0" x="0" y="0" hdg="0" length="100">
        <arc curvature="0.01"/>
      </geometry>
    </planView>
    <lanes><laneSection s="0"><center><lane id="0" type="none"/></center>
      <right>
        <lane id="-1" type="driving"><width sOffset="0" a="3.5" b="0" c="0" d="0"/></lane>
        <lane id="-2" type="driving"><width sOffset="0" a="3.5" b="0" c="0" d="0"/></lane>
      </right>
    </laneSection></lanes>
  </road>
</OpenDRIVE>
"""


def test_arc_reference_line_and_lane_width_convert_to_world_coordinates():
    road = parse_road_geometry(CURVED_ROAD)["1"]

    x, y = road.segments[0].point_at(30)
    lane_x, lane_y, heading = road.world_from_lane(30, -1)

    assert heading == pytest.approx(0.3)
    assert x == pytest.approx(100 * math.sin(0.3))
    assert y == pytest.approx(100 * (1 - math.cos(0.3)))
    assert math.dist((x, y), (lane_x, lane_y)) == pytest.approx(1.75)


def test_mixed_lane_and_world_positions_use_curved_road_coordinates():
    road = parse_road_geometry(CURVED_ROAD)["1"]
    target_x, target_y, _ = road.world_from_lane(30, -2)
    scenario = f"""<?xml version="1.0"?>
    <OpenSCENARIO>
      <FileHeader revMajor="1" revMinor="2" description="Curve relation"/>
      <RoadNetwork><LogicFile filepath="curve.xodr"/></RoadNetwork>
      <Entities>
        <ScenarioObject name="Ego"><Vehicle vehicleCategory="car"/></ScenarioObject>
        <ScenarioObject name="Target"><Vehicle vehicleCategory="car"/></ScenarioObject>
      </Entities>
      <Storyboard><Init><Actions>
        <Private entityRef="Ego"><PrivateAction><TeleportAction><Position>
          <LanePosition roadId="1" laneId="-1" s="10" offset="0"/>
        </Position></TeleportAction></PrivateAction></Private>
        <Private entityRef="Target"><PrivateAction><TeleportAction><Position>
          <WorldPosition x="{target_x}" y="{target_y}" z="0" h="0.3"/>
        </Position></TeleportAction></PrivateAction></Private>
      </Actions></Init></Storyboard>
    </OpenSCENARIO>"""

    bundle = parse_bundle(scenario, CURVED_ROAD, "curve.xodr")

    assert bundle_participant_relations(bundle) == {"front", "right"}
    assert [item.key() for item in bundle_participant_signatures(bundle)] == [
        "vehicle@front_right:same:static"
    ]
    assert "road_geometry" not in bundle.to_dict()


def test_absolute_orientation_controls_forward_direction_on_reference_line():
    scenario = """<?xml version="1.0"?>
    <OpenSCENARIO>
      <FileHeader revMajor="1" revMinor="2" description="Reverse relation"/>
      <RoadNetwork><LogicFile filepath="curve.xodr"/></RoadNetwork>
      <Entities>
        <ScenarioObject name="Ego"><Vehicle vehicleCategory="car"/></ScenarioObject>
        <ScenarioObject name="Target"><Vehicle vehicleCategory="car"/></ScenarioObject>
      </Entities>
      <Storyboard><Init><Actions>
        <Private entityRef="Ego"><PrivateAction><TeleportAction><Position>
          <LanePosition roadId="1" laneId="-1" s="10" offset="0">
            <Orientation type="absolute" h="3.241592653589793"/>
          </LanePosition>
        </Position></TeleportAction></PrivateAction></Private>
        <Private entityRef="Target"><PrivateAction><TeleportAction><Position>
          <LanePosition roadId="1" laneId="-1" s="30" offset="0"/>
        </Position></TeleportAction></PrivateAction></Private>
      </Actions></Init></Storyboard>
    </OpenSCENARIO>"""

    bundle = parse_bundle(scenario, CURVED_ROAD, "curve.xodr")

    assert bundle_participant_relations(bundle) == {"rear"}
    assert bundle_participant_signatures(bundle)[0].facing == "opposite"


def test_relative_lane_position_keeps_longitudinal_and_lane_relationships():
    scenario = """<?xml version="1.0"?>
    <OpenSCENARIO>
      <FileHeader revMajor="1" revMinor="2" description="Relative lane"/>
      <RoadNetwork><LogicFile filepath="curve.xodr"/></RoadNetwork>
      <Entities>
        <ScenarioObject name="Ego"><Vehicle vehicleCategory="car"/></ScenarioObject>
        <ScenarioObject name="Target"><Vehicle vehicleCategory="car"/></ScenarioObject>
      </Entities>
      <Storyboard><Init><Actions>
        <Private entityRef="Ego"><PrivateAction><TeleportAction><Position>
          <LanePosition roadId="1" laneId="-1" s="10" offset="0"/>
        </Position></TeleportAction></PrivateAction></Private>
        <Private entityRef="Target"><PrivateAction><TeleportAction><Position>
          <RelativeLanePosition entityRef="Ego" dLane="-1" ds="20" offset="0"/>
        </Position></TeleportAction></PrivateAction></Private>
      </Actions></Init></Storyboard>
    </OpenSCENARIO>"""

    bundle = parse_bundle(scenario, CURVED_ROAD, "curve.xodr")

    assert bundle_participant_relations(bundle) == {
        "front",
        "right",
        "adjacent_lane",
    }


def _road(road_id, x, geometries, junction="-1"):
    """A road along the x axis from (x, 0): `geometries` are (length, curvature) pieces, 0 for a line."""
    planview, s = [], 0.0
    for length, curvature in geometries:
        shape = f'<arc curvature="{curvature}"/>' if curvature else "<line/>"
        planview.append(f'<geometry s="{s}" x="{x + s}" y="0" hdg="0" length="{length}">{shape}</geometry>')
        s += length
    return (f'<road id="{road_id}" length="{s}" junction="{junction}"><planView>{"".join(planview)}</planView>'
            '<lanes><laneSection s="0"><center><lane id="0" type="none"/></center><right><lane id="-1" type="driving">'
            '<width sOffset="0" a="3.5" b="0" c="0" d="0"/></lane></right></laneSection></lanes></road>')


def _roads(*roads):
    return parse_road_geometry(f'<OpenDRIVE><header revMajor="1" revMinor="6"/>{"".join(roads)}</OpenDRIVE>'.encode())


def test_road_ahead_reads_a_curve_drawn_as_short_pieces_within_the_distance():
    # 50 m straight, then a R50 curve drawn as four 16 m pieces (each shorter than a curve on its own).
    roads = _roads(_road("1", 0, [(50, 0)] + [(16, 0.02)] * 4))
    ahead = road_ahead(roads, 10, -1.75, 0.0, 250)
    assert (ahead.curve_radius, ahead.junction, ahead.distance) == (50, False, 40)
    assert ahead.at == pytest.approx((50, 0))
    assert road_ahead(roads, 10, -1.75, 0.0, 30) == RoadAhead()  # the curve starts beyond the distance
    assert road_ahead(roads, 10, -1.75, math.pi, 250) == RoadAhead()  # driving away from it
    assert road_ahead(roads, 10, -60, 0.0, 250) is None  # on no road of the file


def test_road_ahead_follows_joined_roads_and_stops_at_a_junction():
    curve_on = _roads(_road("1", 0, [(100, 0)]), _road("2", 100, [(100, 0.004)]))
    assert road_ahead(curve_on, 10, -1.75, 0.0, 250).distance == 90
    assert road_ahead(curve_on, 10, -1.75, 0.0, 250).curve_radius == 250
    junction = _roads(_road("1", 0, [(100, 0)]), _road("3", 100, [(20, 0)], junction="7"),
                      _road("2", 120, [(100, 0.004)]))
    ahead = road_ahead(junction, 10, -1.75, 0.0, 250)
    assert (ahead.curve_radius, ahead.junction, ahead.distance) == (None, True, 90)
    assert ahead.at == pytest.approx((100, 0))
    assert road_ahead(junction, 10, -1.75, 0.0, 80) == RoadAhead()


def _arc(road_id, centre, radius, start_angle, sweep):
    """A counter-clockwise arc road around `centre` from `start_angle` (radians)."""
    x, y = centre[0] + radius * math.cos(start_angle), centre[1] + radius * math.sin(start_angle)
    return (f'<road id="{road_id}" length="{radius * sweep}" junction="-1"><planView><geometry s="0" x="{x}" y="{y}" '
            f'hdg="{start_angle + math.pi / 2}" length="{radius * sweep}"><arc curvature="{1 / radius}"/></geometry></planView></road>')


def _ring(centre, radius, pieces=6):
    return [_arc(f"r{n}", centre, radius, n * math.tau / pieces, math.tau / pieces) for n in range(pieces)]


def test_tight_curves_closing_a_ring_around_one_centre_are_a_roundabout():
    assert [tuple(round(value) for value in ring) for ring in roundabouts(_roads(*_ring((100, 0), 20)))] == [(100, 0, 20)]
    assert roundabouts(_roads(*_ring((100, 0), 20)[:3])) == []  # half a ring
    assert roundabouts(_roads(*_ring((100, 0), 150, pieces=12))) == []  # a ring that wide is a road
    # An ordinary junction's left turns curve around different corners.
    turns = [_arc(f"t{n}", (20 * math.cos(n * math.pi / 2), 20 * math.sin(n * math.pi / 2)), 15, n * math.pi / 2, math.pi / 2)
             for n in range(4)]
    assert roundabouts(_roads(*turns)) == []

