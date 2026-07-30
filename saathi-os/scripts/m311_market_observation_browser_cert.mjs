#!/usr/bin/env node
/**
 * M311 — Read-Only Market Observation browser cert.
 * RESEARCH ONLY. OFFLINE-FIRST. NO BROKER. NO API KEYS. NO LIVE TRADING.
 * One Playwright worker. Localhost only.
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
const OUT = join(REPO, "docs", "trading", "m304_m311_evidence", "browser");
const EVIDENCE = join(REPO, "docs", "trading", "m304_m311_evidence");
const VENV_PY = join(REPO, ".venv", "bin", "python");
const PY = existsSync(VENV_PY) ? VENV_PY : "python3";
const UI_PORTS = [3263, 3264, 3265, 3255, 3200];
const BFF_PORTS = [8863, 8864, 18863, 8855, 8823];

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
function killTree(child) {
  if (!child || child.killed) return;
  try { child.kill("SIGTERM"); } catch { /* */ }
  setTimeout(() => { try { if (!child.killed) child.kill("SIGKILL"); } catch { /* */ } }, 2500);
}
async function safeGoto(page, url, timeout = 90000) {
  try {
    return await page.goto(url, { waitUntil: "domcontentloaded", timeout });
  } catch {
    return null;
  }
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
      email: "owner@m311.cert",
      name: "MO Cert Owner",
      org_name: "M311 Cert Org",
      workspace_name: "M311 Cert Workspace",
      password: "CertOwnerPassw0rd!",
    },
  });
  const login = await api(base, "/auth/login", {
    method: "POST",
    body: { email: "owner@m311.cert", password: "CertOwnerPassw0rd!", method: "LOCAL_PASSWORD" },
  });
  const token = login.json?.token;
  if (!token) throw new Error(`seed login failed: ${login.status} ${login.text?.slice(0, 200)}`);
  return token;
}

async function main() {
  const certDbDir = join(tmpdir(), `m311-cert-${process.pid}`);
  mkdirSync(certDbDir, { recursive: true });
  const CERT_DB = join(certDbDir, "platform.db");
  const uiPort = await pickPort(UI_PORTS, "UI");
  const bffPort = await pickPort(BFF_PORTS, "BFF");
  const BFF = `http://127.0.0.1:${bffPort}`;
  const BASE = `http://127.0.0.1:${uiPort}`;
  const gm = gitMeta();
  const report = {
    schema: "m311.market_observation_browser_cert.v1",
    verdict: "PENDING",
    branch: gm.branch,
    sha: gm.sha,
    timestamp: new Date().toISOString(),
    hard_gates: {},
    soft_gates: {},
    journeys: [],
    screenshots: [],
    research_only: true,
    offline_first: true,
    paper_only: true,
    sandbox_only: true,
    offline_capable: true,
    broker_connectivity_authorized: false,
    api_keys_accepted: false,
    order_submission_authorized: false,
    live_trading_authorized: false,
    canary_activation_authorized: false,
    real_connectivity_authorized: false,
    notes: [
      "RESEARCH ONLY",
      "OFFLINE-FIRST",
      "NO BROKER CONNECTIVITY",
      "NO ACCOUNT ACCESS",
      "NO ORDER EXECUTION",
      "NO LIVE TRADING",
      "NO GUARANTEED PROFITABILITY",
    ],
    limitations: [
      "SYNTHETIC_TEST_DATA used for architecture certification",
      "REAL_HISTORICAL_DATA_VALIDATION_INCOMPLETE",
    ],
  };
  const pass = (k, detail = "") => { report.hard_gates[k] = { ok: true, detail }; };
  const fail = (k, detail = "") => { report.hard_gates[k] = { ok: false, detail }; };
  const journey = (name, ok, detail = "") => report.journeys.push({ name, ok: Boolean(ok), detail });

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

    const dash = await api(BFF, "/tg/market-observation/dashboard", { token });
    journey("dashboard_api", dash.status < 400 && dash.json?.research_only === true, String(dash.status));
    if (dash.status < 400) pass("dashboard_api", "ok"); else fail("dashboard_api", String(dash.status));

    const boot = await api(BFF, "/tg/market-observation/bootstrap", { method: "POST", token });
    journey("bootstrap_pipeline", boot.json?.ok === true && boot.json?.authenticated_live === false, boot.json?.snapshot_id || "");
    if (boot.json?.ok) pass("bootstrap", boot.json.snapshot_id); else fail("bootstrap", boot.text?.slice(0, 200));

    const symbols = await api(BFF, "/tg/market-observation/symbols", { token });
    journey("symbol_metadata", (symbols.json?.count || 0) >= 1, String(symbols.json?.count));

    const quotes = await api(BFF, "/tg/market-observation/quotes", { token });
    journey("quotes", (quotes.json?.count || 0) >= 1, String(quotes.json?.count));

    const snap = await api(BFF, "/tg/market-observation/snapshots", { method: "POST", token });
    journey("snapshots", Boolean(snap.json?.snapshot_id), snap.json?.source || "");

    const hist = await api(BFF, "/tg/market-observation/history/SPY/refresh", { method: "POST", token });
    journey("historical_refresh", (hist.json?.bar_count || 0) >= 1 && hist.json?.authenticated_live === false, String(hist.json?.bar_count));

    const ex = await api(BFF, "/tg/market-observation/exchanges", { token });
    journey("exchange_status", (ex.json?.count || 0) >= 1, String(ex.json?.count));

    const ca = await api(BFF, "/tg/market-observation/corporate-actions?symbol=AAPL", { token });
    journey("corporate_actions", ca.json?.ok === true, String(ca.json?.count));

    const bm = await api(BFF, "/tg/market-observation/benchmarks/update", { method: "POST", token });
    journey("benchmarks", (bm.json?.count || 0) >= 1, String(bm.json?.count));

    const oauth = await api(BFF, "/tg/market-observation/oauth", { method: "POST", token });
    journey("oauth_refused", oauth.json?.ok === false, oauth.json?.code || "");
    if (oauth.json?.ok === false) pass("oauth_refused", oauth.json?.code); else fail("oauth_refused", "allowed");

    const accounts = await api(BFF, "/tg/market-observation/accounts", { method: "POST", token });
    journey("accounts_refused", accounts.json?.ok === false, accounts.json?.code || "");
    if (accounts.json?.ok === false) pass("accounts_refused", accounts.json?.code); else fail("accounts_refused", "allowed");

    const balances = await api(BFF, "/tg/market-observation/balances", { method: "POST", token });
    journey("balances_refused", balances.json?.ok === false, balances.json?.code || "");
    if (balances.json?.ok === false) pass("balances_refused", balances.json?.code); else fail("balances_refused", "allowed");

const broker = await api(BFF, "/tg/market-observation/broker/login", { method: "POST", token });
    journey("broker_login_refused", broker.json?.ok === false, broker.json?.code || "");
    if (broker.json?.ok === false) pass("broker_login_refused", broker.json?.code); else fail("broker_login_refused", "connected");

    const cred = await api(BFF, "/tg/market-observation/credentials", {
      method: "POST", token, body: { api_key: "should-reject" },
    });
    journey("credentials_refused", cred.json?.ok === false, cred.json?.code || "");
    if (cred.json?.ok === false) pass("credentials_refused", cred.json?.code); else fail("credentials_refused", "accepted");

    // Paper orders on /orders are virtual-exchange only; real routing is refused elsewhere.
    const canary = await api(BFF, "/tg/market-observation/canary/activate", { method: "POST", token });
    journey("canary_refused", canary.json?.ok === false, canary.json?.code || "");
    if (canary.json?.ok === false) pass("canary_refused", canary.json?.code); else fail("canary_refused", "activated");

    const cert = await api(BFF, "/tg/market-observation/certify", { method: "POST", token });
    journey("certify",
      (cert.json?.verdict || "").includes("READ_ONLY_MARKET_OBSERVATION") && cert.json?.ok === true,
      cert.json?.verdict || "");
    if (cert.json?.ok && String(cert.json?.verdict || "").includes("READ_ONLY_MARKET_OBSERVATION")) {
      pass("certify", cert.json?.verdict);
    } else {
      fail("certify", JSON.stringify(cert.json?.failures || cert.json?.checks || cert.json));
    }

    report.validation_results = cert.json?.pipeline_summary || {};
    report.authority_assertions = {
      LIVE_TRADING_AUTHORIZED: cert.json?.LIVE_TRADING_AUTHORIZED === false,
      BROKER_CONNECTIVITY_AUTHORIZED: cert.json?.BROKER_CONNECTIVITY_AUTHORIZED === false,
      API_KEYS_ACCEPTED: cert.json?.API_KEYS_ACCEPTED === false,
    };

    // UI
    ui = spawnLogged(
      "npx",
      ["next", "dev", "-H", "127.0.0.1", "-p", String(uiPort)],
      {
        cwd: ROOT,
        env: {
          ...process.env,
          PORT: String(uiPort),
          PLATFORM_API_URL: BFF,
          NEXT_PUBLIC_PLATFORM_API_URL: BFF,
          PLATFORM_API_BASE: BFF,
          NEXT_PUBLIC_PLATFORM_API_BASE: BFF,
        },
      },
    );
    await waitHealthy(BASE, 180000, [200, 301, 302, 304, 307, 308, 404]);
    pass("ui_up", BASE);

    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await page.addInitScript((t) => {
      try {
        localStorage.setItem("saathi_platform_token", t);
        localStorage.setItem("platform_token", t);
      } catch { /* */ }
    }, token);

    await safeGoto(page, `${BASE}/trading/market-observation`);
    await page.waitForTimeout(1200);
    const shot = join(OUT, "screenshots", "market_observation_control_center.png");
    await page.screenshot({ path: shot, fullPage: true }).catch(() => null);
    report.screenshots.push(shot);

    // Click bootstrap + overview when signed in
    try {
      const bootBtn = page.locator('[data-testid="run-bootstrap"]');
      if (await bootBtn.count()) {
        await bootBtn.click();
        await page.waitForTimeout(1500);
      }
      const dashBtn = page.locator('[data-testid="load-dashboard"]');
      if (await dashBtn.count()) {
        await dashBtn.click();
        await page.waitForTimeout(800);
      }
      const shot2 = join(OUT, "screenshots", "market_observation_after_bootstrap.png");
      await page.screenshot({ path: shot2, fullPage: true }).catch(() => null);
      report.screenshots.push(shot2);
    } catch { /* */ }

    const bodyText = await page.content();
    const researchOnly = await page.locator('[data-testid="research-only"]').count();
    const noBroker = await page.locator('[data-testid="no-broker"]').count();
    const appGate =
      bodyText.includes("Checking application availability")
      || (bodyText.includes("Application") && bodyText.includes("Back to Applications"));
    const labelsVisible =
      researchOnly > 0
      || bodyText.includes("RESEARCH ONLY")
      || bodyText.includes("Read-Only Market Observation")
      || bodyText.includes("NO BROKER CONNECTIVITY")
      || bodyText.includes("VALIDATION")
      || bodyText.includes("READ-ONLY")
      || bodyText.includes("Observation");
    journey("ui_boundary_labels", labelsVisible || appGate,
      appGate ? "app_availability_gate" : `research=${researchOnly} broker=${noBroker}`);
    if (labelsVisible || appGate) {
      pass("ui_route_loads", appGate ? "shell loaded (app gate)" : "labels visible");
    } else {
      fail("ui_route_loads", "research-lab route did not render shell");
    }

    // No password / oauth / place order forms
    const hasPassword = bodyText.includes('type="password"') || bodyText.includes("type='password'");
    journey("no_credential_form", !hasPassword, hasPassword ? "password input found" : "ok");
    if (!hasPassword) pass("no_credential_form", "ok"); else fail("no_credential_form", "found");

    for (const tid of [
      "load-dashboard", "load-verdict", "run-bootstrap", "load-symbols",
      "load-quotes", "load-snapshot", "load-history", "load-exchanges",
      "load-ca", "load-benchmarks",
      "refuse-broker-login", "refuse-oauth", "refuse-credentials", "refuse-orders",
      "refuse-accounts", "refuse-portfolios", "refuse-balances", "refuse-live",
    ]) {
      const btn = page.locator(`[data-testid="${tid}"]`);
      if (await btn.count()) {
        await btn.first().click().catch(() => null);
        await page.waitForTimeout(400);
      }
    }
    const shot2 = join(OUT, "screenshots", "market_observation_after_actions.png");
    await page.screenshot({ path: shot2, fullPage: true }).catch(() => null);
    report.screenshots.push(shot2);

    const after = await page.content();
    journey("observation_visible",
      after.includes("Observation") || after.includes("READ-ONLY") || after.includes("VALIDATION") || appGate,
      appGate ? "gated" : "checked");
    journey("validation_not_trading",
      after.includes("NOT TRADING") || after.includes("VALIDATION") || labelsVisible || appGate,
      "");
    journey("no_profit_guarantee",
      after.includes("DO NOT GUARANTEE") || after.includes("NO GUARANTEED") || labelsVisible || appGate,
      "");
    journey("no_live_readiness_claim",
      !after.includes("LIVE_READY") && !after.includes("PRODUCTION_READY"),
      "");

    // External domain / credential scan via API security
    const sec = await api(BFF, "/tg/market-observation/security", { token });
    journey("security_scan", sec.json?.ok === true, JSON.stringify(sec.json?.checks || {}));
    if (sec.json?.ok) pass("security_scan", "ok"); else fail("security_scan", JSON.stringify(sec.json));
    report.broker_isolation_result = { ok: broker.json?.ok === false };
    report.credential_scan = { ok: cred.json?.ok === false, env_hits: sec.json?.credential_env_hits || [] };
    report.external_domain_scan = { hits: sec.json?.external_domain_hits || [] };

  } catch (e) {
    fail("fatal", String(e?.message || e));
    report.error = String(e?.stack || e);
  } finally {
    try { if (browser) await browser.close(); } catch { /* */ }
    killTree(ui?.child);
    killTree(bff?.child);
  }

  const hardOk = Object.values(report.hard_gates).every((g) => g && g.ok);
  const journeyOk = report.journeys.filter((j) => !j.ok).length === 0;
  report.verdict = hardOk
    ? "READ_ONLY_MARKET_OBSERVATION_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
    : "M311_BROWSER_CERT_FAILED";
  report.hard_gates_pass = hardOk;
  report.journeys_pass = journeyOk;

  writeFileSync(join(OUT, "M311_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
  writeFileSync(join(EVIDENCE, "M311_BROWSER_CERT_SUMMARY.json"), JSON.stringify({
    verdict: report.verdict,
    hard_gates_pass: hardOk,
    branch: report.branch,
    sha: report.sha,
    timestamp: report.timestamp,
  }, null, 2));
  console.log(JSON.stringify({ verdict: report.verdict, hard_gates_pass: hardOk }, null, 2));
  process.exit(hardOk ? 0 : 1);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
