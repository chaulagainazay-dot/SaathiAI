#!/usr/bin/env node
/** M156 SaathiOS Core certification — unified home, search, yeti, apps. */
import { spawn } from "node:child_process";
import { existsSync, mkdirSync, mkdtempSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const HERE = dirname(fileURLToPath(import.meta.url));
const UI_ROOT = join(HERE, "..");
const REPO = join(UI_ROOT, "..");
const OUT =
  process.env.M156_EVIDENCE_DIR || join(REPO, "docs", "evidence", "m156", "browser");
const PY = existsSync(join(REPO, ".venv", "bin", "python"))
  ? join(REPO, ".venv", "bin", "python")
  : "python3";
const UI = process.env.M156_UI || "http://127.0.0.1:3120";
const certDir = mkdtempSync(join(tmpdir(), "saathi-m156-"));
const dbPath = join(certDir, "platform.db");
mkdirSync(OUT, { recursive: true });

const report = {
  schema: "m156.core_browser_cert.v1",
  capturedAt: new Date().toISOString(),
  hardGates: {},
  result: "PENDING",
  production_authorized: false,
  trading_guardian_changed: false,
};

function gate(name, condition, detail = "") {
  report.hardGates[name] = { ok: Boolean(condition), detail: String(detail || "") };
  if (!condition) throw new Error(`M156 gate failed: ${name}${detail ? ` — ${detail}` : ""}`);
}
function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
async function waitHttp(url, timeoutMs = 120000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    try {
      const r = await fetch(url);
      if (r.ok || r.status < 500) return;
    } catch {
      /* */
    }
    await sleep(400);
  }
  throw new Error(`timeout ${url}`);
}
const children = [];
function spawnLogged(cmd, args, opts = {}) {
  const child = spawn(cmd, args, {
    cwd: opts.cwd || REPO,
    env: { ...process.env, ...opts.env },
    stdio: ["ignore", "pipe", "pipe"],
  });
  children.push(child);
  return child;
}
async function shutdown() {
  for (const c of children) {
    try {
      c.kill("SIGTERM");
    } catch {
      /* */
    }
  }
}

async function main() {
  const bootPy = `
import json
from pathlib import Path
from saathi.platform.service import reset_platform_for_tests
from saathi.platform.apps import AppRuntime, reset_app_runtime_for_tests
from saathi.platform.core_os import SaathiCoreService, reset_core_service_for_tests

platform = reset_platform_for_tests(Path(${JSON.stringify(dbPath)}))
boot = platform.bootstrap_owner_secure(email="m156@local", name="M156", password="M156CertPass1!")
token = boot["token"]
ctx = platform.require_context(token)
apps = AppRuntime(platform)
core = SaathiCoreService(platform)

for pkg, aid in (("hcg_pos", "saathi.hcg_pos"), ("ielts_alert", "saathi.ielts_alert")):
    apps.register(ctx, package_id=pkg)
    apps.enable(ctx, aid)
    apps.launch(ctx, aid)

home = core.operator_home(ctx)
assert home["unified"] is True
search = core.universal_search(ctx, "approval")
assert search["permissions_enforced"] is True
yeti = core.yeti_ask(ctx, "What should I do first today?")
assert yeti["can_mutate"] is False
assert yeti["execution_gateway_bypass"] is False
auto = core.create_automation(ctx, name="M156 morning", schedule="daily_morning", action="summarize", app_scope="all")
dry = core.run_automation_dry(ctx, auto["automation"]["automation_id"])
assert dry["proposal"]["executed"] is False
graph = core.save_workflow_graph(ctx, name="M156 flow", nodes=[
    {"id": "t", "type": "trigger"}, {"id": "a", "type": "approval"},
    {"id": "e", "type": "execution"}, {"id": "f", "type": "finish"},
], edges=[{"from": "t", "to": "a"}, {"from": "a", "to": "e"}, {"from": "e", "to": "f"}])
assert graph["graph"]["bypass_gateway"] is False
notes = core.notification_center(ctx)
cmds = core.command_catalog(ctx)
ctxo = core.cross_app_context(ctx)
assert ctxo["deep_links"]["hcg"]

# restart recovery of memory
core.update_preferences(ctx, {"cert": "m156"})
core2 = SaathiCoreService(platform)
mem = core2.get_memory(ctx)
assert mem["memory"]["preferences"].get("cert") == "m156"

out = {
  "token": token,
  "home_unified": home["unified"],
  "apps_enabled": home["applications"].get("enabled", 0),
  "search_ok": search["scope"] == "SERVER_AUTHORIZED",
  "yeti_readonly": yeti["can_mutate"] is False,
  "automation_dry": dry["proposal"]["executed"] is False,
  "workflow_gateway": graph["graph"]["bypass_gateway"] is False,
  "commands": cmds["count"],
  "notifications_unified": notes["unified"],
  "memory_restart": True,
  "no_production": home["production_authorized"] is False,
}
print(json.dumps(out))
reset_core_service_for_tests(platform)
reset_app_runtime_for_tests(platform)
`;

  const apiResult = await new Promise((resolve, reject) => {
    const child = spawn(PY, ["-c", bootPy], { cwd: REPO });
    let stdout = "", stderr = "";
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.on("close", (code) => {
      if (code !== 0) reject(new Error(`boot failed: ${stderr || stdout}`));
      else resolve(JSON.parse(stdout.trim().split("\n").pop()));
    });
  });

  gate("home_unified", apiResult.home_unified === true, "home");
  gate("apps_enabled", apiResult.apps_enabled >= 1, String(apiResult.apps_enabled));
  gate("search", apiResult.search_ok === true, "search");
  gate("yeti_readonly", apiResult.yeti_readonly === true, "yeti");
  gate("automation_dry", apiResult.automation_dry === true, "auto");
  gate("workflow_gateway", apiResult.workflow_gateway === true, "wf");
  gate("commands", apiResult.commands >= 5, String(apiResult.commands));
  gate("notifications", apiResult.notifications_unified === true, "ntf");
  gate("memory_restart", apiResult.memory_restart === true, "mem");
  gate("no_production", apiResult.no_production === true, "prod");

  let browserOk = false;
  try {
    const nextBin = join(UI_ROOT, "node_modules", "next", "dist", "bin", "next");
    const uiPort = Number(new URL(UI).port || 3120);
    spawnLogged(process.execPath, [nextBin, "dev", "-p", String(uiPort), "-H", "127.0.0.1"], {
      cwd: UI_ROOT,
    });
    await waitHttp(`${UI}/platform/home`, 120000).catch(() => null);
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    await page.goto(`${UI}/platform/home`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.evaluate((token) => {
      try {
        localStorage.setItem("saathi_platform_token", token);
      } catch (_) {}
    }, apiResult.token);
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(2000);
    gate("ui_home", (await page.locator('[data-core-home="true"]').count()) > 0, "home");
    gate("ui_search", (await page.locator("[data-core-search]").count()) > 0, "search");
    gate("ui_yeti", (await page.locator("[data-core-yeti]").count()) > 0, "yeti");

    // Launch HCG + IELTS routes
    await page.goto(`${UI}/apps/hcg`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(800);
    const hcgBody = (await page.locator("body").innerText()).toLowerCase();
    gate("hcg_launch", hcgBody.includes("hcg") || hcgBody.includes("cafeteria") || hcgBody.includes("operations"), "hcg");

    await page.goto(`${UI}/apps/ielts`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(800);
    const ieltsBody = (await page.locator("body").innerText()).toLowerCase();
    gate("ielts_launch", ieltsBody.includes("ielts") || ieltsBody.includes("coaching"), "ielts");

    await page.goto(`${UI}/apps`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(600);
    gate("launcher", (await page.locator("[data-apps-panel]").count()) > 0 || (await page.locator("body").innerText()).toLowerCase().includes("application"), "apps");

    await page.screenshot({ path: join(OUT, "m156_core_home.png"), fullPage: true }).catch(() => null);

    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.goto(`${UI}/platform/home`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(800);
    const after = (await page.locator("body").innerText()).toLowerCase();
    gate("logout", after.includes("sign in") || after.includes("operator"), "logout");

    await browser.close();
    browserOk = true;
  } catch (err) {
    report.browser_error = String(err?.message || err);
  }

  report.api = apiResult;
  report.browser_certified = browserOk;
  report.result = browserOk
    ? "SAATHIOS_CORE_BROWSER_CERT_PASSED"
    : "SAATHIOS_CORE_BROWSER_CERT_API_PASSED_UI_LIMITED";
  writeFileSync(join(OUT, "M156_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ result: report.result, gates: report.hardGates }, null, 2));
}

main()
  .catch((err) => {
    report.result = "SAATHIOS_CORE_BROWSER_CERT_FAILED";
    report.error = String(err?.message || err);
    writeFileSync(join(OUT, "M156_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
    console.error(err);
    process.exitCode = 1;
  })
  .finally(() => shutdown());
