from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.request import urlopen


ESMINI_COMMIT = "4b8fbafb1a8abd13f3d57b97e4a1b7e68cd93418"
ESMINI_REPOSITORY = "https://github.com/esmini/esmini"
_RAW_BASE = f"https://raw.githubusercontent.com/esmini/esmini/{ESMINI_COMMIT}"


class _Response(Protocol):
    def read(self) -> bytes: ...

    def __enter__(self) -> "_Response": ...

    def __exit__(self, *args: object) -> None: ...


@dataclass(frozen=True, slots=True)
class PublicDemo:
    xosc_name: str
    xosc_data: bytes
    xodr_name: str
    xodr_data: bytes
    source_url: str = ESMINI_REPOSITORY
    license_name: str = "Mozilla Public License 2.0"


class DemoDownloadError(RuntimeError):
    """Raised when the optional public demo cannot be retrieved."""


def fetch_public_demo(
    opener: Callable[..., _Response] = urlopen,
    timeout: float = 20,
) -> PublicDemo:
    """Fetch a reproducible OpenSCENARIO/OpenDRIVE pair from esmini."""

    files = {
        "cut-in.xosc": "resources/xosc/cut-in.xosc",
        "e6mini.xodr": "resources/xodr/e6mini.xodr",
    }
    downloaded: dict[str, bytes] = {}
    try:
        for name, path in files.items():
            with opener(f"{_RAW_BASE}/{path}", timeout=timeout) as response:
                downloaded[name] = response.read()
    except (HTTPError, URLError, OSError, TimeoutError) as exc:
        raise DemoDownloadError(str(exc)) from exc

    return PublicDemo(
        xosc_name="cut-in.xosc",
        xosc_data=downloaded["cut-in.xosc"],
        xodr_name="e6mini.xodr",
        xodr_data=downloaded["e6mini.xodr"],
    )
