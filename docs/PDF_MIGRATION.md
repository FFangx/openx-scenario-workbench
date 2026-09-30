# PDF extraction and classification migration

## User workflow

1. Open **Settings → Language model**. Enter a Chat Completions compatible base
   URL and API key. Fetch the model list, choose an ID or type one manually, test
   the selected model, then save. Listing models and completing a JSON request
   are separate checks. Some services do not implement `/models`; manual IDs
   remain supported.
2. Create/select a project and import a text-based PDF in **PDF workflow**.
   Import sends document text to the configured model. It parses blocks and the
   chapter tree first, then performs scene-first extraction and classification.
3. Select a scene, inspect its own and shared clauses, structure, classification
   and review issues. Edits create a revision; original page evidence is immutable.
4. **Confirm and publish revision** adds a snapshot to the machine-wide PDF
   requirement library. Find it under **Asset management → PDF requirements**,
   download the scene package or return to the source document. These requirements
   are distinct from runnable XOSC/XODR assets.
5. Import `.sim`, `.xosc`/`.xodr`, or ZIP assets as before. Enable model
   classification on import, or classify a saved version later. Inspect the
   rule/model/final audit, correct the labels, and confirm them. Classification
   never modifies the immutable scenario or road files.

Old rule-extracted PDFs remain readable. **Re-extract with V2** creates a separate
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
default `chain` heading decoder and `scene-first-prompt-v6`, preserves typed scene
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

Deferred: OCR/scanned/mixed documents, Paddle structure rescue, image-only
semantics, and full table reconstruction. Native table regions help reject false
headings, but that is not complete table understanding. Unreliable chapter
coverage produces an explicit error. Model results still require source review.

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
