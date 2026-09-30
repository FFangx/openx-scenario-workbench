# OpenX Scenario Workbench — UI direction

## Approved target

The approved visual target is a local-only design reference at
`.impeccable/mocks/comp-a.png`. Mockups and browser review artifacts are excluded
from Git; the composition and behavior are specified below.

## Product composition

- Left: PDF evidence, extracted scenes, selected source pages, and structured requirements.
- Center: paired XOSC/XODR asset catalog, retrieval controls, and ranked candidates.
- Right: reuse verdict, matched evidence, blocking differences, required edits, and trace export.
- A functional road-centerline trace connects the selected evidence, asset, and verdict.

## Visual language

- Systems-engineering traceability matrix and automotive safety-case workstation.
- Matte cool-white workspace, graphite text, slate structural rules, deep navy navigation.
- Safety cyan marks the active selection; amber is reserved for warnings; green is reserved for verified matches.
- Compact humanist sans typography, sentence case, precise alignment, restrained shadows, 6px panel radii.
- Dense but legible desktop-first information layout. Avoid generic SaaS cards, decorative charts, gradients, glass effects, and icon-heavy navigation.

## Functional fidelity

Every prominent visual region must be backed by a real application capability. The UI must expose PDF extraction, structured scene requirements, catalog construction and pairing health, semantic and structured retrieval, XODR road compatibility, reuse decision evidence, and exportable trace data. Disabled or unavailable optional capabilities must be labeled honestly rather than simulated.

The approved composition is a layout and interaction target, not a license to fabricate content. PDF thumbnails must come from the uploaded document. Asset previews must come from the selected XOSC/XODR pair through the available esmini integration or a deterministic schematic derived from parsed scene and road data. When rendering is unavailable, show a compact capability state such as `Parsed · preview unavailable`; never substitute a photorealistic mock image.

## Responsive behavior

The three-column desktop composition collapses into the same evidence-to-decision order on narrower screens. Tables may scroll horizontally, but primary decisions and controls must remain readable and keyboard accessible.

## Navigation and workspace controls (2026-09-28)

The desktop shell now uses a deep-navy sidebar with full-row icon/text navigation,
a clear active state, project selection and a compact new-project popover. The
light workspace header groups project context, real file/history popovers, help,
settings and a small language toggle. Language and esmini path persist locally.
The mobile sidebar can collapse and reopen; the toolbar wraps into a compact
context row and control row. Preserve native buttons, focus and accessible labels.
Help/settings and source inspection are functional. Account is represented by
local workspace status; no sign-in UI is exposed. Source inspection is read-only,
with downloads of the exact stored XOSC/XODR version, not a graphical editor.

## Icons and appearance (2026-09-28)

User preference: visible, consistent icons. Use Material Symbols with text labels
for navigation and workspace actions, including compact screens. The header's
Appearance menu offers Light, Dark and System; default is System. Preference is
saved locally. CSS color-scheme and light-dark() respond to system changes without
polling. Engineering content uses coordinated surface/text/status colors in both
modes. Preserve original colors in PDF imagery and genuine esmini frames.

## Asset management (2026-09-30)

Asset management is an operation surface: the asset list is the primary workspace.
Keep search, filters, sort and version scope together above a compact table. Show
the latest version of each asset by default. Selection opens details on demand;
an unselected library must still expose import and navigation without presenting
an arbitrary asset as selected. Group overview, classification, stored source
files and version history in detail tabs, with actions scoped to the selected
immutable version. Keep the PDF requirements library in a separate tab.

Import is contextual and collapsible. Its background task keeps a compact status
strip outside the import workspace, so closing import does not hide task progress
or stopping controls. Expand pairing reports and error details when requested.
Preserve the established typography, coordinated appearance modes and native
accessible controls. Avoid adding decorative cards or repeating full asset
details under every list row.
