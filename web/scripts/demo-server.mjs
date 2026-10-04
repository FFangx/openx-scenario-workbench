// Starts the API on a throwaway data folder seeded with the self-authored demo workspace
// (scripts/seed_demo_workspace.py). It serves the built UI from web/dist, so run `npm run build` first.
// Never points at the user's data: OPENX_DATA_DIR is always a fresh temp folder.
import { spawn, spawnSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const WEB = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const REPO = path.resolve(WEB, "..");

function python() {
  if (process.env.OPENX_PYTHON) return process.env.OPENX_PYTHON;
  const venv = process.platform === "win32" ? path.join(REPO, ".venv", "Scripts", "python.exe") : path.join(REPO, ".venv", "bin", "python");
  return fs.existsSync(venv) ? venv : "python";
}

/** Model credentials from the developer's shell must not reach the demo service. */
function cleanEnv(dataDir) {
  const env = { ...process.env, OPENX_DATA_DIR: dataDir, PYTHONUTF8: "1" };
  for (const key of ["OPENX_LLM_URL", "OPENX_LLM_MODEL", "OPENX_LLM_API_KEY", "DEEPSEEK_API_KEY"]) delete env[key];
  return env;
}

export async function startDemo({ port = 8767, preferences = { language: "en", encoder: "hashing" } } = {}) {
  if (!fs.existsSync(path.join(WEB, "dist", "index.html"))) throw new Error("web/dist is missing; run `npm run build` first.");
  const dataDir = fs.mkdtempSync(path.join(os.tmpdir(), "openx-demo-"));
  const env = cleanEnv(dataDir);
  const seeded = spawnSync(python(), [path.join(REPO, "scripts", "seed_demo_workspace.py"), dataDir], { env, encoding: "utf8" });
  if (seeded.status !== 0) throw new Error(`Seeding failed:\n${seeded.stderr}`);
  const seed = JSON.parse(seeded.stdout.trim().split("\n").pop());

  const server = spawn(python(), ["-m", "openx_workbench.api", "--port", String(port)], { env, cwd: REPO, stdio: ["ignore", "ignore", "pipe"] });
  let log = "";
  server.stderr.on("data", (d) => (log += d));
  const base = `http://127.0.0.1:${port}`;
  for (let i = 0; ; i++) {
    try {
      if ((await fetch(`${base}/api/health`)).ok) break;
    } catch { /* not up yet */ }
    if (server.exitCode !== null || i > 100) throw new Error(`API did not start:\n${log}`);
    await new Promise((r) => setTimeout(r, 200));
  }
  await fetch(`${base}/api/settings/preferences`, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(preferences) });

  const stop = () => {
    server.kill();
    fs.rmSync(dataDir, { recursive: true, force: true, maxRetries: 5, retryDelay: 200 });
  };
  return { base, dataDir, seed, stop };
}
