"""Isolated PP-StructureV3 process; does not import OpenX or its model runtime."""
from __future__ import annotations

import argparse
import json
import sys
import time
from importlib.metadata import version
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--wait-for-owner", action="store_true")
    args = parser.parse_args()
    if args.wait_for_owner and sys.stdin.readline().strip() != "start":
        return
    from paddleocr import PPStructureV3
    started = time.monotonic()

    pipeline = PPStructureV3(
        device="cpu", engine="paddle", enable_mkldnn=True, cpu_threads=4,
        layout_detection_model_name="PP-DocLayoutV2",
        use_doc_orientation_classify=False, use_doc_unwarping=False,
        use_textline_orientation=False, use_table_recognition=True,
        use_seal_recognition=False, use_formula_recognition=False,
        use_chart_recognition=False,
        use_region_detection=False,
        text_detection_model_name="PP-OCRv5_server_det",
        text_recognition_model_name="PP-OCRv5_server_rec",
    )
    print("OCR models ready", flush=True)
    pages = []
    for page in json.loads(args.manifest.read_text(encoding="utf-8")):
        print(f"Recognizing page {page['number']}", flush=True)
        results = list(pipeline.predict(page["image"]))
        if len(results) != 1:
            raise ValueError("OCR must produce exactly one result per page")
        payload = results[0].json
        payload = payload.get("res", payload)
        pages.append({**page, "blocks": payload["parsing_res_list"]})
    args.output.write_text(json.dumps({
        "runtime": {name: version(name) for name in ("paddleocr", "paddlex", "paddlepaddle")},
        "seconds": round(time.monotonic() - started, 3),
        "pages": pages,
    }, ensure_ascii=False), encoding="utf-8")


if __name__ == "__main__":
    main()
