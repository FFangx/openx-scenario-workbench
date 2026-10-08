"""Parsed assets kept on disk, one file per asset version, so a restart or a change to one asset parses
and describes only what changed.

An entry holds the parsed asset with its labels, its structure (the requirement-shaped description
every search compares against; describing a few hundred assets takes seconds, and the catalog
fingerprint needs it too) and its part of that fingerprint. It serves while the version's labels, its
SIM case metadata, the schema registry and this package's sources are what they were when it was
written; otherwise, or when the file does not load, the entry is made again. Entries are pickles in
the user's own data folder, written and read by this program only.
"""

from __future__ import annotations

import pickle
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

from .asset_store import AssetStore, AssetVersion
from .atomic_write import write_bytes
from .catalog import OpenXAsset
from .checkout import package_revision
from .retrieval import asset_fingerprint
from .reuse_facts import asset_structure_query
from .scene_package import RetrievalQuery

FOLDER = "catalog_cache"
# The sources this process runs: an entry that other code wrote is made again.
REVISION = package_revision(Path(__file__).resolve().parent)


@dataclass(frozen=True)
class Entry:
    asset: OpenXAsset
    structure: RetrievalQuery
    fingerprint: str  # the asset's part of the catalog fingerprint


def _path(store: AssetStore, version: AssetVersion) -> Path:
    return store.root / FOLDER / f"{version.asset_id}-{version.version_id}.pickle"


def read(store: AssetStore, version: AssetVersion, identity: tuple) -> Entry | None:
    """The entry kept for `version` under `identity`, or None."""
    try:
        kept = pickle.loads(_path(store, version).read_bytes())
    except Exception:  # noqa: BLE001 - missing, damaged or from other code: made again
        return None
    return kept["entry"] if isinstance(kept, dict) and kept.get("identity") == (REVISION, *identity) else None


def make(store: AssetStore, version: AssetVersion) -> Entry:
    asset = store.load_asset(version)
    structure = asset_structure_query(asset)
    return Entry(asset, structure, asset_fingerprint(asset, structure))


def write(store: AssetStore, version: AssetVersion, identity: tuple, entry: Entry) -> None:
    path = _path(store, version)
    with suppress(OSError):  # an entry that cannot be kept only costs the next start its time
        path.parent.mkdir(parents=True, exist_ok=True)
        write_bytes(path, pickle.dumps({"identity": (REVISION, *identity), "entry": entry},
                                       protocol=pickle.HIGHEST_PROTOCOL), suffix=".tmp")


def prune(store: AssetStore, versions: list[AssetVersion]) -> None:
    """Remove the entries of versions no longer in the catalog."""
    kept = {_path(store, version).name for version in versions}
    folder = store.root / FOLDER
    for path in folder.iterdir() if folder.is_dir() else ():
        if path.name not in kept:
            with suppress(OSError):
                path.unlink()
