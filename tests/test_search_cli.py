import json
import os
import shutil
import subprocess
import sys
from pathlib import Path


FIXTURES = Path(__file__).parent / "fixtures"
SOURCE_ROOT = Path(__file__).parents[1] / "src"


def test_search_cli_builds_and_queries_openx_catalog(tmp_path):
    shutil.copyfile(FIXTURES / "minimal.xosc", tmp_path / "minimal.xosc")
    shutil.copyfile(FIXTURES / "minimal.xodr", tmp_path / "minimal.xodr")

    result = subprocess.run(
        [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "openx_workbench.search_cli",
            str(tmp_path),
            "cut-in SpeedAction",
        ],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={**os.environ, "PYTHONPATH": str(SOURCE_ROOT)},
    )

    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["asset_count"] == 1
    assert payload["results"][0]["xodr"] == "minimal.xodr"
