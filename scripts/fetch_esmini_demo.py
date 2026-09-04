from __future__ import annotations

from pathlib import Path
from urllib.request import urlopen


ESMINI_COMMIT = "4b8fbafb1a8abd13f3d57b97e4a1b7e68cd93418"
BASE = f"https://raw.githubusercontent.com/esmini/esmini/{ESMINI_COMMIT}"
FILES = {
    "cut-in.xosc": "resources/xosc/cut-in.xosc",
    "e6mini.xodr": "resources/xodr/e6mini.xodr",
    "LICENSE": "LICENSE",
}


def main() -> None:
    target = Path(__file__).resolve().parents[1] / "examples" / "esmini"
    target.mkdir(parents=True, exist_ok=True)
    for output_name, source_path in FILES.items():
        destination = target / output_name
        with urlopen(f"{BASE}/{source_path}", timeout=30) as response:
            destination.write_bytes(response.read())
        print(f"Downloaded {destination.relative_to(target.parent.parent)}")


if __name__ == "__main__":
    main()
