// Usage: LIVE=1 node scripts/screenshot.mjs <name> [light|dark] [baseUrl]
// Captures the app at 1586x992, then builds side-by-side comparisons (target | actual)
// for the full page and for left / middle / right columns.
import { chromium } from "playwright";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

const round = process.argv[2] ?? "r1";
const theme = process.argv[3] ?? "light";
const TARGET = path.join(WEB, "..", ".impeccable", "approved-target.png");
const OUT = path.join(WEB, ".verify-out", "shots", round);
fs.mkdirSync(OUT, { recursive: true });

const W = 1586, H = 992;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: W, height: H }, colorScheme: theme });
const errors = [];
page.on("console", (m) => { if (m.type() === "error" || m.type() === "warning") errors.push(`[${m.type()}] ${m.text()}`); });
page.on("pageerror", (e) => errors.push(`[pageerror] ${e.message}`));
await page.goto((process.argv[4] ?? "http://localhost:5173") + "/", { waitUntil: "networkidle" });
if (process.env.LIVE) {
  // The workbench opens on the start page; enter the first PDF's workflow.
  await page.locator(".start-doc").first().click();
  await page.waitForSelector(".cand-table tbody tr.ant-table-row", { timeout: 120000 });
  await page.waitForLoadState("networkidle");
}
await page.waitForTimeout(800);

const actual = path.join(OUT, `actual-${theme}.png`);
await page.screenshot({ path: actual });

const metrics = await page.evaluate(() => {
  const d = document.documentElement;
  const q = (s) => [...document.querySelectorAll(s)].map((e) => { const r = e.getBoundingClientRect(); return { x: Math.round(r.x), y: Math.round(r.y), w: Math.round(r.width), h: Math.round(r.height) }; });
  return {
    scroll: { sw: d.scrollWidth, sh: d.scrollHeight, cw: d.clientWidth, ch: d.clientHeight },
    rows: q(".ant-table-tbody > tr").slice(0, 8),
    boxes: Object.fromEntries([".panel", ".pdfcard", ".left-tabs .ant-tabs-nav", ".scene", ".evi", ".evi .bd > img", ".mid-tabs > .ant-tabs-nav", ".search-row", ".chips", ".cand-head", ".cand-table thead", ".preview", ".pv-link", ".preview .ant-tabs-nav", ".pv-img img", ".pv-road", ".decision", ".sel-item", ".kvt", ".blocking", ".facts-wrap", ".trace", ".actions"].map((s) => [s, q(s).map((r) => `${r.x},${r.y} ${r.w}x${r.h} ->${r.y + r.h}`)])),
  };
});
fs.writeFileSync(path.join(OUT, `metrics-${theme}.json`), JSON.stringify({ metrics, errors }, null, 2));

// Side-by-side composites rendered by the browser itself
const b64 = (p) => "data:image/png;base64," + fs.readFileSync(p).toString("base64");
const t = b64(TARGET), a = b64(actual);
const cols = { full: [0, W], left: [0, 400], middle: [380, 1130], right: [1110, W] };
const cmp = await browser.newPage({ viewport: { width: 400, height: 400 } });
for (const [name, [x0, x1]] of Object.entries(cols)) {
  const cw = x1 - x0;
  const html = `<body style="margin:0;background:#888;display:flex;gap:8px;width:max-content">
    ${[["TARGET", t], ["ACTUAL", a]].map(([lbl, src]) => `<div style="position:relative;width:${cw}px;height:${H}px;overflow:hidden">
      <img src="${src}" style="position:absolute;left:${-x0}px;top:0;width:${W}px;height:${H}px">
      <span style="position:absolute;top:0;right:0;background:#d00;color:#fff;font:bold 12px sans-serif;padding:2px 6px">${lbl}</span></div>`).join("")}
  </body>`;
  await cmp.setViewportSize({ width: cw * 2 + 8, height: H });
  await cmp.setContent(html);
  await cmp.screenshot({ path: path.join(OUT, `cmp-${name}-${theme}.png`) });
}
await browser.close();
console.log(JSON.stringify({ out: OUT, ...metrics, errors }, null, 2));
