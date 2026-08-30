from openx_workbench.i18n import tr


def test_both_interface_languages_are_available():
    assert tr("zh", "inspect") == "开始检查"
    assert tr("en", "inspect") == "Inspect files"
