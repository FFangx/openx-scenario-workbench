# ScenarioManager core alignment — 2026-10-01

This change connects the existing migrated PDF schema to retrieval and decisions.
It retains OpenX's versioned asset store, source evidence and esmini preview.
It does not introduce a second ingestion, model or indexing stack.

## Implemented contract

- Typed `SceneStructure` overrides stale flat fields and descriptive text. Manual
  edits derive compatibility fields from that structure. The editor exposes one
  structural source; the store rejects independent flat-field edits for typed scenes.
- Matching compares participant count/type, relative bearing/facing and actor-owned
  behavior, tested function, road, triggers, initial speeds and environment.
  Additional participants/actions prevent direct reuse. Missing facts and declared
  unsupported constraints produce `review`, rather than silently disappearing.
- Participants are paired one-to-one for the fewest blocking differences, then the
  lowest change cost, over all pairings. A participant's own initial speed, when the
  requirement states it, is compared after pairing; otherwise the requirement's speed
  list is compared with duplicates when it has one speed per participant.
- Verdicts (2026-10-04): `direct`; `modify` for verified changes only; `major_modify`
  when those changes cost at least `MAJOR_MODIFY_COST` (5: a behavior change plus an
  extra participant removed); `review` for any unverified fact; `new_build` for any
  blocking difference. All numbers live in `reuse_policy.py`.
- A `review` assessment is saved only when the reviewer confirms each open item with a
  reason. The verdict stays `review`; the reasons are kept in the trace
  (`reuse.review_signoff`) and shown as "confirmed after review".
- Initialization speed is separate from story speed events. A single positive-to-zero
  target establishes stopping; complex events or unresolved speed actions require
  review. Function labels describe an accepted classification, not ASAM certification.
- Environment labels follow coarse ScenarioManager conventions: precipitation
  intensity distinguishes active rain/snow, 06:00–18:00 denotes daytime and visibility
  up to 350 m denotes the fog-test category. Raw fog visibility is retained. Multiple
  environments remain unknown; this is not a weather-transition interpreter.
- Names/accepted labels and name-free structure have independent recall routes using
  the same encoder. Blocking differences and explicit change costs govern final
  ranking. Existing exhaustive structural bucket inclusion is retained.
- Confirmed asset labels reach retrieval and function comparison. Rule suggestions
  and unaccepted low-confidence results cannot certify a function. Classification
  excludes Ego from targets and uses vehicle categories for motorcycles/trucks.
- Both disk and session index caches include parsed facts and accepted labels.
  Changing models or classification invalidates the index. Identical BGE inputs
  are encoded once per batch; structural profiles are reused across queries.
- Saved decisions include the parsed facts and accepted labels used at decision
  time. Explanations cite classification separately from XOSC facts. Report pinning,
  deletion and PDF revision/publication use one reentrant cross-process store guard.
  Failed report writes release their own references; deleted versions cannot acquire
  new report pins. A process crash after pinning can leave a conservative orphan pin.

## BGE-M3 runtime

The default semantic model is **`BAAI/bge-m3`**, producing 1024-dimensional normalized
vectors. There is no fallback to `bge-small`. Hashing remains a separately selected
offline baseline and must not be described as semantic BGE retrieval.

The actual OpenX worktree environment was tested with sentence-transformers 5.7.0,
transformers 5.18.0 and torch 2.6.0+cpu. The newer torch 2.14.1 wheel failed to load
`c10.dll` on this Windows machine. Installing the CPU version already used by the
local ScenarioManager resolved that failure. No model weights or private data are
bundled in this repository.

```powershell
uv pip install --python .venv/Scripts/python.exe '.[semantic]'
uv pip install --python .venv/Scripts/python.exe --no-deps --index https://download.pytorch.org/whl/cpu 'torch==2.6.0+cpu'
```

## Reproducible quality gate

`tests/fixtures/reuse/corpus.json` contains six original authored parser assets and
eight Chinese/English requirements, with 48 independently declared expected verdicts.
The counterexamples cover front/rear, cruise/stop, pedestrian/type/facing, additional
actions and missing topology. Additional tests cover rename invariance, action
ownership, unsupported requirements, invalid numbers, persisted index invalidation,
live PDF revision → changed decision → saved snapshot, and concurrent references.

```powershell
python -m openx_workbench.evaluation tests/fixtures/reuse/corpus.json --encoder hashing --sizes 1000 10000 --output hashing.json
python -m openx_workbench.evaluation tests/fixtures/reuse/corpus.json --encoder bge --sizes 1000 10000 --output bge-m3.json
```

Both encoders passed all eight first-candidate checks and all 48 verdict checks,
with zero false `direct` decisions on this set. The M3 run loaded real cached model
weights, used 1024-dimensional embeddings and FAISS, with network access disabled.
These results validate the structural contract. They do not establish production
retrieval accuracy, foreign-language extraction accuracy or superiority over every
other model. The reported raw recall routes are separate from final reranking.

Final validation: **133 tests passed**, Ruff source/test checks passed and both
wheel and source distributions built successfully. The [complete authored evaluation
record](evaluations/reuse-20261001.json) includes the actual runtime versions,
per-case verdicts and scale measurements. CI now runs the static checks alongside
the regression suite on its existing Windows/Linux and Python matrix; the current
unpublished changes have not yet run through remote CI.

Preliminary CPU timings on this development machine, collected while local QA was
running (not an isolated throughput benchmark):

| Encoder | Asset count | Build seconds | Median query ms |
|---|---:|---:|---:|
| Hashing | 1,000 | 0.39 | 19 |
| Hashing | 10,000 | 5.86 | 414 |
| BGE-M3 | 1,000 | 3.72 | 1,045 |
| BGE-M3 | 10,000 | 14.08 | 1,407 |

Scale runs repeat the same six authored patterns with unique asset IDs. Encoding
deduplication therefore saves substantial work; this does **not** measure building
an index of 10,000 distinct semantic scenes. Vector-memory figures describe only
float32 payload, excluding the model, Python objects, catalog and index overhead.
The structural compatibility pass still visits every candidate, so large libraries
remain linear despite FAISS recall. Incremental insertion, ANN and production corpus
benchmarks remain future work.

## Boundaries

The subsequent [PDF migration extension](PDF_MIGRATION.md) adds scanned/mixed PDF
ingestion, native/OCR table evidence and offline version-specific XSD checks.
Complete table semantics, native-text Paddle layout rescue and full ASAM semantic
conformance remain outside the implemented scope.
The fixture files test parsing and decisions; they are not certified executable
scenarios. The existing esmini preview remains a separate execution check. A licensed
public PDF/asset corpus with independently reviewed extraction labels is still needed
for an end-to-end business accuracy benchmark.

Document-wide matching and summary reports now share the interactive retrieval and
trace contracts. Agent/API functionality remains deferred; the standard-check
and export closure is described below.

## Closure improvements on 2026-10-01

- Both retrieval pages default to BGE-M3. An explicitly selected Hashing baseline
  persists locally across navigation and restart. Model loading failures remain
  visible; they never select a smaller model or a different encoder automatically.
- The existing four structural verdicts and ranking remain compatible. `review_kind`
  distinguishes `partial` (known core interaction, remaining unverified facts),
  `undecidable` (missing core structure), and `recall` (unstructured text retrieval).
  The distinction appears in candidate tables, decisions and exported snapshots.
- XOSC parsing resolves lexical `$name` references, aliases and bounded `${...}`
  numeric arithmetic (`+`, `-`, `*`, `/`, `%`, unary signs). It records declarations,
  original/resolved attributes and failures. Unsupported functions, cyclic chains,
  non-finite results and dynamic parameter mutation require review. This is a
  deliberately limited reader, not a complete ASAM expression evaluator. The
  [ASAM parameter specification](https://www.asam.net/fileadmin/Standards/OpenSCENARIO/ASAM_OpenSCENARIO_BS-1-2_User-Guide_V1-2-0.html)
  defines the reference syntax and scope rules. Original XML bytes and their XSD
  validation remain unchanged.
- Parsed event paths retain maneuver ownership, priority, actions and condition
  groups through source paths. Condition attributes preserve referenced targets.
  Global actions within story actions are counted once and do not inherit private
  actor ownership. Events are retained for evidence, not assumed playback ordering.
- A document batch uses all current scene revisions, one index, and one batched
  query encoding call. It applies the same comparison, ranking and trace builder
  as individual matching. Summary exports include every source revision and up to
  three candidates per scene; empty recall is `no_candidates`, never `new_build`.
  Changing the document, reviewed facts, catalog or encoder invalidates UI results.
- Single and batch reports share one atomic save/pin/rollback path. Batch reports
  may retain pending assessments, with their state explicit; they pin every
  included candidate version. Saved reports reopen in Overview without rerunning
  matching or replacing their evidence with current asset facts.
- Local regression: **207 tests passed**; Ruff, wheel and source builds passed.
  Tests include parameter shadowing and aliases, unsupported expressions, dynamic
  updates, event ownership, review scopes, encoder preferences, batch/single
  equivalence, stale inputs, immutable reports and rollback of failed writes.
  These authored tests do not establish accuracy on a production corpus.
- Real cached M3 weights (offline, 1024 dimensions, FAISS) matched three authored
  PDF scenes against one authored asset: one `direct`, one `partial`, one
  `undecidable`. Batch scores/verdicts equaled individual matching and saved JSON
  snapshots reopened unchanged. Encoding and matching took 1.518 seconds after
  model/index setup; this small CPU smoke check is not a throughput benchmark.
  Sanitized evidence: [closure record](evaluations/closure-20261001.json).
- Real browser checks covered desktop and 390px layouts, M3 batch execution,
  saving and reopening summaries. Verdict columns appear first; narrow layouts
  scroll within the table without widening the page. Shared caption styling uses
  the existing muted color at full opacity for readable light/dark annotations.
  The updated tray service passed its health check; the existing library remains
  **21 assets / 21 versions**. Isolated authored QA data stays outside Git.

## Standard confirmation and SIM export closure

Structural comparison remains independent of file-standard validation. A
structural `direct` result becomes `review` with `review_kind=standards` unless
both scenario and road checks are `valid`. Missing, unavailable, unsupported or
failed checks cannot confirm direct reuse. Ranking, BGE-M3 vectors and structural
differences remain unchanged. Validation records participate in the catalog
fingerprint, shared traces and grounded evidence.

Single and batch persistence recheck the actual immutable asset files before
accepting a `direct` claim; supplied trace flags cannot bypass this gate. Historic
reports retain their original bytes, while display and export downgrade direct
claims that lack passing validation evidence. Batch decisions with no candidate
cannot assert direct reuse. Pending and modification assessments remain useful
records and do not certify standards compliance.

In Asset management → Source, Prepare standard export creates a separate copy
using a small conversion whitelist: root element ordering, unambiguous parameter
declaration names, editor-only private action labels retained in the audit,
custom-command content serialization, the bundled road path, and empty optional
lane sides. Referenced or ambiguous labels and conflicting commands require
review. Geometry, controllers and unsupported extensions are never invented or
discarded. The audit includes original/export hashes, source version identity,
every conversion, pinned schema revision/hash, unresolved facts and dependencies.

Standard ZIP downloads require both actual XSD checks plus resolved parameters
and dependencies. They contain a checked pair and exact original files/archive.
Diagnostic ZIPs retain candidate files and errors and cannot enter the library
as a standard copy. Reimport checks the exported hashes and stages only the
checked pair, avoiding original-road aliases; the full ZIP remains the immutable
source blob. This is XSD validation, not complete simulation certification.
Custom commands remain explicit and need target-engine execution verification.
Private corpus evidence and screenshots stay outside Git.
