from __future__ import annotations

import argparse
import json
from pathlib import Path

from .i18n import tr
from .parser import parse_bundle


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect an OpenSCENARIO/OpenDRIVE pair.")
    parser.add_argument("xosc", type=Path)
    parser.add_argument("xodr", type=Path)
    parser.add_argument("--language", choices=("zh", "en"), default="en")
    args = parser.parse_args()
    bundle = parse_bundle(args.xosc.read_bytes(), args.xodr.read_bytes(), args.xodr.name)
    for warning in bundle.warnings:
        print(f"WARNING: {tr(args.language, warning)}")
    print(json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
