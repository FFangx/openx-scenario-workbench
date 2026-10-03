# OpenX redesign / design review build

Use frontend-design and UI UX Pro Max. The user's existing comp-a reference and
queue/current-task workflow override suggested marketing heroes or motion-heavy
layouts. The refined database query supports a dense workstation; preserve the
existing blue engineering palette instead of introducing another style.

Palette: navy #142e46 header; dark #111a23 page, #18242f work surface,
#273849 control boundary, #e5edf5 text, #75baff link accent, #0876d9 primary action.
Light: #edf1f5 page, #ffffff surface, #cbd8e2 boundary, #172b3c text,
#0876d9 action. Secondary text must remain readable in both themes.
Typography: Segoe UI / Noto Sans SC, 14px data, 13px metadata, 22px task heading.
No new display typeface, decorative gradients, dashboard hero or invented scores.

Layout:
```
navy brand + project / local state / appearance
horizontal global destinations                         original workbench link
document + continuous queue | task title + stage navigation
                            | original PDF      | fact sheet
                            |                   | participants
                            | compact task footer
```
The queue is a continuous list with separators; selected item has one blue rail.
The task is a flat work surface. Sections use headings and dividers, not repeated
boxed cards. UI components are sourced from Untitled UI's MIT repository, with
product palette and density overrides. Preserve vendor license locally.

Scope: clickable review prototype reads actual local requirements, asset
classification and cached esmini frames. Local session edits are not persisted to
the source stores. Missing frames and unresolved assessment remain explicit.
Full functional migration is a separate step; original Streamlit remains running.

Acceptance: inspect desktop, narrow desktop and 390px; both themes; open menus;
queue switching/filter empty state; edit dialog cancel/apply; source reader;
asset selection and absence of frames. Inspect whole screens after each fix.

Review checkpoint: visual similarity to comp-a was assessed as 4/10 in dark mode and about 5/10 in light mode. This is not an accepted target-image restoration.
