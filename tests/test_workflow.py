from pathlib import Path

import pytest

from openx_workbench.workflow import InputFile, InputValidationError, inspect_pair


FIXTURES = Path(__file__).parent / "fixtures"


def test_inspect_pair_validates_and_parses_inputs():
    bundle = inspect_pair(
        InputFile("minimal.xosc", (FIXTURES / "minimal.xosc").read_bytes()),
        InputFile("minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes()),
    )
    assert bundle.scenario.name == "Minimal cut-in"
    assert bundle.warnings == []


@pytest.mark.parametrize(
    ("xosc_name", "xodr_name", "code"),
    [
        ("scenario.xml", "road.xodr", "invalid_xosc_extension"),
        ("scenario.xosc", "road.xml", "invalid_xodr_extension"),
    ],
)
def test_inspect_pair_rejects_wrong_extensions(xosc_name, xodr_name, code):
    with pytest.raises(InputValidationError) as exc_info:
        inspect_pair(InputFile(xosc_name, b"x"), InputFile(xodr_name, b"x"))
    assert exc_info.value.code == code
