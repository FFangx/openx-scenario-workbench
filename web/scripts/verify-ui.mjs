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
  p.on("console", (m) => m.type() === "error" && errors.push(m.text()));
  const rows = () => p.locator(".cand-table tbody tr.ant-table-row");
  const idle = async () => { await p.waitForFunction(() => !document.querySelector(".cand-table .ant-spin-spinning"), null, { timeout: 120000 }); await p.waitForTimeout(150); };
  const total = () => p.locator(".cand-head .n").innerText();

  await p.goto(BASE + "/", { waitUntil: "networkidle" });
  await rows().first().waitFor({ timeout: 120000 });
  await idle();
  check("scenes load from API", (await p.locator(".scene").count()) === 4, `${await p.locator(".scene").count()} scenes`);
  check("candidates load from API", (await rows().count()) === 6, `${await rows().count()} rows`);
  check("evidence shows source text", (await p.locator(".evi .src").count()) > 0);
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
  check("filter adds a chip and narrows results", (await p.locator(".chip").count()) === 1 && (await total()).startsWith("1 "), await total());
  await p.locator(".chip .ant-tag-close-icon").click();
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

  // file links resolve
  const xosc = await p.locator(".pair a").first().getAttribute("href");
  const r1 = await p.request.get(BASE + xosc);
  check("XOSC link serves the stored file", r1.ok() && (await r1.text()).includes("OpenSCENARIO"));
  const page = await p.locator(".evi .bd > img").getAttribute("src");
  const r2 = await p.request.get(BASE + page);
  check("evidence page renders from the PDF", r2.ok() && r2.headers()["content-type"] === "image/png");

  // save a decision on a "Modify and reuse" candidate, then find it under Recent activity
  await p.locator(".scene").first().click();
  await idle();
  const modify = rows().filter({ has: p.locator(".mtag.modify") }).first();
  await modify.click();
  await p.locator(".actions > .ant-btn").click();
  await p.locator(".ant-message-success").waitFor({ timeout: 30000 });
  await p.locator(".ox-steps .tools button").filter({ hasText: "Recent activity" }).click();
  await p.locator(".pop-history .row").first().waitFor();
  check("saved decision appears under Recent activity", (await p.locator(".pop-history .row b").first().innerText()) === (await p.locator(".scene.sel .t").innerText()));
  await p.keyboard.press("Escape");

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

  // language toggle re-labels interface and server vocabulary, and is saved on the server
  await p.locator(".lang button").filter({ hasText: "中文" }).click();
  await idle();
  check("中文 relabels the interface", (await p.locator(".ox-nav button.on").innerText()) === "工作台");
  const zh = await p.locator(".facts-t tbody td").first().innerText();
  check("中文 shows Chinese assessment vocabulary", /[一-鿿]/.test(zh), zh);
  await p.reload({ waitUntil: "networkidle" });
  check("language preference survives a reload", (await p.locator(".ox-nav button.on").innerText()) === "工作台");
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
  await p.keyboard.press("Escape");
  await p.mouse.move(800, 5);
  await p.waitForTimeout(400);
  await p.screenshot({ path: path.join(OUT, "dark.png") });
  const saved = await (await p.request.get(BASE + "/api/settings")).json();
  check("appearance is saved on the server", saved.preferences.appearance === "dark");

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
} finally {
  await b.close();
  demo.stop();
}
console.log(results.join("\n"));
if (results.some((r) => r.startsWith("FAIL"))) process.exitCode = 1;
