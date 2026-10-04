"""Seed an empty data folder with a self-authored demo workspace.

    python scripts/seed_demo_workspace.py <empty-folder> [--dataset fixtures|benchmark]

``fixtures`` (the default, used by the browser checks) holds six parser fixtures
and eight requirements; ``benchmark`` holds the 25-asset reuse benchmark and its
35 requirements. See openx_workbench/demo_workspace.py. Nothing is downloaded
and no model is called.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(usage=__doc__)
    parser.add_argument("target", type=Path)
    parser.add_argument("--dataset", choices=("fixtures", "benchmark"), default="fixtures")
    args = parser.parse_args()
    sys.path.insert(0, str(REPO / "src"))
    from openx_workbench.demo_workspace import seed

    print(json.dumps(seed(args.target.resolve(), args.dataset), ensure_ascii=False))
