from openx_workbench.i18n import TEXT, tr


def test_both_interface_languages_are_available():
    assert tr("zh", "inspect") == "开始检查"
    assert tr("en", "inspect") == "Inspect files"
    assert tr("zh", "load_demo") == "加载公开示例"
    assert tr("en", "load_demo") == "Load public demo"


def test_interface_languages_expose_the_same_keys():
    assert set(TEXT["zh"]) == set(TEXT["en"])
