# Reuse evaluation and ablation

This page measures how the workbench ranks library assets for a typed requirement
and whether its reuse verdict is right, and which part of the ranking does the work.
Everything runs on the authored [reuse benchmark](../examples/reuse-benchmark/)
and is reproducible from this repository.

**Short answer:** on this benchmark, names and text similarity are weak evidence;
the structural comparison carries both retrieval and the verdict. Similarity
computed over the same structural facts finds most right candidates, but cannot
tell whether the top hit may be reused as is.

## Benchmark

| | |
|---|---|
| Library | 26 OpenSCENARIO assets on two authored OpenDRIVE roads (straight and curved, two lanes per direction) |
| Families | AEB car-to-car (stationary, moving, braking), truck, motorcycle, cyclist and pedestrian cases, oncoming car, ACC follow/brake/cut-in/cut-out, BSM with and without a lead car |
| Variants | ego speed, night, rain, curve, an extra roadside pedestrian, and one asset whose target start position is not declared |
| Requirements | 38 typed requirements, 20 in Chinese and 18 in English, each with a title and protocol-style text |
| Expected best verdict | 25 direct, 8 modify, 1 review, 4 new build (two confusers are labelled major modify) |

Every asset is generated from its specification in
[`benchmark.json`](../examples/reuse-benchmark/benchmark.json) by
`scripts/build_reuse_benchmark.py`; a test fails if the committed files drift.
Nothing comes from a test protocol, a company library or a third-party dataset.

**Labels.** For every requirement, `relevant` names every asset that needs the
least change, with the verdict a reviewer following the documented
[reuse contract](REUSE_ALIGNMENT.md) expects; `confusers` add similar-looking
assets and their verdicts (111 labelled pairs in total). Labels were declared
from the asset specifications before running the system. The first run found one
labelling mistake, not a system error: a child-crossing requirement states no time
of day, so the night variant needs the same change as the day asset and is now
also listed as relevant.

## Rankers and conditions

| Ranker | What orders the library |
|---|---|
| Name similarity | Cosine similarity of requirement text against asset text (title, labels, entity, action and road statistics) |
| Structure-text similarity | Cosine similarity of the two canonical, name-free structure summaries: the same facts the rules use, compared by an encoder |
| Structural rules only | Blocking differences, then estimated change cost; ties keep library order |
| Rules + similarity | The workbench ranking (two stages, since 2026-10-05): direct and modify verdicts first by change cost; among review candidates within `NAME_TIE_COST` of the cheapest, a standout name or text match (`NAME_STANDOUT_Z` standard deviations above the library mean) leads; then the other standout matches; then the rest by rules. With only new builds, rules alone. |

Each encoder ranker runs with the hashing baseline and with BGE-M3. Each run is
repeated with **descriptive** asset names and with **opaque** names
(`Asset 001` …), which removes the file names and descriptions a curated library
may or may not have.

## Metrics

- **R@k, MRR**: rank of the first relevant asset, over the 35 requirements that have one.
- **Decision accuracy**: the verdict for the top hit equals the expected best verdict,
  and the top hit is relevant. Similarity rankers give no verdict; their decision is read
  as "reuse the top hit". That can only be right for the 25 direct cases, so their
  ceiling is 65.8 %.
- **Unsafe reuse**: requirements whose top hit would be reused as is although it is not
  a direct match.
- **Verdict accuracy, false direct**: for rankers that give verdicts, agreement on all
  labelled pairs, and `direct` verdicts on any asset outside the relevant direct set.

## Results

Recorded on 2026-10-04 on a Windows development machine (Python 3.12, BGE-M3 through
sentence-transformers 5.7.0 on CPU). The [full report](evaluations/ablation-20261004.json)
holds per-requirement rankings and verdicts.

| Ranker | Encoder | Names | R@1 | R@3 | MRR | Decision acc. | Unsafe reuse | Verdict acc. | False direct |
|---|---|---|---:|---:|---:|---:|---:|---:|---:|
| Name similarity | hashing | descriptive | 40.0% | 57.1% | 0.542 | 31.6% | 26/38 | n/a | n/a |
| Name similarity | BGE-M3 | descriptive | 57.1% | 82.9% | 0.715 | 42.1% | 22/38 | n/a | n/a |
| Name similarity | hashing | opaque | 8.6% | 22.9% | 0.252 | 5.3% | 36/38 | n/a | n/a |
| Name similarity | BGE-M3 | opaque | 25.7% | 54.3% | 0.431 | 13.2% | 33/38 | n/a | n/a |
| Structure-text similarity | hashing | either | 94.3% | 94.3% | 0.957 | 65.8% | 13/38 | n/a | n/a |
| Structure-text similarity | BGE-M3 | either | 80.0% | 94.3% | 0.877 | 55.3% | 17/38 | n/a | n/a |
| Structural rules only | — | either | 100.0% | 100.0% | 1.000 | 100.0% | 0/38 | 100.0% | 0 |
| Rules + similarity (workbench) | hashing or BGE-M3 | either | 100.0% | 100.0% | 1.000 | 100.0% | 0/38 | 100.0% | 0 |

"Either" rows gave identical results with descriptive and opaque names.

Rerun on 2026-10-05 after the two-stage ranking: all workbench rows are unchanged
(100 %, 0 unsafe, 0 false direct, both encoders, both namings). The only moved baseline
is BGE-M3 structure-text similarity, now 77.1 % R@1 / 91.4 % R@3, because the
structure summaries carry the SIM structure facts added the same day. Rerun again after the
difference tiers, lane facts and information gate (same day): workbench rows unchanged.
Benchmark version 2026-10-05 relabels seven confusers from `new_build` to `modify`: ACC
following against AEB moving-target assets and ACC lead braking against AEB braking-target
assets, both ways. They share the story; only the tested function and its scoring differ,
which is now a change rather than a rebuild. No requirement's best candidate changed.

## What the numbers say

1. **Names are unreliable evidence.** With good English names, name similarity puts a
   right asset first for 40 % (hashing) to 57 % (BGE-M3) of requirements. Hashing finds
   28 % of the Chinese requirements against English names, BGE-M3 56 %. With opaque names
   both collapse (9 % and 26 %).
2. **The structural facts carry the retrieval signal.** Comparing canonical structure
   summaries reaches 80–94 % R@1 whatever the names. BGE-M3 does worse than hashing here:
   it blurs tokens that differ in one decisive word, ranking a stationary car above a
   braking one and a left cut-in above a right one. Exact tokens suit this text better
   than semantic smoothing.
3. **Similarity cannot decide reuse.** Even the best similarity ranker would reuse a wrong
   or unverified asset in 13 of 38 requirements: every case where the best asset needs a
   change, needs review, or no asset fits. The structural verdict separates those cases
   without a single false `direct`.
4. **Within-bucket similarity changes nothing here.** Rules alone already reach 100 %. This
   follows from how relevance is labelled (least change under the contract), so the
   benchmark does not measure the value of the similarity tie-break among assets needing
   the same change.

## Corrections found with the benchmark

Each fix below was reproduced first, then added to the benchmark as a counterexample.

- **Participant pairing (2026-10-04).** Requested participants were paired with the
  candidate's one at a time in key order, so a participant with no counterpart could take
  the candidate participant another one needed. `follow-ped-beside-en` (a slower car ahead
  plus a pedestrian beside the ego) put the asset that only needs the pedestrian added at
  rank 4, below an asset whose pedestrian and car both have to change. Pairing now
  minimises blocking differences, then change cost, over all pairings (enumerated up to six
  participants, an assignment problem beyond), the same order candidates are ranked by.
- **Target speeds (2026-10-04).** Requirement and asset speeds were compared as sets of
  distinct values, with no participant attached. `bsm-lead-swapped-en` asks for the lead
  car at 80 km/h and the car behind on the left at 50 km/h; the library asset has them the
  other way round, and the sets {50, 80} matched, a false `direct`. A typed participant may
  now carry its own speed (`speed_kph`, also requested from the extraction model since
  prompt v7), compared after pairing. Revisions without it keep one list: compared with
  duplicates when it has one speed per participant, as distinct values otherwise
  ("all targets stand still": [0]). `bsm-lead-zh` checks that the matching asset stays
  `direct`.

## Limits

- The verdict labels follow the same documented contract the rules implement. A 100 %
  verdict accuracy shows the implementation is consistent with that contract on these
  cases; it does not show that the contract matches every engineer's judgement.
- Requirements enter as reviewed typed structures. PDF extraction errors, which dominate
  real use, are not part of this benchmark.
- 26 assets and 38 requirements are small and authored by the same person who wrote the
  rules. A licensed public corpus with independently reviewed labels is still needed for a
  business accuracy claim.
- The assets are parser inputs, not certified executable scenarios; they are not checked
  against the XSD here or run in esmini.
- Query times in the report come from a development machine and are not a benchmark.

## Reproduce

```bash
openx-ablation                          # hashing only, no model needed
openx-ablation --encoders hashing bge --output report.json --markdown table.md
python scripts/build_reuse_benchmark.py --check
```

`openx-ablation` exits non-zero if the workbench ranking gives a false `direct` or an
unsafe reuse. `tests/test_reuse_benchmark.py` runs the hashing gate in CI, and
`tests/test_demo_workspace.py` checks that the benchmark demo workspace, served through the
API, reaches the same decisions.
