"""Ablation of the reuse ranking on the authored benchmark (examples/reuse-benchmark).

Each ranker orders the whole library for every typed requirement:

- ``name``: cosine similarity between the requirement text and the asset text
  (title, labels, entity and action names, road statistics). Similarity alone.
- ``structure-text``: cosine similarity between the two canonical, name-free
  structure summaries. The same facts as the rules, but compared by an encoder.
- ``rules``: the structural comparison alone (blocking differences, then change
  cost); ties keep library order.
- ``full``: the production ranking, rules first and similarity within a bucket.

Similarity rankers produce no verdict. Their decision is read as "reuse the top
hit", which is what a reviewer relying on similarity alone would do.
"""

from __future__ import annotations

import argparse
import json
import platform
import statistics
import time
from pathlib import Path

from .catalog import AssetFile, OpenXAsset, build_catalog
from .checkout import checkout_root
from .retrieval import OpenXIndex, build_encoder
from .reuse import LEVELS, change_cost, classify_reuse_level, compare_query_to_asset
from .scene_package import ScenePackage, query_structure_text, scene_package_to_query

RANKERS = ("name", "structure-text", "rules", "full")
NAMINGS = ("descriptive", "opaque")


def load_benchmark(path: Path, naming: str = "descriptive"):
    """Assets as the workbench would import them, and the typed requirements as queries."""
    spec = json.loads(path.read_text(encoding="utf-8"))
    root = path.parent
    roads = [AssetFile(f"roads/{item.name}", item.read_bytes()) for item in sorted((root / "roads").glob("*.xodr"))]
    assets: list[OpenXAsset] = []
    for number, record in enumerate(spec["assets"], 1):
        name = f"assets/{record['id']}.xosc"
        asset = build_catalog([AssetFile(name, (root / name).read_bytes()), *roads])[0]
        asset.asset_id = record["id"]
        asset.classification = {"function_type": record["function"]}
        if naming == "opaque":
            # A library whose names say nothing: only the file contents remain.
            asset.title = f"Asset {number:03d}"
            asset.bundle.scenario.name = asset.title
            asset.bundle.scenario.description = asset.title
        assets.append(asset)
    ids = {asset.asset_id for asset in assets}
    cases = []
    for record in spec["cases"]:
        labelled = {**record.get("confusers", {}), **record["relevant"]}
        if not set(labelled) <= ids or not set(labelled.values()) <= set(LEVELS):
            raise ValueError(f"Case {record['id']} labels an unknown asset or verdict.")
        best = set(record["relevant"].values()) or {record.get("best_level")}
        if len(best) != 1 or None in best:
            raise ValueError(f"Case {record['id']} needs one expected verdict for its best candidates.")
        # Title and text form the query text, as for a reviewed scene in the workbench.
        query = scene_package_to_query(ScenePackage(record["id"], record["title"], record["text"],
                                                    structure=record["structure"]))
        cases.append(({**record, "labels": labelled, "best_level": best.pop()}, query))
    if len(ids) != len(assets) or not cases:
        raise ValueError("The benchmark needs uniquely identified assets and at least one case.")
    return assets, cases


def rank(index: OpenXIndex | None, assets: list[OpenXAsset], query, ranker: str) -> list[tuple[str, str | None]]:
    """The whole library in ranked order, with each asset's verdict where the ranker gives one."""
    if ranker == "rules":
        keyed = []
        for position, asset in enumerate(assets):
            differences = compare_query_to_asset(query, asset)
            keyed.append(((sum(item.blocking for item in differences), change_cost(differences), position),
                          asset.asset_id, classify_reuse_level(differences)))
        return [(asset_id, level) for _, asset_id, level in sorted(keyed)]
    if ranker == "full":
        return [(item.asset.asset_id, item.reuse_level) for item in index.search("", query=query, top_k=len(assets))]
    structure = ranker == "structure-text"
    text = query_structure_text(query) if structure else query.text
    return [(index.assets[position].asset_id, None)
            for position, _ in index.recall(index.encoder.encode(text), len(assets), structure=structure)]


def score(ranked_by_case: list[tuple[dict, list[tuple[str, str | None]]]]) -> dict:
    rows, retrieval, pairs = [], [], []
    for case, ranked in ranked_by_case:
        order = [asset_id for asset_id, _ in ranked]
        verdicts = dict(ranked)
        top, top_verdict = ranked[0]
        relevant = case["relevant"]
        direct = {key for key, value in relevant.items() if value == "direct"}
        decision = top_verdict or "direct"  # similarity alone: reuse the top hit
        correct = decision == case["best_level"] and (not relevant or top in relevant)
        row = {"case": case["id"], "language": case["language"], "top": top, "decision": decision,
               "expected": case["best_level"], "decision_correct": correct,
               "unsafe_reuse": decision == "direct" and top not in direct}
        if relevant:
            row["first_relevant_rank"] = min(order.index(key) + 1 for key in relevant)
            retrieval.append(row["first_relevant_rank"])
        if top_verdict is not None:
            row["false_direct"] = sorted(key for key, value in verdicts.items() if value == "direct" and key not in direct)
            row["verdict_errors"] = {key: {"expected": value, "actual": verdicts[key]}
                                     for key, value in case["labels"].items() if verdicts[key] != value}
            pairs.extend(verdicts[key] == value for key, value in case["labels"].items())
        rows.append(row)
    result = {
        "cases": len(rows),
        "retrieval_cases": len(retrieval),
        **{f"recall_at_{k}": round(sum(rank <= k for rank in retrieval) / len(retrieval), 4) for k in (1, 3, 5)},
        "mrr": round(statistics.mean(1 / rank for rank in retrieval), 4),
        "recall_at_1_by_language": {
            language: round(statistics.mean(row["first_relevant_rank"] == 1 for row in subset), 4)
            for language in ("zh", "en")
            if (subset := [row for row in rows if row["language"] == language and "first_relevant_rank" in row])
        },
        "decision_accuracy": round(sum(row["decision_correct"] for row in rows) / len(rows), 4),
        "unsafe_reuse": sum(row["unsafe_reuse"] for row in rows),
    }
    if pairs:
        result["labelled_pairs"] = len(pairs)
        result["verdict_accuracy"] = round(sum(pairs) / len(pairs), 4)
        result["false_direct"] = sum(len(row["false_direct"]) for row in rows)
    result["per_case"] = rows
    return result


def run(path: Path, encoders: list[str]) -> dict:
    variants = []
    for naming in NAMINGS:
        assets, cases = load_benchmark(path, naming)
        variants.append({"ranker": "rules", "encoder": None, "naming": naming,
                         **score([(case, rank(None, assets, query, "rules")) for case, query in cases])})
        for encoder_name in encoders:
            encoder = build_encoder(encoder_name)
            index = OpenXIndex(assets, encoder)
            for ranker in ("name", "structure-text", "full"):
                started = time.perf_counter()
                ranked = [(case, rank(index, assets, query, ranker)) for case, query in cases]
                variants.append({"ranker": ranker, "encoder": encoder.encoder_id, "naming": naming,
                                 "mean_query_ms": round((time.perf_counter() - started) * 1000 / len(cases), 2),
                                 **score(ranked)})
    spec = json.loads(path.read_text(encoding="utf-8"))
    return {
        "benchmark": spec["name"], "benchmark_version": spec["version"], "scope": spec["scope"],
        "assets": len(spec["assets"]), "cases": len(spec["cases"]),
        "languages": {language: sum(case["language"] == language for case in spec["cases"]) for language in ("zh", "en")},
        "expected_best": {level: sum((set(case["relevant"].values()) or {case.get("best_level")}) == {level}
                                     for case in spec["cases"]) for level in LEVELS},
        "runtime": _runtime(encoders),
        "variants": variants,
    }


def _runtime(encoders: list[str]) -> dict:
    from importlib.metadata import PackageNotFoundError, version

    packages = {}
    for name in ("openx-scenario-workbench", "faiss-cpu", "numpy", *(("sentence-transformers", "torch") if "bge" in encoders else ())):
        try:
            packages[name] = version(name)
        except PackageNotFoundError:
            packages[name] = None
    return {"python": platform.python_version(), "platform": platform.system(), "packages": packages}


RANKER_LABELS = {
    "name": "Name similarity",
    "structure-text": "Structure-text similarity",
    "rules": "Structural rules only",
    "full": "Rules + similarity (workbench)",
}


def markdown(report: dict) -> str:
    lines = [
        "| Ranker | Encoder | Names | R@1 | R@3 | MRR | Decision acc. | Unsafe reuse | Verdict acc. | False direct |",
        "|---|---|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for item in report["variants"]:
        encoder = str(item["encoder"] or "—")
        encoder = "BGE-M3" if "bge-m3" in encoder else "hashing" if encoder.startswith("hashing") else encoder
        verdict = f"{item['verdict_accuracy']:.1%}" if "verdict_accuracy" in item else "n/a"
        false_direct = str(item["false_direct"]) if "false_direct" in item else "n/a"
        lines.append(
            f"| {RANKER_LABELS[item['ranker']]} | {encoder} | {item['naming']} | {item['recall_at_1']:.1%} | "
            f"{item['recall_at_3']:.1%} | {item['mrr']:.3f} | {item['decision_accuracy']:.1%} | "
            f"{item['unsafe_reuse']}/{item['cases']} | {verdict} | {false_direct} |"
        )
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("benchmark", type=Path, nargs="?",
                        default=checkout_root() / "examples" / "reuse-benchmark" / "benchmark.json")
    parser.add_argument("--encoders", nargs="+", choices=("hashing", "bge"), default=["hashing"])
    parser.add_argument("--output", type=Path, help="write the full report as JSON")
    parser.add_argument("--markdown", type=Path, help="write the summary table as Markdown")
    args = parser.parse_args(argv)
    report = run(args.benchmark, args.encoders)
    table = markdown(report)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.markdown:
        args.markdown.parent.mkdir(parents=True, exist_ok=True)
        args.markdown.write_text(table, encoding="utf-8")
    print(table)
    workbench = [item for item in report["variants"] if item["ranker"] == "full"]
    # The gate covers the shipped ranking only; the baselines are expected to fail it.
    return 0 if all(item["false_direct"] == 0 and item["unsafe_reuse"] == 0 for item in workbench) else 1


if __name__ == "__main__":
    raise SystemExit(main())
