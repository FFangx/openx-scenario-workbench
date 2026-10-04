// UI checks against the self-authored demo workspace (see demo-server.mjs); safe to run anywhere, including CI.
// Usage: npm run build && node scripts/verify-ui.mjs
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { startDemo } from "./demo-server.mjs";

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
  const idle = async () => { await p.waitForFunction(() => !document.querySelector(".cand-table .ant-spin-spinning"), null, { timeout: 120000 }); await p.waitForTimeout(150); };
  const total = () => p.locator(".cand-head .n").innerText();
  const closeModal = async () => {
    await p.locator(".ant-modal-wrap:visible .ant-modal-close").first().click();
    await p.locator(".ant-modal-wrap:visible").first().waitFor({ state: "hidden" });
  };

  await p.goto(BASE + "/", { waitUntil: "networkidle" });
  // the workbench opens on the start page: text search, PDF import, and the project's PDFs
  await p.locator(".start-doc").first().waitFor();
  check("the workbench opens on the start page", (await p.locator(".start-search input").count()) === 1 && (await p.locator(".start-doc").count()) === 2
    && (await p.locator(".ox-steps").count()) === 0);
  await p.locator(".start-doc").first().click();
  await rows().first().waitFor({ timeout: 120000 });
  await idle();
  check("scenes load from API", (await p.locator(".scene").count()) === 4, `${await p.locator(".scene").count()} scenes`);
  check("candidates load from API", (await rows().count()) === 6, `${await rows().count()} rows`);
  check("evidence shows source text", (await p.locator(".evi .src").count()) > 0);
  check("the step track marks the steps already done", (await p.locator(".ox-step.done").count()) === 2 && (await p.locator(".ox-step.on").innerText()).includes("Assess reuse"));
  check("interface follows the saved English preference", (await p.locator(".ox-nav button.on").innerText()) === "Workbench");

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
  const rowTitle = await rows().nth(2).locator(".desc").getAttribute("title");
  await p.waitForTimeout(150);
  check("row click updates selected item", (await p.locator(".sel-item .name").getAttribute("title")) === rowTitle, rowTitle);
  check("row click updates preview", (await p.locator(".pv-link a").first().getAttribute("title")) === (await rows().nth(2).locator(".pair a").first().getAttribute("title")));

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

  // exports
  let [dl] = await Promise.all([p.waitForEvent("download", { timeout: 60000 }), p.locator(".actions .ant-btn-primary").first().click()]);
  const jp = path.join(OUT, dl.suggestedFilename()); await dl.saveAs(jp);
  const trace = JSON.parse(fs.readFileSync(jp, "utf8"));
  check("JSON export is the backend trace", !!trace.source && !!trace.candidate?.version_id && !!trace.reuse?.level, dl.suggestedFilename());
  await p.locator(".actions .ant-space-compact .ant-btn").nth(1).click();
  [dl] = await Promise.all([p.waitForEvent("download"), p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "CSV" }).click()]);
  const cp = path.join(OUT, dl.suggestedFilename()); await dl.saveAs(cp);
  check("CSV export has header + difference rows", fs.readFileSync(cp, "utf8").startsWith("field,requirement,candidate,status,action"));
  await p.locator(".actions .ant-space-compact .ant-btn").nth(1).click();
  [dl] = await Promise.all([p.waitForEvent("download"), p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "HTML" }).click()]);
  const hp = path.join(OUT, dl.suggestedFilename()); await dl.saveAs(hp);
  check("HTML export is the assessment report", fs.readFileSync(hp, "utf8").includes("OpenX reuse trace"), dl.suggestedFilename());

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
  const traced = await p.locator(".actions .ant-btn-primary").first();
  [dl] = await Promise.all([p.waitForEvent("download"), traced.click()]);
  const ep = path.join(OUT, "explained.json"); await dl.saveAs(ep);
  check("the explanation travels with the export", JSON.parse(fs.readFileSync(ep, "utf8")).explanation?.method === "structural");

  // free text search: no requirement, so similar assets only, on its own page
  const sceneQuery = await p.locator(".search-row input").inputValue();
  await p.locator(".scene-chip .ant-tag-close-icon").click();
  await p.locator(".sresults-bar input").fill("pedestrian crossing the road");
  await p.locator(".sresults-bar .ant-btn-primary").click();
  await p.locator(".rcard").first().waitFor();
  check("free text search lists similar assets", (await p.locator(".rcard").count()) > 0, `${await p.locator(".rcard").count()} cards`);
  check("free text search makes no reuse decision", (await p.locator(".decision").count()) === 0 && (await p.locator(".actions").count()) === 0);
  await p.locator(".sresults-bar button[aria-label='Back to start']").click();
  await p.locator(".start-doc").first().click();
  await idle();
  check("back in the PDF workflow the requirement is still selected", (await p.locator(".scene-chip").count()) === 1 && (await p.locator(".search-row input").inputValue()) === sceneQuery, sceneQuery);

  // file links resolve
  const xosc = await p.locator(".pair a").first().getAttribute("href");
  const r1 = await p.request.get(BASE + xosc);
  check("XOSC link serves the stored file", r1.ok() && (await r1.text()).includes("OpenSCENARIO"));
  const page = await p.locator(".evi .bd > img").getAttribute("src");
  const r2 = await p.request.get(BASE + page);
  check("evidence page renders from the PDF", r2.ok() && r2.headers()["content-type"] === "image/png");

  // a "Needs review" candidate is saved only after each review item is confirmed with a reason
  await p.locator(".scene").first().click();
  await idle();
  await rows().filter({ has: p.locator(".mtag.review") }).first().click();
  await p.locator(".actions > .ant-btn").click();
  const signoff = p.locator(".ant-modal:visible");
  await signoff.locator(".signoff-list li").first().waitFor();
  const items = await signoff.locator(".signoff-list li").count();
  const confirm = signoff.locator(".ant-btn-primary");
  const blockedWithoutReasons = await confirm.isDisabled();
  for (let i = 0; i < items; i++) {
    const item = signoff.locator(".signoff-list li").nth(i);
    await item.locator(".ant-checkbox-input").check();
    await item.locator("textarea").fill("Checked against the source text");
  }
  check("review sign-off needs every item confirmed with a reason", blockedWithoutReasons && !(await confirm.isDisabled()), `${items} items`);
  await confirm.click();
  await p.locator(".ant-message-success").first().waitFor({ timeout: 30000 });
  await signoff.waitFor({ state: "hidden" });
  check("a signed-off review decision is saved", (await p.locator(".actions > .ant-btn").innerText()).includes("Review next requirement"));

  // save a decision on a "Modify and reuse" candidate, then find it under Recent activity
  const modify = rows().filter({ has: p.locator(".mtag.modify") }).first();
  await modify.click();
  await p.locator(".actions > .ant-btn").click();
  await p.locator(".ant-message-success").waitFor({ timeout: 30000 });
  await p.waitForTimeout(400);
  check("saved scene shows as assessed in the queue", (await p.locator(".scene.sel .c").innerText()) === "Assessed");
  check("after saving, the next requirement is one click away", (await p.locator(".actions > .ant-btn").innerText()).includes("Review next requirement"));
  await p.locator(".ox-steps .tools button").filter({ hasText: "Recent activity" }).click();
  await p.locator(".pop-history .row").first().waitFor();
  const savedScene = await p.locator(".scene.sel .t").innerText();
  check("saved decision appears under Recent activity", (await p.locator(".pop-history .row b").first().innerText()) === savedScene);

  // overview: library counts, the saved decision, its downloads, and the way back to the requirement
  await p.locator(".pop-history .ant-btn-link").click();
  await p.locator(".ov-detail").waitFor();
  check("View all decisions opens Overview", (await p.locator(".ox-nav button.on").innerText()) === "Overview");
  check("Overview counts the demo library", (await p.locator(".metric b").first().innerText()) === "6" && (await p.locator(".ov-library tbody tr.ant-table-row").count()) === 6);
  check("Overview lists the saved decision", (await p.locator(".ov-reports tbody tr.row-active").innerText()).includes(savedScene));
  const html = await p.request.get(BASE + (await p.locator(".ov-actions a").nth(1).getAttribute("href")));
  check("saved decision downloads as an HTML report", html.ok() && (await html.text()).includes("OpenX reuse trace"));
  await p.locator(".ox-nav button").filter({ hasText: "Workbench" }).click();
  await p.locator(".scene").nth(1).click();
  await idle();
  await p.locator(".ox-nav button").filter({ hasText: "Overview" }).click();
  await p.locator(".ov-detail").waitFor();
  await p.locator(".ov-actions .ant-btn").filter({ hasText: "Continue reviewing" }).click();
  await idle();
  check("Continue reviewing opens the requirement facts", (await p.locator(".left-tabs .ant-tabs-tab-active").innerText()) === "Requirement facts");
  await p.locator(".left-tabs .ant-tabs-tab").filter({ hasText: "Scenes" }).click();
  check("Continue reviewing reopens the saved requirement", (await p.locator(".scene.sel .t").innerText()) === savedScene);

  // project files list both PDFs with download links
  await p.locator(".ox-steps .tools button").filter({ hasText: "Project files" }).click();
  await p.locator(".file-row").first().waitFor();
  const links = await p.locator(".file-row a[download]").count();
  check("Project files lists PDFs with downloads", (await p.locator(".file-row").count()) === 2 && links === 2, `${links} links`);
  const before = await p.locator(".scene .t").first().innerText();
  await p.locator(".file-row:not(.on) button").click();
  await p.waitForFunction((t) => document.querySelector(".scene .t")?.textContent !== t, before);
  await idle();
  check("choosing another PDF loads its scenes", (await p.locator(".scene").count()) === 4, `${before} → ${await p.locator(".scene .t").first().innerText()}`);
  await p.locator(".ox-steps .tools button").filter({ hasText: "Project files" }).click();
  await p.locator(".ant-popover:visible").waitFor({ state: "hidden" });

  // queue tools: scope over all PDFs, text filter
  await p.locator(".pdfcard .doc-switch").click();
  await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "Scenes of all PDFs" }).click();
  await p.waitForFunction(() => document.querySelectorAll(".scene").length === 8);
  check("All PDFs shows every requirement", (await p.locator(".scene").count()) === 8);
  await p.getByRole("textbox", { name: "Find a scene" }).fill("pedestrian");
  check("scene filter narrows the queue", (await p.locator(".scene").count()) === 1 && (await p.locator(".left-tabs .ant-tabs-tab").first().innerText()) === "Scenes (1/8)");
  await p.getByRole("textbox", { name: "Find a scene" }).fill("");
  await p.locator(".pdfcard .doc-switch").click();
  await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "demo-aeb-protocol.pdf" }).click();
  await p.waitForFunction(() => document.querySelectorAll(".scene").length === 4);

  // requirement facts: edit a typed value, save a revision, publish it
  await p.locator(".scene").nth(1).click();
  await idle();
  await p.locator(".left-tabs .ant-tabs-tab").filter({ hasText: "Requirement facts" }).click();
  await p.locator(".fact-sheet").first().waitFor();
  check("facts tab shows the typed requirement", (await p.locator(".fact-sheet").first().innerText()).includes("AEB"));
  const revision = Number((await p.locator(".facts-head .muted").innerText()).replace(/\D+/g, ""));
  await p.locator(".facts-actions .ant-btn").filter({ hasText: "Edit facts" }).click();
  const speed = p.locator(".ant-drawer .ant-form-item").filter({ hasText: "Ego speed" }).locator("input");
  await speed.fill("42");
  await p.locator(".ant-drawer .ant-btn-primary").click();
  await p.locator(".ant-message-success").filter({ hasText: `revision ${revision + 1}` }).waitFor();
  await idle();
  check("saving facts creates the next revision", (await p.locator(".facts-head .muted").innerText()) === `Revision ${revision + 1}`);
  check("the new revision holds the edited value", (await p.locator(".fact-sheet").first().innerText()).includes("42"));
  check("the queue shows the new revision", (await p.locator(".scene.sel .p").innerText()).includes(`v${revision + 1}`));
  await p.locator(".facts-actions .ant-btn").filter({ hasText: "Confirm and publish" }).click();
  await p.locator(".ant-popconfirm .ant-btn-primary").click();
  await p.locator(".facts-actions .ant-btn").filter({ hasText: "Revision published" }).waitFor();
  check("publishing confirms the revision in the queue", (await p.locator(".scene.sel .c").innerText()) === "Confirmed");
  await p.locator(".facts-actions .ant-btn").filter({ hasText: "Revision history" }).click();
  await p.locator(".ant-modal:visible tbody tr.ant-table-row").first().waitFor();
  check("revision history lists every revision", (await p.locator(".ant-modal:visible tbody tr.ant-table-row").count()) === revision + 1);
  await closeModal();
  await p.locator(".left-tabs .ant-tabs-tab").filter({ hasText: "Scenes" }).click();

  // whole-PDF matching and its summary
  await p.locator(".pdfcard .more").click();
  await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "Match entire PDF" }).click();
  await p.locator(".ant-modal:visible .ant-btn").filter({ hasText: "Match all scenes" }).click();
  await p.locator(".ant-modal:visible .batch-table tbody tr.ant-table-row").first().waitFor({ timeout: 120000 });
  check("whole-PDF matching assesses every scene", (await p.locator(".ant-modal:visible .batch-table tbody tr.ant-table-row").count()) === 4);
  const batchHtml = await p.request.get(BASE + (await p.locator(".ant-modal:visible a.ant-btn").nth(1).getAttribute("href")));
  check("the summary downloads as HTML", batchHtml.ok() && (await batchHtml.text()).includes("OpenX document assessment"));
  await p.locator(".ant-modal:visible .ant-btn").filter({ hasText: "Save summary report" }).click();
  await p.locator(".ant-message-success").filter({ hasText: "Summary saved" }).waitFor();
  check("the summary is saved as a report", (await (await p.request.get(`${BASE}/api/projects/${demo.seed.project_id}/reports`)).json()).some((r) => r.kind === "batch"));
  await closeModal();

  // extraction record of the rule-extracted demo PDF
  await p.locator(".pdfcard .more").click();
  await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "Extraction record" }).click();
  await p.locator(".ant-modal:visible .ant-descriptions").waitFor();
  check("extraction record offers re-extraction for an older engine", await p.locator(".ant-modal:visible .ant-btn").filter({ hasText: "Extract scenes again" }).isVisible());
  await closeModal();

  // PDF import runs as a job; without a configured model it fails cleanly and keeps the project intact
  await p.locator(".pdfcard .more").click();
  await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "Import PDFs" }).click();
  const demoDocs = await (await p.request.get(`${BASE}/api/projects/${demo.seed.project_id}/documents`)).json();
  const pdfBytes = await (await p.request.get(`${BASE}/api/projects/${demo.seed.project_id}/documents/${demoDocs[0].document_id}/file`)).body();
  await p.locator(".ant-modal:visible input[type=file]").setInputFiles({ name: "authored-protocol.pdf", mimeType: "application/pdf", buffer: pdfBytes });
  await p.locator(".ant-modal:visible .ant-btn-primary").filter({ hasText: "Import PDFs" }).click();
  await p.locator(".ant-modal:visible .job .ant-alert-error").waitFor({ timeout: 60000 });
  check("PDF import without a model reports the failure", (await p.locator(".ant-modal:visible .job-head b").innerText()) === "Failed", await p.locator(".ant-modal:visible .job .ant-alert-error").innerText());
  await p.locator(".ant-modal:visible .ant-btn").filter({ hasText: "Done" }).click();
  check("a failed import adds no document", (await (await p.request.get(`${BASE}/api/projects/${demo.seed.project_id}/documents`)).json()).length === 2);

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
  await p.reload({ waitUntil: "networkidle" });
  check("language preference survives a reload", (await p.locator(".ox-nav button.on").innerText()) === "工作台");
  await p.locator(".start-doc").first().click();
  await idle();
  await p.locator(".lang button").filter({ hasText: "EN" }).click();
  await idle();

  // settings: model, local service, display
  await p.locator('button[aria-label="Settings"]').click();
  await p.locator(".settings-form").first().waitFor();
  check("settings show no saved key in the demo", (await p.locator('.settings-form input[type="password"]').getAttribute("placeholder")) === "Enter API key");
  await p.locator(".settings-tabs .ant-tabs-tab").filter({ hasText: "Local service" }).click();
  check("settings show the demo data folder", (await p.locator(".location code").last().innerText()) === demo.dataDir);
  await p.locator(".settings-tabs .ant-tabs-tab").filter({ hasText: "Display" }).click();
  await p.locator(".ant-radio-button-wrapper").filter({ hasText: "Dark" }).click();
  await p.waitForTimeout(300);
  check("appearance switches to dark", (await p.evaluate(() => document.documentElement.dataset.theme)) === "dark");
  await closeModal();
  await p.mouse.move(800, 5);
  await p.waitForTimeout(400);
  await p.screenshot({ path: path.join(OUT, "dark.png") });
  const saved = await (await p.request.get(BASE + "/api/settings")).json();
  check("appearance is saved on the server", saved.preferences.appearance === "dark");

  // asset management: table, labels, deletion guard, deletion, import, requirement library
  await p.locator(".ox-nav button").filter({ hasText: "Asset management" }).click();
  const assetRows = () => p.locator(".asset-table tbody tr.ant-table-row");
  await assetRows().first().waitFor();
  check("asset table lists the latest versions", (await assetRows().count()) === 6, `${await assetRows().count()} rows`);
  await assetRows().filter({ hasText: "Opaque 003" }).click();
  await p.locator(".asset-detail .ant-tabs-tab").filter({ hasText: "Classification" }).click();
  await p.locator(".asset-detail .ant-form-item").filter({ hasText: "Road type" }).locator(".ant-select").click();
  await p.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: /^Curve$/ }).click();
  await p.locator(".asset-detail .ant-btn-primary").filter({ hasText: "Save and confirm" }).click();
  await p.locator(".ant-message-success").filter({ hasText: "Classification confirmed" }).waitFor();
  await p.waitForTimeout(400);
  check("confirmed labels show in the table", (await assetRows().filter({ hasText: "Opaque 003" }).innerText()).includes("Curve"));
  const facets = (await (await p.request.get(`${BASE}/api/library`)).json()).facets.label_road_type;
  check("confirmed labels reach the search facets", facets.includes("弯道"), facets.join(", "));

  const savedAsset = trace.candidate.title;
  await assetRows().filter({ hasText: savedAsset }).click();
  await p.locator(".asset-detail-head").filter({ hasText: savedAsset }).waitFor();
  check("a version used by a saved decision cannot be deleted", await p.locator(".asset-detail-head .ant-btn-dangerous").isDisabled());
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

  await p.locator(".assets-tabs .ant-tabs-tab").filter({ hasText: "PDF requirement library" }).click();
  const requirementRows = p.locator(".req-library tbody tr.ant-table-row");
  await requirementRows.first().waitFor();
  check("published requirement is in the library", (await requirementRows.count()) === 1);
  await requirementRows.first().click();
  const publishedTitle = await p.locator(".asset-detail-head .name").innerText();
  await p.locator(".asset-detail .ant-btn").filter({ hasText: "Open source document" }).click();
  await idle();
  check("Open source document returns to the requirement facts", (await p.locator(".ox-nav button.on").innerText()) === "Workbench"
    && (await p.locator(".left-tabs .ant-tabs-tab-active").innerText()) === "Requirement facts"
    && (await p.locator(".facts-title").innerText()).endsWith(publishedTitle), publishedTitle);

  // new project starts empty and becomes current
  await p.locator(".hbtn").first().click();
  await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "New project" }).click();
  await p.locator(".ant-modal input").fill("Verify project");
  await p.locator(".ant-modal .ant-btn-primary").click();
  await p.locator(".ant-message-success").filter({ hasText: "Verify project" }).waitFor();
  await p.waitForTimeout(400);
  check("new project becomes current and starts empty",
    (await p.locator(".hbtn b").first().innerText()) === "Verify project" && (await p.locator(".scene").count()) === 0);

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
