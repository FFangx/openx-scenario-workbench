# Reuse benchmark

An authored library and requirement set for evaluating OpenX reuse retrieval and
verdicts. Results and method: [docs/EVALUATION.md](../../docs/EVALUATION.md).

- `benchmark.json`: the single source. 26 asset specifications (ego, participants,
  lanes, speeds, story events, environment) and 38 typed requirements in Chinese and
  English with their expected candidates and verdicts.
- `assets/*.xosc`, `roads/*.xodr`: rendered from `benchmark.json` by
  `python scripts/build_reuse_benchmark.py`. Do not edit them by hand; change the
  specification and re-render.
- `suggestions.json`: the reuse suggestions of one real model run on the 38
  requirements (model, thinking effort and date inside), which `openx-demo` replays and
  marks as recorded so the assessment table is filled without a model. They are model
  output, not labels. After changing the benchmark, remake them with
  `openx-demo --record-suggestions` (calls the model of your normal settings).

Everything here was written for this repository and is licensed under MIT. The files
are parser and matching inputs, not certified executable scenarios. Load them in the
workbench with `openx-demo` (or `python scripts/seed_demo_workspace.py <empty-folder>
--dataset benchmark`).
