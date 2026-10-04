"""Seed an empty data folder with a self-authored demo workspace.

Uses only the authored fixtures in tests/fixtures (MIT): six reuse assets on one
road, two small protocol PDFs written here, and the corpus's typed requirement
structures. Nothing is downloaded and no model is called.

    python scripts/seed_demo_workspace.py <empty-folder>
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
FIXTURES = REPO / "tests" / "fixtures"


def _pdf(sections: list[tuple[str, str]], chinese: bool) -> bytes:
    import pymupdf

    document = pymupdf.open()
    for heading, body in sections:
        page = document.new_page()
        font = {"fontname": "china-s"} if chinese else {}
        page.insert_text((72, 80), heading, fontsize=13, **font)
        page.insert_textbox(pymupdf.Rect(72, 100, 520, 400), body, fontsize=11, **font)
    data = document.tobytes()
    document.close()
    return data


def seed(target: Path) -> dict:
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"Refusing to seed a non-empty folder: {target}")
    target.mkdir(parents=True, exist_ok=True)
    os.environ["OPENX_DATA_DIR"] = str(target)

    from openx_workbench.asset_store import AssetStore
    from openx_workbench.catalog import AssetFile
    from openx_workbench.classification import classify_asset, confirm_classification
    from openx_workbench.pdf_store import PdfStore
    from openx_workbench.project_store import ProjectStore

    corpus = json.loads((FIXTURES / "reuse" / "corpus.json").read_text(encoding="utf-8"))
    store = AssetStore()
    road = AssetFile("minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes())
    versions = []
    for asset in corpus["assets"]:
        scenario = AssetFile(f"demo_{asset['id']}.xosc", (FIXTURES / "reuse" / asset["xosc"]).read_bytes())
        version = store.import_files([scenario, road])[0]
        versions.append(version)
        # Confirm the corpus labels on top of the rule suggestion, as a reviewer would in asset management.
        rule = classify_asset(store, version)["rule"]
        confirm_classification(store, version, {**rule, "label_road_type": "直道", **asset["classification"]})

    pdf = PdfStore(store)
    project = ProjectStore(store).create("Demo · AEB protocol")
    cases = {case["id"]: case for case in corpus["cases"]}
    documents = []
    for language, chinese in (("en", False), ("zh", True)):
        chosen = [cases[f"{name}-{language}"] for name in ("forward", "rear", "stop", "pedestrian")]
        # Headings without a closing full stop, and an explicit "scenario" signal for the rule-based extractor.
        note = "测试场景：AEB 目标车辆。" if chinese else "Test scenario for AEB with a target vehicle."
        sections = [(f"5.{index} {case['title'].rstrip('.')}", f"{case['text']} {note}") for index, case in enumerate(chosen, 1)]
        name = "demo-aeb-protocol.pdf" if language == "en" else "demo-aeb-protocol-zh.pdf"
        document = pdf.import_pdf(project.project_id, name, _pdf(sections, chinese), "Demo AEB", engine="legacy")
        scenes = pdf.scenes(project.project_id, document.document_id)
        for scene, case in zip(scenes, chosen):
            pdf.revise_scene(project.project_id, document.document_id, scene.scene_id,
                             {"title": case["title"], "structure": case["structure"]})
        documents.append({"document_id": document.document_id, "scenes": len(scenes)})
    return {"data_dir": str(target), "project_id": project.project_id, "assets": len(versions), "documents": documents}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(__doc__)
    sys.path.insert(0, str(REPO / "src"))
    print(json.dumps(seed(Path(sys.argv[1]).resolve()), ensure_ascii=False))
