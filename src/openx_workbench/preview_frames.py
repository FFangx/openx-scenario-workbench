"""Atomic, version-specific snapshots of frames produced by esmini."""
from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path

from .atomic_write import write_json
from .asset_store import AssetStore, AssetVersion


def frame_path(store: AssetStore, version: AssetVersion) -> Path:
    identity = json.dumps([version.asset_id, version.version_id, version.content_sha256])
    return store.root / "preview_frames" / (hashlib.sha256(identity.encode()).hexdigest() + ".json")


def save_frame(path: Path, jpeg: bytes, frame_number: int) -> None:
    """Publish image and provenance together; interrupted writes keep the old frame."""
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"renderer": "esmini", "frame_number": frame_number,
               "simulation_seconds": round(frame_number * 0.1, 1),
               "jpeg": base64.b64encode(jpeg).decode("ascii")}
    write_json(path, payload)


def read_frame(store: AssetStore, version: AssetVersion) -> tuple[bytes, dict] | None:
    try:
        payload = json.loads(frame_path(store, version).read_text(encoding="utf-8"))
        jpeg = base64.b64decode(payload.pop("jpeg"), validate=True)
        if payload["renderer"] != "esmini" or not jpeg.startswith(b"\xff\xd8") or not jpeg.endswith(b"\xff\xd9"):
            return None
        if not isinstance(payload["frame_number"], int) or payload["frame_number"] < 1:
            return None
        if payload["simulation_seconds"] != round(payload["frame_number"] * 0.1, 1):
            return None
        return jpeg, payload
    except (OSError, ValueError, KeyError, TypeError):
        return None
