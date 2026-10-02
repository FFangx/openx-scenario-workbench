"""Reproducible multi-candidate evaluation, independent of private corpora."""

from __future__ import annotations

import argparse
import json
import statistics
import time
from dataclasses import replace
from pathlib import Path

from .catalog import AssetFile, build_catalog
from .retrieval import OpenXIndex, build_encoder, asset_text, asset_structure_text
from .scene_package import ScenePackage, scene_package_to_query, query_structure_text


def load_corpus(path: Path):
    corpus = json.loads(path.read_text(encoding="utf-8"))
    assets = []
    for record in corpus["assets"]:
        files = [
            AssetFile(record[key], (path.parent / record[key]).read_bytes())
            for key in ("xosc", "xodr")
        ]
        asset = build_catalog(files)[0]
        asset.asset_id = record["id"]
        asset.classification = record.get("classification", {})
        assets.append(asset)
    cases = [
        (
            record,
            scene_package_to_query(
                ScenePackage(
                    record["id"],
                    record["title"],
                    record["text"],
                    structure=record["structure"],
                )
            ),
        )
        for record in corpus["cases"]
    ]
    if (
        not cases
        or not assets
        or len({asset.asset_id for asset in assets}) != len(assets)
    ):
        raise ValueError("Evaluation requires cases and uniquely identified assets.")
    return assets, cases


def evaluate(index: OpenXIndex, cases):
    rows = []
    for case, query in cases:
        name_route = index._recall(
            index.encoder.encode(query.text), min(5, len(index.assets))
        )
        structure_route = index._recall(
            index.encoder.encode(query_structure_text(query)),
            min(5, len(index.assets)),
            structure=True,
        )
        relevant = set(case["relevant"])
        name_ids = [index.assets[position].asset_id for position, _ in name_route]
        structure_ids = [
            index.assets[position].asset_id for position, _ in structure_route
        ]
        started = time.perf_counter()
        results = index.search("", query=query, top_k=len(index.assets))
        duration = time.perf_counter() - started
        ranks = [
            rank
            for rank, result in enumerate(results, 1)
            if result.asset.asset_id in case["relevant"]
        ]
        if not ranks:
            raise ValueError(f"Case {case['id']} has no relevant asset in the corpus.")
        expected = case["levels"]
        verdicts = {result.asset.asset_id: result.reuse_level for result in results}
        rows.append(
            {
                "case": case["id"],
                "first_relevant_rank": min(ranks),
                "verdicts": verdicts,
                "name_route_hit_at_1": name_ids[0] in relevant,
                "structure_route_hit_at_1": structure_ids[0] in relevant,
                "union_hit_at_5": bool(relevant & set(name_ids + structure_ids)),
                "correct_verdicts": sum(
                    verdicts[key] == value for key, value in expected.items()
                ),
                "verdict_count": len(expected),
                "false_direct": sum(
                    verdicts[key] == "direct" and value != "direct"
                    for key, value in expected.items()
                ),
                "query_ms": round(duration * 1000, 3),
            }
        )
    total = sum(row["verdict_count"] for row in rows)
    if not total:
        raise ValueError("Expected verdicts are required.")
    return {
        "verdict_scope": "structural_comparison",
        "encoder": index.encoder.encoder_id,
        "backend": index.recall_backend,
        "dimensions": len(index.vectors[0]),
        "asset_count": len(index.assets),
        "case_count": len(rows),
        "hit_at_1": sum(row["first_relevant_rank"] <= 1 for row in rows) / len(rows),
        "hit_at_3": sum(row["first_relevant_rank"] <= 3 for row in rows) / len(rows),
        "mrr": statistics.mean(1 / row["first_relevant_rank"] for row in rows),
        "name_route_hit_at_1": statistics.mean(
            row["name_route_hit_at_1"] for row in rows
        ),
        "structure_route_hit_at_1": statistics.mean(
            row["structure_route_hit_at_1"] for row in rows
        ),
        "union_hit_at_5": statistics.mean(row["union_hit_at_5"] for row in rows),
        "verdict_accuracy": sum(row["correct_verdicts"] for row in rows) / total,
        "false_direct": sum(row["false_direct"] for row in rows),
        "cases": rows,
    }


def benchmark(assets, cases, encoder, size: int):
    if size <= 0:
        raise ValueError("Benchmark sizes must be positive.")
    # Repeated authored patterns isolate scaling; they are not production data
    # or an extraction benchmark. Unique IDs preserve catalog multiplicity.
    expanded = [
        replace(assets[index % len(assets)], asset_id=f"scale-{index}")
        for index in range(size)
    ]
    started = time.perf_counter()
    index = OpenXIndex(expanded, encoder)
    build_s = time.perf_counter() - started
    durations = []
    for _, query in cases:
        started = time.perf_counter()
        index.search("", query=query, top_k=5)
        durations.append((time.perf_counter() - started) * 1000)
    return {
        "size": size,
        "data": "repeated authored patterns",
        "unique_name_texts": len({asset_text(asset) for asset in expanded}),
        "unique_structure_texts": len(
            {asset_structure_text(asset) for asset in expanded}
        ),
        "build_s": round(build_s, 3),
        "median_query_ms": round(statistics.median(durations), 3),
        "max_query_ms": round(max(durations), 3),
        "vector_float32_bytes": size * len(index.vectors[0]) * 4 * 2,
        "memory_note": "vector payload only; excludes Python objects, model and catalog",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("corpus", type=Path)
    parser.add_argument("--encoder", choices=("hashing", "bge"), default="hashing")
    parser.add_argument("--sizes", type=int, nargs="*", default=[])
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    assets, cases = load_corpus(args.corpus)
    encoder = build_encoder(args.encoder)
    report = evaluate(OpenXIndex(assets, encoder), cases)
    report["scope"] = (
        "Authored structural ranking/verdict regression; not PDF extraction accuracy or ASAM conformance."
    )
    report["benchmarks"] = [
        benchmark(assets, cases, encoder, size) for size in args.sizes
    ]
    content = json.dumps(report, ensure_ascii=False, indent=2)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(content, encoding="utf-8")
    print(content)
    if (
        report["hit_at_1"] < 1
        or report["verdict_accuracy"] < 1
        or report["false_direct"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
