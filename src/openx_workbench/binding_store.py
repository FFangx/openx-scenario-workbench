"""Requirement ↔ asset bindings a person confirmed: one table for the machine, shared by every project.

A requirement is a scene of a PDF, keyed by the PDF's content, its clause number and the title the
extraction gave it, so the same standard imported into another project, or extracted again, finds
its bindings. A binding names one or more asset versions (variants of the same test) with one
preferred, and pins them like a saved report does. Nothing here changes a binding by itself: a newer
asset version or an edited scene only marks it for a second look.

The model's suggestions are kept next to the table, one file per PDF, so a suggestion survives the
dialog and the service; they enter the table only when a person confirms them.
"""

from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .asset_store import AssetStore, AssetVersion
from .atomic_write import write_json
from .pdf_store import PdfStore, StoredScene
from .scene_package import ScenePackage
from .store_lock import store_transaction

STATUSES = ("same", "modify", "none")  # same test / same test after changes / no asset builds it
SOURCES = ("suggestion", "manual")  # the model's suggestion accepted as is / chosen or changed by a person
FACTS = ("title", "preferred_text", "road_types", "weather", "time_of_day", "entities", "actions", "triggers",
         "parameters", "structure")
REFERENCE = "binding:"
TEXT_LIMIT = 2000


def scene_digest(package: ScenePackage) -> str:
    """The facts matching reads from a scene; an edit that changes none of them changes nothing here."""
    facts = {key: getattr(package, key) for key in FACTS}
    return hashlib.sha256(json.dumps(facts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def section_of(package: ScenePackage) -> str:
    return package.evidence[0].section_id if package.evidence else ""


def requirement_keys(pdf: PdfStore, project_id: str, document_id: str,
                     scenes: list[StoredScene]) -> dict[str, str]:
    """Scene id -> requirement key: PDF content, clause number and extracted title (revision 1, which
    later edits never change), with the occurrence number for a clause and title that repeat."""
    seen: Counter = Counter()
    keys = {}
    for scene in scenes:
        first = pdf.revisions(project_id, document_id, scene.scene_id)[0].package
        identity = (scene.document.sha256, section_of(first), first.title.strip())
        seen[identity] += 1
        keys[scene.scene_id] = hashlib.sha256(
            json.dumps([*identity, seen[identity]], ensure_ascii=False).encode()).hexdigest()[:24]
    return keys


def requirement_record(scene: StoredScene) -> dict[str, Any]:
    document = scene.document
    return {"pdf_sha256": document.sha256, "filename": document.filename, "standard": document.source_standard,
            "section_id": section_of(scene.package), "title": scene.package.title,
            "project_id": document.project_id, "document_id": document.document_id, "scene_id": scene.scene_id,
            "revision": scene.revision, "scene_digest": scene_digest(scene.package)}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _text(value: Any, limit: int = TEXT_LIMIT) -> str:
    return value.strip()[:limit] if isinstance(value, str) else ""


class BindingStore:
    def __init__(self, assets: AssetStore | None = None):
        self.assets = assets or AssetStore()
        self.root = self.assets.root / "bindings"
        self.path = self.root / "bindings.json"

    # ---------- the table ----------

    def entries(self) -> dict[str, dict[str, Any]]:
        if not self.path.is_file():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8")).get("entries", {})

    def _write(self, entries: dict[str, dict[str, Any]]) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        write_json(self.path, {"entries": entries}, ensure_ascii=False, indent=1, prefix="bindings-", suffix=".tmp")

    def confirm(self, key: str, scene: StoredScene, status: str, assets: list[dict[str, Any]], *,
                changes: str = "", source: str = "manual") -> dict[str, Any]:
        """Store what a person confirmed for the scene, replacing an earlier binding of it.

        `assets` lists {"version": AssetVersion, "preferred": bool, "verdict", "reason", "changes"}; the
        model's words for an asset travel with it. The named versions are pinned, those no longer named
        released.
        """
        if status not in STATUSES or source not in SOURCES:
            raise ValueError("Unknown binding status or source.")
        if (status == "none") != (not assets):
            raise ValueError("绑定“没有素材”时不能选素材，其余必须至少选一个 / "
                             "Select assets unless marking the scene as having none.")
        ids = [item["version"].asset_id for item in assets]
        if len(set(ids)) != len(ids):
            raise ValueError("Bind each asset once.")
        preferred = [item for item in assets if item.get("preferred")]
        if assets and len(preferred) > 1:
            raise ValueError("Mark one preferred asset.")
        chosen = preferred[0] if preferred else (assets[0] if assets else None)
        with store_transaction(self.assets.root):
            versions = {(item.asset_id, item.version_id): item for item in self.assets.versions()}
            if any((item["version"].asset_id, item["version"].version_id) not in versions for item in assets):
                raise ValueError("Unknown asset version.")
            entries = self.entries()
            before = entries.get(key)
            entry = {
                "key": key, "requirement": requirement_record(scene), "status": status,
                "changes": _text(changes) if status == "modify" else "",
                "assets": [{"asset_id": item["version"].asset_id, "version_id": item["version"].version_id,
                            "version_number": item["version"].version_number, "title": item["version"].title,
                            "preferred": item is chosen, "verdict": _text(item.get("verdict"), 40),
                            "reason": _text(item.get("reason")), "changes": _text(item.get("changes"))}
                           for item in assets],
                "source": source, "confirmed_at": _now(),
            }
            new = {(item["asset_id"], item["version_id"]) for item in entry["assets"]}
            old = {(item["asset_id"], item["version_id"]) for item in (before or {}).get("assets", [])}
            for pair in sorted(new - old):
                self.assets.pin_version(REFERENCE + key, versions[pair])
            entries[key] = entry
            self._write(entries)
            for pair in sorted(old - new):
                if pair in versions:
                    self.assets.release_reference(REFERENCE + key, versions[pair])
        return entry

    def remove(self, key: str) -> None:
        with store_transaction(self.assets.root):
            entries = self.entries()
            entry = entries.pop(key, None)
            if entry is None:
                raise ValueError("This scene has no confirmed binding.")
            self._write(entries)
            versions = {(item.asset_id, item.version_id): item for item in self.assets.versions()}
            for item in entry["assets"]:
                version = versions.get((item["asset_id"], item["version_id"]))
                if version is not None:
                    self.assets.release_reference(REFERENCE + key, version)

    # ---------- the model's suggestions, one file per PDF ----------

    def _suggestion_path(self, pdf_sha256: str) -> Path:
        if len(pdf_sha256) != 64 or any(char not in "0123456789abcdef" for char in pdf_sha256):
            raise ValueError("Invalid PDF checksum.")
        return self.root / "suggestions" / f"{pdf_sha256}.json"

    def suggestions(self, pdf_sha256: str) -> dict[str, dict[str, Any]]:
        path = self._suggestion_path(pdf_sha256)
        return json.loads(path.read_text(encoding="utf-8")).get("scenes", {}) if path.is_file() else {}

    def save_suggestion(self, pdf_sha256: str, key: str, suggestion: dict[str, Any]) -> None:
        """The newest suggestion of one requirement; the others in the file stay."""
        path = self._suggestion_path(pdf_sha256)
        with store_transaction(self.assets.root):
            scenes = self.suggestions(pdf_sha256)
            scenes[key] = suggestion
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, {"scenes": scenes}, ensure_ascii=False, indent=1, prefix="suggestions-", suffix=".tmp")


def stale_reasons(entry: dict[str, Any], scene: StoredScene | None, latest: dict[str, AssetVersion]) -> list[str]:
    """Why a confirmed binding needs a second look: "scene" (its facts changed since), "asset" (a bound
    asset has a newer version, or none any more)."""
    reasons = []
    if scene is not None and entry["requirement"].get("scene_digest") != scene_digest(scene.package):
        reasons.append("scene")
    if any((version := latest.get(item["asset_id"])) is None or version.version_id != item["version_id"]
           for item in entry["assets"]):
        reasons.append("asset")
    return reasons
