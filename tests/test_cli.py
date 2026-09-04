import json
import shutil
import subprocess
import sys
from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures"


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-X", "utf8", "-m", "openx_workbench.cli", *map(str, args)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_cli_keeps_stdout_valid_json_when_warning_is_reported(tmp_path):
    road = tmp_path / "other.xodr"
    shutil.copyfile(FIXTURES / "minimal.xodr", road)
    result = run_cli(FIXTURES / "minimal.xosc", road)
    assert result.returncode == 0
    assert "road_file_mismatch" in json.loads(result.stdout)["warnings"]
    assert "WARNING:" in result.stderr


def test_cli_reports_missing_file_without_traceback():
    result = run_cli(FIXTURES / "missing.xosc", FIXTURES / "minimal.xodr")
    assert result.returncode == 2
    assert result.stdout == ""
    assert "error:" in result.stderr
    assert "Traceback" not in result.stderr


def test_cli_rejects_unrelated_xml(tmp_path):
    wrong = tmp_path / "wrong.xosc"
    wrong.write_text("<unrelated />", encoding="utf-8")
    result = run_cli(wrong, FIXTURES / "minimal.xodr")
    assert result.returncode == 2
    assert "OpenSCENARIO root" in result.stderr
