from openx_workbench.i18n import TEXT, tr


def test_both_interface_languages_are_available():
    assert tr("zh", "inspect") == "开始检查"
    assert tr("en", "inspect") == "Inspect files"
    assert tr("zh", "load_demo") == "加载公开示例"
    assert tr("en", "load_demo") == "Load public demo"


def test_interface_languages_expose_the_same_keys():
    assert set(TEXT["zh"]) == set(TEXT["en"])


def test_lane_counts_read_as_lanes_not_as_a_score():
    from openx_workbench.presentation import display

    assert display("at least 2 lanes in total") == "至少 2 条车道（双向合计）"
    assert display("3 lanes in one direction") == "3 条车道（单向）"
    assert display("at least 2 lanes in total", "en") == "at least 2 lanes in total"
    assert display("cruise") == "匀速行驶"
