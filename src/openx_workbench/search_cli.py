from __future__ import annotations

import argparse
import json
from pathlib import Path

from .catalog import build_catalog_from_directory
from .retrieval import OpenXIndex


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Build an XOSC/XODR asset catalog and search it."
    )
    parser.add_argument("library", type=Path)
    parser.add_argument("query")
    parser.add_argument("--top-k", type=int, default=5)
    args = parser.parse_args()

    try:
        assets = build_catalog_from_directory(args.library)
        results = OpenXIndex(assets).search(args.query, top_k=args.top_k)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))

    payload = {
        "asset_count": len(assets),
        "results": [
            {
                "rank": rank,
                "asset_id": result.asset.asset_id,
                "title": result.asset.title,
                "xosc": result.asset.xosc_name,
                "xodr": result.asset.xodr_name,
                "score": result.score,
                "reuse_level": result.reuse_level,
                "reasons": result.reasons,
            }
            for rank, result in enumerate(results, start=1)
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
