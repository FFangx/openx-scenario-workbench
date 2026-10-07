"""Self-authored demo workspaces, and the one-command demo (``openx-demo``).

Two datasets, both written for this repository (MIT) and read from the checkout:

- ``benchmark``: the 26-asset reuse benchmark in examples/reuse-benchmark, with
  an English and a Chinese protocol PDF holding its 38 reviewed requirements.
- ``fixtures``: the six parser fixtures in tests/fixtures/reuse and eight
  requirements. Small and stable; the browser checks in web/scripts use it.

Nothing is downloaded and no model is called. The benchmark comes with the reuse
suggestions of one real model run (examples/reuse-benchmark/suggestions.json,
made with ``openx-demo --record-suggestions``), replayed and marked as recorded,
so its assessment table is filled without a model. A workspace only ever lives
in the folder it was seeded into, never in the normal data folder.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import tempfile
import threading
import time
import webbrowser
from pathlib import Path
from urllib.request import urlopen

from .checkout import checkout_root

REPO = checkout_root()
FIXTURES = REPO / "tests" / "fixtures"
BENCHMARK = REPO / "examples" / "reuse-benchmark"
RECORDED = BENCHMARK / "suggestions.json"
MARKER = "demo-workspace.json"
ROAD_LABELS = {"straight": "直道", "curve": "弯道"}


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


def _protocol(pdf, project_id: str, name: str, standard: str, cases: list[dict], note: str, chinese: bool) -> dict:
    # Headings without a closing full stop, and an explicit "scenario" signal for the rule-based extractor.
    sections = [(f"5.{index} {case['title'].rstrip('.')}", f"{case['text']} {note}") for index, case in enumerate(cases, 1)]
    document = pdf.import_pdf(project_id, name, _pdf(sections, chinese), standard, engine="legacy")
    scenes = pdf.scenes(project_id, document.document_id)
    if len(scenes) != len(cases):
        raise RuntimeError(f"{name}: expected {len(cases)} requirements, the extractor found {len(scenes)}.")
    for scene, case in zip(scenes, cases):
        # The typed structure a reviewer would confirm, saved as revision 2.
        pdf.revise_scene(project_id, document.document_id, scene.scene_id,
                         {"title": case["title"], "structure": case["structure"]})
    return {"document_id": document.document_id, "scenes": len(scenes)}


def _seed_fixtures(store, pdf, projects) -> dict:
    from .catalog import AssetFile
    from .classification import classify_asset, confirm_classification

    corpus = json.loads((FIXTURES / "reuse" / "corpus.json").read_text(encoding="utf-8"))
    road = AssetFile("minimal.xodr", (FIXTURES / "minimal.xodr").read_bytes())
    versions = []
    for asset in corpus["assets"]:
        scenario = AssetFile(f"demo_{asset['id']}.xosc", (FIXTURES / "reuse" / asset["xosc"]).read_bytes())
        version = store.import_files([scenario, road])[0]
        versions.append(version)
        # Confirm the corpus labels on top of the rule suggestion, as a reviewer would in asset management.
        rule = classify_asset(store, version)["rule"]
        confirm_classification(store, version, {**rule, "label_road_type": "直道", **asset["classification"]})
    project = projects.create("Demo · AEB protocol")
    cases = {case["id"]: case for case in corpus["cases"]}
    documents = []
    for language, chinese in (("en", False), ("zh", True)):
        chosen = [cases[f"{name}-{language}"] for name in ("forward", "rear", "stop", "pedestrian")]
        note = "测试场景：AEB 目标车辆。" if chinese else "Test scenario for AEB with a target vehicle."
        name = "demo-aeb-protocol.pdf" if language == "en" else "demo-aeb-protocol-zh.pdf"
        documents.append(_protocol(pdf, project.project_id, name, "Demo AEB", chosen, note, chinese))
    return {"project_id": project.project_id, "assets": len(versions), "documents": documents}


def _seed_benchmark(store, pdf, projects) -> dict:
    from .catalog import AssetFile
    from .classification import classify_asset, confirm_classification

    spec = json.loads((BENCHMARK / "benchmark.json").read_text(encoding="utf-8"))
    roads = {path.name: AssetFile(path.name, path.read_bytes()) for path in (BENCHMARK / "roads").glob("*.xodr")}
    road_files = {"straight": "straight-2x2.xodr", "curve": "curve-2x2.xodr"}
    versions = []
    for asset in spec["assets"]:
        scenario = AssetFile(f"{asset['id']}.xosc", (BENCHMARK / "assets" / f"{asset['id']}.xosc").read_bytes())
        version = store.import_files([scenario, roads[road_files[asset["road"]]]])[0]
        versions.append(version)
        rule = classify_asset(store, version)["rule"]
        confirm_classification(store, version, {**rule, "function_type": asset["function"],
                                                "label_road_type": ROAD_LABELS[asset["road"]]})
    project = projects.create("Demo · ADAS reuse benchmark")
    documents = [
        _protocol(pdf, project.project_id, "demo-adas-protocol-en.pdf", "Demo ADAS",
                  [case for case in spec["cases"] if case["language"] == "en"], "Test scenario; the test vehicle is the ego car.", chinese=False),
        _protocol(pdf, project.project_id, "demo-adas-protocol-zh.pdf", "Demo ADAS",
                  [case for case in spec["cases"] if case["language"] == "zh"], "测试场景，主车为测试车辆。", chinese=True),
    ]
    return {"project_id": project.project_id, "assets": len(versions), "documents": documents}


# What a recording keeps of a suggestion (binding_suggest.suggestion_record) besides its candidates, and of
# each candidate besides the asset it names; asset and scene ids are this workspace's and found again on replay.
SUGGESTION_KEPT = ("judge", "binding", "preferred", "note", "failure", "readings", "agree", "other_preferred")
CANDIDATE_KEPT = ("rank", "routes", "level", "verdict", "reason", "changes")


def _asset_name(version) -> str:
    return Path(version.xosc_name).stem  # the benchmark's asset id


def _requirements(pdf, project_id: str) -> dict[tuple[str, str, str], tuple]:
    """(PDF file name, clause number, title) -> (scene, requirement key) of every scene in the project."""
    from .binding_store import requirement_keys, section_of

    found = {}
    for document in pdf.documents(project_id):
        scenes = pdf.scenes(project_id, document.document_id)
        keys = requirement_keys(pdf, project_id, document.document_id, scenes)
        for scene in scenes:
            found[(document.filename, section_of(scene.package), scene.package.title)] = (scene, keys[scene.scene_id])
    return found


def replay_suggestions(store, pdf, project_id: str, recording: dict) -> int:
    """Save the recorded suggestions as the workspace's own, marked as recorded; returns how many."""
    from .binding_store import BindingStore, scene_digest

    versions = {_asset_name(version): version for version in store.latest()}
    requirements = _requirements(pdf, project_id)
    bindings = BindingStore(store)
    for item in recording["scenes"]:
        scene, key = requirements[(item["document"], item["section_id"], item["title"])]
        candidates = []
        for candidate in item["candidates"]:
            version = versions[candidate["asset"]]
            candidates.append({"id": candidate["id"], "asset_id": version.asset_id, "version_id": version.version_id,
                               "version_number": version.version_number, "title": version.title,
                               **{name: candidate[name] for name in CANDIDATE_KEPT}})
        bindings.save_suggestion(scene.document.sha256, key, {
            "created_at": recording["recorded_at"], "model": recording["model"], "revision": scene.revision,
            "scene_digest": scene_digest(scene.package), "candidates": candidates,
            **{name: item[name] for name in SUGGESTION_KEPT}, "recorded": True})
    return len(recording["scenes"])


def seed(target: Path, dataset: str = "fixtures", recorded: bool = True) -> dict:
    """Fill an empty folder with a demo workspace and return what was created; `recorded` replays the
    benchmark's recorded suggestions."""
    if dataset not in {"fixtures", "benchmark"}:
        raise ValueError(f"Unknown demo dataset: {dataset}")
    if target.exists() and any(target.iterdir()):
        raise SystemExit(f"Refusing to seed a non-empty folder: {target}")
    target.mkdir(parents=True, exist_ok=True)
    os.environ["OPENX_DATA_DIR"] = str(target)

    from .asset_store import AssetStore
    from .pdf_store import PdfStore
    from .project_store import ProjectStore

    store = AssetStore()
    pdf = PdfStore(store)
    seeder = _seed_benchmark if dataset == "benchmark" else _seed_fixtures
    result = {"data_dir": str(target), "dataset": dataset, **seeder(store, pdf, ProjectStore(store))}
    if dataset == "benchmark" and recorded and RECORDED.is_file():
        recording = json.loads(RECORDED.read_text(encoding="utf-8"))
        result["recorded_suggestions"] = replay_suggestions(store, pdf, result["project_id"], recording)
    (target / MARKER).write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return result


def record_suggestions(out: Path = RECORDED, work: Path | None = None) -> dict:
    """Ask the model of the normal settings for the suggestions of every benchmark scene and write them to
    `out`. The benchmark is seeded in `work` (kept, so a second run reuses its cached replies) or in a
    temporary folder. Calls the model: 38 scenes, three readings each."""
    from .llm_service import ModelClient, load_config

    config = load_config()  # the normal data folder's, read before the workspace takes its place
    if not config.api_key:
        raise SystemExit("Configure a model in the workbench settings first.")
    temporary = work is None
    target = Path(tempfile.mkdtemp(prefix="openx-record-")) if temporary else work.resolve()
    try:
        summary = (json.loads((target / MARKER).read_text(encoding="utf-8")) if (target / MARKER).is_file()
                   else seed(target, "benchmark", recorded=False))
        if summary["dataset"] != "benchmark":
            raise SystemExit(f"{target} holds the {summary['dataset']} demo, not the benchmark.")
        os.environ["OPENX_DATA_DIR"] = str(target)

        from .api_common import _catalog, _index
        from .asset_store import AssetStore
        from .binding_store import scene_digest, section_of
        from .binding_suggest import Judge, judge_efforts, suggest_scenes
        from .pdf_store import PdfStore

        store = AssetStore()
        pdf = PdfStore(store)
        scenes = [scene for scene, _ in _requirements(pdf, summary["project_id"]).values()]
        client = ModelClient(config)
        efforts = judge_efforts(client)
        catalog, versions = _catalog()
        judge = Judge(client, target / "model_cache", efforts=efforts)
        records: dict[tuple[str, str], dict] = {}  # scene ids repeat across PDFs
        failed = suggest_scenes(scenes, _index(catalog, "hashing"), versions, judge, config.concurrency, digest=scene_digest,
                                save=lambda scene, record: records.__setitem__((scene.document.document_id, scene.scene_id), record))
        if failed:
            raise SystemExit(f"{failed} scenes got no usable reply; run again with --data-dir to keep the replies so far.")
        names = {version.asset_id: _asset_name(version) for version in versions.values()}
        recording = {
            "about": "Reuse suggestions of one real model run on this benchmark, replayed by openx-demo "
                     "without calling a model. Remake with: openx-demo --record-suggestions",
            "model": config.model, "effort": efforts[0], "encoder": "hashing",
            "recorded_at": max(record["created_at"] for record in records.values()),
            "scenes": [{"document": scene.document.filename, "section_id": section_of(scene.package),
                        "title": scene.package.title, **{name: record[name] for name in SUGGESTION_KEPT},
                        "candidates": [{"id": item["id"], "asset": names[item["asset_id"]],
                                        **{name: item[name] for name in CANDIDATE_KEPT}} for item in record["candidates"]]}
                       for scene, record in ((scene, records[scene.document.document_id, scene.scene_id]) for scene in scenes)],
        }
        out.write_bytes((json.dumps(recording, ensure_ascii=False, indent=1) + "\n").encode("utf-8"))
        return {"scenes": len(scenes), "effort": efforts[0], "usage": dict(judge.spent)}
    finally:
        if temporary:
            shutil.rmtree(target, ignore_errors=True)


def _open_when_ready(url: str) -> None:
    for _ in range(150):
        try:
            with urlopen(url + "/api/health", timeout=1):
                break
        except OSError:
            time.sleep(0.2)
    webbrowser.open(url)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Start the workbench on a self-authored demo workspace. Your normal data folder is not used.")
    parser.add_argument("--dataset", choices=("benchmark", "fixtures"), default="benchmark")
    parser.add_argument("--data-dir", type=Path,
                        help="keep the demo workspace in this folder (seeded on first use); default: a temporary folder removed on exit")
    parser.add_argument("--port", type=int, default=8770)
    parser.add_argument("--no-browser", action="store_true")
    parser.add_argument("--record-suggestions", action="store_true",
                        help="for maintainers: remake the benchmark's recorded suggestions with the model of your normal "
                             "settings (calls it; --data-dir keeps the workspace and its cached replies)")
    args = parser.parse_args(argv)
    if args.record_suggestions:
        done = record_suggestions(work=args.data_dir)
        print(f"Recorded {done['scenes']} suggestions (effort {done['effort']}, {done['usage']}) in {RECORDED}", flush=True)
        return 0

    from .api import WEB_DIST

    if not (WEB_DIST / "index.html").is_file():
        raise SystemExit(f"The web interface is not built ({WEB_DIST}). In web/, run: npm ci && npm run build")
    temporary = args.data_dir is None
    target = Path(tempfile.mkdtemp(prefix="openx-demo-")) if temporary else args.data_dir.resolve()
    try:
        if (target / MARKER).is_file():
            os.environ["OPENX_DATA_DIR"] = str(target)
            print(f"Reusing the demo workspace in {target}", flush=True)
        else:
            summary = seed(target, args.dataset)
            print(f"Seeded the {args.dataset} demo: {summary['assets']} assets, "
                  f"{sum(item['scenes'] for item in summary['documents'])} requirements in {target}", flush=True)
            from .preferences import save_preferences

            # The hashing baseline needs no model download; switch to BGE-M3 in Settings if it is installed.
            save_preferences(encoder="hashing")
        import uvicorn

        from .api import app

        url = f"http://127.0.0.1:{args.port}"
        print(f"Demo workbench: {url}  (Ctrl+C to stop)", flush=True)
        if not args.no_browser:
            threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
        uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")
    finally:
        if temporary:
            shutil.rmtree(target, ignore_errors=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
