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
  Additional participants/actions prevent direct reuse. Missing core facts and declared
  unsupported core constraints produce `review`, rather than silently disappearing.
- Participants are paired one-to-one for the fewest blocking differences, then the
  lowest change cost, over all pairings. A participant's own initial speed, when the
  requirement states it, is compared after pairing; otherwise the requirement's speed
  list is compared with duplicates when it has one speed per participant.
- Placement (2026-10-06). A participant that differs from the requested one only in
  where it is placed is moved, not rebuilt: a `placement` change costing
  `COST_PLACEMENT`, adjustable. Two cases. A moving participant doing the same on the
  same side of the ego, only further ahead or behind: a standard describes the
  interaction (right alongside when the ego changes lanes), an asset where it starts
  (right behind, catching up), so its start or trigger moves. Doing something else as
  well stays a rebuild (a car cutting in from ahead does not overtake from behind), as
  does the ego's own lane (a lead car, a car closing in from behind). A standing
  participant facing another way is turned: near 30° the facing classes split noisily
  (an oblique car reads as crossing in a standard and as same-way in its asset).
- Behaviors (2026-10-07). A participant that keeps its distance to another
  (`LongitudinalDistanceAction`, read as `following`) drives along until the test event:
  for a requirement that has it move otherwise, that is no behavior of its own, and it
  drives as a requested cruise does (a lead car held at a gap, then braking, is the
  requested hard stop). Requested to stand still or to follow, it stays a behavior.
  A requirement that names no behavior leaves every one open: nothing the asset's
  participant does is extra (it is verified as a participant fact).
- When both the requirement and the asset put the ego under system control, a
  requested lane change the asset does not script is the system's to make (a
  system-triggered lane change leaves nothing in the file): listed to confirm, at no
  cost. An asset that shows a lane change still scores higher.
- Whether the system under test drives is a setting of the reuse, like the tested
  function, and never a change (2026-10-06): an asset under system control serves a
  requirement that does not say who drives, and a requirement under system control
  against an asset without an engage command lists it to confirm (`COST_PARAMETER`,
  adjustable). Standards differ in whether they say it at all.
- Verdicts (2026-10-04, tiers 2026-10-05): `direct`; `modify` for changes to make;
  `major_modify` when they cost at least `MAJOR_MODIFY_COST` (5: a behavior change plus
  an extra participant removed); `review` for an unverified core fact; `new_build` for
  any blocking difference. All numbers and tiers live in `reuse_policy.py`.
- Every difference has a tier, after the ScenarioManager layering (story > map >
  parameters, 2026-07-27). **Core**: participants, behaviors, occlusion, road type,
  lane count and lane lines, venue, a misuse or activation-boundary test intent,
  unresolved asset parameters. **Adjustable**: tested function, speeds, TTC, distances,
  triggers, placement, environment, lateral direction, a lane change left to the system. **Note**: a functional test intent and the
  end condition, which describe the evaluation and are listed but never compared or
  costed. An unverified core fact makes a review; an unverified adjustable fact is
  listed as "confirm when changing" and makes a modification. Unknown categories are
  core. **Figure** (2026-10-07): a fact the requirement's figure shows but its text does
  not (evidence source "图": a bearing or facing, the ego's turn or lane) is an aid. An
  asset that shows it ranks ahead of an equal one that does not; one that does not is
  listed to check against the figure (`COST_FIGURE`) and is neither blocking nor a review.
  The verdict and the change cost rest on the text; figure checks order candidates of
  equal change cost. A person's edit of the fact drops its figure evidence.
- The tested function is a setting of the reuse, not part of the scenario (2026-10-05):
  a story built for AEB serves FCW or ACC after the system and its scoring are switched.
  Most of it lives outside the scenario file: on the 230 assets with confirmed function
  labels, standard OpenSCENARIO content alone tells the function family for 33 %; the
  rest needs simulator-specific commands (`EnableXXX`) that other libraries may not
  write. So a different function is a change (`COST_FUNCTION`) and an unknown one is
  confirmed while reusing; neither blocks. A parking requirement against a driving
  asset stays blocking through the parking operation.
- Either-or participants (2026-10-06, prompt v8). A requirement may offer alternatives
  of which one takes part in a run ("a car, a tricycle or a pedestrian stands ahead"):
  they share an `alternative_group`. An asset builds one of them, so every combination
  of one participant per group is compared (`VARIANT_LIMIT`) and the best kept; the
  others are neither missing nor the asset's concern, and their ages leave the
  requirement with them. A `variant` note names the choice and costs nothing.
  Prompt v9 also reads them from parameter tables whose rows differ in the target.
- A driver's request to the system (a lane-change request or confirmation command,
  `scene_facts.driver_requests`, a library convention) is a driver input for a
  driver-intervention test whose ego changes lanes, and nothing to remove for a functional
  test: "驾驶员触发的换道" reads either way. Only the inputs that take over the controls
  (pedals, wheel) count against a functional test.
- The ego's lane among its direction's lanes (`ego_lane`, prompt v9) is not compared with
  an asset's start lane yet: it stays an adjustable item to verify, like a placement (read
  from a figure, a figure check).
- The way the ego leaves a junction (`ego_turn`: straight, left, right, U-turn) is read
  from the ego's routing (`scene_facts.ego_turn`). A road file without a junction leaves
  nowhere to turn, so its ego goes straight whatever the routing says (the bend of a
  curve is no turn); without a road file a routing outweighs the map name, which only
  says "straight" for a road with nowhere to turn. Another turn is a route to change in
  the same junction (`COST_BEHAVIOR`, core); an unread one is verified
  (`COST_PARAMETER`, core, so a review).
- Traffic control the test relies on (`traffic_controls`: traffic lights, speed-limit
  signs) and the signed speed-limit values come from the road file: present, nothing;
  absent from a readable road, a road change (`COST_ROAD`), or a sign value to set
  (`COST_PARAMETER`) when other limits are signed; road file missing, unverified. Of
  several requested values (chosen by the set speed) any one will do.
- Information gate: a requirement with no participant or occlusion is a review, even
  when both sides test the same function. Two near-empty stories always match: before
  the gate, misuse tests were matched `direct` to any asset testing the same function and
  a traffic-light test was offered a static-obstacle asset.
- A driver-intervention requirement against an asset without driver inputs is blocking:
  another kind of test. The other way round, removing the inputs is a change.
- Lanes (2026-10-05): the parser reads the most driving lanes one direction and both
  directions offer on one cross-section, and the line types drawn on driving lanes
  (`solid`, `broken`). A requirement's lane count is a lower bound: 单向 N counts one
  direction, 双向 N both (an odd 双向 N, as in 双向单车道, N each way), a count without
  direction both. A requested line type matches when the road has it anywhere: the
  requirement does not say which line it means. Unread lanes or lines, or a missing road
  file, are unverified, never a guess. Same rules as ScenarioManager `lane_requirement`.
- A `review` assessment is saved only when the reviewer confirms each open core item
  with a reason. The verdict stays `review`; the reasons are kept in the trace
  (`reuse.review_signoff`) and shown as "confirmed after review". Differences saved
  before tiers existed count as core.
- Speeds and environments are read as described in "SIM structure facts" below
  (2026-10-05). Function labels describe an accepted classification or a simulator
  command that switches the function on, not ASAM certification.
- Environment labels follow coarse ScenarioManager conventions: precipitation
  intensity distinguishes active rain/snow, 06:00–18:00 denotes daytime and visibility
  up to 350 m denotes the fog-test category. Raw fog visibility is retained.
- Ranking has two stages (2026-10-05, `retrieval.rank_candidates`). Every asset is
  compared structurally, and structure alone gives the verdict. Direct and modify
  verdicts lead by change cost; a major modification is close to a new build and does
  not lead. Review candidates whose cost is within `NAME_TIE_COST` of the cheapest
  review are structurally tied; among them a
  standout name or text match (`NAME_STANDOUT_Z` standard deviations above the library
  mean similarity) goes first. The other standout matches among the `NAME_RECALL` most
  similar assets follow, then everything else by blocking differences, change cost and
  score. When every candidate is a new build, structure alone orders them. Before,
  the order was blocking differences, change cost, score, so a cost difference of half
  a parameter pushed the asset a library names for the requirement below an unrelated
  one. The threshold is relative: a library whose names say nothing rarely produces an
  outlier and stays close to the structural order. The structure-text vectors remain
  in the index for the ablation baseline only.
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

## SIM structure facts (2026-10-05)

ScenarioManager libraries carry their meaning in details a reading by element type
misses. `scene_facts.py` re-derives ScenarioManager's structure rules on the parsed
scenario (not on SIM JSON); none of them reads a scenario's name.

- **Import.** Each SIM case keeps a `.case.json` sidecar with its map name and
  environment presets. A case whose road is a simulator built-in map (not packed in
  the archive) is still imported: its road type is read from the map name, it is
  marked "road file missing", it can be matched, and it cannot be previewed, exported
  as a standard copy or confirmed as `direct`.
- **Scenery.** A `MiscObject` (cone, barrier, carton) is scenery, not a participant.
  Props are counted by 3D model and lane, and grouped by position: a group can stand
  for every requested obstacle there (cones and barriers ahead are both the group
  ahead) but is never an extra participant. A standing obstacle's
  facing is not compared. Occlusion is read per instance before grouping: a nearer
  object whose BoundingBox width covers the ego's line of sight to a farther one (for
  a moving target, any part of its sweep toward the ego's path); props occluding props
  are not recorded.
- **Background participants** (2026-10-06). A standing traffic participant that no
  trigger condition refers to, that has no story action, that does not stand in the
  ego's path ahead (its lane, or its body reaching into the ego's width) and that hides
  nothing taking part is background: the parked cars of a narrow passage, a VRU crowd
  standing by. Of a row standing in the path, those hidden behind another (covering at
  least `HIDDEN_SHARE` of their width) are background too. A scenario where no
  participant takes part has no background. A background participant can still stand
  for a requested one; left over, it costs `COST_BACKGROUND_PARTICIPANT` per group of
  equal signatures instead of `COST_EXTRA_PARTICIPANT` each. Read from structure only;
  the ego's path is taken as straight ahead, so a target in the lane the ego will
  change into, or beside a parking ego, may be read as background.
- **Start position** (2026-10-06). An actor starts where its Init teleports it. Init
  may also say where it is sent (route waypoints, an `AcquirePositionAction` target,
  a synchronization point); read last, those moved the ego to where it goes (42 of 336
  cases in a real library), past the junction or construction zone it drives into, so
  the targets and props there read as behind it.
- **Speed.** An actor's speed is the highest absolute SpeedAction target, since
  initialization often sets 0 and the story accelerates. A story transition (not a
  step) to standstill is a stop; two distinct non-zero targets are a speed change; a
  relative target speed means moving at no stated speed. Event order is not used.
- **Commands.** `EnableXXX` names the tested function and, like `SysEngReq`, puts the
  ego under system control; lane-offset, lane-change-request and ALCA-mode commands
  are lane changes; `EnableAPA` / `ParkingOut` are parking in or out; door commands
  and the driver's closing brake (`BrakePosition`) are recorded facts.
- **Driver input.** Active `OverrideControllerValueAction` channels make a
  driver-intervention test; an active reverse gear is reversing.
- **Simulation control.** `TurnOff` and `just_for_test` events are dropped.
- **Scoring** (2026-10-06). The sidecar keeps the case's scoring criteria
  (`caseData.judgements`); `scene_facts.scoring_criteria` lists the enabled ones beyond
  the authoring tool's defaults (timeout, collision): distance to lane crossing
  (`dtlc>1.75`), longitudinal acceleration limits (`lonacc<-5`), leaving the road
  (`offtrack`), a red-light stop region (`stopandgo: stopTrigger=red`). Like `EnableXXX`
  they are the simulator's convention, not OpenSCENARIO: they describe what a run
  measures when present and mean nothing when absent. A requirement states no scoring,
  so they enter no comparison; they describe the asset to a reviewer. Re-importing a
  SIM archive refreshes the sidecar of versions imported before it was read.
- **Named checks** (2026-10-06). A library's `UserDefinedValueCondition` names
  (`Check_LaneChangeCompleted`, `Check_SysEngReq_Rejected`, `Trigger_HandsOff`) are
  its own convention, treated like `EnableXXX` as an accelerator: present, strong
  evidence; absent, nothing; never a reason for a new build. The set-up and teardown
  checks every case waits on (`EgoPrepareCompleted`, `EndTheCase`) are ignored. A
  lane-change check makes the ego change lanes (the system's lane change leaves no
  action in the file). Activation checks (`*_Activated`, `SysEngReq_Accepted` /
  `Rejected`, a takeover request before a rain or fog area) confirm a requirement's
  activation-boundary test intent, which otherwise stays unverified.
- **3D models** (2026-10-06). Model names are the library's convention too, read the
  same way. A child model (`Child01`, `ACEA_Child01`) confirms a requested child, once
  per child shown; a tricycle model authored as a car (`Tricycle01`,
  `vehicleCategory="car"`) stands for a requested tricycle and still for a car. Other
  models (rollover vehicle, umbrella, debris, warning triangle, construction signs)
  have no requirement field to confirm and describe the asset only. BoundingBox
  heights are read but decide nothing: libraries keep default boxes (a child model as
  tall as an adult one, sedans at 1.65–1.9 m).
- **Lateral direction and route** (2026-10-06). The ego's sideways direction is read
  from its `LaneChangeAction` target (a relative lane counts positive to the left; an
  absolute one against the lane it starts in, for right-hand traffic) or from a
  command naming the side (`ALCAMode=left`, `LaneOffset=right`, the library's
  convention). It confirms a requirement's `lateral_direction`; a different side
  leaves it unverified, since a requirement may mean another participant's side (a
  cut-in "from the left"). The ego's routing turns left or right when the stated
  headings from where it starts through its `AssignRouteAction` waypoints,
  `FollowTrajectoryAction` vertices or `AcquirePositionAction` target change by 45°
  or more (each step's change summed, so one vertex heading stated wrong inside a curve
  cancels out), and turns around from 135°. A requirement's `ego_turn` compares it (see
  above). It also changes how participants face: after a turn, people crossing the road
  the ego enters walk its starting way, so each participant also carries its facing
  relative to the turned ego, and either reading matches the requested one (a
  requirement may describe the start or the interaction).
- **Curve radius** (2026-10-06, ScenarioManager `ego_curve_radius`). The radius is the
  first curve ahead of where the ego starts, not the map's: one road can hold curves
  of R251 to R833. Junction connectors are left out; spirals are transitions; segments
  under 30 m or flatter than R1000 count as straight (the gap between real test curves,
  R15–R833, and transition polynomials, R1174 and up). The search follows up to two
  joined roads. A road that states the radius confirms a requirement's
  `curve_radius_m` within `CURVE_RADIUS_TOLERANCE`; another radius is a road change.
- **Environment changes.** The story's EnvironmentActions are also listed in order
  (rain growing from 10 to 70 mm/h, fog closing to 25 m, a tunnel's day-night-day)
  to describe the asset; the comparison keeps using the merged environment. Light
  turning to night and back to day is a tunnel, lit the way a library without tunnel
  roads simulates one (2026-10-06): it confirms a requirement's tunnel venue, which
  otherwise stays unverified (a tunnel may be built another way). A night test turns
  once.
- **Asset story** (2026-10-06, ScenarioManager `scene_context`). `asset_story` retells
  an asset line by line for a reviewer: road (curve ahead, lanes, lines, speed-limit
  signs, traffic lights, crosswalks), environment and its changes, the ego's speed
  targets in file order, its commands and driver inputs, which way it moves, where the
  driver's closing brake fires (AEB tests close within about 100 m, pilot tests after
  about 1 km), participants with their 3D models, props by model and lane, occlusion,
  the events and what starts them, named checks and scoring. Nothing comes from the
  asset's name; what cannot be read is left out. The model explanation receives it as
  evidence `S1` next to the raw facts `X1` and `R1`.
- **Environment.** Every declared environment is read; story changes to rain, snow
  or fog make the scenario that weather, conflicting readings stay unknown. Missing
  values come from the case's environment preset, where rain and snow amounts
  outrank the preset category and the preset fog level (a rendering setting) is not
  read.
- **Requirements.** Occlusion relations, a driver-intervention test intent and a
  parking operation are now compared instead of left unverified.

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

## Matching corrections and refactor — 2026-10-04

Participant pairing is now a global optimum, target speeds can be bound to
participants, reviewers can sign off review items, and verified changes above
`MAJOR_MODIFY_COST` are `major_modify` (contract above; benchmark evidence in
[evaluation](EVALUATION.md)). The comparison is split into `reuse_facts`,
`reuse_structured`, `reuse_legacy`, `reuse_differences` and `reuse_policy`;
API responses stayed byte-identical through the refactors on both demo
workspaces. Local regression: **304 tests passed**, Ruff passed, and 73 browser
checks passed against the fixture demo workspace.
