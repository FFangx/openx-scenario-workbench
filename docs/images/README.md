# Documentation images

`workbench.jpg` / `workbench-en.jpg` and `assets.jpg` / `assets-en.jpg` are Chinese
and English screenshots of the React workbench, refreshed on 2026-10-07 at
1586×992.

They were captured against the fixtures demo workspace (`scripts/seed_demo_workspace.py`:
authored assets, authored PDFs and reviewed typed requirements), without an XSD
registry. The workbench shot shows manual search with a "modify and reuse" candidate
whose standard checks are still open. For the asset shot the public esmini cut-in
example (MPL-2.0) was imported under **Asset management** and played once: a real
frame rendered by esmini, with the road drawn from above. No private assets, user
project data or credentials appear.

To refresh: start `openx-web` on a freshly seeded folder (`OPENX_DATA_DIR`), import
the public example under **Asset management**, play it, and capture both languages
through the normal interface. Keep evidence and check states visible; never relabel a
pending check as a successful reuse or preview.

`demo-en.gif` / `demo-zh.gif` open the authored
[reuse benchmark](../../examples/reuse-benchmark/) in the running workbench: first the
clause reuse assessment with the recorded model suggestions the demo replays, then
manual search through four requirements: two direct structural matches (shown as
undetermined, since no XSD registry was installed for the recording), one needing
parameter changes and one with no reusable asset. Regenerate them with `node scripts/demo-gif.mjs en|zh` in `web/`
after `npm run build`; the script seeds its own throwaway workspace.

`architecture-overview.svg` is the editable architecture illustration. It includes
BGE-M3 recall, structural comparison, the XSD confirmation gate and all four
assessment outcomes.
