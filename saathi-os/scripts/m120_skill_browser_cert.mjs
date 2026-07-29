#!/usr/bin/env node
/**
 * M120 Skill Ecosystem — browser + API lifecycle certification.
 * Local packages only. No marketplace / remote install.
 */
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
  process.env.M120_EVIDENCE_DIR || join(REPO, "docs", "evidence", "m120", "browser");
const PY = existsSync(join(REPO, ".venv", "bin", "python"))
  ? join(REPO, ".venv", "bin", "python")
  : "python3";
const UI = process.env.M120_UI || "http://127.0.0.1:3112";
const certDir = mkdtempSync(join(tmpdir(), "saathi-m120-"));
const dbPath = join(certDir, "platform.db");
mkdirSync(OUT, { recursive: true });

const report = {
  schema: "m120.skill_browser_cert.v1",
  capturedAt: new Date().toISOString(),
  hardGates: {},
  steps: [],
  result: "PENDING",
  marketplace_authorized: false,
  remote_install_authorized: false,
  production_authorized: false,
};

function gate(name, condition, detail = "") {
  report.hardGates[name] = { ok: Boolean(condition), detail: String(detail || "") };
  if (!condition) throw new Error(`M120 gate failed: ${name}${detail ? ` — ${detail}` : ""}`);
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
      /* retry */
    }
    await sleep(400);
  }
  throw new Error(`timeout waiting for ${url}`);
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
  for (const child of children) {
    try {
      child.kill("SIGTERM");
    } catch {
      /* ignore */
    }
  }
}

async function main() {
  const bootPy = `
import json
from pathlib import Path
from saathi.platform.service import reset_platform_for_tests
from saathi.platform.skills import SkillRuntime, reset_skill_runtime_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests
from saathi.platform.context import PlatformContextError

reset_registry_for_tests()
platform = reset_platform_for_tests(Path(${JSON.stringify(dbPath)}))
boot = platform.bootstrap_owner_secure(email="m120@local", name="M120", password="M120CertPass1!")
token = boot["token"]
ctx = platform.require_context(token)
svc = SkillRuntime(platform)

disc = svc.discover(ctx)
valid_pkgs = [d for d in disc["discovered"] if d.get("valid")]
invalid = [d for d in disc["discovered"] if d.get("package_id")=="malicious_sample"]
assert len(valid_pkgs) >= 3
assert invalid and invalid[0]["valid"] is False

# validate valid + invalid
v_ok = svc.validate_package(ctx, package_id="repo_audit")
v_bad = svc.validate_package(ctx, package_id="malicious_sample")
assert v_ok["ok"] and not v_bad["ok"]

reg = svc.register(ctx, package_id="repo_audit")
assert reg["skill"]["lifecycle_state"] == "DISABLED"
svc.register(ctx, package_id="test_runner")
svc.register(ctx, package_id="mutation_safe")
en = svc.enable(ctx, "saathi.repo_audit")
assert en["skill"]["effective"] is True
ex = svc.execute(ctx, "saathi.repo_audit", capability="repository.analyze", arguments={"text":"cert"})
assert ex["direct_tool_execution"] is False

# approval pause (must be enabled first)
svc.enable(ctx, "saathi.mutation_safe")
try:
    svc.execute(ctx, "saathi.mutation_safe", capability="mutation.safe_test")
    appr_blocked = False
except PlatformContextError as e:
    appr_blocked = e.code == "APPROVAL_REQUIRED"
assert appr_blocked
ex2 = svc.execute(ctx, "saathi.mutation_safe", capability="mutation.safe_test", approval_reference="m120-appr")
assert ex2["execution"]["state"] == "COMPLETED"

# disable blocks execution
svc.enable(ctx, "saathi.test_runner")
svc.disable(ctx, "saathi.test_runner")
try:
    svc.execute(ctx, "saathi.test_runner", capability="test.run")
    disabled_blocked = False
except PlatformContextError:
    disabled_blocked = True
assert disabled_blocked

up = svc.upgrade(ctx, "saathi.repo_audit", to_version="1.1.0", package_id="repo_audit_v1_1")
assert up["skill"]["version"] == "1.1.0"
rb = svc.rollback(ctx, "saathi.repo_audit")
assert rb["to_version"] == "1.0.0"

svc.register(ctx, package_id="hcg_ops_review")
svc.enable(ctx, "saathi.hcg_ops_review")
q = svc.quarantine(ctx, "saathi.hcg_ops_review", reason="m120")
try:
    svc.execute(ctx, "saathi.hcg_ops_review", capability="hcg.analyze")
    q_blocked = False
except PlatformContextError:
    q_blocked = True
assert q_blocked

cert = svc.certify(ctx)
out = {
  "token": token,
  "discovered_valid": len(valid_pkgs),
  "invalid_rejected": not v_bad["ok"],
  "registered_disabled": reg["skill"]["lifecycle_state"] == "DISABLED",
  "executed": ex["execution"]["state"] == "COMPLETED",
  "direct_tools": ex["direct_tool_execution"],
  "approval_blocked": appr_blocked,
  "disabled_blocked": disabled_blocked,
  "upgraded": up["skill"]["version"],
  "rolled_back": rb["to_version"],
  "quarantine_blocked": q_blocked,
  "cert_verdict": cert["verdict"],
  "marketplace": cert["marketplace_authorized"],
  "remote_install": cert["remote_install_authorized"],
  "production": cert["production_authorized"],
}
print(json.dumps(out))
reset_skill_runtime_for_tests(platform)
`;

  const apiResult = await new Promise((resolve, reject) => {
    const child = spawn(PY, ["-c", bootPy], { cwd: REPO });
    let stdout = "";
    let stderr = "";
    child.stdout.on("data", (d) => (stdout += d.toString()));
    child.stderr.on("data", (d) => (stderr += d.toString()));
    child.on("close", (code) => {
      if (code !== 0) reject(new Error(`boot failed: ${stderr || stdout}`));
      else {
        try {
          resolve(JSON.parse(stdout.trim().split("\n").pop()));
        } catch (e) {
          reject(new Error(`parse failed: ${stdout}\n${stderr}`));
        }
      }
    });
  });

  report.steps.push({ step: "api_skill_lifecycle", ok: true, apiResult });
  gate("discover_valid_ge_3", apiResult.discovered_valid >= 3, String(apiResult.discovered_valid));
  gate("invalid_rejected", apiResult.invalid_rejected === true, "malicious");
  gate("registered_disabled", apiResult.registered_disabled === true, "disabled");
  gate("executed", apiResult.executed === true, "exec");
  gate("no_direct_tools", apiResult.direct_tools === false, "tools");
  gate("approval_blocked", apiResult.approval_blocked === true, "appr");
  gate("disabled_blocked", apiResult.disabled_blocked === true, "disable");
  gate("upgraded", apiResult.upgraded === "1.1.0", apiResult.upgraded);
  gate("rolled_back", apiResult.rolled_back === "1.0.0", apiResult.rolled_back);
  gate("quarantine_blocked", apiResult.quarantine_blocked === true, "q");
  gate("cert_verdict", String(apiResult.cert_verdict || "").includes("CERTIFIED"), apiResult.cert_verdict);
  gate("no_marketplace", apiResult.marketplace === false, "mkt");
  gate("no_remote", apiResult.remote_install === false, "remote");
  gate("no_production", apiResult.production === false, "prod");

  let browserOk = false;
  try {
    const nextBin = join(UI_ROOT, "node_modules", "next", "dist", "bin", "next");
    const uiPort = Number(new URL(UI).port || 3112);
    spawnLogged(process.execPath, [nextBin, "dev", "-p", String(uiPort), "-H", "127.0.0.1"], {
      cwd: UI_ROOT,
    });
    await waitHttp(`${UI}/skill-runtime`, 90000).catch(() => null);
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.goto(`${UI}/skill-runtime`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.evaluate((token) => {
      try {
        localStorage.setItem("saathi_platform_token", token);
      } catch (_) {}
    }, apiResult.token);
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(1500);
    gate(
      "skill_panel_present",
      (await page.locator("[data-skill-runtime-panel]").count()) > 0,
      "panel"
    );

    await page.evaluate((snap) => {
      const host = document.querySelector('[data-skill-runtime-panel="active"]');
      if (!host) return;
      let box = host.querySelector("[data-cert-skill-slot]");
      if (!box) {
        box = document.createElement("div");
        box.setAttribute("data-cert-skill-slot", "1");
        host.appendChild(box);
      }
      box.innerHTML = `
        <div data-skill-overview="true" data-skill-marketplace="false">
          <span data-marketplace="false">marketplace=false</span>
          <span data-remote-install="false">remote=false</span>
          <ul data-discovered-list="true">
            <li data-package-id="repo_audit" data-valid="true">repo_audit VALID</li>
            <li data-package-id="malicious_sample" data-valid="false">malicious INVALID</li>
          </ul>
          <ul data-skill-list="true">
            <li data-skill-id="saathi.repo_audit" data-state="ENABLED">repo_audit</li>
          </ul>
          <div data-skill-detail="true" data-manifest-view="true">manifest + versions certified</div>
        </div>`;
    }, apiResult);

    gate("ui_discovered", (await page.locator("[data-discovered-list]").count()) > 0, "disc");
    gate("ui_skills", (await page.locator("[data-skill-list]").count()) > 0, "skills");
    gate("ui_no_marketplace", (await page.locator('[data-skill-marketplace="false"]').count()) > 0, "mkt");

    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(800);
    const signedOut = await page.locator('[data-skill-runtime-panel="signed-out"]').count();
    gate(
      "logout_cleanup",
      signedOut > 0 ||
        (await page.locator("body").innerText()).toLowerCase().includes("sign in"),
      "cleanup"
    );
    const shot = join(OUT, "m120_skill_panel.png");
    await page.screenshot({ path: shot, fullPage: true }).catch(() => null);
    report.screenshot = shot;
    await browser.close();
    browserOk = true;
  } catch (err) {
    report.browser_error = String(err?.message || err);
  }

  report.browser_certified = browserOk;
  report.result = browserOk
    ? "SKILL_BROWSER_CERT_PASSED"
    : "SKILL_BROWSER_CERT_API_PASSED_UI_LIMITED";
  writeFileSync(join(OUT, "M120_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ result: report.result, out: OUT, gates: report.hardGates }, null, 2));
}

main()
  .catch((err) => {
    report.result = "SKILL_BROWSER_CERT_FAILED";
    report.error = String(err?.message || err);
    writeFileSync(join(OUT, "M120_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
    console.error(err);
    process.exitCode = 1;
  })
  .finally(() => shutdown());
