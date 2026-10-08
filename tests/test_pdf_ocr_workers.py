"""PDF pages shared by several real worker processes, with a stand-in for the Paddle engine."""
import json
import sys
import threading
import time

import pymupdf
import pytest

from openx_workbench import native_layout, pdf_ocr
from openx_workbench.native_layout import rescue_native_structure
from openx_workbench.pdf_ocr import WorkerPool, parse_ocr_pages, recognize_pdf_pages, run_pdf_sidecar
from openx_workbench.pdf_v2.parser import parse_pdf_structure

FAKE_WORKER = """
import json, os, sys, time
manifest, output = sys.argv[1], sys.argv[2]
assert sys.stdin.readline().strip() == "start"
pages = json.loads(open(manifest, encoding="utf-8").read())
numbers = [page["number"] for page in pages]
started = time.time()
if int(os.environ.get("FAKE_FAIL", "0")) in numbers:
    print("boom", flush=True)
    sys.exit(3)
time.sleep(float(os.environ["FAKE_SECONDS"]))
with open(os.path.join(os.environ["FAKE_RECORD"], f"{os.getpid()}.json"), "w") as record:
    json.dump({"pages": numbers, "start": started, "end": time.time()}, record)
with open(output, "w", encoding="utf-8") as stream:
    json.dump({"runtime": {"paddle": "fake"}, "seconds": 1.0, "pages": [{**page, "regions": [], "blocks": [
        {"block_label": "text", "block_content": f"Text on page {page['number']}", "block_bbox": [10, 10, 100, 40]}]}
        for page in pages]}, stream)
"""


@pytest.fixture
def fake_engine(tmp_path, monkeypatch):
    """Runs the stand-in through the real process owner; returns the records of finished workers."""
    script, records = tmp_path / "fake_worker.py", tmp_path / "records"
    script.write_text(FAKE_WORKER, encoding="utf-8")
    records.mkdir()
    real = pdf_ocr._run_worker
    monkeypatch.setattr(pdf_ocr, "_run_worker",
        lambda command, log, timeout, *stop: real([sys.executable, str(script), *command[2:]], log, timeout, *stop))
    monkeypatch.setenv("FAKE_RECORD", str(records))
    monkeypatch.setenv("FAKE_SECONDS", "1.5")
    return lambda: [json.loads(path.read_text()) for path in records.iterdir()]


def text_pdf(path, pages, label="Scan"):
    # The stand-in engine never looks at the rendered pages.
    with pymupdf.open() as pdf:
        for number in range(1, pages + 1):
            pdf.new_page(width=200, height=280).insert_text((20, 40), f"{number} {label} page {number}")
        pdf.save(path)
    return path


def sidecar(path, pages, root, pool):
    return run_pdf_sidecar(path, pages, root=root, progress=None, identity={"engine": "fake"}, worker="ocr_worker.py",
                           parse_pages=parse_ocr_pages, cache_name="ocr", message="", timeout=60, pool=pool)


def test_pages_are_split_across_workers_running_at_once(tmp_path, fake_engine):
    blocks, audit = sidecar(text_pdf(tmp_path / "scan.pdf", 5), [1, 2, 3, 4, 5], tmp_path, WorkerPool(2))
    records = fake_engine()
    assert sorted(record["pages"] for record in records) == [[1, 3, 5], [2, 4]]
    assert max(record["start"] for record in records) < min(record["end"] for record in records)
    assert [block.page_number for block in blocks] == [1, 2, 3, 4, 5]
    cached = json.loads(next((tmp_path / "ocr_cache").glob("*.json")).read_text(encoding="utf-8"))
    assert [page["number"] for page in cached["pages"]] == [1, 2, 3, 4, 5]
    assert not any("image" in page for page in cached["pages"])
    assert audit["runtime"] == {"paddle": "fake"} and audit["seconds"] == 1.0 and not audit["cached"]


def test_worker_count_changes_neither_result_nor_cache(tmp_path, monkeypatch, fake_engine):
    monkeypatch.setenv("FAKE_SECONDS", "0")
    path = text_pdf(tmp_path / "scan.pdf", 4)
    runs = []
    for pool in (None, WorkerPool(3)):
        root = tmp_path / f"root-{len(runs)}"
        blocks, audit = sidecar(path, [1, 2, 3, 4], root, pool)
        cache = next((root / "ocr_cache").glob("*.json"))
        runs.append((blocks, audit, cache.name, cache.read_text(encoding="utf-8")))
    assert runs[0] == runs[1]
    assert len(fake_engine()) == 1 + 3


def test_failed_worker_stops_the_others_and_keeps_its_log(tmp_path, monkeypatch, fake_engine):
    monkeypatch.setenv("FAKE_FAIL", "2")
    monkeypatch.setenv("FAKE_SECONDS", "60")
    started = time.monotonic()
    with pytest.raises(ValueError, match="ocr_last_failure.log"):
        sidecar(text_pdf(tmp_path / "scan.pdf", 4), [1, 2, 3, 4], tmp_path, WorkerPool(2))
    assert time.monotonic() - started < 30
    assert "boom" in (tmp_path / "ocr_last_failure.log").read_text(encoding="utf-8")
    assert not fake_engine() and not list(tmp_path.glob("ocr_cache/*.json"))


def at_once(extract, labels):
    """Extract several PDFs in threads, as an import of several PDFs does."""
    errors = []

    def run(label):
        try:
            extract(label)
        except Exception as error:  # noqa: BLE001 - reported by the assertion below
            errors.append(error)

    threads = [threading.Thread(target=run, args=(label,)) for label in labels]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors


def most_at_once(records):
    return max(sum(other["start"] <= record["start"] < other["end"] for other in records) for record in records)


def test_pdfs_extracted_at_once_share_one_pool(tmp_path, monkeypatch, fake_engine):
    monkeypatch.setenv("FAKE_SECONDS", "0.5")
    pool = WorkerPool(2)
    at_once(lambda label: sidecar(text_pdf(tmp_path / f"{label}.pdf", 4, label), [1, 2, 3, 4], tmp_path, pool),
            ("first", "second"))
    records = fake_engine()
    assert len(records) == 4 and most_at_once(records) <= 2


def test_scanned_pdfs_extracted_at_once_are_recognized_one_at_a_time(tmp_path, monkeypatch, fake_engine):
    monkeypatch.setenv("FAKE_SECONDS", "0.5")
    at_once(lambda label: recognize_pdf_pages(text_pdf(tmp_path / f"{label}.pdf", 2, label), [1, 2], root=tmp_path),
            ("first", "second", "third"))
    records = fake_engine()
    assert [record["pages"] for record in records] == [[1, 2]] * 3
    assert most_at_once(records) == 1


def test_layout_shares_its_pages_and_ocr_keeps_one_process_per_pdf(tmp_path, monkeypatch, fake_engine):
    monkeypatch.setenv("FAKE_SECONDS", "0")
    monkeypatch.setattr(native_layout, "WORKERS", WorkerPool(2), raising=False)
    path = text_pdf(tmp_path / "native.pdf", 3, "Native")
    document, _ = parse_pdf_structure(path)
    rescue_native_structure(path, document, root=tmp_path)
    assert sorted(record["pages"] for record in fake_engine()) == [[1, 3], [2]]
    for record in (tmp_path / "records").iterdir():
        record.unlink()
    recognize_pdf_pages(path, [1, 2, 3], root=tmp_path)
    assert [record["pages"] for record in fake_engine()] == [[1, 2, 3]]
