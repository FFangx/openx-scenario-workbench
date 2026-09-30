from openx_workbench.scene_package import (
    EvidenceRef,
    ScenePackage,
    scene_package_to_query,
)


def test_scene_package_becomes_grounded_structured_query():
    evidence = EvidenceRef("standard.pdf", "7.4.1", 12, 13, "目标车切入，自车 TTC 为 3.0 s。")
    package = ScenePackage(
        package_id="L2_7.4.1",
        title="目标车切入场景",
        preferred_text=evidence.source_text,
        evidence=[evidence],
        road_types=["直道"],
        entities=["目标车"],
        actions=["切入"],
        triggers=["TTC"],
        parameters={"ttc_s": 3.0},
    )

    query = scene_package_to_query(package)

    assert query.entity_kinds == frozenset({"vehicle"})
    assert query.action_kinds == frozenset({"lane_change"})
    assert query.trigger_kinds == frozenset({"ttc"})
    assert query.road_features == frozenset({"straight"})
    assert query.parameters == (("ttc_s", 3.0),)
    assert query.evidence == (evidence,)


def test_scene_package_preserves_scenario_family_and_ptw_type():
    package = ScenePackage(
        package_id="EuroNCAP_4.3.2",
        title="Car-to-PTW",
        preferred_text="A vehicle approaches a stationary motorcyclist.",
    )

    query = scene_package_to_query(package)

    assert query.scenario_families == frozenset({"car_to_ptw"})
    assert query.entity_kinds >= frozenset({"vehicle", "motorcycle"})


def test_scene_package_preserves_explicit_relative_position():
    package = ScenePackage(
        package_id="DEMO_2",
        title="Adjacent overtaking vehicle",
        preferred_text="A vehicle approaches in the adjacent lane from the rear.",
    )

    query = scene_package_to_query(package)

    assert query.participant_relations == frozenset({"rear", "adjacent_lane"})
