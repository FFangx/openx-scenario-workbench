"""One trace contract shared by interactive and document-wide assessments."""
from dataclasses import asdict
from collections import Counter
from datetime import datetime, timezone

from .asset_store import AssetVersion
from .retrieval import RetrievalResult
from .scene_package import ScenePackage


def checked_trace(trace):
    """Display historical snapshots conservatively without rewriting reports."""
    from .schema_validation import standard_gate
    if trace.get("kind") == "batch_match":
        entries, counts = [], Counter()
        for entry in trace.get("entries", []):
            candidates = [checked_trace(candidate) for candidate in entry.get("candidates", [])]
            assessment = candidates[0]["reuse"] if candidates else entry["assessment"]
            if not candidates and assessment.get("level") == "direct":
                assessment = {**assessment, "level": "review", "structural_level": "direct", "review_kind": "standards"}
            counts[assessment.get("review_kind") or assessment["level"]] += 1
            entries.append({**entry, "candidates": candidates, "assessment": assessment})
        return {**trace, "entries": entries, "counts": dict(counts)}
    validation = ((trace.get("candidate") or {}).get("parsed_facts") or {}).get("validation")
    gate = standard_gate(validation)
    reuse = dict(trace.get("reuse") or {})
    if reuse.get("level") == "direct" and not gate["passed"]:
        reuse.update(level="review", structural_level="direct", review_kind="standards")
    return {**trace, "standard_checks": gate, "reuse": reuse}


def review_items(reuse: dict) -> list[dict]:
    """What a reviewer must confirm before a "review" assessment can be saved.

    Each unverified difference, or the file standard checks when they alone keep a structural
    direct match from being confirmed. `reuse` is a trace's "reuse" section.
    """
    if reuse.get("level") != "review":
        return []
    if reuse.get("structural_level") == "direct":
        return [{"id": "standards", "kind": "standards", "difference": None}]
    return [{"id": f"difference:{item['category']}:{item['requested']}:{item['candidate']}", "kind": "difference",
             "difference": index}
            for index, item in enumerate(reuse.get("differences", [])) if not item.get("verified", True)]


def sign_off(trace: dict, confirmations: dict[str, str]) -> dict:
    """The trace with each review item confirmed by its reason, or ValueError naming what is missing.

    A signed-off assessment keeps its verdict; the sign-off records who-decided-why next to it.
    """
    reuse = trace["reuse"]
    items = review_items(reuse)
    unknown = set(confirmations) - {item["id"] for item in items}
    if unknown:
        raise ValueError("Some confirmations do not match the current review items. Reload the assessment.")
    if not items:
        return trace
    missing = [item["id"] for item in items if not confirmations.get(item["id"], "").strip()]
    if missing:
        raise ValueError(f"Confirm each review item with a reason before saving ({len(missing)} open).")
    differences = reuse.get("differences", [])
    signed = [{"id": item["id"], "kind": item["kind"], "reason": confirmations[item["id"]].strip(),
               **({"difference": differences[item["difference"]]} if item["difference"] is not None else {})}
              for item in items]
    signoff = {"signed_at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": signed}
    return {**trace, "reuse": {**reuse, "review_signoff": signoff}}


def build_trace(result: RetrievalResult, package: ScenePackage | None,
                version: AssetVersion | None = None, source_identity: dict | None = None) -> dict:
    source = asdict(package) if package else None
    if source is not None:
        source.update(source_identity or {})
    candidate = {"asset_id": version.asset_id if version else result.asset.asset_id,
                 "version_id": version.version_id if version else None,
                 "version_number": version.version_number if version else None,
                 "content_sha256": version.content_sha256 if version else None,
                 "title": result.asset.title, "xosc": result.asset.xosc_name,
                 "xodr": result.asset.xodr_name,
                 "classification": result.asset.classification,
                 "parsed_facts": result.asset.bundle.to_dict()}
    return {"source": source, "candidate": candidate,
            "scores": {"combined": result.score, "semantic": result.vector_score,
                       "scenario": result.scenario_score, "road": result.road_score},
            "standard_checks": result.standard_checks,
            "reuse": {"level": result.confirmation_level, "structural_level": result.reuse_level,
                      "review_kind": result.confirmation_review_kind,
                      "estimated_change_cost": result.estimated_change_cost,
                      "reasons": list(result.reasons),
                      "differences": [asdict(item) for item in result.differences]}}
