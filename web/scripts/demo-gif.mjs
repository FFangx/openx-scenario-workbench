// Records docs/images/demo-en.gif or demo-zh.gif: the workbench on the authored reuse benchmark
// (examples/reuse-benchmark), stepping through requirements whose best verdicts differ.
// Runs on a throwaway workspace (demo-server.mjs). Usage: npm run build && node scripts/demo-gif.mjs [en|zh]
import { chromium } from "playwright";
import { spawnSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { python, startDemo } from "./demo-server.mjs";

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const FRAMES = path.join(WEB, ".verify-out", "gif");
const LANGUAGE = process.argv[2] === "zh" ? "zh" : "en";
const TARGET = path.join(WEB, "..", "docs", "images", `demo-${LANGUAGE}.gif`);
// One requirement per outcome: direct match, a second direct match, a parameter change, nothing suitable.
const SCENES = {
  en: ["Stationary car ahead, 50 km/h", "Cut-in from the left", "Lead car brakes from 70 km/h", "Motorcyclist crossing from the left"],
  zh: ["静止前车，主车 50 km/h", "右侧车辆切入", "夜间行人横穿，主车 60 km/h", "前方静止三轮车"],
}[LANGUAGE];
const PDF = { en: ["demo-adas-protocol-en.pdf", 16], zh: ["demo-adas-protocol-zh.pdf", 19] }[LANGUAGE];

fs.rmSync(FRAMES, { recursive: true, force: true });
fs.mkdirSync(FRAMES, { recursive: true });
const demo = await startDemo({ port: 8768, dataset: "benchmark", preferences: { language: LANGUAGE, encoder: "hashing" } });
const browser = await chromium.launch();
try {
  const page = await browser.newPage({ viewport: { width: 1586, height: 992 } });
  const idle = async () => {
    await page.waitForFunction(() => !document.querySelector(".cand-table .ant-spin-spinning"), null, { timeout: 120000 });
    await page.waitForLoadState("networkidle");
    await page.waitForTimeout(400);
  };
  await page.goto(demo.base + "/", { waitUntil: "networkidle" });
  // The workbench opens on the start page; hold it briefly, then enter the protocol's workflow.
  await page.locator(".start-doc").filter({ hasText: PDF[0] }).waitFor();
  await page.waitForTimeout(1200);
  await page.locator(".start-doc").filter({ hasText: PDF[0] }).click();
  await page.locator(".cand-table tbody tr.ant-table-row").first().waitFor({ timeout: 120000 });
  if (!(await page.locator(".pdfcard").innerText()).includes(PDF[0])) {
    await page.locator(".pdfcard .doc-switch").click();
    await page.locator(".ant-dropdown:visible .ant-dropdown-menu-item").filter({ hasText: PDF[0] }).click();
  }
  await page.waitForFunction((count) => document.querySelectorAll(".scene").length === count, PDF[1]);
  for (const [index, title] of SCENES.entries()) {
    await page.locator(".scene").filter({ has: page.locator(".t", { hasText: title }) }).first().click();
    await idle();
    await page.screenshot({ path: path.join(FRAMES, `frame-${index}.png`) });
  }
} finally {
  await browser.close();
  demo.stop();
}

const assemble = `
import sys
from pathlib import Path
from PIL import Image
frames_dir, target = Path(sys.argv[1]), Path(sys.argv[2])
frames = []
for path in sorted(frames_dir.glob("frame-*.png")):
    image = Image.open(path).convert("RGB")
    image = image.resize((1100, round(image.height * 1100 / image.width)), Image.LANCZOS)
    frames.append(image.quantize(colors=128, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE))
frames[0].save(target, save_all=True, append_images=frames[1:], duration=2600, loop=0, optimize=True)
print(target, target.stat().st_size)
`;
const result = spawnSync(python(), ["-c", assemble, FRAMES, TARGET], { encoding: "utf8" });
if (result.status !== 0) throw new Error(result.stderr);
console.log(result.stdout.trim());
