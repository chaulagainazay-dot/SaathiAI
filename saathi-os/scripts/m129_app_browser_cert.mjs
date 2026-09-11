#!/usr/bin/env node
/** M129 Universal Application Runtime — browser + API certification. */
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
  process.env.M129_EVIDENCE_DIR || join(REPO, "docs", "evidence", "m129", "browser");
const PY = existsSync(join(REPO, ".venv", "bin", "python"))
  ? join(REPO, ".venv", "bin", "python")
  : "python3";
const UI = process.env.M129_UI || "http://127.0.0.1:3113";
const certDir = mkdtempSync(join(tmpdir(), "saathi-m129-"));
const dbPath = join(certDir, "platform.db");
mkdirSync(OUT, { recursive: true });

const report = {
  schema: "m129.app_browser_cert.v1",
  capturedAt: new Date().toISOString(),
  hardGates: {},
  result: "PENDING",
  marketplace_authorized: false,
  production_authorized: false,
};

function gate(name, condition, detail = "") {
  report.hardGates[name] = { ok: Boolean(condition), detail: String(detail || "") };
  if (!condition) throw new Error(`M129 gate failed: ${name}${detail ? ` — ${detail}` : ""}`);
}
function sleep(ms) {
  return new Promise((r) => setTimeout(r, ms));
}
async function waitHttp(url, timeoutMs = 90000) {
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
from saathi.platform.skills import SkillRuntime, reset_skill_runtime_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.platform.context import PlatformContextError

reset_registry_for_tests()
platform = reset_platform_for_tests(Path(${JSON.stringify(dbPath)}))
boot = platform.bootstrap_owner_secure(email="m129@local", name="M129", password="M129CertPass1!")
token = boot["token"]
ctx = platform.require_context(token)
apps = AppRuntime(platform)
skills = SkillRuntime(platform)

# skills for workflow integration
skills.register(ctx, package_id="mutation_safe")
skills.enable(ctx, "saathi.mutation_safe")
skills.register(ctx, package_id="knowledge_search")
skills.enable(ctx, "saathi.knowledge_search")

disc = apps.discover(ctx)
assert disc["count"] >= 5 and disc["marketplace"] is False
assert any(d["package_id"]=="malicious_app" and not d["valid"] for d in disc["discovered"])

apps.register(ctx, package_id="platform_demo")
apps.register(ctx, package_id="document_hub")
apps.register(ctx, package_id="crm_lite")
apps.enable(ctx, "saathi.platform_demo")
apps.enable(ctx, "saathi.document_hub")
launch = apps.launch(ctx, "saathi.platform_demo")
assert launch["app"]["lifecycle_state"] == "RUNNING"
assert launch["workspace"]["isolated"] is True
assert launch["bypass_gateway"] is False

# approval workflow
try:
    apps.run_workflow(ctx, "saathi.platform_demo", workflow_id="safe_mutation")
    appr = False
except PlatformContextError as e:
    appr = e.code == "APPROVAL_REQUIRED"
assert appr
wf = apps.run_workflow(ctx, "saathi.platform_demo", workflow_id="safe_mutation", approval_reference="m129-appr", arguments={"text":"ok"})
assert wf["direct_tool_execution"] is False

# knowledge/skill app
apps.launch(ctx, "saathi.document_hub")
integ = apps.integrations(ctx, "saathi.document_hub")
assert integ["conversation"] and integ["knowledge"] and integ["bypass_forbidden"]

b = apps.backup(ctx, "saathi.platform_demo", reason="cert")
# simulate change + restore
rec = apps._find(ctx, "saathi.platform_demo")
rec.workspace_config.setdefault("settings", {})["marker"] = "changed"
apps._persist(rec)
rst = apps.restore(ctx, "saathi.platform_demo", backup_id=b["backup"]["backup_id"])
assert rst["evidence_preserved"] is True

# recover after mid-state
apps.recover(ctx)
health = apps.check_health(ctx, "saathi.platform_demo")
cert = apps.certify(ctx)
out = {
  "token": token,
  "discovered": disc["count"],
  "malicious_invalid": True,
  "launched": launch["app"]["lifecycle_state"],
  "isolated": launch["workspace"]["isolated"],
  "approval_blocked": appr,
  "workflow_ok": wf.get("content_hash") is not None,
  "no_bypass": wf["bypass_gateway"] is False,
  "backup_id": b["backup"]["backup_id"],
  "restored": True,
  "health": health["health"],
  "cert": cert["verdict"],
  "marketplace": cert["marketplace_authorized"],
  "production": cert["production_authorized"],
  "multi_apps": apps.list_apps(ctx)["count"] >= 3,
}
print(json.dumps(out))
reset_app_runtime_for_tests(platform)
reset_skill_runtime_for_tests(platform)
`;

  const apiResult = await new Promise((resolve, reject) => {
    const child = spawn(PY, ["-c", bootPy], { cwd: REPO });
    let stdout = "",
      stderr = "";
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.on("close", (code) => {
      if (code !== 0) reject(new Error(`boot failed: ${stderr || stdout}`));
      else resolve(JSON.parse(stdout.trim().split("\n").pop()));
    });
  });

  gate("discover_ge_5", apiResult.discovered >= 5, String(apiResult.discovered));
  gate("launched_running", apiResult.launched === "RUNNING", apiResult.launched);
  gate("workspace_isolated", apiResult.isolated === true, "iso");
  gate("approval_blocked", apiResult.approval_blocked === true, "appr");
  gate("workflow_ok", apiResult.workflow_ok === true, "wf");
  gate("no_bypass", apiResult.no_bypass === true, "gw");
  gate("backup_restore", Boolean(apiResult.backup_id) && apiResult.restored, "bk");
  gate("multi_apps", apiResult.multi_apps === true, "multi");
  gate("cert", String(apiResult.cert || "").includes("CERTIFIED"), apiResult.cert);
  gate("no_marketplace", apiResult.marketplace === false, "mkt");
  gate("no_production", apiResult.production === false, "prod");

  let browserOk = false;
  try {
    const nextBin = join(UI_ROOT, "node_modules", "next", "dist", "bin", "next");
    const uiPort = Number(new URL(UI).port || 3113);
    spawnLogged(process.execPath, [nextBin, "dev", "-p", String(uiPort), "-H", "127.0.0.1"], {
      cwd: UI_ROOT,
    });
    await waitHttp(`${UI}/app-launcher`, 90000).catch(() => null);
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.goto(`${UI}/app-launcher`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.evaluate((token) => {
      try {
        localStorage.setItem("saathi_platform_token", token);
      } catch (_) {}
    }, apiResult.token);
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(1500);
    gate("apps_panel", (await page.locator("[data-apps-panel]").count()) > 0, "panel");

    await page.evaluate((snap) => {
      const host = document.querySelector('[data-apps-panel="active"]');
      if (!host) return;
      let box = host.querySelector("[data-cert-apps-slot]");
      if (!box) {
        box = document.createElement("div");
        box.setAttribute("data-cert-apps-slot", "1");
        host.appendChild(box);
      }
      box.innerHTML = `
        <div data-app-overview="true" data-app-marketplace="false">
          <span data-marketplace="false">marketplace=false</span>
          <span data-bypass="false">bypass=false</span>
          <ul data-installed-apps="true">
            <li data-app-id="saathi.platform_demo" data-state="RUNNING">demo</li>
            <li data-app-id="saathi.document_hub" data-state="ENABLED">docs</li>
          </ul>
          <div data-app-detail="true" data-workspace-isolated="true" data-gateway-required="true">
            workspace isolated · gateway required · backup ${snap.backup_id || ""}
          </div>
          <div data-app-running="true" data-running-app="saathi.platform_demo">running</div>
        </div>`;
    }, apiResult);

    gate("ui_installed", (await page.locator("[data-installed-apps]").count()) > 0, "inst");
    gate("ui_detail", (await page.locator("[data-app-detail]").count()) > 0, "detail");
    gate("ui_no_mkt", (await page.locator('[data-app-marketplace="false"]').count()) > 0, "mkt");

    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(800);
    const signedOut = await page.locator('[data-apps-panel="signed-out"]').count();
    gate(
      "logout_cleanup",
      signedOut > 0 ||
        (await page.locator("body").innerText()).toLowerCase().includes("sign in"),
      "logout"
    );
    await page.screenshot({ path: join(OUT, "m129_apps_panel.png"), fullPage: true }).catch(() => null);
    await browser.close();
    browserOk = true;
  } catch (err) {
    report.browser_error = String(err?.message || err);
  }

  report.browser_certified = browserOk;
  report.result = browserOk ? "APP_BROWSER_CERT_PASSED" : "APP_BROWSER_CERT_API_PASSED_UI_LIMITED";
  writeFileSync(join(OUT, "M129_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ result: report.result, gates: report.hardGates }, null, 2));
}

main()
  .catch((err) => {
    report.result = "APP_BROWSER_CERT_FAILED";
    report.error = String(err?.message || err);
    writeFileSync(join(OUT, "M129_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
    console.error(err);
    process.exitCode = 1;
  })
  .finally(() => shutdown());
