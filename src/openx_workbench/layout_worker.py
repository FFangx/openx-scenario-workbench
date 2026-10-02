"""Isolated native-heading layout provider; does not perform OCR or edit text."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from importlib.metadata import version
from pathlib import Path

MODEL_NAME = "PP-DocLayoutV2"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--wait-for-owner", action="store_true")
    args = parser.parse_args()
    if args.wait_for_owner and sys.stdin.readline().strip() != "start":
        return
    from paddlex import create_model
    from paddlex.inference.models.runners.paddle_static.config import PaddlePredictorOption

    started = time.monotonic()
    option = PaddlePredictorOption()
    option.enable_mkldnn = False
    option.cpu_threads = 4
    model = create_model(model_name=MODEL_NAME, device="cpu", engine="paddle_static", pp_option=option)
    digest = hashlib.sha256()
    model_dir = Path.home() / ".paddlex" / "official_models" / MODEL_NAME
    for path in sorted(model_dir.rglob("*")):
        if path.is_file():
            digest.update(path.relative_to(model_dir).as_posix().encode())
            digest.update(path.read_bytes())
    pages = []
    for page in json.loads(args.manifest.read_text(encoding="utf-8")):
        print(f"Analyzing layout on page {page['number']}", flush=True)
        results = list(model.predict(page["image"], batch_size=1, layout_nms=True))
        if len(results) != 1:
            raise ValueError("Layout must produce exactly one result per page")
        pages.append({**page, "regions": [{"label": box["label"], "score": float(box["score"]),
            "bbox": [float(v) for v in box["coordinate"]]} for box in results[0]["boxes"]]})
    args.output.write_text(json.dumps({"runtime": {name: version(name) for name in ("paddlex", "paddlepaddle")},
        "provenance": {"model": MODEL_NAME, "model_sha256": digest.hexdigest()},
        "seconds": round(time.monotonic() - started, 3), "pages": pages}), encoding="utf-8")


if __name__ == "__main__":
    main()
