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
