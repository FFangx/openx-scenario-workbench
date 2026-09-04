from openx_workbench.i18n import tr


def test_both_interface_languages_are_available():
    assert tr("zh", "inspect") == "开始检查"
    assert tr("en", "inspect") == "Inspect files"
    assert tr("zh", "load_demo") == "加载公开示例"
    assert tr("en", "load_demo") == "Load public demo"
