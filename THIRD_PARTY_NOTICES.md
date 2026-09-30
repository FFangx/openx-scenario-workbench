# Third-party notices

The web application's optional public-demo loader and the download script retrieve example files from the [esmini repository](https://github.com/esmini/esmini). esmini is distributed under the Mozilla Public License 2.0. Downloads are pinned to upstream commit `4b8fbafb1a8abd13f3d57b97e4a1b7e68cd93418` for reproducibility. The script stores the upstream `LICENSE` file next to the downloaded examples.

No esmini example is included in this repository by default. Users are responsible for checking the applicable upstream license and notices when redistributing downloaded files.

The screenshot in `docs/images/workbench-en.png` shows this application's inspection of the pinned esmini cut-in example. Scenario values shown there originate from esmini; it is an application screenshot, not a simulator rendering.

The files in `tests/fixtures/` are small, locally authored parser fixtures distributed with the project under MIT. They are not copied from esmini and are not intended as simulator-ready scenarios.

## Related project: ScenarioManager PDF core

`src/openx_workbench/pdf_v2/` adapts the PDF core from the author's related
[ScenarioManager project](https://github.com/FFangx/ScenarioManager), using the
local V2 development revision. It includes native block parsing, heading and
chapter decoding, scene-first schemas and prompts, shared clauses, and review
validation. The source module hashes are recorded in `pdf_v2/upstream.json`;
adaptation scope and limitations are described in `docs/PDF_MIGRATION.md`.

The adaptation contains generic source algorithms only. ScenarioManager assets,
private L2 scenarios, PDFs, evaluation datasets, extracted document content,
model responses and machine configuration are not included.
