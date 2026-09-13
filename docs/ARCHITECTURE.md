# Architecture

## One inspection, two entry points

`workflow.inspect_pair` validates filenames and empty inputs, then calls `parser.parse_bundle`. Both the CLI and Streamlit UI use this workflow. XML documents must have the expected OpenSCENARIO or OpenDRIVE root element.

`parser.py` extracts selected XML elements into the dataclasses in `models.py`. The resulting `ParseBundle` has a scenario, a road summary, and warning codes. `to_dict()` produces the JSON representation used by both interfaces.

| Module | Responsibility |
| --- | --- |
| `parser.py` | XML extraction and cross-file road-name check |
| `models.py` | Entities, actions, triggers, positions, road summary |
| `catalog.py` | Pair XOSC files with referenced XODR files into OpenX assets |
| `retrieval.py` | Local vector retrieval with scenario and road reranking |
| `scene_package.py` | Stable PDF-to-retrieval contract with source evidence |
| `pdf_pipeline.py` | Page-aware PDF text extraction and scene-section packaging |
| `reuse.py` | Grounded scenario and road differences for each candidate |
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
- A position preserves selected position-element attributes as strings.
- Road counts describe XML elements. In particular, lane_count includes center lanes and repeated lane IDs across lane sections; it is not a count of unique drivable lanes.
- Road retrieval also uses total declared road length, lane types, plan-view geometry types, junctions, signals, and static objects.

## Asset retrieval flow

`catalog.build_catalog` resolves each OpenSCENARIO `LogicFile` reference against the uploaded or discovered OpenDRIVE files. `OpenXIndex` embeds a compact text representation, then combines vector similarity with explicit scenario-structure and road-fit scores. Results retain the XOSC/XODR pair and explain which structures matched.

The encoder boundary has two implementations: deterministic hashing for a zero-model offline demo, and `BAAI/bge-small-zh-v1.5` through SentenceTransformers for semantic retrieval. Corpus encoding is batched. Index files store normalized vectors, the encoder identity, and ordered asset IDs; loading fails when the encoder or catalog differs.

PDF scene sections are converted to a `ScenePackage` that retains filename, section ID, page range, and source text. Its canonical entity, action, trigger, road, and parameter fields form a `RetrievalQuery`. The index combines text-vector retrieval with those explicit constraints, and each candidate reports missing scene or road features as grounded reuse differences.

The current PDF path is deliberately compact: PyMuPDF extracts page text, numbered headings define traceable sections, and deterministic bilingual signals identify candidate scenes. OCR, tables, and document-specific classification remain later quality work. The public implementation shares the generic ScenePackage contract with ScenarioManager, but contains no private documents, `.sim` adapters, customer configuration, or internal evaluation data.

The road-reference check compares the referenced basename with the supplied filename, case-insensitively. It does not verify road IDs, geometry, or whether the scene can execute.

## Current limits

This is a structure inspector for selected XML constructs, not an ASAM conformance validator or simulator. Unsupported details may not appear in the summary:

- Parameter expressions are not resolved. A nonnumeric speed expression currently produces a null target value.
- Catalog references are identified but not expanded.
- Event hierarchy, trigger thresholds and entity references, action units, and source-element paths are not fully represented.
- Geometry, road coordinates, physical feasibility, and scenario behavior are not simulated or validated.
- OpenSCENARIO DSL is outside the current parser's scope.

These limits determine the next parser improvements in the [roadmap](../DEVELOPMENT_PLAN.md).

## Data flow and dependencies

Uploaded files are read in memory by the local app. The parser makes no network requests. Public-demo mode downloads a fixed OpenSCENARIO/OpenDRIVE pair from GitHub and caches it through Streamlit. The optional download script also saves the upstream license.

No API key or inference service is required. Lightweight retrieval has no model download. BGE semantic retrieval is an optional local dependency and downloads the model on first use.
