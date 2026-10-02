import copy
import os
import subprocess
import sys
from pathlib import Path

import pymupdf
import pytest

from openx_workbench.pdf_ocr import _run_worker, parse_ocr_pages
from openx_workbench.pdf_v2.parser import parse_pdf_structure


def payload(number=2):
    return {"runtime": {"paddleocr": "authored"}, "pages": [{
        "number": number, "width": 595, "height": 842, "image_width": 1190, "image_height": 1684,
        "blocks": [
            {"block_label": "paragraph_title", "block_content": "2.1 Stationary car braking", "block_bbox": [120, 100, 800, 160]},
            {"block_label": "text", "block_content": "Target car ahead at 50 km/h.", "block_bbox": [120, 180, 950, 230]},
            {"block_label": "table", "block_content": "<table><tr><td>Speed</td><td>50</td></tr></table>", "block_bbox": [120, 250, 950, 400]},
        ],
    }]}


def test_ocr_preserves_page_coordinates_table_and_provenance():
    blocks = parse_ocr_pages(payload(), [2])
    assert blocks[0].bbox == (60, 50, 400, 80)
    assert blocks[0].heading_level == 2
    assert blocks[-1].block_type == "table"
    assert blocks[-1].heading_level is None
    assert all(block.page_number == 2 and block.source == "ocr" for block in blocks)


@pytest.mark.parametrize("bad", ["duplicate", "missing", "invalid_entry", "nan", "outside", "empty"])
def test_ocr_rejects_incomplete_or_untraceable_results(bad):
    data = copy.deepcopy(payload())
    if bad == "duplicate":
        data["pages"].append(data["pages"][0])
    elif bad == "missing":
        data["pages"] = []
    elif bad == "invalid_entry":
        data["pages"].append(None)
    elif bad == "empty":
        data["pages"][0]["blocks"] = []
    else:
        data["pages"][0]["blocks"][0]["block_bbox"][0] = float("nan") if bad == "nan" else -5
    with pytest.raises(ValueError):
        parse_ocr_pages(data, [2])


def test_mixed_pdf_routes_only_image_page_and_preserves_native_page(tmp_path, monkeypatch):
    path = tmp_path / "mixed.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((60, 60), "1.1 Test conditions", fontsize=16)
        page.insert_text((60, 90), "All tests use a dry straight road in daylight.")
        pixmap = page.get_pixmap()
        scan = pdf.new_page()
        scan.insert_image(scan.rect, stream=pixmap.tobytes("png"))
        # A selectable footer must not mask the image-only body.
        scan.insert_text((60, 800), "Copyright - authored document for regression")
        pdf.save(path)
    observed = []
    def recognize(source, pages, **kwargs):
        assert Path(source) == path
        observed.append(pages)
        return parse_ocr_pages(payload(), pages), {"cached": False}
    monkeypatch.setattr("openx_workbench.pdf_ocr.recognize_pdf_pages", recognize)
    document, _ = parse_pdf_structure(path, ocr=True, root=tmp_path)
    assert observed == [[2]]
    assert {b.source for b in document.blocks if b.page_number == 1} == {"native_text"}
    assert {b.source for b in document.blocks if b.page_number == 2} == {"ocr"}
    assert "Copyright" not in "\n".join(b.text for b in document.blocks)


def test_native_table_preserves_row_and_column_associations(tmp_path):
    path = tmp_path / "table.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((60, 60), "2.1 Test parameters", fontsize=16)
        for x in (60, 230, 400):
            page.draw_line((x, 100), (x, 190))
        for y in (100, 130, 160, 190):
            page.draw_line((60, y), (400, y))
        for y, left, right in ((120, "Parameter", "Value"), (150, "Ego speed (km/h)", "50"), (180, "Target speed (km/h)", "0")):
            page.insert_text((70, y), left)
            page.insert_text((240, y), right)
        pdf.save(path)
    document, _ = parse_pdf_structure(path)
    tables = [block for block in document.blocks if block.block_type == "table"]
    assert len(tables) == 1
    assert "<tr><td>Ego speed (km/h)</td><td>50</td></tr>" in tables[0].text
    assert "<tr><td>Target speed (km/h)</td><td>0</td></tr>" in tables[0].text
    assert not any("Ego speed" in block.text for block in document.blocks if block.block_type != "table")


@pytest.mark.skipif(os.name != "nt", reason="Windows venv redirector/process tree")
def test_ocr_timeout_releases_redirector_and_grandchild_files(tmp_path):
    log = tmp_path / "worker.log"
    code = (
        "import sys,subprocess,time; sys.stdin.readline(); "
        "subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); time.sleep(30)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        _run_worker([sys.executable, "-c", code], log, 1)
    # An inherited handle held by a surviving grandchild blocks deletion on Windows.
    log.unlink()
