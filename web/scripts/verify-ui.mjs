// UI checks against the self-authored demo workspace (see demo-server.mjs); safe to run anywhere, including CI.
// Usage: npm run build && node scripts/verify-ui.mjs
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { startDemo } from "./demo-server.mjs";
import { startFakeModel } from "./fake-model.mjs";

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const OUT = path.join(WEB, ".verify-out", "ui");
fs.mkdirSync(OUT, { recursive: true });

const demo = await startDemo();
const BASE = demo.base;
const b = await chromium.launch();
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);

try {
  const ctx = await b.newContext({ viewport: { width: 1586, height: 992 }, acceptDownloads: true });
  const p = await ctx.newPage();
  const errors = [];
  p.on("pageerror", (e) => errors.push(e.message));
  p.on("console", (m) => m.type() === "error" && !m.text().startsWith("Failed to load resource") && errors.push(m.text()));
  // Expected refusals (400) are shown in the UI; anything else failing to load is an error.
  p.on("response", (r) => r.status() >= 400 && r.status() !== 400 && errors.push(`${r.status()} ${new URL(r.url()).pathname}`));
  const rows = () => p.locator(".cand-table tbody tr.ant-table-row");
  const bindRows = () => p.locator(".bind-table tbody tr.ant-table-row");
  const counts = () => p.locator(".bind-list .bind-counts");
  const tool = (label) => p.locator(".bind-toolbar .ant-btn").filter({ hasText: label });
  const idle = async () => { await p.waitForFunction(() => !document.querySelector(".cand-table .ant-spin-spinning"), null, { timeout: 120000 }); await p.waitForTimeout(150); };
  const total = () => p.locator(".cand-head .n").innerText();
  const closeModal = async () => {
    await p.locator(".ant-modal-wrap:visible .ant-modal-close").first().click();
    await p.locator(".ant-modal-wrap:visible").first().waitFor({ state: "hidden" });
  };
  const project = demo.seed.project_id;
  const allDocs = async () => (await p.request.get(`${BASE}/api/projects/${project}/documents`)).json();
  const view = async () => {
    const docs = await allDocs();
    return (await p.request.get(`${BASE}/api/projects/${project}/bindings?${docs.map((d) => `document_ids=${d.document_id}`).join("&")}`)).json();
  };
  /** Back to the binding table from finding by hand. */
  const backToTable = async () => {
    await p.locator(".manual-bar .ant-btn").click();
    await bindRows().first().waitFor();
  };
  /** Find an asset by hand for the clause in this row of the binding table. */
  const byHand = async (row) => {
    await bindRows().nth(row).click();
    await p.locator(".bind-head .ant-btn").filter({ hasText: "Search manually" }).click();
    await rows().first().waitFor({ timeout: 120000 });
    await idle();
  };

  await p.goto(BASE + "/", { waitUntil: "networkidle" });
  // the workbench opens on the start page: text search, PDF import, and the project's PDFs
  await p.locator(".start-doc").first().waitFor();
  check("the workbench opens on the start page", (await p.locator(".start-search input").count()) === 1 && (await p.locator(".start-doc").count()) === 2
    && (await p.locator(".ox-steps").count()) === 0);
  check("interface follows the saved English preference", (await p.locator(".ox-nav button.on").innerText()) === "Workbench");

  // a PDF opens on its binding table: every clause, nothing suggested or confirmed yet
  await p.locator(".start-doc").first().click();
  await bindRows().first().waitFor({ timeout: 60000 });
  check("a PDF opens on its binding table", (await bindRows().count()) === 4 && (await bindRows().filter({ hasText: "No suggestion yet" }).count()) === 4);
  check("the step track waits for the model's suggestions", (await p.locator(".ox-step.done").count()) === 1 && (await p.locator(".ox-step.on").innerText()).includes("Generate suggestions"));
  await p.locator(".bind-detail .evi .src").first().waitFor();
  check("the selected clause shows its source text", (await p.locator(".bind-detail .bind-title").innerText()).includes(await bindRows().first().locator("td").first().innerText()));

  // the model suggests assets for every clause; a person confirms
  await tool("Generate suggestions").click();
  await p.locator(".bind-list .ant-alert-error").filter({ hasText: "Configure a model" }).waitFor();
  check("suggesting without a model says what is missing", true);
  const fake = await startFakeModel();
  await p.request.put(`${BASE}/api/settings/model`, { data: { base_url: fake.url, model: "fake-judge", api_key: "test-key", thinking: false } });
  await tool("Generate suggestions").click();
  await p.locator(".bind-table .mtag.steady").first().waitFor({ timeout: 60000 });
  await p.waitForFunction(() => document.querySelectorAll(".bind-table tr.ant-table-row .mtag.direct").length === 4, null, { timeout: 60000 });
  check("the model's suggestion shows on every clause", fake.calls() === 12, `${fake.calls()} calls`);
  check("assessments that agree are consistent, the clause whose assessments disagree is marked inconsistent",
    (await bindRows().filter({ hasText: "Consistent 3/3" }).count()) === 3 && (await bindRows().filter({ hasText: "Inconsistent 2/3" }).count()) === 1);
  check("a later suggestion clears the earlier error", (await p.locator(".bind-list .ant-alert-error").count()) === 0);
  check("the step track moves on to confirming", (await p.locator(".ox-step.on").innerText()).includes("Confirm reuse"));
  await p.screenshot({ path: path.join(OUT, "binding-suggestions.png") });
  await tool("Adopt consistent").click();
  await counts().filter({ hasText: "3 / 4 confirmed" }).waitFor();
  check("adopting all suggestions leaves the inconsistent clause to a person", (await bindRows().filter({ hasText: "Inconsistent" }).count()) === 1
    && (await p.locator(".bind-table .bind-confirmed").count()) === 3);
  await bindRows().filter({ hasText: "Inconsistent" }).locator(".bind-actions .ant-btn").filter({ hasText: /^Adopt$/ }).click();
  await counts().filter({ hasText: "4 / 4 confirmed" }).waitFor();
  check("adopted conclusions keep the level and carry the confirmed mark", (await bindRows().filter({ hasText: "Direct reuse" }).count()) === 4
    && (await p.locator(".bind-table .bind-confirmed").count()) === 4 && (await bindRows().filter({ hasText: "Consistent" }).count()) === 0);
  check("the step track ends at exporting once every clause is confirmed", (await p.locator(".ox-step.on").innerText()).includes("Export assessment"));
  await bindRows().first().click();
  const editor = p.locator(".bind-detail .bind-editor");
  await editor.locator(".bind-cand.on").first().waitFor();
  check("the detail shows the bound group with the model's reasons", (await editor.locator(".bind-cand.on").count()) === 2
    && (await editor.locator(".bind-cand.on .why").first().innerText()).includes("authored reason"));
  await p.locator(".bind-preview .player").waitFor();
  check("the preferred asset can be played next to its road", (await p.locator(".bind-preview .road-drawing, .bind-preview .img-empty").count()) >= 1);
  await p.screenshot({ path: path.join(OUT, "bindings.png") });
  await editor.locator(".bind-form .ant-radio-wrapper").filter({ hasText: "Modify and reuse" }).click();
  await editor.locator("textarea").fill("Slow the target down");
  await editor.locator(".ant-btn-primary").filter({ hasText: "Update" }).click();
  await bindRows().first().filter({ hasText: "Modify and reuse" }).waitFor();
  const bound = (await view()).scenes.find((s) => s.binding?.status === "modify");
  check("a person's change is stored as their own choice", bound?.binding.source === "manual" && bound.binding.changes === "Slow the target down");
  await p.request.delete(`${BASE}/api/settings/model/key`);
  fake.stop();

  // one export of the whole table
  await p.locator(".bind-export").click();
  const csvHref = await p.locator(".ant-dropdown:visible a").first().getAttribute("href");
  const htmlHref = await p.locator(".ant-dropdown:visible a").nth(1).getAttribute("href");
  await p.keyboard.press("Escape");
  const csv = await p.request.get(BASE + csvHref);
  const csvText = (await csv.body()).toString("utf8");
  check("the table exports as CSV a spreadsheet opens", csv.ok() && csvText.startsWith("\ufeffPDF,Clause,Title,Reuse conclusion") && csvText.includes("Slow the target down")
    && csvText.split("\r\n").filter(Boolean).length === 5);
  const tableHtml = await p.request.get(BASE + htmlHref);
  check("the table exports as a web page", tableHtml.ok() && (await tableHtml.text()).includes("Clause reuse assessment"));

  // several PDFs in one table; the project files list switches back to one
  await p.locator(".bind-docs .ant-select").click();
  await p.locator(".ant-select-dropdown:visible .ant-select-item-option:not(.ant-select-item-option-selected)").first().click();
  await p.locator(".bind-list .ph").click();
  await counts().filter({ hasText: "4 / 8 confirmed" }).waitFor();
  const docNames = await bindRows().locator("td:first-child").allInnerTexts();
  check("two PDFs show in one table naming each row's PDF", docNames.length === 8 && new Set(docNames).size === 2, docNames.join(", "));
  await p.locator(".ox-steps .tools button").filter({ hasText: "Project files" }).click();
  await p.locator(".file-row").first().waitFor();
  const links = await p.locator(".file-row a[download]").count();
  check("Project files lists PDFs with downloads", (await p.locator(".file-row").count()) === 2 && links === 2, `${links} links`);
  await p.locator(".file-row button").first().click();
  await counts().filter({ hasText: "4 / 4 confirmed" }).waitFor();
  check("choosing a PDF in Project files shows its clauses only", (await bindRows().count()) === 4);
  await p.locator(".ox-steps .tools button").filter({ hasText: "Project files" }).click();
  await p.locator(".ant-popover:visible").waitFor({ state: "hidden" });

  // extraction record of the rule-extracted demo PDF
  await p.locator(".bind-docs .more").click();
  await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "Extraction record" }).click();
  await p.locator(".ant-modal:visible .ant-descriptions").waitFor();
  check("extraction record offers re-extraction for an older engine", await p.locator(".ant-modal:visible .ant-btn").filter({ hasText: "Extract scenes again" }).isVisible());
  await closeModal();

  // PDF import runs as a job; without a configured model it fails cleanly and keeps the project intact
  await p.locator(".bind-docs .more").click();
  await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "Import PDFs" }).click();
  const demoDocs = await allDocs();
  const pdfBytes = await (await p.request.get(`${BASE}/api/projects/${project}/documents/${demoDocs[0].document_id}/file`)).body();
  await p.locator(".ant-modal:visible input[type=file]").setInputFiles({ name: "authored-protocol.pdf", mimeType: "application/pdf", buffer: pdfBytes });
  await p.locator(".ant-modal:visible .ant-btn-primary").filter({ hasText: "Import PDFs" }).click();
  await p.locator(".ant-modal:visible .job .ant-alert-error").waitFor({ timeout: 60000 });
  check("PDF import without a model reports the failure", (await p.locator(".ant-modal:visible .job-head b").innerText()) === "Failed", await p.locator(".ant-modal:visible .job .ant-alert-error").innerText());
  await p.locator(".ant-modal:visible .ant-btn").filter({ hasText: "Done" }).click();
  check("a failed import adds no document", (await allDocs()).length === 2);

  // finding an asset by hand: the rule-based search of one clause
  const clause = await bindRows().nth(1).locator("td").first().innerText();
  await byHand(1);
  check("finding by hand opens the clause in the rule-based search", (await p.locator(".manual-bar").count()) === 1
    && clause.includes(await p.locator(".scene.sel .t").innerText()) && (await rows().count()) === 6, `${await rows().count()} rows`);
  check("scenes load from API", (await p.locator(".scene").count()) === 4, `${await p.locator(".scene").count()} scenes`);
  check("evidence shows source text", (await p.locator(".evi .src").count()) > 0);

  // scene -> query + new search + evidence
  const firstTop = await p.locator(".decision .big").innerText();
  await p.locator(".scene").nth(3).click();
  await idle();
  const sceneTitle = await p.locator(".scene.sel .t").innerText();
  const q = await p.locator(".search-row input").inputValue();
  check("scene click sets query to scene title", q === sceneTitle, q);
  check("scene click updates evidence", (await p.locator(".evi .x b").innerText()).includes(sceneTitle));
  check("scene click re-runs matching", (await rows().count()) === 6, `top verdict ${firstTop} → ${await p.locator(".decision .big").innerText()}`);

  // row -> right panel + preview
  await rows().nth(2).click();
  const rowTitle = await rows().nth(2).locator(".pair a").first().getAttribute("title");
  await p.waitForTimeout(150);
  check("row click updates selected item", (await p.locator(".sel-item .name").getAttribute("title")) === rowTitle, rowTitle);
  check("row click updates preview", (await p.locator(".pv-link a").first().innerText()) === (await rows().nth(2).locator(".pair .fn").first().innerText()));

  // filters through the Filters tab, then chip removal
  await p.locator(".mid-tabs .ant-tabs-tab").filter({ hasText: "Filters" }).click();
  await p.locator(".ant-form-item").filter({ hasText: "Target" }).locator(".ant-select").click();
  await p.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: /^行人$/ }).click();
  await idle();
  await p.locator(".mid-tabs .ant-tabs-tab").filter({ hasText: "Search" }).click();
  check("filter adds a chip and narrows results", (await p.locator(".chip:not(.scene-chip)").count()) === 1 && (await total()).startsWith("1 "), await total());
  await p.locator(".chip:not(.scene-chip) .ant-tag-close-icon").click();
  await idle();
  check("removing the chip restores all assets", (await total()).startsWith("6 "), await total());

  // Show dropdown filters client side
  await p.locator(".cand-head .ant-select").click();
  await p.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: "Not reusable" }).click();
  await p.waitForTimeout(150);
  const tags = await p.locator(".cand-table tbody .mtag").allInnerTexts();
  check("Show filter keeps only that verdict", tags.length > 0 && tags.every((t) => t === "Not reusable"), `${tags.length} rows`);
  await p.locator(".cand-head .ant-select").click();
  await p.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: "All candidates" }).click();

  // files and evidence behind the selected candidate
  const menu = async (label) => {
    await p.locator(".sel-item .top .ant-btn").click();
    await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: label }).click();
    await p.locator(".ant-modal:visible").waitFor();
  };
  await menu("View source files");
  await p.locator(".ant-modal:visible .code-view").first().waitFor();
  check("source files show the stored XOSC", (await p.locator(".ant-modal:visible .code-view").first().innerText()).includes("OpenSCENARIO"));
  await closeModal();
  await menu("File standard checks");
  check("standard checks explain unavailable XSD checks", (await p.locator(".ant-modal:visible .check-block").count()) === 2
    && (await p.locator(".ant-modal:visible .mtag").first().innerText()) === "Check unavailable");
  await closeModal();
  await menu("Evidence explanation");
  await p.locator(".ant-modal:visible .evidence-list li").first().waitFor();
  check("evidence explanation lists the cited evidence", (await p.locator(".ant-modal:visible .evidence-list li").first().innerText()).startsWith("[P1]"));
  check("model explanation needs a configured key", await p.locator(".ant-modal:visible .ant-btn-primary").isDisabled());
  await p.locator(".ant-modal:visible .ant-btn").filter({ hasText: "Explain from structure" }).click();
  await p.locator(".ant-modal:visible .explanation li").first().waitFor();
  check("structural explanation cites evidence", /\[P1/.test(await p.locator(".ant-modal:visible .explanation li").first().innerText()));
  await closeModal();

  // file links resolve
  const xosc = await p.locator(".pair a").first().getAttribute("href");
  const r1 = await p.request.get(BASE + xosc);
  check("XOSC link serves the stored file", r1.ok() && (await r1.text()).includes("OpenSCENARIO"));
  const page = await p.locator(".evi .bd > img").getAttribute("src");
  const r2 = await p.request.get(BASE + page);
  check("evidence page renders from the PDF", r2.ok() && r2.headers()["content-type"] === "image/png");

  // queue tools: scope over all PDFs, text filter
  await p.locator(".pdfcard .doc-switch").click();
  await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "Scenes of all PDFs" }).click();
  await p.waitForFunction(() => document.querySelectorAll(".scene").length === 8);
  check("All PDFs shows every requirement", (await p.locator(".scene").count()) === 8);
  await p.getByRole("textbox", { name: "Find a scene" }).fill("pedestrian");
  check("scene filter narrows the queue", (await p.locator(".scene").count()) === 1 && (await p.locator(".left-tabs .ant-tabs-tab").first().innerText()) === "Scenes (1/8)");
  await p.getByRole("textbox", { name: "Find a scene" }).fill("");
  await p.locator(".pdfcard .doc-switch").click();
  await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "demo-aeb-protocol-zh.pdf" }).click();
  await p.waitForFunction(() => document.querySelectorAll(".scene").length === 4);

  // binding a candidate found by hand stores it on the clause and returns to the table
  await p.locator(".scene").nth(2).click();
  await idle();
  const handScene = await p.locator(".scene.sel .t").innerText();
  const modify = rows().filter({ has: p.locator(".mtag.modify") }).first();
  await modify.click();
  const handAsset = await p.locator(".sel-item .name").getAttribute("title");
  await p.locator(".actions .ant-btn-primary").filter({ hasText: "Adopt for this clause" }).click();
  await p.locator(".ant-message-success").filter({ hasText: "Adopted for this clause" }).waitFor({ timeout: 30000 });
  await bindRows().first().waitFor();
  const byHandRow = (await view()).scenes.find((s) => s.title === handScene);
  check("binding a candidate found by hand returns to the table with it", (await p.locator(".bind-table .row-active").innerText()).includes(handScene)
    && byHandRow?.binding?.source === "manual" && byHandRow.binding.status === "modify" && byHandRow.binding.changes.length > 0
    && byHandRow.binding.assets[0].title === handAsset, `${handScene} → ${handAsset}: ${JSON.stringify(byHandRow?.binding ?? null).slice(0, 300)}`);

  // requirement facts: edit a typed value, save a revision; the confirmed binding asks for a recheck
  await byHand(1);
  await p.locator(".left-tabs .ant-tabs-tab").filter({ hasText: "Requirement facts" }).click();
  await p.locator(".fact-sheet").first().waitFor();
  check("facts tab shows the typed requirement", (await p.locator(".fact-sheet").first().innerText()).includes("AEB"));
  const revision = Number((await p.locator(".facts-head .muted").innerText()).replace(/\D+/g, ""));
  const factScene = await p.locator(".facts-title").innerText();
  await p.locator(".facts-actions .ant-btn").filter({ hasText: "Edit facts" }).click();
  const speed = p.locator(".ant-drawer .ant-form-item").filter({ hasText: "Ego speed" }).locator("input");
  await speed.fill("42");
  await p.locator(".ant-drawer .ant-btn-primary").click();
  await p.locator(".ant-message-success").filter({ hasText: `revision ${revision + 1}` }).waitFor();
  await idle();
  check("saving facts creates the next revision", (await p.locator(".facts-head .muted").innerText()) === `Revision ${revision + 1}`);
  check("the new revision holds the edited value", (await p.locator(".fact-sheet").first().innerText()).includes("42"));
  check("requirement facts no longer publish to a separate library", (await p.locator(".facts-actions .ant-btn").filter({ hasText: "publish" }).count()) === 0);
  await p.locator(".facts-actions .ant-btn").filter({ hasText: "Revision history" }).click();
  await p.locator(".ant-modal:visible tbody tr.ant-table-row").first().waitFor();
  check("revision history lists every revision", (await p.locator(".ant-modal:visible tbody tr.ant-table-row").count()) === revision + 1);
  await closeModal();
  await p.locator(".left-tabs .ant-tabs-tab").filter({ hasText: "Scenes" }).click();

  // esmini: capture a real frame when esmini is installed on this machine; otherwise the controls say why
  await rows().first().click();
  const play = p.locator(".player-bar .ant-btn-primary");
  if (await play.isEnabled()) {
    await p.locator(".player-bar .ant-btn").nth(2).click();
    // The authored demo fixtures are parser fixtures that esmini rejects; the player must say so rather than show a picture.
    await p.locator(".player .ant-image img, .player-error").first().waitFor({ timeout: 60000 });
    check("esmini capture shows a real frame or explains the failure",
      (await p.locator(".player .ant-image img").isVisible()) || (await p.locator(".player-error").innerText()).includes("could not play"));
    check("the preview outcome is recorded on the version",
      (await (await p.request.get(`${BASE}/api/overview`)).json()).untested === 5);
  } else {
    check("without esmini the player explains how to set it up", (await p.locator(".player-bar .small-link").first().innerText()) === "Settings");
  }

  // language toggle re-labels interface and server vocabulary, and is saved on the server
  await p.locator(".lang button").filter({ hasText: "中文" }).click();
  await idle();
  check("中文 relabels the interface", (await p.locator(".ox-nav button.on").innerText()) === "工作台");
  const zh = await p.locator(".facts-t tbody td").first().innerText();
  check("中文 shows Chinese assessment vocabulary", /[一-鿿]/.test(zh), zh);
  await p.locator(".lang button").filter({ hasText: "EN" }).click();
  await idle();

  // settings: model, local service, display, advanced
  await p.locator('button[aria-label="Settings"]').click();
  await p.locator(".settings-form").first().waitFor();
  check("settings show no saved key in the demo", (await p.locator('.settings-form input[type="password"]').getAttribute("placeholder")) === "Enter API key");
  await p.locator(".settings-tabs .ant-tabs-tab").filter({ hasText: "Local service" }).click();
  check("settings show the demo data folder", (await p.locator(".location code").last().innerText()) === demo.dataDir);
  await p.locator(".switch-row .ant-switch").click();
  await p.waitForTimeout(300);
  check("the setting to make previews after an import is saved", (await (await p.request.get(BASE + "/api/settings")).json()).preferences.auto_preview === true);
  await p.locator(".switch-row .ant-switch").click();
  await p.waitForTimeout(300);
  await p.locator(".settings-tabs .ant-tabs-tab").filter({ hasText: "Advanced" }).click();
  check("the retrieval backend and file standards sit under Advanced", (await p.locator(".ant-modal:visible .ant-radio-wrapper").filter({ hasText: "Lightweight offline retrieval" }).count()) === 1
    && (await p.locator(".ant-modal:visible .settings-h").filter({ hasText: "File standards" }).count()) === 1);
  await p.locator(".settings-tabs .ant-tabs-tab").filter({ hasText: "Display" }).click();
  await p.locator(".ant-radio-button-wrapper").filter({ hasText: "Dark" }).click();
  await p.waitForTimeout(300);
  check("appearance switches to dark", (await p.evaluate(() => document.documentElement.dataset.theme)) === "dark");
  await p.locator(".ant-radio-button-wrapper").filter({ hasText: "File names" }).click();
  await p.waitForTimeout(300);
  const fileNamed = await rows().first().locator(".pair .fn").first().innerText();
  await p.locator(".ant-radio-button-wrapper").filter({ hasText: "Scenario and map names" }).click();
  await p.waitForTimeout(300);
  const named = await rows().first().locator(".pair .fn").first().innerText();
  check("candidates are named by scenario and map, or by file on request", fileNamed.endsWith(".xosc") && !named.endsWith(".xosc"), `${named} / ${fileNamed}`);
  await closeModal();
  await p.mouse.move(800, 5);
  await p.waitForTimeout(400);
  await p.screenshot({ path: path.join(OUT, "dark.png") });
  const saved = await (await p.request.get(BASE + "/api/settings")).json();
  check("appearance is saved on the server", saved.preferences.appearance === "dark");

  // back on the table, the edited clause asks for a recheck; a reload keeps the language and opens the start page
  await backToTable();
  check("editing a clause's facts marks its binding for a recheck", (await bindRows().filter({ hasText: factScene.replace(/^\S+\s/, "") }).filter({ hasText: "Reconfirm" }).count()) === 1, factScene);
  await p.locator(".lang button").filter({ hasText: "中文" }).click();
  await p.reload({ waitUntil: "networkidle" });
  check("language preference survives a reload", (await p.locator(".ox-nav button.on").innerText()) === "工作台" && (await p.locator(".start-doc").count()) === 2);
  await p.locator(".lang button").filter({ hasText: "EN" }).click();

  // free text search: no requirement, so similar assets only, on its own page
  await p.locator(".start-search input").fill("pedestrian crossing the road");
  await p.locator(".start-search .ant-btn-primary").click();
  await p.locator(".rcard").first().waitFor();
  check("free text search lists similar assets", (await p.locator(".rcard").count()) > 0, `${await p.locator(".rcard").count()} cards`);
  check("free text search makes no reuse decision", (await p.locator(".decision").count()) === 0 && (await p.locator(".actions").count()) === 0);
  await p.locator(".sresults-bar button[aria-label='Back to start']").click();
  await p.locator(".start-doc").first().waitFor();

  // asset management: table, labels, deletion guard, deletion, import
  await p.locator(".ox-nav button").filter({ hasText: "Asset management" }).click();
  const assetRows = () => p.locator(".asset-table tbody tr.ant-table-row");
  await assetRows().first().waitFor();
  check("asset table lists the latest versions", (await assetRows().count()) === 6, `${await assetRows().count()} rows`);
  check("asset management is one list without a requirement library", (await p.locator(".assets-tabs").count()) === 0);
  await p.locator(".assets-page .ph .ant-btn").filter({ hasText: "Make previews" }).click();
  await p.locator(".preview-strip .job-summary b").filter({ hasText: /Previews (made|stopped|failed)/ }).waitFor({ timeout: 180000 });
  const previewRun = (await (await p.request.get(`${BASE}/api/jobs?kind=preview_batch`)).json())[0];
  check("one preview run draws every road and tries every version once", previewRun.status === "completed" && previewRun.result.drawings === 6
    && previewRun.result.frames + previewRun.result.failed + previewRun.result.kept === 6, JSON.stringify(previewRun.result));
  await assetRows().filter({ hasText: "Opaque 003" }).click();
  await p.locator(".asset-detail .road-drawing").waitFor();
  check("an asset shows its road from above", await p.locator(".asset-detail .road-drawing").evaluate((img) => img.complete && img.naturalWidth > 0));
  await p.locator(".asset-detail .ant-tabs-tab").filter({ hasText: "Source" }).click();
  await p.locator(".asset-detail .ant-collapse-header").filter({ hasText: "Classification" }).click();
  await p.locator(".asset-detail .ant-form-item").filter({ hasText: "Road type" }).locator(".ant-select").click();
  await p.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: /^Curve$/ }).click();
  await p.locator(".asset-detail .ant-btn-primary").filter({ hasText: "Save and confirm" }).click();
  await p.locator(".ant-message-success").filter({ hasText: "Classification confirmed" }).waitFor();
  await p.waitForTimeout(400);
  check("labels set under Source show in the table", (await assetRows().filter({ hasText: "Opaque 003" }).innerText()).includes("Curve"));
  const facets = (await (await p.request.get(`${BASE}/api/library`)).json()).facets.label_road_type;
  check("confirmed labels reach the search facets", facets.includes("弯道"), facets.join(", "));

  await p.locator(".assets-page .ph .ant-btn-primary").click();
  const fixtures = path.join(WEB, "..", "tests", "fixtures");
  await p.locator(".ant-modal:visible input[type=file]").setInputFiles([path.join(fixtures, "minimal.xosc"), path.join(fixtures, "minimal.xodr")]);
  await p.locator(".ant-modal:visible .ant-btn-primary").filter({ hasText: "Start import" }).click();
  await p.locator(".ant-modal:visible .job-head b").filter({ hasText: "Completed" }).waitFor({ timeout: 60000 });
  check("asset import job saves the scenario", (await p.locator(".ant-modal:visible .job-note").first().innerText()).startsWith("1 scenarios saved"));
  await p.locator(".ant-modal:visible .ant-btn-primary").filter({ hasText: "Done" }).click();
  await p.waitForTimeout(600);
  check("imported asset appears in the table", (await assetRows().count()) === 7 && (await assetRows().first().innerText()).includes("Minimal cut-in"));

  await assetRows().filter({ hasText: "Minimal cut-in" }).click();
  await p.locator(".asset-detail-head").filter({ hasText: "Minimal cut-in" }).waitFor();
  await p.locator(".asset-detail-head .ant-btn-dangerous").click();
  await p.locator(".ant-popconfirm .ant-btn-dangerous").click();
  await p.locator(".ant-message-success").filter({ hasText: "Version deleted" }).waitFor();
  await p.waitForTimeout(400);
  check("an unreferenced version is deleted", (await assetRows().count()) === 6);

  // an asset lists the requirement clauses bound to it, and opening one returns to its row in the table
  const boundTitle = bound.binding.assets.find((a) => a.preferred).title;
  await assetRows().filter({ hasText: boundTitle }).first().click();
  await p.locator(".asset-detail-head").filter({ hasText: boundTitle }).waitFor();
  await p.locator(".asset-detail .ant-tabs-tab").filter({ hasText: "Clauses" }).click();
  await p.locator(".asset-detail .bind-clauses tbody tr.ant-table-row").first().waitFor();
  check("an asset lists the requirement clauses bound to it", (await p.locator(".asset-detail .bind-clauses tbody tr.ant-table-row").filter({ hasText: bound.title }).count()) === 1
    && (await p.locator(".asset-detail .ant-tabs-tab").filter({ hasText: /Clauses \(\d+\)/ }).count()) === 1);
  check("a bound version cannot be deleted", await p.locator(".asset-detail-head .ant-btn-dangerous").isDisabled());
  await p.locator(".asset-detail .bind-clauses tbody tr.ant-table-row").filter({ hasText: bound.title }).click();
  await bindRows().first().waitFor();
  await p.waitForTimeout(400);
  check("opening a bound clause shows its row in the table", (await p.locator(".ox-nav button.on").innerText()) === "Workbench"
    && (await p.locator(".bind-table .row-active").innerText()).includes(bound.title));

  // overview: how the project's PDFs are covered by confirmed bindings, then the library in numbers
  await p.locator(".ox-nav button").filter({ hasText: "Overview" }).click();
  await p.locator(".ov-coverage .cov-head").first().waitFor();
  const heads = await p.locator(".ov-coverage .cov-head").allInnerTexts();
  check("Overview shows each PDF's binding coverage", heads.length === 2
    && heads.some((h) => h.includes("4 clauses · 4 reusable · 0 not applicable · 0 to confirm")) && heads.some((h) => h.includes("4 to confirm")), heads.join(" | "));
  check("Overview counts the assets no clause uses", /Assets no clause adopts: \d \/ 6/.test(await p.locator(".ov-coverage").innerText()));
  check("Overview counts the demo library", (await p.locator(".metric b").first().innerText()) === "6" && (await p.locator(".ov-reports, .ov-decisions").count()) === 0);
  await p.screenshot({ path: path.join(OUT, "coverage.png") });

  // new project starts empty and becomes current
  await p.locator(".hbtn").first().click();
  await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "New project" }).click();
  await p.locator(".ant-modal input").fill("Verify project");
  await p.locator(".ant-modal .ant-btn-primary").click();
  await p.locator(".ant-message-success").filter({ hasText: "Verify project" }).waitFor();
  await p.waitForTimeout(400);
  check("new project becomes current and starts empty",
    (await p.locator(".hbtn b").first().innerText()) === "Verify project" && (await p.locator(".start-doc").count()) === 0);

  check("no runtime errors", errors.length === 0, errors.join(" | "));
} catch (error) {
  check("script ran to the end", false, error.message.split("\n")[0]);
  await b.contexts()[0]?.pages()[0]?.screenshot({ path: path.join(OUT, "failure.png") }).catch(() => undefined);
} finally {
  await b.close();
  demo.stop();
}
console.log(results.join("\n"));
if (results.some((r) => r.startsWith("FAIL"))) process.exitCode = 1;
