"""Matching of every scene of one or more PDFs against one index and immutable source revisions."""
from collections import Counter
from dataclasses import asdict
import hashlib
import json

from .matching import source_identity
from .pdf_store import StoredScene
from .retrieval import OpenXIndex
from .reuse_trace import build_trace
from .scene_package import scene_package_to_query


def batch_signature(documents, scenes: list[StoredScene], fingerprint: str, versions, encoder: str) -> str:
    """`fingerprint` is the asset catalog's `catalog_fingerprint`."""
    snapshot = {"documents": [asdict(document) for document in documents], "scenes": [
        {"document": scene.document.document_id, "id": scene.scene_id, "revision": scene.revision,
         "package": asdict(scene.package)} for scene in scenes],
        "catalog": fingerprint, "versions": {
            key: value.version_id for key, value in sorted(versions.items())}, "encoder": encoder}
    return hashlib.sha256(json.dumps(snapshot, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def batch_source(documents) -> dict:
    """What the summary covers: one PDF keeps its identity, a group of PDFs lists each one."""
    listed = [{"document_id": item.document_id, "filename": item.filename, "pdf_sha256": item.sha256}
              for item in documents]
    single = {"document_id": documents[0].document_id, "pdf_sha256": documents[0].sha256} if len(documents) == 1 else {}
    return {"title": " + ".join(item.filename for item in documents), **single, "documents": listed}


def match_documents(documents, scenes: list[StoredScene], index: OpenXIndex, versions: dict, top_k=3) -> dict:
    """One summary of the scenes of `documents`, in the order given; each row names its PDF."""
    if not documents:
        raise ValueError("Select at least one PDF.")
    by_id = {document.document_id: document for document in documents}
    if any(by_id.get(scene.document.document_id) != scene.document for scene in scenes):
        raise ValueError("Batch scenes must belong to the selected documents.")
    if top_k < 1:
        raise ValueError("Select at least one candidate per scene.")
    results = index.search_many([scene_package_to_query(scene.package) for scene in scenes], top_k)
    entries = []
    counts = Counter()
    for scene, candidates in zip(scenes, results):
        identity = source_identity(scene)  # scene.document is one of `documents`, checked above
        traces = [build_trace(result, scene.package, versions.get(result.asset.asset_id), identity)
                  for result in candidates]
        best = traces[0]["reuse"] if traces else {"level": "no_candidates", "review_kind": ""}
        state = best.get("review_kind") or best["level"]
        counts[state] += 1
        entries.append({"source": {**asdict(scene.package), **identity, "filename": scene.document.filename},
                        "assessment": best, "candidates": traces})
    return {"kind": "batch_match", "source": batch_source(documents),
            "signature": batch_signature(documents, scenes, index.fingerprint, versions, index.encoder.encoder_id),
            "encoder": index.encoder.encoder_id, "catalog_fingerprint": index.fingerprint,
            "scene_count": len(entries), "counts": dict(counts), "entries": entries}
