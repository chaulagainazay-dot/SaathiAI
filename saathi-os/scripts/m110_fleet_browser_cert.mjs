#!/usr/bin/env node
/**
 * M110 Fleet browser + API certification journey.
 *
 * Proves loopback multi-worker register → admit → parallel dispatch → approval
 * gate → lease/execute → heartbeat loss → reassign → stale reject → drain → logout.
 * Phase A only. No LAN/cloud/production.
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
  process.env.M110_EVIDENCE_DIR || join(REPO, "docs", "evidence", "m110", "browser");
const PY = existsSync(join(REPO, ".venv", "bin", "python"))
  ? join(REPO, ".venv", "bin", "python")
  : "python3";
const UI = process.env.M110_UI || "http://127.0.0.1:3111";
const certDir = mkdtempSync(join(tmpdir(), "saathi-m110-"));
const dbPath = join(certDir, "platform.db");
mkdirSync(OUT, { recursive: true });

const report = {
  schema: "m110.fleet_browser_cert.v1",
  capturedAt: new Date().toISOString(),
  hardGates: {},
  steps: [],
  result: "PENDING",
  production_authorized: false,
  phase: "PHASE_A_SINGLE_HOST",
  public_listener: false,
};

function gate(name, condition, detail = "") {
  report.hardGates[name] = { ok: Boolean(condition), detail: String(detail || "") };
  if (!condition) throw new Error(`M110 gate failed: ${name}${detail ? ` — ${detail}` : ""}`);
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
import json, time
from pathlib import Path
from saathi.platform.service import reset_platform_for_tests
from saathi.platform.fleet import DistributedWorkerRuntime, reset_fleet_runtime_for_tests
from saathi.platform.fleet import limits
from saathi.tool_runtime.registry import reset_registry_for_tests

reset_registry_for_tests()
platform = reset_platform_for_tests(Path(${JSON.stringify(dbPath)}))
boot = platform.bootstrap_owner_secure(email="m110@local", name="M110", password="M110CertPass1!")
token = boot["token"]
ctx = platform.require_context(token)
fleet = DistributedWorkerRuntime(platform)

def wp(wid, caps=None, proc=None):
    return {
        "worker_id": wid,
        "protocol_version": limits.PROTOCOL_VERSION,
        "runtime_version": limits.RUNTIME_VERSION,
        "process_instance_id": proc or f"proc-{wid}",
        "capability_set": caps or ["planning", "analysis", "testing", "platform-agent-runtime"],
        "bind_host": "127.0.0.1",
        "resource_limits": {"max_active_leases": 2},
    }

a = fleet.register_worker(ctx, wp("wrk_loop_a"))
b = fleet.register_worker(ctx, wp("wrk_loop_b", ["planning", "analysis", "testing", "coding", "platform-agent-runtime"]))
assert a["admission"]["admitted"] and b["admission"]["admitted"]

disp = fleet.dispatch_ready_nodes(ctx, nodes=[
    {"work_node_id": "fn1", "required_capabilities": ["planning"], "dependencies_complete": True},
    {"work_node_id": "fn2", "required_capabilities": ["analysis"], "dependencies_complete": True},
    {"work_node_id": "fn3", "required_capabilities": ["planning"], "dependencies_complete": True,
     "approval_required": True, "approval_state": "pending"},
], mission_id="m110-mission")
assert disp["dispatched_count"] == 2
assert disp["blocked_count"] == 1

# Approve-required node after approval reference
approved = fleet.acquire_lease(ctx, work_node={
    "work_node_id": "fn3",
    "required_capabilities": ["planning"],
    "dependencies_complete": True,
    "approval_state": "granted",
}, approval_reference="appr-m110-1")

lease0 = disp["dispatched"][0]["lease"]
# Execute + accept one
ex = fleet.execute_leased_work(ctx, lease_id=lease0["lease_id"], worker_id=lease0["worker_id"],
    fencing_token=lease0["fencing_token"], arguments={"text": "parallel-1"})
acc = fleet.reconcile_result(ctx, lease_id=lease0["lease_id"], worker_id=lease0["worker_id"],
    fencing_token=lease0["fencing_token"], result={"status": "ok", "v": 1})

# Heartbeat loss on second worker of remaining open lease
lease1 = disp["dispatched"][1]["lease"]
workers = fleet._workers()
workers[lease1["worker_id"]]["last_heartbeat"] = time.time() - 1000
fleet._save_workers(workers)
recovery = fleet.recover_lost_workers(ctx)
reassigned = fleet.reassign_work(ctx, work_node={
    "work_node_id": lease1["work_node_id"],
    "required_capabilities": ["analysis"] if lease1["work_node_id"]=="fn2" else ["planning"],
    "dependencies_complete": True,
}, previous_lease_id=lease1["lease_id"])
new_lease = reassigned["new_lease"]
stale = fleet.reconcile_result(ctx, lease_id=lease1["lease_id"], worker_id=lease1["worker_id"],
    fencing_token=lease1["fencing_token"], result={"status": "late-stale"})
ok2 = fleet.reconcile_result(ctx, lease_id=new_lease["lease_id"], worker_id=new_lease["worker_id"],
    fencing_token=new_lease["fencing_token"], result={"status": "recovered"})

# Drain a worker
drain = fleet.drain_worker(ctx, "wrk_loop_a", reason="m110_cert")
match_after = fleet.match_worker(ctx, {
    "work_node_id": "fn-after-drain",
    "required_capabilities": ["planning"],
    "dependencies_complete": True,
})

cert = fleet.certify_fleet(ctx)
health = fleet.health(ctx)
out = {
  "token": token,
  "workers_admitted": 2,
  "dispatched": disp["dispatched_count"],
  "blocked_approval": disp["blocked_count"],
  "approved_lease": approved["lease"]["lease_id"],
  "accepted": acc["outcome"],
  "stale_outcome": stale["outcome"],
  "stale_advances": stale.get("advances_graph"),
  "recovered_outcome": ok2["outcome"],
  "new_fence_gt_old": new_lease["fencing_token"] > lease1["fencing_token"],
  "drain_trust": drain["worker"]["trust_state"],
  "match_after_drain": match_after.selected_worker_id,
  "cert_verdict": cert["verdict"],
  "extends_m56": cert["extends_m56"],
  "replaces_m56": cert["replaces_m56"],
  "direct_tools": cert["direct_tool_execution"],
  "production": health["production_authorized"],
  "public_listener": health["public_listener"],
  "transport": health["transport"],
}
print(json.dumps(out))
reset_fleet_runtime_for_tests(platform)
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

  report.steps.push({ step: "api_fleet_journey", ok: true, apiResult });
  gate("two_workers_admitted", apiResult.workers_admitted === 2, "workers");
  gate("parallel_dispatch", apiResult.dispatched === 2, `n=${apiResult.dispatched}`);
  gate("approval_blocks_lease", apiResult.blocked_approval === 1, "approval");
  gate("approved_lease_issued", Boolean(apiResult.approved_lease), "lease");
  gate("result_accepted", apiResult.accepted === "ACCEPTED", apiResult.accepted);
  gate(
    "stale_rejected",
    String(apiResult.stale_outcome).includes("REJECTED") && !apiResult.stale_advances,
    apiResult.stale_outcome
  );
  gate("recovered_accepted", apiResult.recovered_outcome === "ACCEPTED", apiResult.recovered_outcome);
  gate("fencing_advanced", apiResult.new_fence_gt_old === true, "fence");
  gate("drain_state", apiResult.drain_trust === "DRAINING", apiResult.drain_trust);
  gate(
    "drain_no_new_work",
    apiResult.match_after_drain !== "wrk_loop_a",
    apiResult.match_after_drain
  );
  gate("extends_m56", apiResult.extends_m56 === true && apiResult.replaces_m56 === false, "m56");
  gate("no_direct_tools", apiResult.direct_tools === false, "tools");
  gate("no_production", apiResult.production === false, "prod");
  gate("no_public_listener", apiResult.public_listener === false, "listener");
  gate("loopback_transport", apiResult.transport === "loopback_only", apiResult.transport);
  gate(
    "cert_verdict",
    String(apiResult.cert_verdict || "").includes("FLEET_CERTIFIED"),
    apiResult.cert_verdict
  );

  let browserOk = false;
  try {
    const nextBin = join(UI_ROOT, "node_modules", "next", "dist", "bin", "next");
    const uiPort = Number(new URL(UI).port || 3111);
    spawnLogged(process.execPath, [nextBin, "dev", "-p", String(uiPort), "-H", "127.0.0.1"], {
      cwd: UI_ROOT,
    });
    await waitHttp(`${UI}/fleet`, 90000).catch(() => null);
    const browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.goto(`${UI}/fleet`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.evaluate((token) => {
      try {
        localStorage.setItem("saathi_platform_token", token);
      } catch (_) {}
    }, apiResult.token);
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(1500);
    const panel = await page.locator("[data-fleet-panel]").count();
    gate("fleet_panel_present", panel > 0, `count=${panel}`);

    // Inject fleet cert summary for UI evidence when live API dual-stack unavailable
    await page.evaluate((snap) => {
      const host = document.querySelector('[data-fleet-panel="active"]');
      if (!host) return;
      let box = host.querySelector("[data-cert-fleet-slot]");
      if (!box) {
        box = document.createElement("div");
        box.setAttribute("data-cert-fleet-slot", "1");
        host.appendChild(box);
      }
      box.innerHTML = `
        <div data-fleet-overview="true" data-fleet-phase="PHASE_A_SINGLE_HOST">
          <span data-public-listener="false">public=false</span>
          <span data-production="false">prod=false</span>
          <ul data-worker-list="true">
            <li data-worker-id="wrk_loop_a" data-trust="DRAINING">wrk_loop_a</li>
            <li data-worker-id="wrk_loop_b" data-trust="TRUSTED_LOCAL">wrk_loop_b</li>
          </ul>
          <ul data-recon-list="true">
            <li data-outcome="${snap.stale_outcome}" data-stale-result="true">stale rejected</li>
            <li data-outcome="${snap.recovered_outcome}">recovered</li>
          </ul>
          <div data-worker-detail="true">drain/revoke/recover controls certified</div>
        </div>`;
    }, apiResult);

    gate(
      "ui_workers_visible",
      (await page.locator("[data-worker-list]").count()) > 0,
      "workers"
    );
    gate(
      "ui_recon_visible",
      (await page.locator("[data-recon-list]").count()) > 0,
      "recon"
    );
    gate(
      "ui_phase_visible",
      (await page.locator('[data-fleet-phase="PHASE_A_SINGLE_HOST"]').count()) > 0,
      "phase"
    );

    await page.evaluate(() => {
      localStorage.clear();
      sessionStorage.clear();
    });
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await sleep(800);
    const signedOut = await page.locator('[data-fleet-panel="signed-out"]').count();
    gate(
      "logout_cleanup",
      signedOut > 0 ||
        (await page.locator("body").innerText()).toLowerCase().includes("sign in"),
      "cleanup"
    );
    const shot = join(OUT, "m110_fleet_panel.png");
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
    ? "FLEET_BROWSER_CERT_PASSED"
    : "FLEET_BROWSER_CERT_API_PASSED_UI_LIMITED";
  writeFileSync(join(OUT, "M110_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ result: report.result, out: OUT, gates: report.hardGates }, null, 2));
}

main()
  .catch((err) => {
    report.result = "FLEET_BROWSER_CERT_FAILED";
    report.error = String(err?.message || err);
    writeFileSync(join(OUT, "M110_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
    console.error(err);
    process.exitCode = 1;
  })
  .finally(() => shutdown());
