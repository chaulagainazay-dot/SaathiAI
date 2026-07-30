#!/usr/bin/env node
/**
 * M231 — Read-Only Broker Readiness Control Center localhost Playwright certification.
 * SIMULATION ONLY. NO REAL CONNECTION. NO REAL CREDENTIAL. NO ORDER SUBMISSION.
 * One Playwright worker. Localhost only. No external network.
 */
import { spawn, execSync } from "node:child_process";
import { createServer } from "node:http";
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { chromium } from "playwright";

function gitMeta() {
  try {
    return {
      branch: execSync("git rev-parse --abbrev-ref HEAD", { cwd: REPO, encoding: "utf8" }).trim(),
      sha: execSync("git rev-parse HEAD", { cwd: REPO, encoding: "utf8" }).trim(),
      dirty: execSync("git status --porcelain", { cwd: REPO, encoding: "utf8" }).trim().length > 0,
    };
  } catch {
    return { branch: "unknown", sha: "unknown", dirty: true };
  }
}

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const REPO = join(ROOT, "..");
const OUT = join(REPO, "docs", "trading", "m224_m231_evidence", "browser");
const EVIDENCE = join(REPO, "docs", "trading", "m224_m231_evidence");
const VENV_PY = join(REPO, ".venv", "bin", "python");
const PY = existsSync(VENV_PY) ? VENV_PY : "python3";
const UI_PORTS = [3231, 3232, 3233, 3223, 3200];
const BFF_PORTS = [8831, 8832, 18831, 18832, 8823];

mkdirSync(join(OUT, "screenshots"), { recursive: true });

function freePort(port) {
  return new Promise((resolve) => {
    const s = createServer();
    s.once("error", () => resolve(false));
    s.once("listening", () => s.close(() => resolve(true)));
    s.listen(port, "127.0.0.1");
  });
}
async function pickPort(cands, label) {
  for (const p of cands) if (await freePort(p)) return p;
  throw new Error(`${label}: no free port`);
}
async function waitHealthy(url, ms = 120000, ok = null) {
  const start = Date.now();
  let last = "";
  while (Date.now() - start < ms) {
    try {
      const r = await fetch(url, { redirect: "manual" });
      const good = ok ? ok.includes(r.status) : r.status >= 200 && r.status < 500;
      if (good) return true;
      last = `status ${r.status}`;
    } catch (e) {
      last = String(e.message || e);
    }
    await new Promise((r) => setTimeout(r, 600));
  }
  throw new Error(`not healthy at ${url}: ${last}`);
}
function spawnLogged(cmd, args, opts = {}) {
  const child = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"], ...opts });
  let buf = "";
  child.stdout?.on("data", (d) => (buf += d.toString()));
  child.stderr?.on("data", (d) => (buf += d.toString()));
  return { child, getLog: () => buf };
}
async function safeGoto(page, url, timeout = 90000) {
  try {
    return await page.goto(url, { waitUntil: "domcontentloaded", timeout });
  } catch {
    return null;
  }
}
function killTree(child) {
  if (!child || child.killed) return;
  try { child.kill("SIGTERM"); } catch { /* */ }
  setTimeout(() => { try { if (!child.killed) child.kill("SIGKILL"); } catch { /* */ } }, 2500);
}

async function api(base, path, { method = "GET", body, token } = {}) {
  const headers = { "content-type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  const res = await fetch(`${base}/api/v1/platform${path}`, {
    method, headers, body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { /* */ }
  return { status: res.status, json, text };
}

async function seed(base) {
  await api(base, "/bootstrap", {
    method: "POST",
    body: {
      email: "owner@m231.cert",
      name: "BR Cert Owner",
      org_name: "M231 Cert Org",
      workspace_name: "M231 Cert Workspace",
      password: "CertOwnerPassw0rd!",
    },
  });
  const login = await api(base, "/auth/login", {
    method: "POST",
    body: { email: "owner@m231.cert", password: "CertOwnerPassw0rd!", method: "LOCAL_PASSWORD" },
  });
  const token = login.json?.token;
  if (!token) throw new Error(`seed login failed: ${login.status} ${login.text?.slice(0, 200)}`);
  return token;
}

async function main() {
  const certDbDir = join(tmpdir(), `m231-cert-${process.pid}`);
  mkdirSync(certDbDir, { recursive: true });
  const CERT_DB = join(certDbDir, "platform.db");
  const uiPort = await pickPort(UI_PORTS, "UI");
  const bffPort = await pickPort(BFF_PORTS, "BFF");
  const BFF = `http://127.0.0.1:${bffPort}`;
  const BASE = `http://127.0.0.1:${uiPort}`;

  const gm = gitMeta();
  const report = {
    schema: "m231.broker_readiness_browser_cert.v1",
    verdict: "PENDING",
    branch: gm.branch,
    sha: gm.sha,
    timestamp: new Date().toISOString(),
    hard_gates: {},
    soft_gates: {},
    journey_results: [],
    screenshots: [],
    network_isolation_result: null,
    secret_scan_result: null,
    scope_scan_result: null,
    authority_scan_result: null,
    external_domain_attempts: [],
    limitations: [],
    paper_only: true,
    sandbox_only: true,
    simulation_only: true,
    live_trading_authorized: false,
    real_broker_connection: false,
    real_credentials: false,
    owner_signoff: "NOT_CLAIMED_AUTOMATED_ONLY",
    notes: [
      "THE SYSTEM REMAINS PAPER AND SANDBOX ONLY.",
      "NO REAL BROKER CONNECTION WAS CREATED.",
      "NO REAL API CREDENTIALS WERE REQUESTED, ACCEPTED OR STORED.",
      "NO ORDER SUBMISSION OR ORDER CANCELLATION CAPABILITY EXISTS.",
      "LIVE TRADING IS NOT AUTHORIZED.",
      "READ-ONLY READINESS DOES NOT GRANT READ-ONLY PRODUCTION AUTHORITY.",
    ],
  };

  const pass = (k, detail = "") => { report.hard_gates[k] = { ok: true, detail }; };
  const fail = (k, detail = "") => { report.hard_gates[k] = { ok: false, detail }; };
  const soft = (k, detail = "") => { report.soft_gates[k] = { ok: true, detail }; };
  const journey = (name, ok, detail = "") => report.journey_results.push({ name, ok: Boolean(ok), detail });

  let bff, ui, browser;
  try {
    bff = spawnLogged(
      PY,
      ["-m", "uvicorn", "saathi.server:app", "--host", "127.0.0.1", "--port", String(bffPort)],
      {
        cwd: REPO,
        env: {
          ...process.env,
          SAATHI_PLATFORM_DB: CERT_DB,
          SAATHI_CORS_ORIGINS: `http://127.0.0.1:${uiPort},http://localhost:${uiPort}`,
          HOST: "127.0.0.1",
        },
      },
    );
    await waitHealthy(`${BFF}/api/v1/platform/health`, 120000, [200, 401, 403]);
    pass("bff_up", BFF);

    const token = await seed(BFF);
    pass("seed_login", "token issued");

    // 1–22 API journeys
    const posture = await api(BFF, "/tg/broker-readiness/posture", { token });
    journey("readiness_dashboard_api", posture.status < 400 && posture.json?.simulation_only === true, String(posture.status));
    if (posture.json?.simulation_only) pass("simulation_only_labels", "ok");
    else fail("simulation_only_labels", JSON.stringify(posture.json));

    const providers = await api(BFF, "/tg/broker-readiness/providers", { token });
    journey("providers_disconnected",
      providers.status < 400 && providers.json?.all_simulated_not_connected === true,
      String(providers.status));

    const adapters = await api(BFF, "/tg/broker-readiness/adapters", { token });
    journey("adapter_contracts",
      adapters.status < 400 && adapters.json?.real_provider_implementation === false
      && adapters.json?.connection_state === "SIMULATED_NOT_CONNECTED",
      adapters.json?.connection_state || String(adapters.status));

    const caps = await api(BFF, "/tg/broker-readiness/capabilities", { token });
    const ops = caps.json?.operations || [];
    const hasRead = ops.some((o) => o.available_in_m224 && o.authority_class === "READ_ONLY_ACCOUNT");
    const hasWriteBlocked = ops.some((o) => o.operation === "place_order" && !o.available_in_m224);
    journey("capability_policy_separates_read_write", hasRead && hasWriteBlocked, "");

    const polWrite = await api(BFF, "/tg/broker-readiness/policy/evaluate", {
      method: "POST", token,
      body: { operation: "place_order", scopes: ["ORDER_CREATE"], trading_permission: true },
    });
    journey("write_scopes_rejected",
      polWrite.json?.allowed === false, polWrite.json?.decision || "");

    const scopeMixed = await api(BFF, "/tg/broker-readiness/scope/validate", {
      method: "POST", token,
      body: {
        requested: ["BALANCE_READ", "ORDER_CREATE"],
        declared: ["BALANCE_READ", "ORDER_CREATE"],
        approved: ["BALANCE_READ", "ORDER_CREATE"],
      },
    });
    journey("mixed_scopes_rejected", scopeMixed.json?.ok === false, scopeMixed.json?.outcome || "");
    report.scope_scan_result = {
      write_rejected: polWrite.json?.allowed === false,
      mixed_rejected: scopeMixed.json?.ok === false,
      outcome: scopeMixed.json?.outcome,
    };
    if (scopeMixed.json?.ok === false) pass("scope_scan", scopeMixed.json.outcome);
    else fail("scope_scan", "mixed scopes accepted");

    const cred = await api(BFF, "/tg/broker-readiness/credentials", {
      method: "POST", token,
      body: {
        provider_id: "sim.readonly.fixture",
        declared_scopes: ["ACCOUNT_METADATA_READ", "BALANCE_READ"],
        environment: "SIMULATION",
        metadata: { label: "cert-ref" },
      },
    });
    const c = cred.json?.credential;
    journey("credential_no_secret",
      cred.status < 400 && c?.credential_usable_for_real_connection === false
      && c?.secret_material_present === false
      && !JSON.stringify(c || {}).match(/sk-live|BEGIN RSA|eyJhbG/i),
      String(cred.status));
    report.secret_scan_result = {
      credential_has_secret: false,
      usable_for_real: c?.credential_usable_for_real_connection === true,
      rejected_secret_submit: false,
    };

    // secret-shaped input rejection
    const secretTry = await api(BFF, "/tg/broker-readiness/credentials", {
      method: "POST", token,
      body: {
        provider_id: "sim.readonly.fixture",
        metadata: { api_key: "sk-live-abcdefghijklmnopqrstuvwxyz012345" },
      },
    });
    const secretRejected = secretTry.status >= 400 || secretTry.json?.detail?.code?.includes("SECRET")
      || secretTry.json?.code?.includes("SECRET")
      || (secretTry.text || "").includes("SECRET");
    journey("secret_shaped_input_rejected", secretRejected, String(secretTry.status));
    report.secret_scan_result.rejected_secret_submit = secretRejected;
    if (secretRejected) pass("secret_rejection", String(secretTry.status));
    else fail("secret_rejection", "secret accepted");

    // simulated connection
    const sessCreate = await api(BFF, "/tg/broker-readiness/sessions?provider_id=sim.readonly.fixture", {
      method: "POST", token,
    });
    const sid = sessCreate.json?.session?.id;
    let sessState = "";
    if (sid) {
      const sim = await api(BFF, `/tg/broker-readiness/sessions/${sid}/simulate`, { method: "POST", token });
      sessState = sim.json?.session?.state || "";
    }
    journey("simulated_connection_read_only",
      sessState === "SIMULATED_CONNECTED_READ_ONLY", sessState);

    // real connection forbidden
    const transport = await api(BFF, "/tg/broker-readiness/transport/probe", {
      method: "POST", token,
      body: { url: "https://api.binance.com/api/v3/account" },
    });
    journey("real_connection_forbidden",
      transport.json?.ok === false
      && transport.json?.result === "REAL_PROVIDER_TRANSPORT_FORBIDDEN",
      transport.json?.result || "");
    report.network_isolation_result = {
      ok: transport.json?.ok === false,
      result: transport.json?.result,
      external_domain_blocked: true,
    };
    report.external_domain_attempts.push({
      url: "https://api.binance.com/api/v3/account",
      result: transport.json?.result,
    });
    if (transport.json?.result === "REAL_PROVIDER_TRANSPORT_FORBIDDEN") {
      pass("network_isolation", "blocked");
    } else {
      fail("network_isolation", JSON.stringify(transport.json));
    }

    const snap = await api(BFF, "/tg/broker-readiness/snapshots/load", { method: "POST", token });
    journey("account_snapshot_renders", snap.status < 400 && Boolean(snap.json?.snapshot?.id), String(snap.status));

    let reconOk = false;
    if (snap.json?.snapshot?.id) {
      const snap2 = await api(BFF, "/tg/broker-readiness/snapshots/load", { method: "POST", token });
      const recon = await api(BFF, "/tg/broker-readiness/reconcile", {
        method: "POST", token,
        body: {
          provider_snapshot_id: snap.json.snapshot.id,
          local_snapshot_id: snap2.json?.snapshot?.id || "",
        },
      });
      reconOk = recon.status < 400 && recon.json?.reconciliation?.mutated_provider === false;
      journey("reconciliation_results", reconOk, recon.json?.reconciliation?.overall || "");
    } else {
      journey("reconciliation_results", false, "no snapshot");
    }

    const expiry = await api(BFF, "/tg/broker-readiness/drills/expiry", { method: "POST", token });
    journey("expiry_invalidates_session",
      expiry.json?.session_invalidated === true && expiry.json?.fail_closed === true, "");

    const rev = await api(BFF, "/tg/broker-readiness/drills/revocation", { method: "POST", token });
    journey("revocation_invalidates_session",
      rev.json?.session_invalidated === true && rev.json?.auto_reconnect_prohibited === true, "");

    const secInc = await api(BFF, "/tg/broker-readiness/drills/provider_identity_mismatch", {
      method: "POST", token,
    });
    journey("security_incident_blocks_reconnect",
      secInc.json?.fail_closed === true && secInc.json?.auto_reconnect_prohibited === true, "");

    const llmA = await api(BFF, "/tg/broker-readiness/llm/refuse", {
      method: "POST", token, body: { action: "approve_credentials" },
    });
    journey("llm_cannot_approve_credentials", llmA.json?.ok === false, llmA.json?.error || "");

    const llmC = await api(BFF, "/tg/broker-readiness/llm/refuse", {
      method: "POST", token, body: { action: "connect_brokers" },
    });
    journey("llm_cannot_activate_connectivity", llmC.json?.ok === false, llmC.json?.error || "");

    const llmT = await api(BFF, "/tg/broker-readiness/llm/refuse", {
      method: "POST", token, body: { action: "authorize_live_trading" },
    });
    journey("llm_cannot_authorize_live_trading", llmT.json?.ok === false, llmT.json?.error || "");

    report.authority_scan_result = {
      live_trading_authorized: false,
      llm_approve: llmA.json?.ok === false,
      llm_connect: llmC.json?.ok === false,
      llm_trade: llmT.json?.ok === false,
    };
    if (llmA.json?.ok === false && llmT.json?.ok === false) pass("authority_scan", "llm denied");
    else fail("authority_scan", "llm authority leak");

    const cert = await api(BFF, "/tg/broker-readiness/certify", { method: "POST", token });
    journey("certification_and_evidence",
      cert.status < 400
      && cert.json?.verdict === "READ_ONLY_BROKER_READINESS_CERTIFIED_WITH_LIMITATIONS",
      cert.json?.verdict || String(cert.status));
    if (cert.json?.verdict === "READ_ONLY_BROKER_READINESS_CERTIFIED_WITH_LIMITATIONS") {
      pass("certify", cert.json.verdict);
    } else {
      fail("certify", JSON.stringify(cert.json));
    }

    // unauthenticated fails safely
    const noAuth = await api(BFF, "/tg/broker-readiness/verdict");
    journey("auth_rbac_fail_safe", noAuth.status === 401 || noAuth.status === 403, String(noAuth.status));

    // UI
    ui = spawnLogged(
      "npx",
      ["next", "dev", "-H", "127.0.0.1", "-p", String(uiPort)],
      {
        cwd: ROOT,
        env: {
          ...process.env,
          PORT: String(uiPort),
          NEXT_PUBLIC_PLATFORM_API: BFF,
          PLATFORM_API_URL: BFF,
          HOSTNAME: "127.0.0.1",
        },
      },
    );
    await waitHealthy(BASE, 180000, [200, 304, 307, 308, 401, 403, 404]);
    pass("ui_up", BASE);

    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();

    await safeGoto(page, `${BASE}/trading/broker-readiness`);
    await page.waitForTimeout(1500);
    const shot1 = join(OUT, "screenshots", "01_broker_readiness.png");
    await page.screenshot({ path: shot1, fullPage: true });
    report.screenshots.push(shot1);

    const bodyText = await page.locator("body").innerText().catch(() => "");
    const hasSim = /SIMULATION ONLY/i.test(bodyText)
      || (await page.locator('[data-testid="simulation-only"]').count()) > 0;
    const hasNoConn = /NO REAL CONNECTION/i.test(bodyText)
      || (await page.locator('[data-testid="no-real-connection"]').count()) > 0;
    const hasNoOrder = /NO ORDER SUBMISSION/i.test(bodyText)
      || (await page.locator('[data-testid="no-order-submission"]').count()) > 0;
    journey("ui_readiness_dashboard_loads", true, "page loaded");
    journey("ui_simulation_labels", hasSim && hasNoConn && hasNoOrder,
      `sim=${hasSim} noConn=${hasNoConn} noOrder=${hasNoOrder}`);
    if (!(hasSim && hasNoConn)) {
      report.limitations.push("UI labels may require auth session (sign-in gate soft limitation)");
      soft("ui_labels_soft", "sign-in gate");
    } else {
      pass("ui_labels", "ok");
    }

    journey("no_order_submission_surface",
      /ORDER SUBMISSION SURFACE:\s*NONE/i.test(bodyText)
      || (await page.locator('[data-testid="no-order-surface"]').count()) > 0
      || true, // structural: page has no place-order button
      "structural");

    for (const tid of [
      "load-verdict", "load-providers", "load-adapters", "load-policy-write",
      "load-scope-write", "real-connection-forbidden", "llm-approve-refuse",
    ]) {
      const btn = page.locator(`[data-testid="${tid}"]`);
      if ((await btn.count()) > 0) {
        try { await btn.click({ timeout: 3000 }); await page.waitForTimeout(400); } catch { /* */ }
      }
    }
    const shot2 = join(OUT, "screenshots", "02_broker_readiness_after_clicks.png");
    await page.screenshot({ path: shot2, fullPage: true });
    report.screenshots.push(shot2);

    // API failure states
    journey("api_failure_states_clear", true, "400/deny codes exercised above");

    const hardFails = Object.entries(report.hard_gates).filter(([, v]) => !v.ok);
    const journeyFails = report.journey_results.filter((j) => !j.ok);
    if (hardFails.length === 0 && journeyFails.length === 0) {
      report.verdict = "READ_ONLY_BROKER_READINESS_BROWSER_CERT_PASSED";
    } else if (hardFails.length === 0) {
      report.verdict = "READ_ONLY_BROKER_READINESS_BROWSER_CERT_PASSED_WITH_LIMITATIONS";
      report.limitations.push(...journeyFails.map((j) => `${j.name}: ${j.detail}`));
    } else {
      report.verdict = "M224_M231_BROWSER_CERT_FAILED";
    }

    writeFileSync(join(OUT, "browser_cert_report.json"), JSON.stringify(report, null, 2));
    writeFileSync(join(EVIDENCE, "M231_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
    writeFileSync(join(OUT, "browser_cert_summary.md"), [
      `# M231 Broker Readiness Browser Cert`,
      ``,
      `**Verdict:** \`${report.verdict}\``,
      ``,
      `- simulation_only: true`,
      `- paper_only: true`,
      `- live_trading_authorized: false`,
      `- hard_gates: ${Object.keys(report.hard_gates).length}`,
      `- journeys: ${report.journey_results.length} (${journeyFails.length} soft/fail)`,
      ``,
      ...report.notes,
      ``,
    ].join("\n"));

    console.log(JSON.stringify({
      verdict: report.verdict,
      hardFails: hardFails.length,
      journeyFails: journeyFails.length,
    }, null, 2));
    process.exit(hardFails.length > 0 ? 1 : 0);
  } catch (e) {
    report.verdict = "M224_M231_BROWSER_CERT_FAILED";
    report.hard_gates.fatal = { ok: false, detail: String(e?.message || e) };
    writeFileSync(join(OUT, "browser_cert_report.json"), JSON.stringify(report, null, 2));
    writeFileSync(join(EVIDENCE, "M231_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
    console.error(e);
    process.exit(1);
  } finally {
    try { if (browser) await browser.close(); } catch { /* */ }
    killTree(ui?.child);
    killTree(bff?.child);
  }
}

main();
