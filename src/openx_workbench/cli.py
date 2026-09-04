from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from xml.etree.ElementTree import ParseError

from .i18n import tr
from .workflow import InputFile, InputValidationError, inspect_pair


def main() -> None:
    parser = argparse.ArgumentParser(description="Inspect an OpenSCENARIO/OpenDRIVE pair.")
    parser.add_argument("xosc", type=Path)
    parser.add_argument("xodr", type=Path)
    parser.add_argument("--language", choices=("zh", "en"), default="en")
    args = parser.parse_args()
    try:
        bundle = inspect_pair(
            InputFile(args.xosc.name, args.xosc.read_bytes()),
            InputFile(args.xodr.name, args.xodr.read_bytes()),
        )
    except InputValidationError as exc:
        parser.error(tr(args.language, exc.code))
    except (OSError, ValueError, ParseError) as exc:
        parser.error(str(exc))
    for warning in bundle.warnings:
        print(f"WARNING: {tr(args.language, warning)}", file=sys.stderr)
    print(json.dumps(bundle.to_dict(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
