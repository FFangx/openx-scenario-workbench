import pymupdf

from openx_workbench.pdf_pipeline import (
    PdfPage,
    extract_scene_packages_from_pages,
    extract_scene_packages_from_pdf,
    split_sections,
)


def test_pdf_pages_keep_section_and_page_evidence():
    pages = [
        PdfPage(4, "7.4.1 目标车切入场景\n测试车辆在直道行驶。"),
        PdfPage(5, "目标车辆换道切入，TTC = 3.0 s。\n7.4.2 评分方法\n记录测试结果。"),
    ]

    packages = extract_scene_packages_from_pages(pages, "adas-standard.pdf", "L2")

    assert len(packages) == 1
    package = packages[0]
    assert package.package_id == "L2_7.4.1"
    assert package.evidence[0].page_start == 4
    assert package.evidence[0].page_end == 5
    assert package.parameters["ttc_s"] == 3.0
    assert package.road_types == ["straight"]
    assert package.actions == ["lane_change"]


def test_split_sections_does_not_create_ungrounded_preamble():
    sections = split_sections(
        [PdfPage(1, "Document title\nTable of contents\n8.1 Pedestrian scenario\nThe pedestrian crosses.")]
    )

    assert [(item.section_id, item.title) for item in sections] == [
        ("8.1", "Pedestrian scenario")
    ]


def test_split_sections_merges_repeated_page_headings():
    sections = split_sections(
        [
            PdfPage(4, "7.4.1 Cut-in scenario\nFirst condition."),
            PdfPage(5, "7.4.1 Cut-in scenario continued\nSecond condition."),
        ]
    )

    assert len(sections) == 1
    assert sections[0].page_start == 4
    assert sections[0].page_end == 5
    assert "First condition" in sections[0].text
    assert "Second condition" in sections[0].text


def test_extract_scene_packages_from_real_pdf_bytes():
    document = pymupdf.open()
    page = document.new_page()
    page.insert_text(
        (72, 72),
        "7.4.1 Cut-in scenario\nTarget vehicle performs a lane change on a straight road. TTC = 3.0 s.",
    )
    pdf_data = document.tobytes()
    document.close()

    packages = extract_scene_packages_from_pdf(pdf_data, "public-standard.pdf", "DEMO")

    assert len(packages) == 1
    assert packages[0].evidence[0].source_pdf == "public-standard.pdf"
    assert packages[0].actions == ["lane_change"]


def test_separate_number_and_title_keep_full_section_id_and_source_text():
    packages = extract_scene_packages_from_pages([
        PdfPage(2, "Table of Contents\n8.2.3.1\nCut-in scenario ........ 20"),
        PdfPage(20, "8.2.3.1\nCut-in scenario\nTarget vehicle changes lane."),
        PdfPage(21, "The test vehicle follows on a straight road.\n9\nAPPENDIX\nUnrelated notes."),
    ], "authored.pdf")
    assert len(packages) == 1
    evidence = packages[0].evidence[0]
    assert evidence.section_id == "8.2.3.1"
    assert (evidence.page_start, evidence.page_end) == (20, 21)
    assert packages[0].title == "Cut-in scenario"
    assert "Cut-in scenario" in evidence.source_text
    assert "Unrelated notes" not in evidence.source_text


def test_numeric_table_values_do_not_become_headings():
    sections = split_sections([PdfPage(1, "8.2 Test scenario\n3.0 4.0\n8.2.1")])
    assert len(sections) == 1
    assert sections[0].section_id == "8.2"
