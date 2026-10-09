# Architecture

## One inspection, two entry points

`workflow.inspect_pair` validates filenames and empty inputs, then calls `parser.parse_bundle`. The CLI and the asset catalog use this workflow. XML documents must have the expected OpenSCENARIO or OpenDRIVE root element.

`parser.py` extracts selected XML elements into the dataclasses in `models.py`. The resulting `ParseBundle` has a scenario, a road summary, and warning codes. `to_dict()` produces the JSON representation used by both interfaces.

| Module | Responsibility |
| --- | --- |
| `parser.py` | XML extraction and cross-file road-name check |
| `road_geometry.py` | OpenDRIVE reference lines, lane widths, and coordinate projection |
| `models.py` | Entities, actions, triggers, positions, road summary |
| `catalog.py` | Pair XOSC files with referenced XODR files into OpenX assets |
| `sim_archive.py` | Expand ScenarioManager-compatible SIM archives and report unpairable cases |
| `retrieval.py` | Asset index (vectors for text recall) and the structural ranking of the whole library |
| `reuse.py`, `reuse_*.py` | Reuse comparison: asset facts, structured and keyword comparison, participant pairing, verdicts; all tunable numbers in `reuse_policy.py` |
| `api_schemas.py` | Documented response models; the web client's types are generated from them |
| `scene_package.py` | Stable PDF-to-retrieval contract with source evidence |
| `pdf_pipeline.py` | Explicit legacy offline extraction for historical compatibility |
| `pdf_tables.py` | Geometrically verified native cell spans; original slots retained on ambiguity |
| `pdf_v2/`, `pdf_extraction.py` | Migrated V2 chapter tree, scene-first extraction (prompt v10: scenes, then structure per scene with quoted evidence and its figures), typed structures and evidence validation |
| `llm_service.py` | Shared model configuration, credential protection, discovery and probes |
| `classification.py` | Rule/final asset labels (function, road ahead of the ego, targets) and manual review history |
| `reuse.py` | Participant interaction signatures, grounded differences, and change cost |
| `workflow.py` | Shared input validation and inspection |
| `demo.py` | Fetch the pinned public example; no model dependency |
| `demo_workspace.py` | Seed the authored demo workspaces; `openx-demo` serves one from a temporary folder |
| `evaluation.py`, `ablation.py` | Fixture regression gate; benchmark retrieval/verdict metrics and ranking ablation |
| `checkout.py` | Locate the checkout holding `web/dist` and the examples after a normal install |
| `i18n.py` | Chinese and English CLI/warning labels |
| `api.py`, `api_common.py` | FastAPI application, loopback guard, search/trace/decision routes, shared caches |
| `api_workflow.py`, `api_assets.py`, `api_jobs.py`, `api_preview.py`, `api_settings.py` | Routes for the requirement workflow, asset management, background jobs, esmini preview and settings |
| `jobs.py`, `import_jobs.py` | Process-owned background jobs (submit, poll, cancel); persisted asset-import status |
| `binding_judge.py`, `binding_suggest.py`, `binding_store.py`, `binding_export.py`, `api_bindings.py` | Clause reuse assessment: candidate pool, model suggestion (three readings), the confirmed conclusions, export, reverse lookup and coverage |
| `preferences.py` | Machine-local language, appearance, encoder and esmini preferences |
| `web/` | React + Ant Design workbench (TypeScript), served from `web/dist` by the API |
| `cli.py` | JSON on stdout, diagnostics on stderr |
| `search_cli.py` | Build and query an OpenX asset catalog from a directory |

## Application layers

The workbench is a local web application. `openx_workbench.api` (FastAPI) serves the built React interface from `web/dist` and a JSON API under `/api`. The API is a thin layer: routes validate input and call the same stores, matcher and parser the CLI uses, so retrieval order, reuse verdicts and exported traces do not depend on the interface.

- **Stores.** `AssetStore` (immutable asset versions shared by all projects), `ProjectStore` (projects and version-pinned reports) and `PdfStore` (PDF sources and scene revisions) write atomically to the machine-local data folder (`OPENX_DATA_DIR`, by default `%LOCALAPPDATA%\OpenXScenarioWorkbench`); each project's records live in its own folder (by default `Documents\OpenX 项目\<name>\.openx`), which the data folder's `projects.json` locates.
- **Background jobs.** PDF extraction, asset import with its labels and reuse suggestions outlive a request. `jobs.py` runs each in a daemon thread; the client receives a job snapshot at once, polls `GET /api/jobs/{id}` and may request a stop, which takes effect after the current step. One job per kind runs at a time. The asset-import status is persisted so a restart reports an interruption instead of a silent loss.
- **Bindings.** A requirement scene is bound to the asset versions that build its test. For every scene of a PDF a background job gathers about twenty candidates (the workbench ranking's top 10, the rules' top 10, and the top 5 by asset name, by name-free structure text and by the requirement title's Chinese pieces in the asset names) and asks the configured model, three times at the thinking effort of the settings, which of them build the same test, grouped with the variants that differ only in values; the preferred asset most readings name is the suggestion, and readings that disagree mark it inconsistent. Only what a person confirms enters the table (`bindings/bindings.json`), one for all projects: a requirement is keyed by the PDF content, its clause and the extracted title, so the same standard in another project finds its bindings. Bound versions are pinned like report versions. A newer asset version or edited scene facts mark a binding for a second look; nothing changes it by itself. Model replies are cached by request.
- **Caches.** Parsed assets are reused until a stored version, its preview status or its classification changes; the retrieval index is keyed by the catalog fingerprint and encoder.
- **Settings.** The model key never leaves the service; responses only say whether one is saved, and a saved key never follows an edited endpoint. Folder dialogs and "open folder" act on fixed, server-known folders on the same desktop.
- **Loopback only.** The service binds to `127.0.0.1`. Requests with a foreign `Host` header (DNS rebinding) and writes with a foreign `Origin` (cross-site forms or fetches) are refused.
- **Preview.** One esmini worker runs at a time in a separate process and serves an MJPEG stream on its own loopback port; the page embeds it in an `<img>`. Polling the status records whether the version played.

The React client (`web/src`) keeps no business logic: it renders API data, keeps the interface language in `(中文, English)` pairs next to their use, and stores preferences on the server. `web/scripts/verify-ui.mjs` exercises the full interface against a throwaway workspace seeded by `scripts/seed_demo_workspace.py`.

## What the fields mean

- An entity identifies a ScenarioObject and its declared category or catalog name.
- An action records a recognized action kind, assigned actor when available, and an absolute speed target when directly numeric.
- A trigger records start/stop scope, condition name/type, delay, and edge.
- A position preserves its actor and selected position-element attributes as strings.
- Road counts describe XML elements. In particular, lane_count includes center lanes and repeated lane IDs across lane sections; it is not a count of unique drivable lanes.
- Road retrieval also uses total declared road length, lane types, plan-view geometry types, junctions, signals, and static objects.

## Asset retrieval flow

`catalog.build_catalog` resolves each OpenSCENARIO `LogicFile` reference against the uploaded or discovered OpenDRIVE files. For a typed requirement, `OpenXIndex` compares every asset's explicit scenario and road facts and ranks by blocking differences, then change cost; the vectors (a text representation and a name-free structure summary) order assets within the same structural bucket and serve free-text search, where FAISS recall applies. Results retain the XOSC/XODR pair and explain which structures matched.

`sim_archive.expand_sim_archives` treats `.sim` as a ZIP container. It reads case JSON and contained OpenDRIVE files in memory, resolves ScenarioManager's logical `<map-id>.xodr` reference to `map/<map-id>/<road-name>.xodr`, converts the embedded OpenSCENARIO-shaped JSON into deterministic XML for the existing parser, and supplements genuinely missing roads with separately uploaded XODR files. Cases whose `LogicFile` cannot be resolved are excluded and summarized in an import report; the adapter does not invent a road or silently accept an incomplete pair.

The encoder boundary has two implementations: deterministic hashing for an explicit offline baseline, and `BAAI/bge-m3` through SentenceTransformers for semantic retrieval. Both name/label and name-free structure recall use the selected encoder, with no small-model fallback. Corpus encoding is batched and identical texts are encoded once per call. Index files store both normalized vector sets, model identity, ordered asset IDs and a fingerprint of parsed facts and accepted labels; loading fails when these change.

The UI defaults to M3 and persists explicit encoder choices. Document matching uses
`OpenXIndex.search_many` to encode all scene queries together, then invokes the same
ranking path as single retrieval. `reuse_trace.build_trace` is shared by both modes;
`ProjectStore` uses one atomic version-pinning save path. Batch reports retain all
source revisions and included candidate versions. `review_kind` explains partial
verification, missing core structure, or text recall without changing verdict ordering.
The parser resolves bounded lexical parameter references in memory and records
event/action/condition ownership; original asset bytes remain immutable.

PDF scene sections are converted to a `ScenePackage` that retains filename, section ID, page range, and source text. Its canonical scenario-family, participant, relative-position, action, trigger, road, and parameter fields form a `RetrievalQuery`. Candidate ranking first minimizes blocking differences, then estimated change cost, and only then uses the combined relevance score. The same change cost is exposed in the UI and CLI. Vector similarity therefore only breaks ties and cannot turn an incompatible scenario into a direct-reuse recommendation.

Reuse levels come from explicit differences: established matches allow direct reuse, adjustable differences allow modification, missing evidence requires review, and known function/type/topology conflicts require a new build. Typed structures are authoritative and compatibility fields are derived from them. Old rule-only requirements retain their legacy adapter. Participant signatures preserve multiplicity, relative bearing, facing and actor-owned behavior. Initialization speeds and story targets distinguish cruise, static, stopping and speed changes; unresolved or complex behavior remains unknown. Structure profiles are computed once per index. Initial relative, lane, road and world positions and OpenDRIVE reference lines support the existing geometry normalization.

A free-text query without a selected `ScenePackage` is recall-only. Before it is encoded, `synonyms.expand_query` appends the library terms its everyday words refer to (急刹 → 制动, 鬼探头 → 横穿, 自动泊车 → APA; ported from ScenarioManager). It returns ranked candidates with semantic evidence and the neutral `review` state, but it cannot claim direct reuse, modification, or a new build because no explicit requested structure exists to compare. This keeps the decision panel consistent with its difference evidence.

Unknown topology is a distinct state rather than a mismatch. If participant type and actions agree but either side lacks a resolvable bearing or facing direction, the result requires placement verification and cannot be marked as direct reuse.

The default PDF path uses the migrated ScenarioManager V2 native block parser, chain chapter decoder, scene-first model extraction (prompt v10: one call finds the scenes, concurrent calls read each scene's structure with quoted, code-checked evidence and, for a model that reads images, the scene's figures rendered from the page; earlier prompts stay frozen), subtree resolution and Stage D review checks. Native tables preserve row/cell boundaries and verified row/column spans; cross-page continuation follows chapter ownership, retaining separate page evidence. Scanned pages (including image bodies with native footers) pass through an isolated local PP-StructureV3 worker; native pages retain their existing parser. Both paths preserve page/bbox/provenance in the same scene contract. Native chapter quality failures can start an isolated PP-DocLayoutV2 overlay using the same runtime/cache runner; it retains original evidence and rechecks coverage before model extraction. Figures are read only for spatial facts (positions, facings, the ego's lane and turn); other image semantics and complete cross-page/merged-table interpretation remain deferred. See [migration scope and validation](PDF_MIGRATION.md). No private corpus or internal evaluation results are bundled.

The road-reference check first resolves the referenced relative path against the scenario directory, then falls back to a unique basename. Ambiguous same-name roads are rejected. Pairing does not prove that the scene can execute.

## Current limits

This is a structure inspector for selected XML constructs with an optional esmini preview, not an ASAM conformance validator. Unsupported details may not appear in the summary:

- Offline XSD validation selects the declared OpenSCENARIO/OpenDRIVE version from a locally installed, checksummed registry. It reports valid, invalid, unsupported or unavailable separately from structural reuse. Exact schema provenance and diagnostics enter saved decisions. Missing schemas never count as successful validation. Schemas are mirrored from esmini into machine-local storage; parsing itself never downloads them. `schema_updates.py` handles user-started updates: it compares GitHub's file ids with the installed files, discovers each version's entry schema by esmini's layout (never guessing between candidates), follows includes, stages and compiles the registry beside the active one, compares library verdicts, then switches it in and keeps the previous registry for rollback. The parsed-catalog cache is keyed by the registry, so a switch re-checks assets without a restart.
- A rule verdict of direct reuse requires passing checks for both files. Manual search, single/batch traces, explanations and report exports use the same gate; persistence rechecks trusted immutable files. A clause's reuse conclusion in the binding table is a person's decision and is not gated: files exported from a simulator often fail the checks, which are shown for information. Historic snapshots are displayed conservatively without rewriting saved evidence.
- SIM standard export uses an audited conversion whitelist and validates a separate copy. Only checked, resolved copies are downloadable as standard packages; diagnostics preserve unsupported extensions. Reimport verifies hashes and stages the checked pair while retaining exact originals in the source ZIP. Custom commands still need target-engine verification.

- Parameter references, aliases and bounded arithmetic have resolution provenance. Unsupported expressions, ambiguous declarations and dynamic mutation require review; this is not a complete expression evaluator.
- Catalog references are identified but not expanded.
- Event paths retain ownership, priority, actions and condition groups. Execution ordering, trigger evaluation and complete action semantics are not established by the flattened parsed facts.
- Road geometry is used for relative-position matching, but physical feasibility and scenario behavior are not simulated or validated.
- OpenSCENARIO DSL is outside the current parser's scope.
- SIM import supports the observed ScenarioManager container shape; it is not a general converter for arbitrary proprietary `.sim` formats.
- The Windows preview runs an available local esmini executable on click and streams real rendered frames into the page. It does not establish semantic or standards conformance; failed previews retain parsed facts.

These limits determine the next parser improvements in the [roadmap](../DEVELOPMENT_PLAN.md).

## Data flow and dependencies

Uploaded files are read in memory by the local service. The parser makes no network requests. The public demo import downloads a fixed OpenSCENARIO/OpenDRIVE pair from GitHub and imports it like any upload. The optional download script also saves the upstream license.

OpenX XML parsing, retrieval and structural decisions run without an API key. Default PDF scene extraction requires a configured model; legacy rule extraction remains an explicit offline API option. Lightweight retrieval has no model download. BGE semantic retrieval is an optional local dependency and downloads the model on first use. On-demand model explanations send the selected evidence payload to the configured service only when explicitly requested in the UI. Binding suggestions, when requested, send each scene's source text and extracted facts and its candidates' names, stories and differences.
