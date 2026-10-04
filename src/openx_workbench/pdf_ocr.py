"""Local OCR sidecar feeding the same anchored PDF V2 contract as native text."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

from .atomic_write import write_json
from .asset_store import default_store_root
from .pdf_v2.models import ParsedBlock

OCR_VERSION = "ppstructure-server-v1"


def _run_worker(command, log, timeout):
    from .windows_job import WindowsJob

    job = WindowsJob() if os.name == "nt" else None
    process = None
    try:
        with log.open("wb") as stream:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=stream, stderr=stream,
                creationflags=(subprocess.CREATE_NO_WINDOW | 4) if job else 0, start_new_session=os.name != "nt",
                env={**os.environ, "PYTHONUTF8": "1", "PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK": "True"})
        if job:
            job.assign(process)
            job.resume(process)
        process.stdin.write(b"start\n")
        process.stdin.close()
        return process.wait(timeout=timeout)
    finally:
        if job:
            job.close()
        elif process:
            import signal
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
        if process and process.poll() is None:
            process.kill()
            process.wait(timeout=10)


def _ocr_config(root=None):
    override = os.environ.get("OPENX_OCR_PYTHON")
    if override:
        return {"python": override}
    config = Path(root or default_store_root()) / "ocr_settings.json"
    saved = json.loads(config.read_text(encoding="utf-8")) if config.is_file() else {}
    return {"python": sys.executable, **saved}


def ocr_python(root=None):
    return _ocr_config(root)["python"]


def ocr_identity(root=None):
    saved = _ocr_config(root)
    return {"engine": OCR_VERSION, "python": str(Path(saved["python"]).resolve()), "runtime": saved.get("runtime", {}),
            "worker_sha256": hashlib.sha256(Path(__file__).with_name("ocr_worker.py").read_bytes()).hexdigest()}


def parse_ocr_pages(payload, expected_pages):
    """Validate completeness and convert rendered pixel boxes to PDF points."""
    if not isinstance(payload, dict):
        raise ValueError("OCR result is invalid")
    pages = payload.get("pages")
    if (not isinstance(pages, list) or len(pages) != len(expected_pages)
            or [p.get("number") for p in pages if isinstance(p, dict)] != list(expected_pages)):
        raise ValueError("OCR page coverage is incomplete or duplicated")
    blocks = []
    for page in pages:
        dimensions = [page.get(key) for key in ("width", "height", "image_width", "image_height")]
        if any(isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value <= 0 for value in dimensions):
            raise ValueError("OCR page dimensions are invalid")
        width, height, iw, ih = dimensions
        raw_blocks = page.get("blocks")
        if not isinstance(raw_blocks, list):
            raise ValueError("OCR page blocks are missing")
        page_blocks = []
        for index, raw in enumerate(raw_blocks):
            if not isinstance(raw, dict):
                raise ValueError("OCR block is invalid")
            text, label = raw.get("block_content", ""), raw.get("block_label", "unknown")
            if not isinstance(text, str):
                raise ValueError("OCR text must be text")
            if not text.strip() or label in {"image", "header_image", "footer_image", "header", "footer", "page_number"}:
                continue
            box = raw.get("block_bbox")
            if not isinstance(box, list) or len(box) != 4 or any(isinstance(v, bool) or not isinstance(v, (float, int)) or not math.isfinite(v) for v in box):
                raise ValueError("OCR bounding box is invalid")
            x0, y0, x1, y1 = box
            if not (0 <= x0 < x1 <= iw and 0 <= y0 < y1 <= ih):
                raise ValueError("OCR bounding box is outside its page")
            kind = "table" if label == "table" else "paragraph"
            level = None
            # Numbering owns chapter hierarchy; arbitrary large titles cannot
            # create chapters or turn table values into headings.
            match = re.match(r"^((?:\d+|[A-Z])(?:[.．]\d+){0,5})[.．]?\s+\S", text.strip())
            if label in {"doc_title", "document_title", "paragraph_title"} and match:
                kind, level = "heading", len(match[1].replace("．", ".").split("."))
            page_blocks.append(ParsedBlock(
                block_id=f"p{page['number']}-ocr{index}", page_number=page["number"],
                bbox=(x0 * width / iw, y0 * height / ih, x1 * width / iw, y1 * height / ih),
                text=text.strip(), block_type=kind, heading_level=level, source="ocr",
            ))
        if not page_blocks:
            raise ValueError(f"OCR found no readable content on page {page['number']}")
        blocks.extend(sorted(page_blocks, key=lambda b: (b.bbox[1], b.bbox[0], b.block_id)))
    return tuple(blocks)


def recognize_pdf_pages(path, pages, *, root=None, progress=None):
    return run_pdf_sidecar(path, pages, root=root, progress=progress,
        identity=ocr_identity(root), worker="ocr_worker.py", parse_pages=parse_ocr_pages,
        cache_name="ocr", message="本机识别扫描页与表格 / Recognizing scanned pages and tables locally",
        timeout=min(1800, 600 + 90 * len(pages)))


def run_pdf_sidecar(path, pages, *, root, progress, identity, worker, parse_pages, cache_name, message, timeout):
    """Render, own and cache a bounded local provider without changing source blocks."""
    import pymupdf

    if Path(path).stat().st_size > 100 * 1024 * 1024:
        raise ValueError("Local PDF recognition is limited to 500 pages and 100 MB")
    root = Path(root or default_store_root())
    identity = {**identity, "pdf_sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest(), "pages": list(pages)}
    checksum = hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest()
    cache = root / (cache_name + "_cache") / (checksum + ".json")
    if cache.is_file():
        cached = json.loads(cache.read_text(encoding="utf-8"))
        if not isinstance(cached, dict) or not isinstance(cached.get("runtime"), dict):
            raise ValueError(f"{cache_name} cache metadata is invalid")
        if cached.get("identity") != identity:
            raise ValueError(f"{cache_name} cache identity mismatch")
        return parse_pages(cached, pages), {"identity": identity, "runtime": cached["runtime"], "seconds": cached.get("seconds"), "cached": True, **cached.get("provenance", {})}
    if progress:
        progress(message)
    with tempfile.TemporaryDirectory(prefix=f"openx-{cache_name}-") as directory:
        folder = Path(directory)
        manifest = []
        with pymupdf.open(path) as pdf:
            if len(pdf) > 500:
                raise ValueError("Local PDF recognition is limited to 500 pages and 100 MB")
            if not pages or len(set(pages)) != len(pages) or any(type(n) is not int or not 1 <= n <= len(pdf) for n in pages):
                raise ValueError("Local PDF recognition pages are invalid")
            for number in pages:
                page = pdf[number - 1]
                image = page.get_pixmap(matrix=pymupdf.Matrix(2, 2), alpha=False)
                image_path = folder / f"page-{number}.png"
                image.save(image_path)
                manifest.append({"number": number, "image": str(image_path), "width": page.rect.width,
                                 "height": page.rect.height, "image_width": image.width, "image_height": image.height})
        input_path, output = folder / "manifest.json", folder / "result.json"
        input_path.write_text(json.dumps(manifest), encoding="utf-8")
        log = folder / "worker.log"
        try:
            result = _run_worker([ocr_python(root), str(Path(__file__).with_name(worker)), str(input_path), str(output), "--wait-for-owner"],
                                 log, timeout)
        except (OSError, subprocess.TimeoutExpired) as exc:
            root.mkdir(parents=True, exist_ok=True)
            if log.exists():
                (root / (cache_name + "_last_failure.log")).write_bytes(log.read_bytes())
            raise ValueError(f"本机 PDF 识别无法启动或超时 / Local {cache_name} failed to start or timed out") from exc
        if result or not output.is_file():
            # Provider logs may include source text. Keep them local; expose a
            # useful setup instruction rather than raw document-bearing output.
            root.mkdir(parents=True, exist_ok=True)
            (root / (cache_name + "_last_failure.log")).write_bytes(log.read_bytes())
            raise ValueError(f"本机 PDF 识别失败，请检查识别引擎配置 / Local {cache_name} failed; check OPENX_OCR_PYTHON. Details: {cache_name}_last_failure.log")
        payload = json.loads(output.read_text(encoding="utf-8"))
        if not isinstance(payload, dict) or not isinstance(payload.get("runtime"), dict):
            raise ValueError(f"{cache_name} provider metadata is invalid")
    blocks = parse_pages(payload, pages)
    # Render paths are temporary, not persistent source evidence.
    for page in payload["pages"]:
        page.pop("image", None)
    payload["identity"] = identity
    cache.parent.mkdir(parents=True, exist_ok=True)
    write_json(cache, payload, ensure_ascii=False)
    return blocks, {"identity": identity, "runtime": payload["runtime"], "seconds": payload.get("seconds"), "cached": False, **payload.get("provenance", {})}
