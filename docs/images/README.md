# Documentation images

`workbench.jpg` / `workbench-en.jpg` and `assets.jpg` / `assets-en.jpg` are Chinese
and English screenshots of the React workbench, refreshed on 2026-10-04 at
1586×992.

They were captured against an isolated data folder created with
`scripts/seed_demo_workspace.py` (authored assets, authored PDFs and reviewed
typed requirements), with the pinned XSD registry installed and the public esmini
cut-in example (MPL-2.0) imported and played once. The workbench shot shows a
"modify and reuse" candidate whose standard check is still pending, because the
authored parser fixtures are not XSD-valid. The asset shot shows a real frame
rendered by esmini. No private assets, user project data or credentials appear.

To refresh: seed a new folder, run `openx-validate --install-schemas` and
`openx-web` with `OPENX_DATA_DIR` pointing at it, import the public example under
**Asset management**, and capture both languages through the normal interface.
Keep evidence and check states visible; never relabel a pending check as a
successful reuse or preview.

`architecture-overview.svg` is the editable architecture illustration. It includes
BGE-M3 recall, structural comparison, the XSD confirmation gate and all four
assessment outcomes.
