// Read-only UI checks against the live API. Needs `python -m openx_workbench.api` and `npm run dev` running.
// Never clicks Save, so it is safe on real data. Usage: node scripts/verify-ui.mjs [baseUrl]
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const BASE = process.argv[2] ?? "http://localhost:5173";
const OUT = path.join(WEB, ".verify-out", "ui");
fs.mkdirSync(OUT, { recursive: true });
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1586, height: 992 }, acceptDownloads: true });
const p = await ctx.newPage();
const errors = [];
p.on("pageerror", (e) => errors.push(e.message));
p.on("console", (m) => m.type() === "error" && errors.push(m.text()));
const results = [];
const check = (name, ok, detail = "") => results.push(`${ok ? "PASS" : "FAIL"}  ${name}${detail ? "  — " + detail : ""}`);
const rows = () => p.locator(".cand-table tbody tr.ant-table-row");
const idle = async () => { await p.waitForFunction(() => !document.querySelector(".cand-table .ant-spin-spinning"), null, { timeout: 120000 }); await p.waitForTimeout(150); };

await p.goto(BASE + "/", { waitUntil: "networkidle" });
await rows().first().waitFor({ timeout: 120000 });
await idle();
check("scenes load from API", (await p.locator(".scene").count()) > 50, `${await p.locator(".scene").count()} scenes`);
check("candidates load from API", (await rows().count()) === 8);
check("evidence shows source text", (await p.locator(".evi .src").count()) > 0);

// scene -> query + new search + evidence
const firstTop = await p.locator(".decision .big").innerText();
await p.locator(".scene").nth(3).click();
await idle();
const sceneTitle = await p.locator(".scene.sel .t").innerText();
const q = await p.locator(".search-row input").inputValue();
check("scene click sets query to scene title", q === sceneTitle, q);
check("scene click updates evidence", (await p.locator(".evi .x b").innerText()).includes(sceneTitle));
check("scene click re-runs matching", (await rows().count()) === 8, `top verdict ${firstTop} → ${await p.locator(".decision .big").innerText()}`);

// row -> right panel + preview
await rows().nth(2).click();
const rowTitle = await rows().nth(2).locator(".desc").getAttribute("title");
await p.waitForTimeout(150);
check("row click updates selected item", (await p.locator(".sel-item .name").getAttribute("title")) === rowTitle, rowTitle);
check("row click updates preview", (await p.locator(".pv-link a").first().getAttribute("title")) === (await rows().nth(2).locator(".pair a").first().getAttribute("title")));

// filters through the Filters tab, then chip removal
await p.locator(".mid-tabs .ant-tabs-tab").filter({ hasText: "Filters" }).click();
const fn = p.locator(".ant-form-item").filter({ hasText: "Function" });
await fn.locator(".ant-select").click();
await p.locator(".ant-select-dropdown:visible .ant-select-item-option").filter({ hasText: /^LDW$/ }).click();
await idle();
await p.locator(".mid-tabs .ant-tabs-tab").filter({ hasText: "Search" }).click();
const total = await p.locator(".cand-head .n").innerText();
check("filter adds a chip and narrows results", (await p.locator(".chip").count()) === 1 && !total.startsWith("21"), total);
await p.locator(".chip .ant-tag-close-icon").click();
await idle();
check("removing the chip restores all assets", (await p.locator(".cand-head .n").innerText()).startsWith("21"));

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
const thumb = await p.locator(".scene img").first().getAttribute("src");
const r2 = await p.request.get(BASE + thumb);
check("scene thumbnail renders from the PDF", r2.ok() && r2.headers()["content-type"] === "image/png");

// language toggle re-labels server vocabulary
await p.locator(".lang button").filter({ hasText: "中文" }).click();
await idle();
const zh = await p.locator(".facts-t tbody td").first().innerText();
check("中文 shows Chinese assessment vocabulary", /[\u4e00-\u9fff]/.test(zh), zh);
await p.locator(".lang button").filter({ hasText: "EN" }).click();
await idle();

await p.mouse.move(800, 5);
await p.screenshot({ path: path.join(OUT, "light.png") });
await p.locator('button[aria-label="Settings"]').click();
await p.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: "Dark" }).click();
await p.mouse.move(800, 5);
await p.waitForTimeout(400);
await p.screenshot({ path: path.join(OUT, "dark.png") });
check("no runtime errors", errors.length === 0, errors.join(" | "));
await p.evaluate(() => localStorage.setItem("openx.appearance", "light"));
console.log(results.join("\n"));
await b.close();
