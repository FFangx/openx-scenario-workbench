# OpenX Scenario Workbench

[![CI](https://github.com/FFangx/openx-scenario-workbench/actions/workflows/ci.yml/badge.svg)](https://github.com/FFangx/openx-scenario-workbench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

English | [中文](README.zh-CN.md)

Turn an ADAS requirement into a traceable OpenX reuse decision. OpenX Scenario Workbench extracts numbered scene sections from **PDF**, builds paired **OpenSCENARIO (`.xosc`) + OpenDRIVE (`.xodr`)** assets from files or ScenarioManager-compatible `.sim` archives, and ranks candidates using text, scenario structure, and road fit.

**Try it:** start the workbench (see [Quick start](#quick-start)), switch to English with the language button in the top-right corner, then open **Asset management → Import assets → Public esmini example**. Importing and inspecting the pinned esmini cut-in example needs no API key, model download, or local input files. For a complete walkthrough without your own files, start it on the [authored demo workspace](#demo-workspace). Semantic search and simulation have separate dependencies below.

![Workbench with a requirement queue, ranked assets and a reuse assessment](docs/images/workbench-en.jpg)

*The running workbench on the authored demo workspace: the requirement was reviewed and saved as revision 2, candidates are ranked, and the selected one needs a change. The authored parser fixtures do not pass the XSD checks, so the workbench keeps showing the pending standard check instead of claiming direct reuse.*

![Asset management with a real esmini frame of the public cut-in example](docs/images/assets-en.jpg)

*Asset management after importing the public esmini cut-in example (MPL-2.0) and playing it once: the frame is rendered by esmini, not drawn.*

## Using the workbench

| Page or action | What to do |
| --- | --- |
| **Workbench** | Create a project from the project menu, configure the language model in **Settings**, and import a PDF from the PDF card's **⋯** menu. Pick a requirement: its source evidence, the ranked candidates and the reuse assessment appear side by side. Review and edit its typed facts under **Requirement facts**, publish the revision, then save the decision. |
| **Free-text search** | Close the scene chip above the candidates and describe a scenario. Results are text recall only; no reuse decision is made. |
| **Play simulation** | Use **Play**, **Stop** or **Capture frame** in the candidate preview or the asset detail. An installed Windows esmini is detected automatically; choose a custom installation under **Settings → Local service**. |
| **Match entire PDF** | From the PDF card's **⋯** menu, match all scenes of the document and download or save a version-pinned JSON/HTML summary. |
| **Overview** | Library statistics, recent imports, and saved decisions and summaries with their downloads; reopen a requirement to continue its review. |
| **Asset management** | Import `.sim`, paired `.xosc` / `.xodr`, or a dependency `.zip`. Select a version to review its preview, classification, source files, standard export and history. The PDF requirement library lists published requirements. |

Asset versions are shared across projects. PDF sources, scene revisions and decisions belong to the selected project.

## Design

![OpenX Scenario Workbench architecture](docs/images/architecture-overview.svg)

The two input paths meet only through stable representations: a PDF-derived `ScenePackage` and a paired OpenX asset catalog. Vector recall finds candidates; explicit scenario and road constraints rerank them; source evidence and parsed candidate facts ground the final reuse decision. The React interface talks to a local FastAPI service; the parser, retrieval core and decision logic are plain Python shared with the command-line tools.

[Architecture](docs/ARCHITECTURE.md) · [Roadmap](DEVELOPMENT_PLAN.md) · [Third-party notices](THIRD_PARTY_NOTICES.md)

## What it does

- Extracts scenario entities, selected action types, actor assignments, trigger types, and raw position attributes.
- Extracts and classifies native or scanned PDF scenes using the migrated ScenarioManager V2 / scene-first v6 path, preserving table cells, chapter/page evidence and review issues. Scanned pages require local OCR; configure a language model in Settings first.
- Publishes confirmed PDF scene revisions into a shared requirement library; simulation assets have optional model classification with rule/model/final audit history.
- Provides model URL/key settings, model discovery, manual model IDs and a selected-model JSON test.
- Converts each PDF scene package into explicit scenario-family, participant, relative-position, action, trigger, road, and parameter constraints.
- Summarizes road IDs and counts of lane elements, junctions, signals, and static objects.
- Preserves total road length, lane-type counts, and OpenDRIVE geometry types, and projects lane/road/world positions through the reference line for relative-position matching.
- Pairs each `.xosc` with its referenced `.xodr` to build an OpenX asset catalog.
- Imports ScenarioManager-compatible `.sim` ZIP archives, converts their embedded OpenSCENARIO JSON to the same parser input, and pairs cases with contained or separately uploaded `.xodr` roads.
- Uses BGE-M3 for semantic recall, with an explicitly selected hashing baseline available offline, then ranks candidates by blocking differences and estimated change cost.
- Builds participant interaction signatures from type, ego-relative bearing, facing direction, and actor-owned actions.
- Reports grounded reuse differences such as a mismatched scenario family or participant interaction, or a missing relation, action, trigger, or road feature.
- Checks road-filename references, missing scenario entities, and missing road elements.
- Provides Workbench, Overview and Asset management pages in Chinese and English; the workbench shows evidence, candidates and the assessment of the selected requirement side by side, and long-running imports run as background jobs with live progress.
- Exports a structured decision trace through the web UI; the inspection and search CLIs expose the same parser and retrieval core.
- Loads a fixed revision of an upstream esmini example for a repeatable demo.
- Stores immutable asset versions in a machine-local global library, keeps named projects and multiple PDFs, and exports version-pinned JSON and HTML decisions.
- Accepts a portable `.zip` containing XOSC, XODR, catalogs, models, and textures in their original relative layout.
- Detects a working local esmini installation on Windows and displays real frames after the user clicks **Play simulation**, with stop/replay controls and retained failure details.
- Offers on-demand evidence-linked explanations from the selected PDF text and versioned OpenX facts when a model key is configured.
- Requires both scenario and road XSD checks to pass before confirming direct reuse, including a fresh check when saving a single or batch decision.
- Exports separate, audited SIM standard copies from **Asset management → Source**. A copy that fails checks is available only as a diagnostic package; originals and unsupported extensions remain preserved.

The app reports offline, version-specific XSD checks when its local schema registry is installed. These do not certify complete ASAM conformance or simulation. Native PDF table cells and optional local PP-StructureV3 OCR feed the same anchored scene workflow; complex merged/cross-page tables, diagrams, unsupported parameter expressions, unresolved external catalogs and event hierarchy still require review. The UI never fabricates media: PDF thumbnails come from the uploaded document and preview images come from esmini. Model explanations cite supplied evidence but require human review for factual accuracy. See [local assets and preview](docs/LOCAL_ASSETS_AND_PREVIEW.md) and [architecture and current limits](docs/ARCHITECTURE.md).

See [PDF migration and model setup](docs/PDF_MIGRATION.md) for scope, storage and validation.

## Quick start

Requires **Python 3.10 or newer** and **Node.js 20 or newer** (to build the interface once). Commands below are run from the repository root.

```bash
git clone https://github.com/FFangx/openx-scenario-workbench.git
cd openx-scenario-workbench
python -m venv .venv
```

Activate the environment:

```powershell
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
source .venv/bin/activate
```

Install, build the interface, and start:

```bash
python -m pip install ".[dev]"
cd web && npm ci && npm run build && cd ..
openx-web
```

Open <http://127.0.0.1:8765>. The service listens on this computer only. Use **Asset management → Import assets** for the public demo or your own files. The public demo downloads a scenario and its road from GitHub; uploads accept `.sim`, `.xosc`, `.xodr`, and portable `.zip` dependency packages. A `.sim` case is admitted only when its referenced road is available inside the archive or among the supplemental uploads; task details list missing road filenames so they can be supplied on reimport.

### Optional capabilities

- **BGE-M3 search:** install with `python -m pip install ".[semantic]"`. The UI defaults to BGE-M3; weights are downloaded on first use unless cached and are not included in the repository. Choose the hashing baseline explicitly for an offline smoke check without model weights.
- **PDF extraction:** configure the model endpoint, key and model in **Settings**. Import sends document text to that service. For scanned PDFs, install and configure local OCR as described in [PDF migration](docs/PDF_MIGRATION.md).
- **Standard checks:** run `openx-validate --install-schemas` once to download the pinned schema registry; later checks run locally. Both XOSC and XODR must pass before direct reuse can be confirmed.
- **Simulation:** install esmini separately on Windows. Detection checks `OPENX_ESMINI_PATH`, PATH, managed folders and esmini folders in Downloads, Desktop, Documents and Program Files. In **Settings → Local service**, **Browse installation folder** opens a native folder picker and saves a valid installation automatically; **Detect automatically** restores automatic discovery. esmini is not bundled; some extensions and missing dependencies prevent playback.
- **Windows desktop entry:** follow [desktop launcher setup](docs/DESKTOP_LAUNCHER.md) for shortcuts and tray controls. Daily use requires no terminal.

### Demo workspace

`scripts/seed_demo_workspace.py` fills an empty folder with an authored demo: six reuse assets, a project with two protocol PDFs (English and Chinese) and reviewed typed requirements. Nothing is downloaded and no model is called.

```bash
python scripts/seed_demo_workspace.py demo-data
OPENX_DATA_DIR=demo-data openx-web
```

On Windows PowerShell set the variable with `$env:OPENX_DATA_DIR = "demo-data"`. The demo never touches your normal data folder.

### CLI and offline sample

The small fixtures are authored for parser tests, not for simulator execution. They also provide an offline inspection example:

```bash
openx-inspect tests/fixtures/minimal.xosc tests/fixtures/minimal.xodr
```

The output has four top-level keys: `scenario`, `road`, `warnings`, and `validation`. The excerpt below shows parsed facts and warnings; `validation` carries the version-specific XSD results:

```json
{
  "scenario": {
    "name": "Minimal cut-in",
    "road_file": "minimal.xodr",
    "entities": [
      {"name": "Ego", "kind": "vehicle", "category": "car"},
      {"name": "Target", "kind": "vehicle", "category": "car"}
    ]
  },
  "road": {"road_ids": ["1"], "lane_count": 3},
  "warnings": []
}
```

This excerpt omits other parsed fields and the `validation` object. Standard output contains JSON only; human-readable warnings go to standard error. Successful parsing exits with 0, including inspections with warnings or failed/unavailable XSD checks. Invalid input or parsing failure exits with 2. Use `openx-validate` when an exit code must reflect XSD validity.

### Download the real public example

```bash
python scripts/fetch_esmini_demo.py
openx-inspect examples/esmini/cut-in.xosc examples/esmini/e6mini.xodr
```

The pinned example currently yields **2 entities, 6 actions, 5 trigger conditions, and 1 road**. These are extraction counts, not simulated behavior measurements. Downloads are stored under ignored `examples/esmini/`, alongside the upstream license.

### Build and search an OpenX asset library

Place related `.xosc` and `.xodr` files under one directory. Pairing resolves each scenario's `LogicFile` path first, with a basename fallback only when unambiguous:

```bash
openx-search examples/esmini "cut-in SpeedAction relative distance"
```

Free-text search in the workbench uses the same retrieval core. For a requirement-based assessment, select an imported scene in the workbench and review its facts. Its text, structured constraints and source evidence become the retrieval query; the candidate and assessment columns explain matching evidence, blocking differences, required edits and traceability links.

For semantic retrieval and a reusable on-disk index:

```bash
python -m pip install ".[semantic]"
openx-search examples/esmini "target vehicle cuts in" --encoder bge --index .openx/index.json
```

Semantic retrieval uses **BAAI/bge-m3** (BGE-M3), with no automatic fallback to a smaller model. SentenceTransformers downloads it on first use unless it is cached. The index records the model, schema version and a fingerprint of parsed facts and accepted classification labels. Changed models, labels or assets require a rebuild.

The name/label and name-free structural routes share one encoder. Typed PDF facts directly control reuse decisions; unsupported or unknown requirements require review. See [alignment, validation and measured limits](docs/REUSE_ALIGNMENT.md).

The workbench defaults to BGE-M3; choose the hashing baseline under **Settings →
Display & search**. **Match entire PDF** matches all current document scenes through
the same retrieval engine. JSON/HTML summaries preserve
source revisions, candidate versions and pending review states. Saved summaries
reopen in Overview and pin all included asset versions.

## Development

After changing Python source files, reinstall with `python -m pip install ".[dev]"`. An editable install (`-e`) is also available, but normal installation avoids editable-path encoding issues on Windows installations with non-ASCII checkout paths.

```bash
python -m pytest -q
```

For interface work, run `openx-web` and, in `web/`, `npm run dev`; Vite serves the interface on port 5173 and forwards `/api` to the service. `npm run build` type-checks and builds; `npm run verify:ui` then runs the browser checks against a throwaway demo workspace (it starts its own service and never uses your data folder).

CI tests on Windows and Linux with Python 3.10 and 3.12, builds the distribution, and builds and checks the web interface. Automated tests use local fixtures and mocked downloads; the live public demo is checked separately.

## License and examples

Code and authored test fixtures are licensed under [MIT](LICENSE). The optional esmini example is fetched from a pinned upstream revision and is not committed to this repository. See [third-party notices](THIRD_PARTY_NOTICES.md) for its source and license.
