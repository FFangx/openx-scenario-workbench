"""Retrieval and assessment steps used by the HTTP API and the command-line tools.

Callers own their caching of the returned index.
"""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from typing import Any

from .asset_store import AssetStore, AssetVersion
from .catalog import OpenXAsset
from .pdf_store import StoredScene
from .preferences import read_preferences
from .retrieval import OpenXIndex, RetrievalResult, build_encoder, catalog_fingerprint
from .reuse_trace import build_trace
from .scene_package import RetrievalQuery, ScenePackage, scene_package_to_query

ENCODERS = {"bge", "hashing"}


def known_encoder(value: Any) -> str:
    # Older preference files stored the display label; treat anything unrecognized as BGE.
    return value if value in ENCODERS else "bge"


def preferred_encoder() -> str:
    return known_encoder(read_preferences().get("encoder"))


@lru_cache(maxsize=2)
def encoder(name: str):
    return build_encoder(name)


def index_identity(catalog: list[OpenXAsset], encoder_name: str, fingerprint: str | None = None) -> tuple[str, str]:
    return encoder_name, fingerprint or catalog_fingerprint(catalog)


def open_index(catalog: list[OpenXAsset], identity: tuple[str, str]) -> OpenXIndex:
    """Load the saved index for `identity`, rebuilding and saving it when the file is missing or unusable."""
    encoder_name, fingerprint = identity
    path = AssetStore().root / "indexes" / encoder_name / f"{fingerprint[:24]}.bin"
    selected = encoder(encoder_name)
    try:
        return OpenXIndex.load(path, catalog, selected, fingerprint=fingerprint)
    except (OSError, ValueError, KeyError, TypeError):
        index = OpenXIndex(catalog, selected, fingerprint=fingerprint)
        index.save(path)
        return index


def scene_query(package: ScenePackage | None, text: str, *, skip_contained: bool = False) -> RetrievalQuery | None:
    """The scene's retrieval query with stripped free `text` appended.

    The web client prefills its search box with the scene title, so the API passes `skip_contained` to avoid
    repeating text the query already holds.
    """
    query = scene_package_to_query(package) if package else None
    text = text.strip()
    if query and text and not (skip_contained and text in query.text):
        query = replace(query, text=f"{query.text} {text}")
    return query


def search(index: OpenXIndex, query: RetrievalQuery | None, text: str, top_k: int) -> list[RetrievalResult]:
    return index.search(query.text if query else text.strip(), query=query, top_k=top_k)


def source_identity(stored: StoredScene) -> dict[str, Any]:
    return {"document_id": stored.document.document_id, "pdf_sha256": stored.document.sha256,
            "scene_id": stored.scene_id, "revision": stored.revision}


def assessment_trace(result: RetrievalResult, package: ScenePackage | None, version: AssetVersion | None,
                     stored: StoredScene | None = None) -> dict:
    """The reuse trace, carrying PDF provenance when `stored` is the scene `package` came from."""
    identity = source_identity(stored) if package and stored and stored.package is package else {}
    return build_trace(result, package, version, identity)
