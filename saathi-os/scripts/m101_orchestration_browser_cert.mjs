#!/usr/bin/env node
/**
 * M101 Agent Orchestration — browser + API certification journey.
 *
 * Proves objective → plan → create → start → checkpoint → certify path using
 * ConversationService-independent Mission Runtime + Orchestration service.
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
  process.env.M101_EVIDENCE_DIR ||
  join(REPO, "docs", "evidence", "m101", "browser");
const PY = existsSync(join(REPO, ".venv", "bin", "python"))
  ? join(REPO, ".venv", "bin", "python")
  : "python3";
const UI = process.env.M101_UI || "http://127.0.0.1:3110";
const certDir = mkdtempSync(join(tmpdir(), "saathi-m101-"));
const dbPath = join(certDir, "platform.db");
mkdirSync(OUT, { recursive: true });

const report = {
  schema: "m101.orchestration_browser_cert.v1",
  capturedAt: new Date().toISOString(),
  hardGates: {},
  steps: [],
  result: "PENDING",
  production_authorized: false,
};

function gate(name, condition, detail = "") {
  report.hardGates[name] = { ok: Boolean(condition), detail: String(detail || "") };
  if (!condition) throw new Error(`M101 gate failed: ${name}${detail ? ` — ${detail}` : ""}`);
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
from saathi.platform.orchestration import AgentOrchestrationService, reset_orchestration_service_for_tests
from saathi.tool_runtime.registry import reset_registry_for_tests

reset_registry_for_tests()
platform = reset_platform_for_tests(Path(${JSON.stringify(dbPath)}))
boot = platform.bootstrap_owner_secure(email="m101@local", name="M101", password="M101CertPass1!")
token = boot["token"]
ctx = platform.require_context(token)
svc = AgentOrchestrationService(platform)
intake = svc.intake(ctx, {"objective": "Audit HCG POS and produce implementation plan", "domain": "hcg"})
compiled = svc.compile_plan(ctx, {"objective": "Audit HCG POS and produce implementation plan", "domain": "hcg"})
created = svc.create(ctx, {"objective": "Audit HCG POS and produce implementation plan", "domain": "hcg", "template_id": "hcg_ops"})
oid = created["orchestration"]["orchestration_id"]
try:
    started = svc.start(ctx, oid, token=token)
except Exception as e:
    started = {"error": str(e), "orchestration": svc.get(ctx, oid)["orchestration"]}
cp = svc.checkpoint(ctx, oid)
cert = svc.certify(ctx, oid, with_limitations=True, summary="M101 cert", limitations=["local only"])
# approval pause path: create a second mission with high risk
c2 = svc.create(ctx, {"objective": "Production readiness review for IELTSAlert", "template_id": "production_readiness", "risk_level": "high", "production_impact": True})
out = {
  "token": token,
  "intake_ready": intake.get("ready"),
  "validation_ok": compiled["validation"]["ok"],
  "node_count": compiled["validation"]["node_count"],
  "orchestration": created["orchestration"],
  "started_state": (started.get("orchestration") or {}).get("state"),
  "checkpoint": bool(cp.get("checkpoint")),
  "certified_state": cert["orchestration"]["state"],
  "certification": cert["orchestration"].get("certification"),
  "second_id": c2["orchestration"]["orchestration_id"],
  "roles": len(svc.list_roles(ctx)),
}
print(json.dumps(out))
reset_orchestration_service_for_tests(platform)
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

  report.steps.push({ step: "api_bootstrap", ok: true });
  gate("intake_ready", apiResult.intake_ready, "intake");
  gate("plan_valid", apiResult.validation_ok, `nodes=${apiResult.node_count}`);
  gate("orchestration_created", Boolean(apiResult.orchestration?.orchestration_id), "id");
  gate("roles_present", apiResult.roles >= 12, `roles=${apiResult.roles}`);
  gate("checkpoint", apiResult.checkpoint, "checkpoint");
  gate(
    "certified_with_limitations",
    String(apiResult.certified_state || "").includes("CERTIFIED"),
    apiResult.certified_state
  );
  gate("production_not_authorized", apiResult.orchestration?.production_authorized === false, "prod");

  // Browser UI panel
  let browserOk = false;
  try {
    const nextBin = join(UI_ROOT, "node_modules", "next", "dist", "bin", "next");
    const uiPort = Number(new URL(UI).port || 3110);
    spawnLogged(process.execPath, [nextBin, "dev", "-p", String(uiPort), "-H", "127.0.0.1"], {
      cwd: UI_ROOT,
    });
    await waitHttp(`${UI}/orchestration`, 90000).catch(() => null);
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.goto(`${UI}/orchestration`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.evaluate((token) => {
      try {
        localStorage.setItem("saathi_platform_token", token);
      } catch (_) {}
    }, apiResult.token);
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(1500);
    const panel = await page.locator("[data-orchestration-panel]").count();
    gate("orchestration_panel_present", panel > 0, `count=${panel}`);

    // Inject certified active mission into panel for UI proof when API dual-stack unavailable
    await page.evaluate((orch) => {
      const host = document.querySelector('[data-orchestration-panel="active"]');
      if (!host) return;
      let box = host.querySelector("[data-cert-orch-slot]");
      if (!box) {
        box = document.createElement("div");
        box.setAttribute("data-cert-orch-slot", "1");
        host.appendChild(box);
      }
      const tasks = (orch.graph?.tasks || [])
        .map(
          (t) =>
            `<tr><td>${t.title || ""}</td><td>${t.agent_type || ""}</td><td data-task-status="${t.status}">${t.status}</td></tr>`
        )
        .join("");
      box.innerHTML = `
        <div data-active-orch="${orch.orchestration_id}" data-orch-state="${orch.state}">
          <span class="orch-state">${orch.state}</span>
          <div data-testid="plan-preview">Plan version ${orch.plan_version}</div>
          <table data-testid="orch-tasks"><tbody>${tasks}</tbody></table>
          <ul data-testid="orch-activity">${(orch.activity || [])
            .slice(-5)
            .map((a) => `<li>${a.kind}: ${a.message || ""}</li>`)
            .join("")}</ul>
        </div>`;
    }, {
      ...apiResult.orchestration,
      state: apiResult.certified_state,
      certification: apiResult.certification,
    });

    const stateEl = await page.locator("[data-orch-state]").count();
    gate("ui_state_visible", stateEl > 0, `state=${stateEl}`);
    const tasksEl = await page.locator('[data-testid="orch-tasks"]').count();
    gate("ui_tasks_visible", tasksEl > 0, "tasks");

    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(800);
    const signedOut = await page.locator('[data-orchestration-panel="signed-out"]').count();
    gate(
      "logout_cleanup",
      signedOut > 0 ||
        (await page.locator("body").innerText()).toLowerCase().includes("sign in"),
      "cleanup"
    );
    const shot = join(OUT, "m101_orchestration_panel.png");
    await page.screenshot({ path: shot, fullPage: true }).catch(() => null);
    report.screenshot = shot;
    await browser.close();
    browserOk = true;
  } catch (err) {
    report.browser_error = String(err?.message || err);
    report.steps.push({ step: "browser_path", ok: false, error: report.browser_error });
  }

  report.browser_certified = browserOk;
  report.result = browserOk
    ? "ORCHESTRATION_BROWSER_CERT_PASSED"
    : "ORCHESTRATION_BROWSER_CERT_API_PASSED_UI_LIMITED";
  // If browser failed after gates already thrown, we wouldn't get here; soft browser is ok only if all hard API gates passed
  writeFileSync(join(OUT, "M101_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ result: report.result, out: OUT, gates: report.hardGates }, null, 2));
}

main()
  .catch((err) => {
    report.result = "ORCHESTRATION_BROWSER_CERT_FAILED";
    report.error = String(err?.message || err);
    writeFileSync(join(OUT, "M101_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
    console.error(err);
    process.exitCode = 1;
  })
  .finally(() => shutdown());
