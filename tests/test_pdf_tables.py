import json
from types import SimpleNamespace

import pymupdf
import pytest

from openx_workbench.asset_store import AssetStore
from openx_workbench.pdf_ocr import parse_ocr_pages
from openx_workbench.pdf_store import PdfStore
from openx_workbench.pdf_tables import native_table_html
from openx_workbench.pdf_v2.parser import parse_pdf_structure
from openx_workbench.pdf_v2.section_tree import build_section_tree
from openx_workbench.project_store import ProjectStore
from test_pdf_v2_migration import fake_client


def table(geometry):
    return SimpleNamespace(rows=[SimpleNamespace(cells=row) for row in geometry])


def test_detected_rowspan_owns_values_once_and_preserves_zero():
    html, kind = native_table_html(table([
        [(0, 0, 100, 20), (100, 0, 200, 10)], [None, (100, 10, 200, 20)]
    ]), [["AEB", "50"], [None, 0]])
    assert html == '<table><tr><td rowspan="2">AEB</td><td>50</td></tr><tr><td>0</td></tr></table>'
    assert kind == "table_merged_cells"


def test_colspan_does_not_turn_real_empty_cell_into_merged_value():
    html, kind = native_table_html(table([
        [(0, 0, 200, 10), None], [(0, 10, 100, 20), (100, 10, 200, 20)]
    ]), [["Parameters", None], ["Notes", ""]])
    assert html == '<table><tr><td colspan="2">Parameters</td></tr><tr><td>Notes</td><td></td></tr></table>'
    assert kind == "table_merged_cells"
    assert "data-unresolved" not in html


@pytest.mark.parametrize("case", ["overlap", "hole", "no_geometry", "text_without_box", "nan", "collapsed", "ambiguous_edge"])
def test_ambiguous_geometry_preserves_slots_without_invented_spans(case):
    geometry = [[(0, 0, 100, 10), (100, 0, 200, 10)]]
    values = [["Target", "0"]]
    if case == "overlap":
        geometry[0][0] = (0, 0, 200, 10)
    elif case == "hole":
        geometry.append([None, (100, 10, 200, 20)])
        values.append([None, "50"])
    elif case == "no_geometry":
        geometry = []
    elif case == "text_without_box":
        geometry[0][1] = None
    elif case == "nan":
        geometry[0][1] = (100, 0, float("nan"), 10)
    elif case == "ambiguous_edge":
        geometry.append([(0, 10, 100.4, 20), (100.6, 10, 200, 20)])
        values.append(["Ego", "50"])
    else:
        geometry[0][1] = (100, 0, 100.1, 10)
    html, kind = native_table_html(table(geometry), values)
    assert kind == "table_geometry_unresolved"
    assert "rowspan" not in html and "colspan" not in html
    assert "<td>0</td>" in html
    assert "Target" in html


def test_table_text_is_escaped_and_newlines_retained():
    html, kind = native_table_html(table([[(0, 0, 100, 10)]]), [["A < B\n50 & 0"]])
    assert html == "<table><tr><td>A &lt; B<br>50 &amp; 0</td></tr></table>"
    assert kind is None


def draw_table(page, *, y, cells):
    xs = (60, 230, 400)
    for r, c, rowspan, colspan, text in cells:
        page.draw_rect((xs[c], y + 30*r, xs[c+colspan], y + 30*(r+rowspan)))
        if text:
            page.insert_text((xs[c] + 10, y + 30*r + 20), text, fontsize=11)


def continued_pdf():
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((60, 60), "1.1 Test conditions", fontsize=16)
        page.insert_text((60, 90), "Use a dry straight road in daylight.")
        page.insert_text((60, 140), "2.1 Stationary car braking", fontsize=16)
        page.insert_text((60, 170), "Ego approaches a stationary target car ahead. Test AEB braking.")
        draw_table(page, y=210, cells=[(0, 0, 1, 2, "Test parameters (km/h)"),
            (1, 0, 1, 1, "Ego speed"), (1, 1, 1, 1, "50"), (2, 0, 1, 1, "Notes"), (2, 1, 1, 1, "")])
        page = pdf.new_page()
        page.insert_text((60, 60), "Table 1 - continued", fontsize=11)
        draw_table(page, y=100, cells=[(0, 0, 1, 1, "Parameter"), (0, 1, 1, 1, "Value (km/h)"),
            (1, 0, 1, 1, "Target speed"), (1, 1, 1, 1, "0")])
        page = pdf.new_page()
        page.insert_text((60, 60), "2.2 Moving target braking", fontsize=16)
        page.insert_text((60, 90), "Ego approaches a moving target car ahead. Test AEB braking.")
        draw_table(page, y=120, cells=[(0, 0, 1, 1, "Ego speed (km/h)"), (0, 1, 1, 1, "80"),
            (1, 0, 1, 1, "Target speed (km/h)"), (1, 1, 1, 1, "20")])
        return pdf.tobytes()


def test_real_native_spans_and_cross_page_owner_stop_at_next_heading(tmp_path):
    path = tmp_path / "continued.pdf"
    path.write_bytes(continued_pdf())
    doc, outline = parse_pdf_structure(path)
    tables = [b for b in doc.blocks if b.block_type == "table"]
    assert len(tables) == 3
    assert '<td colspan="2">Test parameters (km/h)</td>' in tables[0].text
    assert '<tr><td>Notes</td><td></td></tr>' in tables[0].text
    assert '<tr><td>Target speed</td><td>0</td></tr>' in tables[1].text
    assert {f.kind for f in doc.structure_flags} == {"table_merged_cells"}
    tree = build_section_tree(doc, outline=outline)
    first, second = tree.find_by_section_id("2.1"), tree.find_by_section_id("2.2")
    assert first.page_range == (1, 2)
    assert tables[0].block_id in first.block_ids and tables[1].block_id in first.block_ids
    assert tables[2].block_id not in first.block_ids
    assert tables[2].block_id in second.block_ids


def test_real_native_vertical_span(tmp_path):
    path = tmp_path / "rowspan.pdf"
    with pymupdf.open() as pdf:
        page = pdf.new_page()
        page.insert_text((60, 60), "2.1 Test parameters", fontsize=16)
        draw_table(page, y=100, cells=[(0, 0, 2, 1, "AEB"), (0, 1, 1, 1, "50"), (1, 1, 1, 1, "0")])
        pdf.save(path)
    doc, _ = parse_pdf_structure(path)
    block = next(b for b in doc.blocks if b.block_type == "table")
    assert block.text == '<table><tr><td rowspan="2">AEB</td><td>50</td></tr><tr><td>0</td></tr></table>'
    assert block.source == "native_text"


def test_ocr_table_spans_pass_through_without_value_expansion():
    html = '<table><tr><td rowspan="2">AEB</td><td>50</td></tr><tr><td>0</td></tr></table>'
    blocks = parse_ocr_pages({"pages": [{"number": 1, "width": 595, "height": 842, "image_width": 1190,
        "image_height": 1684, "blocks": [{"block_label": "table", "block_content": html, "block_bbox": [120, 200, 800, 320]}]}]}, [1])
    assert blocks[0].text == html and blocks[0].source == "ocr"


def test_continued_table_evidence_and_review_survive_revision_and_publish(tmp_path):
    assets = AssetStore(tmp_path)
    store = PdfStore(assets)
    project = ProjectStore(assets).create("Authored table regression")
    client, calls = fake_client()
    record = store.import_pdf(project.project_id, "continued.pdf", continued_pdf(), client=client)
    request = json.dumps(calls[0], ensure_ascii=False)
    assert 'colspan=\\"2\\"' in request
    scene = store.scenes(project.project_id, record.document_id)[0]
    assert any(ref.page_start == 1 and ref.page_end == 2 for ref in scene.package.evidence)
    tables = [b for b in scene.package.extraction["source_blocks"] if b["block_type"] == "table"]
    assert {b["page_number"] for b in tables} == {1, 2}
    assert not any(">80<" in b["text"] for b in tables)
    published = store.publish_scene(scene)
    revised = store.revise_scene(project.project_id, record.document_id, scene.scene_id, {"title": "Reviewed table scene"})
    assert published["package"]["extraction"]["source_blocks"] == revised.package.extraction["source_blocks"]
    assert published["package"]["extraction"]["structure_flags"] == revised.package.extraction["structure_flags"]
    assert any(f["kind"] == "table_merged_cells" for f in revised.package.extraction["structure_flags"])
