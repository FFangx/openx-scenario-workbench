# PDF extraction and classification migration

## User workflow

1. Open **Settings → Language model**. Enter a Chat Completions compatible base
   URL and API key. Fetch the model list, choose an ID or type one manually, test
   the selected model, then save. Listing models and completing a JSON request
   are separate checks. Some services do not implement `/models`; manual IDs
   remain supported.
2. Create/select a project and import PDFs from the PDF card's **⋯ → Import PDFs** in the workbench; extraction runs as a background job with live progress. Scanned pages require the optional local OCR runtime described below.
   Import sends document text to the configured model. It parses blocks and the
   chapter tree first, then performs scene-first extraction and classification.
3. Select a scene and open **Requirement facts** to inspect its clauses, structure,
   classification and review issues. **Edit facts** creates a revision; original
   page evidence is immutable.
4. **Confirm and publish** adds a snapshot to the machine-wide PDF
   requirement library. Find it under **Asset management → PDF requirement library**,
   download the scene package or return to the source document. These requirements
   are distinct from runnable XOSC/XODR assets.
5. Import `.sim`, `.xosc`/`.xodr`, or ZIP assets as before. Enable model
   classification on import, or classify a saved version later. Inspect the
   rule/model/final audit, correct the labels, and confirm them. Classification
   never modifies the immutable scenario or road files.

Old rule-extracted PDFs remain readable. **⋯ → Extraction record → Extract scenes again** creates a separate
document result; old revisions and saved reports remain intact. The legacy parser
is available explicitly to offline callers via `engine="legacy"`; the UI never
silently falls back to it after a V2/model failure.

## Reference and scope

The standalone `pdf_v2` package adapts these pure modules from the local
ScenarioManager V2 implementation: native block parser, numbering-chain heading
decoder, section tree, structure quality, shared-container prefilter, scene
proposer, scene schema and resolver, Stage D validation, and scene-first runner.
`upstream.json` records source hashes. The v6 prompt text and its frozen digest
are preserved. Historical comments/docstrings containing private evaluation
details were removed; no private corpus, configuration, model responses or
evaluation data was copied. No ScenarioManager installation is needed at runtime.

OpenX owns orchestration, HTTP transport, persistence and UI. It uses the same
default `chain` heading decoder and, since 2026-10-04, `scene-first-prompt-v7`
(v6 plus an optional per-participant `speed_kph`; v6 stays frozen), preserves typed scene
structures, subtree expansion, shared clauses, source anchors and review issues.
Additional checks reject incomplete finishes and malformed response collections
instead of treating them as successful empty extractions. Invalid references are
reported; a response whose scenes all have invalid anchors fails explicitly.

Asset classification implements ScenarioManager's rule → model review → final
labels/audit pattern using OpenX's parsed facts and the PDF function vocabulary.
It is an OpenX adapter, not a port of ScenarioManager's complete SIM metadata
extractor, dynamic vocabulary registry or classification prompt. It does not
claim identical classification for every asset. PDF extraction also does not
replace OpenX's existing retrieval/compatibility engine with ScenarioManager's
full retrieval stack.

Native tables preserve HTML row/cell boundaries, units and geometrically verified
`rowspan`/`colspan` before chapter and scene extraction. Covered slots do not
duplicate values; real blank cells remain empty. Ambiguous grids retain extracted
slots and carry a review flag, without inferred spans or forward-filled values. Scanned/image-dominated pages use PP-StructureV3 with server
OCR models and PP-DocLayoutV2. Mixed PDFs keep native pages and replace scanned
pages once, avoiding duplicate evidence. Both routes retain page coordinates,
block type and native/OCR provenance through revisions and published snapshots.
OCR output is cached by PDF bytes, selected pages and worker/runtime configuration;
incomplete/empty page results fail explicitly. The existing scene-first v6 prompt,
transport, model call limit and typed retrieval contract remain shared.

Native chapter rescue follows ScenarioManager's quality-gated policy: only an
empty chapter tree or low block coverage starts a local PP-DocLayoutV2 worker.
It shares OCR's isolated runtime, renderer, owned process lifecycle and cache
runner. Native text, coordinates, block IDs and reading order remain unchanged.
Only unambiguous, confident visual titles with usable numbering can promote a
paragraph; the same TOC and numbering decoder then checks the result. The chapter
tree and quality report are rebuilt before any model request. Provider failure
or continuing low coverage is recorded and rejected, with no legacy fallback.
Normal native documents do not initialize Paddle; OCR-only documents are not
retried as native text. Heading evidence and review flags survive revisions and
published snapshots. This conservative adapter does not implement every
ScenarioManager layout alignment or unnumbered-title heuristic.

Deferred: diagram/formula semantics, complete cross-page table assembly and
semantic expansion of merged-cell values. These are not silently inferred from OCR.
Model results and OCR/table/layout evidence require source review.

## Local OCR and file-standard setup

```powershell
# Dedicated machine-local runtime; leaves the BGE environment unchanged.
python -m openx_workbench.ocr_setup
# Download version-specific XSDs once; subsequent validation is offline.
python -m openx_workbench.schema_validation --install-schemas
python -m openx_workbench.schema_validation scenario.xosc road.xodr
```

The OCR installer pins PaddleOCR 3.7.0, PaddleX 3.7.2 and PaddlePaddle 3.2.2.
The Python 3.12 Windows development runtime was tested independently of BGE-M3.
PaddlePaddle 3.3.0's oneDNN PIR conversion failed on this machine; no existing
ScenarioManager environment was modified. The optional `[ocr]` extra can also be
installed directly. `OPENX_OCR_PYTHON` or `<data root>/ocr_settings.json` can select
another installed interpreter. Workers own their process trees, have a bounded
timeout, and retain failure diagnostics locally without displaying document text.
Model initialization/CPU recognition can be slow; completed OCR results are cached.

Schemas come from esmini revision `61b44a717d2ade513b4d66d1348b35c5d3dbdc3b`,
preserving their original ASAM license headers. The local registry covers XOSC
1.0–1.4 and XODR 1.4–1.8. Unknown versions are reported as unsupported; no nearest
version is substituted. Settings → File standards can move to a newer esmini revision after
previewing which library verdicts change, and roll back one step. XML structure checks and diagnostics appear in the asset
library, retrieval candidates and JSON/HTML decisions. They do not certify complete
ASAM semantics or esmini execution. `OPENX_SCHEMA_DIR` can select another registry.
Schema diagnostics do not invalidate unchanged semantic vectors.
OpenDRIVE 1.8 uses XSD 1.1 assertions: `xmlschema` enforces these without changing
the upstream schemas; lxml supplies document line numbers only. The installer
compiles every version before publishing the registry. Schema includes remain
local and checksum-verified; document-provided schema locations are ignored.

Older extraction engines can be re-extracted from the original PDF using the newer
V2 path. This creates a separate result and preserves saved scenes/reports.

## Model configuration and storage

Configuration is stored at `<data root>/model_settings.json`. Windows encrypts
the key with current-user DPAPI. Other platforms use an owner-readable local
file (base64 encoding is not encryption). No keys appear in exports, request
hashes or model exceptions. Requests reject redirects, use bounded response
sizes/timeouts, and require HTTPS except on localhost. If no saved settings file
exists, `OPENX_LLM_API_KEY`/`DEEPSEEK_API_KEY`, `OPENX_LLM_URL`, and
`OPENX_LLM_MODEL` remain supported.

One configuration is used for extraction, asset classification and grounded
explanations. DeepSeek's thinking option is sent only to its official endpoint;
generic compatible services receive standard Chat Completions parameters. Output
token limit and timeout are editable for providers with different limits.

PDF response caching is keyed by request content, engine, endpoint, selected
model and thinking setting. A document makes at most two calls (one schema
retry); transport errors and truncation do not trigger repeated calls. Successful
zero-scene results are saved and not repeatedly charged. PDF identity includes
content hash, standard and extraction configuration, not filename alone.

- `pdf_blobs/`: source PDFs, outside the repository.
- Project `documents/<id>/`: original scene revisions and complete extraction audit.
- `model_cache/`: local content-addressed responses; contains document-derived data.
- `ocr_cache/`: local recognized blocks; contains document-derived data.
- `layout_cache/`: local native-page layout predictions, keyed by PDF/pages/runtime/worker.
  Provider model checksum and promotion/quality audit remain available locally.
- `ocr_runtime/`, `ocr_settings.json`: isolated local OCR dependencies/configuration.
- `schemas/`: pinned, checksummed XSD registry; no application-time network access.
- `extraction_failures/`: failed model runs; never successful empty documents.
- `requirements/<id>/<revision>.json`: confirmed immutable requirement snapshots.
- Asset version `classification_history/`: classification changes, with a current
  `classification.json` view. Rule fallback and low confidence are visible.

## Validation on 2026-09-29

- Authored three-page PDF: native blocks and chapter tree equal the reference;
  real model run produced two AEB scenes with original page citations.
- Public Euro NCAP AEB C2C v4.3.1 (39 pages): 402 blocks and 77 chapter nodes equal
  the reference. Real model run produced seven scenes and seven review issues;
  this is a smoke test, not a recall or correctness benchmark.
- Frozen v6 prompt equals the reference byte-for-byte.
- Real model-list and selected-model JSON probes succeeded. An authored OpenX
  asset also completed live classification.
- Full regression suite: **93 passed**. UI detector returned no findings. Desktop
  and 390px browser checks covered model discovery and a real successful model test.
- Automated coverage includes cached duplicate imports, confirmed empty PDFs,
  scan rejection, truncation rejection, invalid references, immutable revisions
  and library snapshots, credential persistence, model-list/manual model controls,
  classification history and returning from the library to source evidence.

All live PDFs, responses and smoke-test records are local temporary artifacts.
Private L2 files were not used or transmitted for this migration's live tests.

## Validation on 2026-10-01

- Authored two-page mixed PDF: page 1 kept native text; page 2 ran the installed
  PP-StructureV3 sidecar. A real configured model produced one AEB scene with
  ego speed 50 km/h and target speed 0 km/h, retaining table HTML and page boxes.
- First CPU OCR took **316.984 seconds** on this machine. Repeated complete
  extraction took **0.172 seconds**, using both OCR and model response caches.
  This is one smoke sample, not a multilingual or large-document accuracy benchmark.
- All ten installed XOSC/XODR schema versions compiled, including XSD 1.1 for
  OpenDRIVE 1.8. Pinned public esmini `cut-in.xosc` (1.1) and `e6mini.xodr` (1.4)
  passed their declared-version checks. Changing the latter's header to 1.8
  correctly rejected its incompatible lane content; versions are not interchangeable.
- Full local regression suite: **148 passed**; Ruff passed. Coverage includes
  selective OCR with native footers, table row/value binding, OCR box/page validation,
  owned worker timeout cleanup, immutable published provenance, XSD assertions,
  missing/corrupt registries and external include rejection.
- Wheel and source builds succeeded. Private L2 documents were not used or sent.

The sanitized smoke record is `docs/evaluations/pdf-migration-20261001.json`.
That smoke sample did not cover cross-page/merged-cell tables or complete ASAM
semantic validation. Subsequent table validation below adds a narrower verified scope.

## Native chapter rescue validation on 2026-10-01

- An authored native one-page PDF with an 11.5 pt non-bold numbered title had no
  initial chapters. The installed PP-DocLayoutV2 recovered one title; revalidated
  body coverage reached **100%**. A real configured model extracted one AEB scene,
  preserving native heading/body evidence and ego speed **50 km/h**. Target speed
  remained unspecified in its structured result and still requires source review.
- CPU layout prediction took **5.141 seconds**. Repeating complete extraction took
  **0.078 seconds**, using both layout and model response caches.
- An authored three-page negative sample recovered only one title. Coverage stayed
  at **60%**, so complete extraction was rejected before any language-model call.
  Its layout inference took **17.469 seconds**. No permissive fallback was added.
- Both layout adapters share the existing OCR cache runner; a prior mixed-PDF
  OCR result still loaded from cache in **0.047 seconds**, without rerunning OCR.
- These two samples validate orchestration and refusal behavior; they do not
  establish multilingual heading accuracy or large-document performance.
- Full local regression suite: **175 passed**; Ruff, wheel and source builds passed.
  Coverage includes native/OCR gating, malformed provider results and caches,
  ambiguous regions, TOC/numbering checks, partial-rescue refusal and immutable
  published heading evidence. The restarted tray service passed its health check.
- Sanitized evidence: `docs/evaluations/native-layout-20261001.json`. Original PDFs
  and complete responses stay outside the repository; no private L2 files were used.

## Native spans, continuation and optimization on 2026-10-01

- The reference implementation keeps cross-page body/table blocks under their
  existing chapter owner. OpenX retains that rule; it does not combine separate
  page evidence into a fabricated single table. A new numbered heading starts
  another scene. The reference has no general automatic table-stitching path.
- OpenX's native adapter now preserves detected row/column spans as HTML, rather
  than labelling every missing grid slot as a merged cell. The geometry must cover
  an unambiguous complete grid. Overlaps, holes, conflicting boundaries and invalid
  boxes retain extracted slots with `table_geometry_unresolved`. Empty cells and
  zero values remain distinct; merged labels are not duplicated or propagated.
  OCR-supplied HTML spans remain unchanged.
- Authored three-page PDF, real configured model: **two AEB scenes**. The first
  preserves native tables from pages 1–2 with ego/target speeds **50/0 km/h**;
  the next preserves page 3 with **80/20 km/h**, without mixing their table values.
  Original page boxes, spans and review flags survive revision and publication.
  Complete extraction took **5.203 seconds**; repeat requests hit the model cache.
- Boundary lookup uses binary search. For authored 200×20 regular geometry,
  seven runs before/after gave median serializer time **77.048 → 11.216 ms**
  (about **6.87×** for this step), with identical output. This is a synthetic
  serializer measurement, not an end-to-end PDF speedup or an accuracy benchmark.
- Engine version 4 gives older stored extractions a separate re-extraction identity;
  the scene-first v6 prompt and existing immutable snapshots remain unchanged.
- Full local regression suite: **189 passed**; Ruff, wheel/source builds and
  restarted tray-service health check passed. Existing assets remain 21 assets
  and 21 versions.
- Sanitized evidence: `docs/evaluations/native-tables-20261001.json`. Source PDFs
  and complete responses stay outside the repository. Private L2 files were not used.
