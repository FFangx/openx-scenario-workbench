"""Document-wide matching against one index and immutable source revisions."""
from collections import Counter
from dataclasses import asdict
import hashlib
import json

from .matching import source_identity
from .pdf_store import StoredScene
from .retrieval import OpenXIndex, catalog_fingerprint
from .reuse_trace import build_trace
from .scene_package import scene_package_to_query


def batch_signature(document, scenes: list[StoredScene], assets, versions, encoder: str) -> str:
    snapshot = {"document": asdict(document), "scenes": [
        {"id": scene.scene_id, "revision": scene.revision, "package": asdict(scene.package)} for scene in scenes],
        "catalog": catalog_fingerprint(assets), "versions": {
            key: value.version_id for key, value in sorted(versions.items())}, "encoder": encoder}
    return hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def match_document(document, scenes: list[StoredScene], index: OpenXIndex, versions: dict, top_k=3) -> dict:
    if any(scene.document != document for scene in scenes):
        raise ValueError("Batch scenes must belong to the selected document.")
    if top_k < 1:
        raise ValueError("Select at least one candidate per scene.")
    results = index.search_many([scene_package_to_query(scene.package) for scene in scenes], top_k)
    entries = []
    counts = Counter()
    for scene, candidates in zip(scenes, results):
        identity = source_identity(scene)  # scene.document == document, checked above
        traces = [build_trace(result, scene.package, versions.get(result.asset.asset_id), identity)
                  for result in candidates]
        best = traces[0]["reuse"] if traces else {"level": "no_candidates", "review_kind": ""}
        state = best.get("review_kind") or best["level"]
        counts[state] += 1
        entries.append({"source": {**asdict(scene.package), **identity},
                        "assessment": best, "candidates": traces})
    return {"kind": "batch_match", "source": {"title": document.filename,
            "document_id": document.document_id, "pdf_sha256": document.sha256},
            "signature": batch_signature(document, scenes, index.assets, versions, index.encoder.encoder_id),
            "encoder": index.encoder.encoder_id, "catalog_fingerprint": catalog_fingerprint(index.assets),
            "scene_count": len(entries), "counts": dict(counts), "entries": entries}
