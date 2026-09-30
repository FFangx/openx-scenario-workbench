from openx_workbench.report_html import render_report


def test_report_contains_version_evidence_and_escapes_source_text():
    html = render_report({
        "source": {"title": "Cut-in", "evidence": [{"source_pdf": "rules.pdf",
                    "section_id": "3.1", "page_start": 4, "page_end": 5,
                    "source_text": "<script>alert(1)</script>"}]},
        "candidate": {"title": "Candidate", "asset_id": "asset-1", "version_id": "version-2",
                      "xosc": "scene.xosc", "xodr": "road.xodr"},
        "reuse": {"level": "modify", "differences": [{"category": "actor",
                  "requested": "car", "candidate": "truck", "action": "replace", "blocking": False}]},
        "scores": {"combined": 0.7},
        "explanation": {"method": "model:test", "observations": [
            {"text": "Grounded comparison", "citations": ["P1", "X1"]}],
            "evidence": [{"evidence_id": "P1", "location": "rules.pdf · page 4"},
                         {"evidence_id": "X1", "location": "scene.xosc"}]},
    })
    assert "version-2" in html
    assert "rules.pdf" in html
    assert "truck" in html
    assert "Grounded comparison" in html
    assert "<script>" not in html
    assert "&lt;script&gt;" in html
