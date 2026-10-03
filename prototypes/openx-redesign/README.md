# OpenX interaction redesign

Local review build with Untitled UI MIT components and the approved engineering
palette. Vendor source/license is in `vendor/untitled`. Official source:
https://github.com/untitleduico/react

## Start

From the OpenX repository, run the repository virtual environment's Python with
`prototypes/openx-redesign/server.py 3130`. It serves only on 127.0.0.1.
Open `http://127.0.0.1:3130/`.

To rebuild, install dependencies in this folder and run `vite build`, or run Node
with `node_modules/vite/bin/vite.js build`. The local dependency runtime's Node
executable may be needed when Node is not on PATH.

## Connected content and interactions

- Read actual projects, documents, scene revisions and latest immutable assets.
- Render actual PDF pages, automatically locating stored evidence blocks.
- Read actual saved classification and cached version-specific esmini frames.
- Invoke the existing offline retrieval/structural comparison. This review build
  uses the local hashing encoder; it does not claim model-backed semantic parity.
- Temporary fact edits can be applied to a copied package for retrieval. No source
  PDF, scene revision, classification or project decision is changed.
- Queue filtering/switching, stage switching, theme menus, source/frame readers,
  asset filtering/selection, CSV export and edit dialogs are interactive.

## Boundary

This is a review prototype, not the production frontend migration. Facts and
review markers are session-only. Imports, playback and persistent decisions still
belong to the original workbench. There are no invented similarity values,
simulation images, accounts or completed reuse conclusions.

All document-derived files, images and browser evidence remain machine-local
outside this source directory in ignored local review folders. Do not add them to version control.
