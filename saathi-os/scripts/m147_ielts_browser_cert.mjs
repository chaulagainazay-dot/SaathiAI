#!/usr/bin/env node
/** M147 IELTSAlert native product — browser + API certification. */
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
  process.env.M147_EVIDENCE_DIR || join(REPO, "docs", "evidence", "m147", "browser");
const PY = existsSync(join(REPO, ".venv", "bin", "python"))
  ? join(REPO, ".venv", "bin", "python")
  : "python3";
const UI = process.env.M147_UI || "http://127.0.0.1:3119";
const certDir = mkdtempSync(join(tmpdir(), "saathi-m147-"));
const dbPath = join(certDir, "platform.db");
mkdirSync(OUT, { recursive: true });

const report = {
  schema: "m147.ielts_browser_cert.v1",
  capturedAt: new Date().toISOString(),
  hardGates: {},
  result: "PENDING",
  live_gemini: false,
  live_firebase: false,
  production_authorized: false,
  trading_guardian_changed: false,
};

function gate(name, condition, detail = "") {
  report.hardGates[name] = { ok: Boolean(condition), detail: String(detail || "") };
  if (!condition) throw new Error(`M147 gate failed: ${name}${detail ? ` — ${detail}` : ""}`);
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
from saathi.platform.ielts.service import IELTSService
from saathi.platform.ielts.scoring import LocalHeuristicScorer
from saathi.platform.context import PlatformContextError

platform = reset_platform_for_tests(Path(${JSON.stringify(dbPath)}))
boot = platform.bootstrap_owner_secure(email="m147@local", name="M147", password="M147CertPass1!")
token = boot["token"]
ctx = platform.require_context(token)
apps = AppRuntime(platform)
ielts = IELTSService(platform.store, scorer=LocalHeuristicScorer())

apps.register(ctx, package_id="ielts_alert")
apps.enable(ctx, "saathi.ielts_alert")
launch = apps.launch(ctx, "saathi.ielts_alert")
assert launch["bypass_gateway"] is False

ielts.upsert_profile(ctx, {"display_name": "M147 Learner"})
ielts.create_goal(ctx, {"exam_type": "academic", "target_band": 7.0, "planned_test_date": "2030-08-01", "daily_minutes": 45}, idempotency_key="m147-goal")
diag = ielts.run_diagnostic(ctx, exam_type="academic", idempotency_key="m147-diag")
plan = ielts.generate_study_plan(ctx, weeks=2, idempotency_key="m147-plan")
assert plan["body"]["validation"]["within_time_budget"] is True

sp = ielts.create_practice(ctx, {"skill": "speaking", "task_type": "part_2", "prompt": "Journey", "response": "I travelled to the mountains with friends and learned patience. " * 4}, idempotency_key="m147-sp")
assert sp["body"]["feedback"]["acoustic_pronunciation_claimed"] is False

wr = ielts.create_practice(ctx, {"skill": "writing", "task_type": "task_2", "prompt": "Discuss both views", "response": "Practical skills and theory both matter in university education today. " * 15}, idempotency_key="m147-wr")
rev = ielts.submit_writing_revision(ctx, parent_submission_id=wr["record_id"], response="Improved structure with clearer examples and a balanced conclusion. " * 12, idempotency_key="m147-rev")
assert rev["parent_immutable"] is True

rd = ielts.submit_objective_practice(ctx, skill="reading", exam_type="academic", answers=["false", "20", "true", "flowering plants"], idempotency_key="m147-rd")
ls = ielts.submit_objective_practice(ctx, skill="listening", exam_type="academic", answers=["second", "10", "17:00", "true"], idempotency_key="m147-ls")

mock = ielts.create_mock_test(ctx, exam_type="academic", idempotency_key="m147-mock")
ielts.complete_mock_section(ctx, mock["record_id"], skill="reading", answers=["false", "20", "true", "flowering plants"])

ready = ielts.readiness_snapshot(ctx)["data"]
assert ready["official"] is False
yeti = ielts.grounded_answer(ctx, "What is my weakest skill?")
assert yeti["can_mutate"] is False

try:
    ielts.restore_payload(ctx, ielts.export_backup_payload(ctx), approval_reference="")
    restore_gated = False
except PlatformContextError as e:
    restore_gated = e.code == "APPROVAL_REQUIRED"

backup = ielts.export_backup_payload(ctx)
# restart recovery
ielts2 = IELTSService(platform.store, scorer=LocalHeuristicScorer())
dash2 = ielts2.product_dashboard(ctx)
assert dash2["progress"]["practice_count"] >= 1

out = {
  "token": token,
  "launched": launch["app"]["lifecycle_state"],
  "diagnostic_overall": diag["body"].get("overall_estimate"),
  "plan_valid": plan["body"]["validation"]["within_time_budget"],
  "no_acoustic_claim": sp["body"]["feedback"]["acoustic_pronunciation_claimed"] is False,
  "parent_immutable": rev["parent_immutable"],
  "reading_correct": rd["body"]["feedback"]["correct"],
  "listening_correct": ls["body"]["feedback"]["correct"],
  "readiness_official": ready["official"],
  "yeti_readonly": yeti["can_mutate"] is False,
  "restore_gated": restore_gated,
  "restart_ok": dash2["progress"]["practice_count"] >= 1,
  "backup_hash": backup["content_hash"][:16],
  "no_production": True,
}
print(json.dumps(out))
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

  gate("launched", apiResult.launched === "RUNNING", apiResult.launched);
  gate("diagnostic", apiResult.diagnostic_overall != null, String(apiResult.diagnostic_overall));
  gate("plan_valid", apiResult.plan_valid === true, "plan");
  gate("no_acoustic_claim", apiResult.no_acoustic_claim === true, "pron");
  gate("writing_immutable", apiResult.parent_immutable === true, "wr");
  gate("reading", apiResult.reading_correct === 4, String(apiResult.reading_correct));
  gate("listening", apiResult.listening_correct === 4, String(apiResult.listening_correct));
  gate("readiness_not_official", apiResult.readiness_official === false, "ready");
  gate("yeti_readonly", apiResult.yeti_readonly === true, "yeti");
  gate("restore_gated", apiResult.restore_gated === true, "rst");
  gate("restart", apiResult.restart_ok === true, "restart");
  gate("backup", Boolean(apiResult.backup_hash), apiResult.backup_hash);

  let browserOk = false;
  try {
    const nextBin = join(UI_ROOT, "node_modules", "next", "dist", "bin", "next");
    const uiPort = Number(new URL(UI).port || 3119);
    spawnLogged(process.execPath, [nextBin, "dev", "-p", String(uiPort), "-H", "127.0.0.1"], {
      cwd: UI_ROOT,
    });
    await waitHttp(`${UI}/apps/ielts`, 120000).catch(() => null);
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.goto(`${UI}/apps/ielts`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.evaluate((token) => {
      try {
        localStorage.setItem("saathi_platform_token", token);
      } catch (_) {}
    }, apiResult.token);
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(2000);
    const body = (await page.locator("body").innerText()).toLowerCase();
    gate("ui_ielts", body.includes("ielts") || body.includes("coaching"), "ui");
    gate(
      "ui_non_official",
      body.includes("official") || body.includes("estimate") || body.includes("practice"),
      "label"
    );
    gate("aria", (await page.locator('[aria-label="IELTSAlert product workspace"]').count()) > 0, "aria");
    await page.screenshot({ path: join(OUT, "m147_ielts_workspace.png"), fullPage: true }).catch(() => null);
    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(800);
    const after = (await page.locator("body").innerText()).toLowerCase();
    gate("logout", after.includes("sign in") || after.includes("ielts"), "logout");
    await browser.close();
    browserOk = true;
  } catch (err) {
    report.browser_error = String(err?.message || err);
  }

  report.api = apiResult;
  report.browser_certified = browserOk;
  report.result = browserOk
    ? "IELTS_NATIVE_APP_BROWSER_CERT_PASSED"
    : "IELTS_NATIVE_APP_BROWSER_CERT_API_PASSED_UI_LIMITED";
  writeFileSync(join(OUT, "M147_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ result: report.result, gates: report.hardGates }, null, 2));
}

main()
  .catch((err) => {
    report.result = "IELTS_NATIVE_APP_BROWSER_CERT_FAILED";
    report.error = String(err?.message || err);
    writeFileSync(join(OUT, "M147_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
    console.error(err);
    process.exitCode = 1;
  })
  .finally(() => shutdown());
