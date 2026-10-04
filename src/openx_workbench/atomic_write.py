"""Write to a temporary file beside the target, then rename it into place.

Readers see either the previous file or the complete new one. Keyword defaults match `json.dump` and
`tempfile.NamedTemporaryFile`, so each caller states only what it changes.
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, IO


def _publish(path: Path, mode: str, write: Callable[[IO], Any], *, prefix: str | None, suffix: str | None,
             permissions: int | None = None) -> None:
    options = {"encoding": "utf-8"} if mode == "w" else {}
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode, dir=path.parent, prefix=prefix, suffix=suffix,
                                         delete=False, **options) as handle:
            temporary = Path(handle.name)
            if permissions is not None:
                os.chmod(handle.name, permissions)
            write(handle)
        temporary.replace(path)
    finally:
        if temporary:
            temporary.unlink(missing_ok=True)


def write_bytes(path: Path, data: bytes, *, prefix: str | None = None, suffix: str | None = None) -> None:
    _publish(path, "wb", lambda handle: handle.write(data), prefix=prefix, suffix=suffix)


def write_json(path: Path, value: Any, *, ensure_ascii: bool = True, indent: int | None = None,
               prefix: str | None = None, suffix: str | None = None, permissions: int | None = None) -> None:
    """Text mode, so line endings follow the platform exactly as `json.dump` to an open file does."""
    _publish(path, "w", lambda handle: json.dump(value, handle, ensure_ascii=ensure_ascii, indent=indent),
             prefix=prefix, suffix=suffix, permissions=permissions)
