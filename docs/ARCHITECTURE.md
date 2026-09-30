# Architecture

## One inspection, two entry points

`workflow.inspect_pair` validates filenames and empty inputs, then calls `parser.parse_bundle`. Both the CLI and Streamlit UI use this workflow. XML documents must have the expected OpenSCENARIO or OpenDRIVE root element.

`parser.py` extracts selected XML elements into the dataclasses in `models.py`. The resulting `ParseBundle` has a scenario, a road summary, and warning codes. `to_dict()` produces the JSON representation used by both interfaces.

| Module | Responsibility |
| --- | --- |
| `parser.py` | XML extraction and cross-file road-name check |
| `road_geometry.py` | OpenDRIVE reference lines, lane widths, and coordinate projection |
| `models.py` | Entities, actions, triggers, positions, road summary |
| `catalog.py` | Pair XOSC files with referenced XODR files into OpenX assets |
| `sim_archive.py` | Expand ScenarioManager-compatible SIM archives and report unpairable cases |
| `retrieval.py` | Local vector retrieval with scenario and road reranking |
| `scene_package.py` | Stable PDF-to-retrieval contract with source evidence |
| `pdf_pipeline.py` | Explicit legacy offline extraction for historical compatibility |
| `pdf_v2/`, `pdf_extraction.py` | Migrated V2 chapter tree, scene-first v6, typed structures and evidence validation |
| `llm_service.py`, `model_ui.py` | Shared model configuration, credential protection, discovery and probes |
| `classification.py` | Rule/model/final asset labels and manual review history |
| `reuse.py` | Participant interaction signatures, grounded differences, and change cost |
| `workflow.py` | Shared input validation and inspection |
| `demo.py` | Fetch the pinned public example; no model dependency |
| `i18n.py` | Chinese and English UI/warning labels |
| `app.py` | Views, session state, JSON download |
| `cli.py` | JSON on stdout, diagnostics on stderr |
| `search_cli.py` | Build and query an OpenX asset catalog from a directory |

## What the fields mean

- An entity identifies a ScenarioObject and its declared category or catalog name.
- An action records a recognized action kind, assigned actor when available, and an absolute speed target when directly numeric.
- A trigger records start/stop scope, condition name/type, delay, and edge.
- A position preserves its actor and selected position-element attributes as strings.
- Road counts describe XML elements. In particular, lane_count includes center lanes and repeated lane IDs across lane sections; it is not a count of unique drivable lanes.
- Road retrieval also uses total declared road length, lane types, plan-view geometry types, junctions, signals, and static objects.

## Asset retrieval flow

`catalog.build_catalog` resolves each OpenSCENARIO `LogicFile` reference against the uploaded or discovered OpenDRIVE files. `OpenXIndex` embeds a compact text representation for candidate recall, then compares explicit scenario and road facts. Results retain the XOSC/XODR pair and explain which structures matched.

`sim_archive.expand_sim_archives` treats `.sim` as a ZIP container. It reads case JSON and contained OpenDRIVE files in memory, resolves ScenarioManager's logical `<map-id>.xodr` reference to `map/<map-id>/<road-name>.xodr`, converts the embedded OpenSCENARIO-shaped JSON into deterministic XML for the existing parser, and supplements genuinely missing roads with separately uploaded XODR files. Cases whose `LogicFile` cannot be resolved are excluded and summarized in an import report; the adapter does not invent a road or silently accept an incomplete pair.

The encoder boundary has two implementations: deterministic hashing for a zero-model offline demo, and `BAAI/bge-small-zh-v1.5` through SentenceTransformers for semantic retrieval. Corpus encoding is batched. Index files store normalized vectors, the encoder identity, and ordered asset IDs; loading fails when the encoder or catalog differs.

PDF scene sections are converted to a `ScenePackage` that retains filename, section ID, page range, and source text. Its canonical scenario-family, participant, relative-position, action, trigger, road, and parameter fields form a `RetrievalQuery`. Candidate ranking first minimizes blocking differences, then estimated change cost, and only then uses the combined relevance score. The same change cost is exposed in the UI and CLI. Vector similarity therefore affects recall but cannot turn an incompatible scenario into a direct-reuse recommendation.

Reuse levels come from the explicit difference set: no differences means direct reuse, a missing non-blocking feature means modify and reuse, and a scenario-family or participant-interaction mismatch means build new. Each asset participant is represented by type, ego-relative bearing, facing direction, and actor-owned actions; participant names and continuous distances do not form the matching key. Initial `RelativeObjectPosition`, `LanePosition`, `RoadPosition`, and `WorldPosition` values support this signature. OpenDRIVE line, arc, spiral, and parametric-cubic reference lines plus polynomial lane widths normalize road, lane, and world coordinates before comparison.

A free-text query without a selected `ScenePackage` is recall-only. It returns ranked candidates with semantic evidence and the neutral `review` state, but it cannot claim direct reuse, modification, or a new build because no explicit requested structure exists to compare. This keeps the decision panel consistent with its difference evidence.

Unknown topology is a distinct state rather than a mismatch. If participant type and actions agree but either side lacks a resolvable bearing or facing direction, the result requires placement verification and cannot be marked as direct reuse.

The default PDF path uses the migrated ScenarioManager V2 native block parser, chain chapter decoder, scene-first v6 model extraction, subtree resolution and Stage D review checks. The typed structure and original evidence are stored with every scene. Confirmed revisions can enter a shared requirement library. OCR, Paddle rescue and full table reconstruction remain deferred. See [migration scope and validation](PDF_MIGRATION.md). No private corpus or internal evaluation results are bundled.

The road-reference check first resolves the referenced relative path against the scenario directory, then falls back to a unique basename. Ambiguous same-name roads are rejected. Pairing does not prove that the scene can execute.

## Current limits

This is a structure inspector for selected XML constructs with an optional esmini preview, not an ASAM conformance validator. Unsupported details may not appear in the summary:

- Parameter expressions are not resolved. A nonnumeric speed expression currently produces a null target value.
- Catalog references are identified but not expanded.
- Event hierarchy, trigger thresholds and entity references, action units, and source-element paths are not fully represented.
- Road geometry is used for relative-position matching, but physical feasibility and scenario behavior are not simulated or validated.
- OpenSCENARIO DSL is outside the current parser's scope.
- SIM import supports the observed ScenarioManager container shape; it is not a general converter for arbitrary proprietary `.sim` formats.
- The Windows preview runs an available local esmini executable on click and streams real rendered frames into the page. It does not establish semantic or standards conformance; failed previews retain parsed facts.

These limits determine the next parser improvements in the [roadmap](../DEVELOPMENT_PLAN.md).

## Data flow and dependencies

Uploaded files are read in memory by the local app. The parser makes no network requests. Public-demo mode downloads a fixed OpenSCENARIO/OpenDRIVE pair from GitHub and caches it through Streamlit. The optional download script also saves the upstream license.

OpenX XML parsing, retrieval and structural decisions run without an API key. Default PDF scene extraction requires a configured model; legacy rule extraction remains an explicit offline API option. Lightweight retrieval has no model download. BGE semantic retrieval is an optional local dependency and downloads the model on first use. On-demand model explanations send the selected evidence payload to the configured service only when explicitly requested in the UI.
