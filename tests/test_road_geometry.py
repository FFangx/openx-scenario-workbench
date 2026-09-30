import math

import pytest

from openx_workbench.parser import parse_bundle
from openx_workbench.reuse import (
    bundle_participant_relations,
    bundle_participant_signatures,
)
from openx_workbench.road_geometry import parse_road_geometry


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
