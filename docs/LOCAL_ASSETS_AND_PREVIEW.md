# Local asset versions and esmini preview

The Streamlit workbench now imports paired XOSC/XODR scenarios into a global,
machine-local library. A SIM import retains the original archive, including its
case JSON and other embedded files, alongside the generated XOSC and paired XODR.
Each asset has a stable ID based on source and scenario names. Changed source or
paired content creates an immutable version. Reimporting identical content is
idempotent. The app loads the newest version of each asset at startup. Exported
JSON traces include the exact asset/version IDs and a content digest.
The original upload is kept in a content-addressed blob store, so multiple cases
from one SIM archive share one copy of the source archive.

Asset management starts with a searchable asset table showing the latest version
of each asset. Function, road, classification and preview filters narrow the
visible rows; sorting and the latest-version control support larger libraries.
Selecting a row opens a detail panel with overview, classification, source files
and version history. No asset is selected automatically. Changing a search,
filter, sort or version scope clears selection so a previous row index cannot
open a different asset. Classification, preview, downloads and deletion apply
to the exact selected version; history allows an
older version to be inspected. PDF requirements have their own library tab and
can return to the original document and scene.

The import workspace opens from the asset page and can be collapsed after files
are submitted. Asset imports run in a background worker independent of page
reruns. A compact task strip remains visible outside the collapsed import
workspace, refreshing once per second with the current stage, saved or reused
scenario count and classification progress. Current file, elapsed time, failures
and SIM pairing reports expand in task details. The last task summary is restored
in a new UI session. Saved assets become available before model classification
finishes. The SIM summary
shows pairable versus total cases and missing road references; skipped cases are
not reported as imported. Add the missing XODR files and reimport to include them.

Only one import/classification job can run per data directory in the service.
Stop takes effect after the current parsing or model operation returns; saved
versions remain intact. Import classification caps the model connection/read
timeout at 90 seconds and pauses after three consecutive failures. This is a
socket timeout, not a guaranteed total response deadline. Resume model
classification retries pending/failed/rule-only versions, skipping classified
and manually confirmed versions. The selected version's **Classify with model**
action explicitly requests a new review, including a previously classified or
manually confirmed version. Merely browsing or filtering the library does not
generate classification records or make model requests.
A service restart reports an interrupted job;
reimporting unchanged files reuses versions. The last task summary is stored in
`import_status.json` outside the repository. Classification edits and deletion
are disabled while an import task is active.

Data defaults to `%LOCALAPPDATA%/OpenXScenarioWorkbench` on Windows, outside
the Git repository. Set `OPENX_DATA_DIR` to use another local directory. Never
copy a private asset library into this public repository. The sidebar creates
named local projects and restores the last selected one. Saving a PDF reuse
decision writes a report under the project and pins its exact asset version.
Pinned versions cannot be deleted from Asset management.
The home page lists saved decisions for the selected project and offers their
original JSON and HTML exports, even after scene revisions or newer asset imports.

**Play simulation** starts a separate Python process that loads `esminiLib.dll`,
captures rendered frames in memory, and serves a token-protected MJPEG stream on
`127.0.0.1`. The page displays that stream inline. **Stop** terminates
the process and removes its temporary staging files. The simulation itself has a
30-second limit. Detection checks `OPENX_ESMINI_PATH`, PATH and conventional local
locations, including `%LOCALAPPDATA%/OpenXScenarioWorkbench/tools/esmini` and
`~/.openx/tools/esmini`, plus esmini folders in Downloads, Desktop, Documents and
Program Files. Versioned download folders are checked one level deep. The tool installation is separate from `OPENX_DATA_DIR`, so selecting a
different asset store does not require configuring the simulator again. Normal
playback shows tool readiness and one Play simulation action. Advanced preview
settings offer a native folder browser for the installation root or its `bin`
directory; a valid choice is saved immediately. **Detect automatically** clears
the saved override. An
invalid explicit choice is rejected rather than falling back to another engine.
The executable needs `esminiLib.dll` beside it and its normal `resources`
directory one level above `bin` for scenarios with catalog/model references.
Parse facts remain available when preview fails.

Settings display the data directory with an always-visible **Open folder** action.
The folder browser and folder-opening action operate on the computer running the
workbench; they are intended for local desktop use.

For a standalone scenario with external catalogs, models, or textures, upload a
ZIP containing the XOSC, referenced XODR, and dependency files in their original
relative directory layout. The original ZIP is versioned and checked for unsafe
paths before its contents are staged for preview. The version manifest lists each
dependency path and checksum. A changed dependency creates a
new asset version even when the XOSC and XODR are unchanged. A bare XOSC/XODR pair
is still supported when it has no additional dependencies.

Current scope: truthful global overview, separate text search and PDF workflow,
asset management with historical-version inspection, local projects, saved
version-pinned reuse decisions, JSON and readable HTML exports, and real inline
preview. A project can now keep several uploaded PDFs; the PDF workflow offers
per-document and all-scenes views. Fact edits create a numbered scene revision,
while the original PDF and its page/section evidence remain unchanged. Exports
identify the PDF document hash and scene revision. Text search displays similar
assets only. Retrieval uses a persisted global vector index with FAISS recall
when installed, followed by structural scoring. The strongest structural matches
are retained even when they fall outside the semantic recall window. A PDF decision shows its
immutable PDF evidence and parsed XOSC/XODR facts, and can request an on-demand
DeepSeek explanation with source citations. The engine's reuse verdict remains
fixed; model output is validated against the evidence IDs before display and
export. This is evidence-linked explanation, not a guarantee that every model
claim is factually correct.
