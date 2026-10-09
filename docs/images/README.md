# Documentation images

`workbench.jpg` / `workbench-en.jpg` and `assets.jpg` / `assets-en.jpg` are Chinese
and English screenshots of the React workbench at 1586×992, refreshed on 2026-10-07;
`workbench-en.jpg` and `demo-en.gif` again on 2026-10-09, when the model's reasons
began to follow the interface language.

The workbench shot is the clause reuse assessment of the benchmark demo workspace
(`scripts/seed_demo_workspace.py <folder> --dataset benchmark --language zh|en`: authored
assets, authored PDFs, reviewed typed requirements and the model suggestions recorded in
that language, which it replays), after
**Make previews** in asset management and adopting the first three clauses: the
preferred asset shows a real esmini frame and its road from above. The asset shot uses
the fixtures demo workspace with the public esmini cut-in example (MPL-2.0) imported
under **Asset management** and played once. No XSD registry was installed. No private
assets, user project data or credentials appear.

To refresh: start `openx-web` on a freshly seeded folder (`OPENX_DATA_DIR`), make the
previews (and import and play the public example for the asset shot), and capture both
languages through the normal interface. Keep evidence and check states visible; never relabel a
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
