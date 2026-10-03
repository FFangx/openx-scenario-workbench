---
name: OpenX Scenario Workbench
description: A traceable engineering workspace for reviewing requirements and scenario reuse.
colors:
  page: "light-dark(#edf1f5,#101922)"
  surface: "light-dark(#fff,#182430)"
  surface-soft: "light-dark(#f4f7fa,#202f3d)"
  line: "light-dark(#d8e1e9,#405669)"
  ink: "light-dark(#10243a,#e4edf5)"
  muted: "light-dark(#526b7e,#a7bbcd)"
  accent: "light-dark(#0876d9,#238de5)"
  selection: "light-dark(#e8f2fd,#203c53)"
  selection-ink: "light-dark(#134e83,#e4edf5)"
  selection-border: "light-dark(#86b7e4,#80c5ff)"
  control: "light-dark(#ffffff,#223240)"
  control-border: "light-dark(#cbd8e2,#486071)"
  header: "#142e46"
  header-ink: "#f2f7fc"
  nav: "light-dark(#e8eef4,#143149)"
  nav-ink: "light-dark(#24384a,#e8f0f6)"
  verified: "light-dark(#128044,#7bd5a0)"
  warning: "light-dark(#a36d00,#f0cc78)"
  blocking: "light-dark(#bd3e35,#ffaaa3)"
typography:
  title:
    fontSize: "20px"
    fontWeight: 650
    lineHeight: 1.45
  title-compact:
    fontSize: "19px"
  section:
    fontSize: "18px"
  body:
    fontFamily: '"Segoe UI Variable Text", "Segoe UI", "Noto Sans SC", sans-serif'
    fontSize: "13px"
  input:
    fontSize: "14px"
  navigation:
    fontSize: "13px"
    fontWeight: 500
  queue-title:
    fontSize: "14px"
  difference:
    fontSize: "13px"
    lineHeight: 1.6
rounded:
  control: "4px"
  inset: "4px"
  navigation: "0px"
  panel: "6px"
spacing:
  tight: "6px"
  small: "8px"
  control: "12px"
  inset: "14px"
  workspace-gap: "14px"
  panel: "12px"
components:
  button-primary:
    backgroundColor: "{colors.accent}"
    textColor: "#fff"
    rounded: "{rounded.control}"
  input:
    backgroundColor: "{colors.control}"
    textColor: "{colors.ink}"
    typography: "{typography.input}"
    rounded: "{rounded.control}"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.ink}"
    rounded: "{rounded.panel}"
    padding: "12px"
  panel-compact:
    padding: "14px"
  evidence:
    backgroundColor: "{colors.surface-soft}"
    rounded: "{rounded.inset}"
    padding: "14px"
  queue-row:
    backgroundColor: "{colors.surface-soft}"
    rounded: "{rounded.inset}"
    padding: "12px"
  queue-row-selected:
    backgroundColor: "{colors.selection}"
    textColor: "{colors.selection-ink}"
  navigation:
    textColor: "{colors.nav-ink}"
    typography: "{typography.navigation}"
    rounded: "{rounded.navigation}"
    padding: "10px 14px"
---

# Design System: OpenX Scenario Workbench

## Overview

### Current design instructions (2026-10-03)

Use `ui-ux-pro-max` and `frontend-design` for UI design guidance, as explicitly
authorized by the user on 2026-10-03. Other UI design skills remain disabled; do
not reintroduce their workflows or delegate UI work to Astra. The approved local reference `.impeccable/mocks/comp-a.png` is the visual
authority, with the chosen requirement queue plus current-task interaction.
Restore its detailed engineering-tool character and useful information density.
Do not simplify it into oversized empty cards or a generic AI dashboard. Check
corner clipping, alignment, Chinese text wrapping, readable metadata, and native
control states in the rendered application. Ask the user about ambiguous choices
that change the design direction; handle routine implementation details directly.
Scene imagery must be a real esmini frame of the selected immutable version.
The user approved the concrete top-navigation example at
`.impeccable/openx-topnav-example/`. Global navigation belongs below the navy
brand/utility header; reserve the left column for the requirement queue.
Show saved facts in compact tables first and disclose the editor on request.
Use the full available workspace width, including wide monitors; the old 1440px
centered workspace cap is retired. Enter an existing document at its first
requirement when no requirement is selected. Empty documents and filters retain
an explicit empty state; do not fabricate task data to fill the page.

**Creative North Star: "The engineering traceability workstation"**

OpenX uses precise cool surfaces, graphite text, navy workspace context and blue selection to connect source evidence with an inspectable reuse decision. Dense comparison belongs in aligned tables; task actions stay with the requirement or immutable asset version they affect. Material Symbols accompany labeled workspace actions.

This is a source-grounded merge of the incumbent direction, approved through `.impeccable/production-workflow-brief.md` on 2026-10-03. The user retained the visual language of the local `.impeccable/mocks/comp-a.png` reference and chose the requirement queue plus current-task interaction. That approval supersedes the original fixed evidence/catalog/verdict three-column composition, decorative connecting road trace, cyan-selection wording and schematic-preview allowance. The reference remains local and does not supply fabricated scene images, values or an account system.

**Key Characteristics:**
- Cool engineering surfaces with a navy context header and blue selection.
- Dense comparison with source evidence and exact-version provenance close at hand.
- Native, labeled controls and coordinated light, dark and system appearance.
- Real PDF imagery and esmini frames; explicit unavailable and unresolved states.

This record derives from `app.py`, `shell.css`, `appearance.py`, `workflow.css` and `preview_frames.py`; later production overrides take precedence over earlier base styles. It records implementation, not a claim of browser or accessibility acceptance. `PRODUCT.md` supplies durable traceability and engineering-honesty principles; its older capability exclusions are not used to deny implemented playback or PDF extraction paths.

## Colors

The primary language is blue over cool neutral surfaces, with a fixed navy workspace header. Frontmatter retains the source's `light-dark()` color pairs rather than converting them into a second palette. Sidecar tonal strips are generated reference swatches from the light-mode colors; they are not additional shipped application colors.

### Primary
- **Selection blue:** primary actions, task underline, focus and active choice. The selected queue row uses the softer selection surface, matching border and dark/light selection ink.

### Secondary
- **Verified green:** supported matches and successful operations.
- **Review amber:** unresolved review and required adjustments.
- **Blocking red:** blocking or rebuild outcomes. Status words and evidence carry the meaning alongside color.

### Neutral
- **Cool workspace:** page, panel and inset surfaces create quiet hierarchy.
- **Graphite ink:** main text; muted ink supports source metadata without reducing opacity.
- **Navy context:** the workspace header stays navy in both modes. Global navigation uses the workspace surface and an active blue underline.
- **Structural rules:** thin boundaries define panels, controls and aligned comparisons.

**The Evidence Color Rule.** Appearance changes recolor interface chrome, never the original PDF page or real simulation image.

## Typography

**Body Font:** Segoe UI Variable Text, Segoe UI, Noto Sans SC, sans-serif. This is the incumbent application text stack, not a new display-face recommendation. No separate expressive display family is established.

**Character:** Compact, sentence-case engineering text with strong alignment and tabular numbers. Keep English and Chinese labels complete; filenames and diagnostics retain their original content.

### Hierarchy
- **Current-task title:** the title token leads the selected requirement; the compact title applies at the narrow workflow breakpoint.
- **Section:** queue and inspection headings are subordinate to the requirement title.
- **Body / differences:** readable task copy and paired required/candidate facts.
- **Inputs:** the current-task editor uses the input token; labels include units.
- **Navigation / queue title:** clearly labeled destinations and requirement names.

**The Legibility Rule.** Preserve useful density through alignment and disclosure, not by inheriting the legacy small-type scale. Existing 8.5–12px badges, captions, header utilities and base selectors are implementation debt, not normative type roles for new surfaces. The title token describes a current-task heading, not a system-display treatment.

## Layout

The PDF workspace has a bounded, searchable queue accompanying one current requirement with three numbered task stages: review, candidates/preview, assessment. At widths above 1050px the production queue/task grid uses `282px minmax(0,1fr)` with a 14px gap. The queue uses available viewport height, clamped between 240px and 600px. Between 651px and 1050px the queue remains 250px wide; mobile stacks the task below it. Global navigation is horizontal; there is no persistent sidebar.

Source pages and saved fact tables sit together at wide desktop widths in a 1.12:1 ratio. Render the original PDF at twice its native resolution, fitted to reader width inside a scrollable viewport clamped between 240px and 510px according to window height; never shrink the whole page into a tiny centered thumbnail. A labeled Enlarge page action opens that same source page in a larger reader. Copyable evidence text is a disclosure when stored text exists. The editor, structure and publication controls sit below the fact sheet in an independently scrolling facts region; mobile lets that region grow naturally. The review action strip stays near the viewport bottom while scrolling the requirement. The source/facts region stacks between 651px and 1050px, with a 430px reader; mobile uses a 390px reader. The theme-aware candidate selection table uses the full available task width with a 280px maximum height, followed by selected-asset facts/frame and a Required/Candidate/Status comparison table. Native sorting, search and CSV tools remain available in a separate disclosure. Search controls keep compact fixed widths while the query field grows. Narrow screens stack content, and comparison tables may scroll horizontally rather than conceal columns. Never apply color inversion to a dataframe canvas: that also alters actual simulation thumbnails.

Task panels use 12px padding and 14px at 650px and below. The desktop brand/utility header is at least 54px high, with 44px navigation controls beneath. Navigation condenses at 1000px; at 650px it wraps into four destinations followed by project controls, and header utilities wrap beneath the brand.

Asset management preserves its list-first operation surface. Search, filters, sort and version scope accompany a compact table; latest versions are the default. Selection reveals detail tabs for overview, classification, source files and history. The PDF requirement library stays a separate tab. Import and technical records are disclosures, with ongoing import progress and stopping controls still visible outside the closed import region.

## Elevation & Depth

The current task and queue panels are flat: their source explicitly sets no shadow. Surface tone, thin rules and blue selection establish hierarchy. The base style still declares a minimal ambient shadow token; it is not a prescription to add shadows to these panels. No glass, gradient or hard-offset-shadow language is established.

**The Flat Workspace Rule.** Use surface contrast and borders for task grouping; do not add decorative elevation to the production queue and task panels.

## Shapes

Use 6px task-panel corners, 4px fact-table and queue-row corners, and compact control corners from the frontmatter. Disclosures have one clipped background owner: the outer details container holds the rounded boundary and overflow; its summary is square inside it. Avoid nested outlines that create duplicate rounded borders.

## Components

### Buttons and fields

Native controls retain keyboard behavior and accessible labels. Primary actions use the accent and white text; secondary controls use coordinated control/ink/border colors. Buttons have an explicit two-pixel accent focus outline with a two-pixel offset. Disabled actions use muted text and subdued surfaces without dropping opacity. Header focus uses a lighter blue against navy. Material Symbols remain outline/rounded font icons in the application; do not apply a global SVG fill override.

Fact editing uses labeled fields and units. Narrative text does not silently set numeric parameters. Advanced JSON remains an explicit override. Saving facts creates a revision; confirmation publishes that exact project/document/scene/revision. Original PDFs and stored XOSC/XODR files are read-only, with exact-version downloads. Save edits before navigating away; this is workflow guidance, not a claim of a global unsaved-change guard.

### Queue and task navigation

Queue rows show a requirement title, source page, revision and revision-specific state: To review, Confirmed or Assessment saved. A selected row has a soft blue surface and boundary. The searchable native selector and row selection target the same requirement. Switching requirements returns to review and clears prior retrieval results.

Three labeled task choices use an accent underline for the active stage. Candidate row selection is synchronized with a by-name selector disclosed beneath the table. Candidate choice persists between task stages and repeated selection of the same requirement.

### Evidence and comparison

The evidence inset presents the original source page and selectable/readable evidence text beside editable facts. The candidate table has tabular numeric alignment, single-row selection and real cached-frame thumbnails where available. No frame is invented for an asset without cached output. Similarity and relative change cost remain distinguished; cost is not working hours.

Difference rows pair Required and Candidate values with explicit Unverified, Blocking or Change needed states. They expose checked facts without claiming that an empty difference list proves complete compatibility. Technical extraction records, raw diagnostics and engine metadata remain inspectable through disclosures or downloads.

### Real simulation

Capture frame and playback are explicit actions. Playback is bound to the selected asset/version and exposes stopped, failed and unavailable states. The persisted frame identity includes asset ID, version ID and content digest; the still caption names simulation time and asset version. Capture and playback use esmini output, and image colors remain untouched. Simulation renderability is distinct from reuse suitability or standards compliance.

### Assessment and continuity

Unresolved review uses warning treatment and actionable guidance, without a success checkmark. Saving an eligible decision pins its candidate version and source revision; unresolved review disables that save action while retaining assessment snapshot export. After saving the current revision, Review next requirement advances through the filtered queue when another item exists. Saved reports can reopen the latest source revision while preserving their original snapshot.

### Workspace controls

The overview uses a divided metrics band and two adjacent preview coverage indicators. Progress tracks follow the control-border color in every appearance mode. Recent imports use a theme-aware HTML table with client-side column sorting, search and fullscreen reading, plus a CSV export of the displayed recent-import dataset. Long original asset names remain accessible through cell tooltips. Status text accompanies the small colored marker. This replaces the fixed-light native dataframe on the overview; remaining native dataframe surfaces still require theme integration.

Project selection, creation, history, file inspection, help and settings remain real controls. Language, appearance and esmini location persist locally. Appearance offers Light, Dark and System; System follows CSS color-scheme without polling. Local workspace status does not imply an account or mandatory sign-in. Data/install paths have explicit Open folder actions; setup discovers common installations and permits native folder selection.

## Do's and Don'ts

### User acceptance constraints (2026-10-03)

The user's rejection of generic generated dashboards applies to the whole
workspace, including expanded menus and secondary pages. The approved reference
still determines the palette and workflow; avoiding generic styling does not
authorize an unrelated color scheme, radical minimalism or decorative animation.

- Containers must express a real task, independent scrolling region or editable
  control. Use headings, alignment, spacing and row dividers for ordinary content
  grouping; do not wrap every heading, status, row and disclosure in another card.
- Queue items form one continuous list. Distinguish the selected item clearly;
  avoid making every unselected item look like a standalone action card.
- Tables, menus, inputs and disclosures across all destinations share semantic
  surface, border, type and focus tokens. An isolated polished table does not
  establish consistency for the rest of the product.
- On-screen copy explains the user's task, result or next action. Keep framework
  names, implementation explanations, design rationale and development caveats
  in project documentation or explicitly requested diagnostics.
- Preserve useful engineering detail through aligned data and progressive
  disclosure. Do not substitute either oversized empty cards or tiny dense text
  for readable information hierarchy.
- Accept changes only after reviewing whole rendered pages at desktop and narrow
  widths, plus both themes and affected open-menu states. Check corner clipping,
  text truncation, competing outlines and the balance of controls versus content.
  A successful local component change is not whole-page visual acceptance.

### Do:
- **Do** preserve the engineering palette, native labeled controls and coordinated appearance modes.
- **Do** keep source evidence, factual differences and exact-version provenance inspectable.
- **Do** use real PDF pages and esmini output, with honest unavailable and failure states.
- **Do** keep dense comparisons tabular and secondary technical records in disclosures.
- **Do** scope confirmation, saved state and continuation to the current source revision.

### Don't:
- **Don't** replace the approved queue/current-task workflow with the retired fixed three-column composition.
- **Don't** substitute invented road/car artwork or deterministic schematics for real simulation frames in this workflow.
- **Don't** treat a rendered frame, similarity score or empty checked-differences list as a reuse or standards certificate.
- **Don't** add mandatory accounts, decorative charts, glass, gradients or generic nested cards.
- **Don't** promote legacy undersized text, glyph-based legacy badges or unresolved styling defects into reusable design rules.
