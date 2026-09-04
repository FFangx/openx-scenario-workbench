from pathlib import Path

from streamlit.testing.v1 import AppTest


def test_streamlit_app_starts_without_exceptions():
    app_path = Path(__file__).parents[1] / "src" / "openx_workbench" / "app.py"
    app = AppTest.from_file(str(app_path)).run(timeout=10)

    assert not app.exception
    assert app.title
    assert app.button
