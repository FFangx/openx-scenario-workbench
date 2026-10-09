"""Machine-local workbench preferences (language, appearance, encoder, esmini path)."""

from __future__ import annotations

import json
from typing import Any

from .asset_store import AssetStore
from .atomic_write import write_json


def read_preferences() -> dict[str, Any]:
    try:
        value = json.loads((AssetStore().root / "preferences.json").read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def interface_language() -> str:
    """"zh" or "en": preferences.json keeps the labels the desktop app has always written."""
    return "en" if read_preferences().get("language") == "English" else "zh"


def save_preferences(**values: Any) -> dict[str, Any]:
    data = {**read_preferences(), **values}
    write_json(AssetStore().root / "preferences.json", data, ensure_ascii=False)
    return data
