# Architecture

## One inspection, two entry points

`workflow.inspect_pair` validates filenames and empty inputs, then calls `parser.parse_bundle`. Both the CLI and Streamlit UI use this workflow. XML documents must have the expected OpenSCENARIO or OpenDRIVE root element.

`parser.py` extracts selected XML elements into the dataclasses in `models.py`. The resulting `ParseBundle` has a scenario, a road summary, and warning codes. `to_dict()` produces the JSON representation used by both interfaces.

| Module | Responsibility |
| --- | --- |
| `parser.py` | XML extraction and cross-file road-name check |
| `models.py` | Entities, actions, triggers, positions, road summary |
| `workflow.py` | Shared input validation and inspection |
| `demo.py` | Fetch the pinned public example; no model dependency |
| `i18n.py` | Chinese and English UI/warning labels |
| `app.py` | Views, session state, JSON download |
| `cli.py` | JSON on stdout, diagnostics on stderr |

## What the fields mean

- An entity identifies a ScenarioObject and its declared category or catalog name.
- An action records a recognized action kind, assigned actor when available, and an absolute speed target when directly numeric.
- A trigger records start/stop scope, condition name/type, delay, and edge.
- A position preserves selected position-element attributes as strings.
- Road counts describe XML elements. In particular, lane_count includes center lanes and repeated lane IDs across lane sections; it is not a count of unique drivable lanes.

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

No LLM, embedding model, API key, or external inference service is required.
