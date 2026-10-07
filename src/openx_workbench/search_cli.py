from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import build_catalog_from_directory
from .retrieval import OpenXIndex, build_encoder
from .synonyms import expand_query


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an XOSC/XODR asset catalog and search it."
    )
    parser.add_argument("library", type=Path)
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=5)
    parser.add_argument("--encoder", choices=("hashing", "bge"), default="hashing")
    parser.add_argument("--index", type=Path)
    args = parser.parse_args()

    try:
        assets = build_catalog_from_directory(args.library)
        encoder = build_encoder(args.encoder)
        if args.index and args.index.exists():
            index = OpenXIndex.load(args.index, assets, encoder)
        else:
            index = OpenXIndex(assets, encoder)
            if args.index:
                index.save(args.index)
        results = index.search(expand_query(args.query), top_k=args.top_k)
    except (OSError, RuntimeError, ValueError) as exc:
        parser.error(str(exc))

    payload = {
        "asset_count": len(assets),
        "encoder": index.encoder.encoder_id,
        "results": [
            {
                "rank": rank,
                "asset_id": result.asset.asset_id,
                "title": result.asset.title,
                "xosc": result.asset.xosc_name,
                "xodr": result.asset.xodr_name,
                "score": result.score,
                "reuse_level": result.confirmation_level,
                "structural_level": result.reuse_level,
                "review_kind": result.confirmation_review_kind,
                "standard_checks": result.standard_checks,
                "estimated_change_cost": result.estimated_change_cost,
                "reasons": result.reasons,
            }
            for rank, result in enumerate(results, start=1)
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
