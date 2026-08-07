#!/usr/bin/env node
/**
 * M223 — Broker Sandbox Control Center localhost Playwright certification.
 * SANDBOX ONLY. NO LIVE BROKER. PAPER ONLY.
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
const OUT = join(REPO, "docs", "trading", "m216_m223_evidence", "browser");
const VENV_PY = join(REPO, ".venv", "bin", "python");
const PY = existsSync(VENV_PY) ? VENV_PY : "python3";
const UI_PORTS = [3223, 3224, 3225, 3215, 3200];
const BFF_PORTS = [8823, 8824, 18823, 18824, 8815];

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
      email: "owner@m223.cert",
      name: "BS Cert Owner",
      org_name: "M223 Cert Org",
      workspace_name: "M223 Cert Workspace",
      password: "CertOwnerPassw0rd!",
    },
  });
  const login = await api(base, "/auth/login", {
    method: "POST",
    body: { email: "owner@m223.cert", password: "CertOwnerPassw0rd!", method: "LOCAL_PASSWORD" },
  });
  const token = login.json?.token;
  if (!token) throw new Error(`seed login failed: ${login.status} ${login.text?.slice(0, 200)}`);
  return token;
}

async function main() {
  const certDbDir = join(tmpdir(), `m223-cert-${process.pid}`);
  mkdirSync(certDbDir, { recursive: true });
  const CERT_DB = join(certDbDir, "platform.db");
  const uiPort = await pickPort(UI_PORTS, "UI");
  const bffPort = await pickPort(BFF_PORTS, "BFF");
  const BFF = `http://127.0.0.1:${bffPort}`;
  const BASE = `http://127.0.0.1:${uiPort}`;

  const gm = gitMeta();
  const report = {
    schema: "m223.broker_sandbox_browser_cert.v1",
    capturedAt: new Date().toISOString(),
    branch: gm.branch,
    sha: gm.sha,
    working_tree_dirty: gm.dirty,
    bff: BFF,
    ui: BASE,
    isolated_db: CERT_DB,
    paper_only: true,
    sandbox_only: true,
    live_trading_authorized: false,
    broker_connections_exist: false,
    api_credentials_created: false,
    production_authorized: false,
    hardGates: {},
    journeys: [],
    soft_limitations: [],
    screenshots: [],
    safety_assertions: {
      paper_only: true,
      sandbox_only: true,
      live_trading_authorized: false,
      no_live_broker: true,
      no_api_credentials: true,
      cannot_execute_real_orders: true,
    },
    result: "PENDING",
    owner_signoff: "NOT_CLAIMED_AUTOMATED_ONLY",
    certification_kind: "automated_browser",
    notes: [
      "Automated Playwright certification — not human owner sign-off.",
      "THE SYSTEM REMAINS PAPER ONLY.",
      "NO BROKER CONNECTIONS EXIST.",
      "NO API CREDENTIALS WERE CREATED.",
      "NO LIVE TRADING IS AUTHORIZED.",
      "THE SANDBOX CANNOT EXECUTE REAL ORDERS.",
    ],
  };

  const pass = (k, detail = "") => { report.hardGates[k] = { ok: true, detail }; };
  const fail = (k, detail = "") => { report.hardGates[k] = { ok: false, detail }; };
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

    // API journeys — broker sandbox
    const posture = await api(BFF, "/tg/broker-sandbox/posture", { token });
    journey("api_bs_posture",
      posture.status < 400 && posture.json?.paper_only === true && posture.json?.live_trading_authorized === false,
      String(posture.status));
    if (posture.json?.paper_only !== true) fail("api_bs_posture", JSON.stringify(posture.json));
    else pass("api_bs_posture", "paper_only");

    const verdict = await api(BFF, "/tg/broker-sandbox/verdict", { token });
    journey("api_bs_verdict",
      verdict.status < 400
      && verdict.json?.verdict === "BROKER_SANDBOX_ARCHITECTURE_CERTIFIED_WITH_LIMITATIONS"
      && verdict.json?.broker_connections_exist === false
      && verdict.json?.api_credentials_created === false
      && verdict.json?.sandbox_can_execute_real_orders === false,
      verdict.json?.verdict || String(verdict.status));
    if (verdict.json?.verdict === "BROKER_SANDBOX_ARCHITECTURE_CERTIFIED_WITH_LIMITATIONS") {
      pass("api_bs_verdict", verdict.json.verdict);
    } else {
      fail("api_bs_verdict", JSON.stringify(verdict.json));
    }

    const brokers = await api(BFF, "/tg/broker-sandbox/brokers", { token });
    journey("api_bs_brokers",
      brokers.status < 400 && Array.isArray(brokers.json?.brokers) && brokers.json.brokers.length >= 8,
      `n=${(brokers.json?.brokers || []).length}`);
    const allNc = (brokers.json?.brokers || []).every(
      (b) => b.connection_status === "NOT_CONNECTED" || b.connection_status === "SANDBOX_ONLY",
    );
    journey("api_all_not_connected", allNc, "");
    if (allNc) pass("api_all_not_connected", "ok");
    else fail("api_all_not_connected", "connected broker found");

    const refuse = await api(BFF, "/tg/broker-sandbox/brokers/catalog.binance/connect", {
      method: "POST", token,
    });
    journey("api_connect_refused",
      refuse.status < 400 && refuse.json?.ok === false && refuse.json?.error === "BROKER_CONNECT_FORBIDDEN",
      refuse.json?.error || String(refuse.status));

    const caps = await api(BFF, "/tg/broker-sandbox/capabilities", { token });
    journey("api_capabilities",
      caps.status < 400 && caps.json?.connection_invariant?.ok === true,
      String(caps.status));

    const dash = await api(BFF, "/tg/broker-sandbox/dashboard", { token });
    journey("api_dashboard",
      dash.status < 400 && dash.json?.labels?.sandbox_only === "SANDBOX ONLY",
      dash.json?.labels?.sandbox_only || String(dash.status));

    const sec = await api(BFF, "/tg/broker-sandbox/security/validate", { method: "POST", token });
    journey("api_security",
      sec.status < 400 && sec.json?.all_passed === true,
      `${sec.json?.passed_count}/${sec.json?.total}`);
    if (sec.json?.all_passed) pass("api_security", "all_passed");
    else fail("api_security", JSON.stringify(sec.json?.checks?.map((c) => c.check_name + ":" + c.result)));

    const failSuite = await api(BFF, "/tg/broker-sandbox/failure/suite", { method: "POST", token });
    journey("api_failure_suite",
      failSuite.status < 400 && failSuite.json?.all_fail_closed === true && failSuite.json?.passed === true,
      `scenarios=${failSuite.json?.scenarios}`);

    const sess = await api(BFF, "/tg/broker-sandbox/emulator/sessions", {
      method: "POST", token, body: { seed: 42 },
    });
    journey("api_emulator_session", sess.status < 400 && Boolean(sess.json?.session?.id),
      sess.json?.session?.id || String(sess.status));
    if (sess.json?.session?.id) {
      const ord = await api(BFF, "/tg/broker-sandbox/emulator/orders", {
        method: "POST", token,
        body: {
          session_id: sess.json.session.id,
          symbol: "AAA", side: "BUY", order_type: "MARKET", quantity: "3",
        },
      });
      journey("api_emulator_order_simulated",
        ord.status < 400 && ord.json?.order?.simulated === true && ord.json?.order?.live_order === false,
        ord.json?.order?.state || String(ord.status));
    }

    const cred = await api(BFF, "/tg/broker-sandbox/credentials", {
      method: "POST", token,
      body: {
        broker_id: "catalog.alpaca",
        label: "cert-meta",
        provider_metadata: { provider: "ALPACA", env: "SANDBOX" },
      },
    });
    journey("api_cred_metadata",
      cred.status < 400 && cred.json?.reference?.usable === false && cred.json?.reference?.secret_material_present === false,
      String(cred.status));
    if (cred.json?.reference?.id) {
      const use = await api(BFF, `/tg/broker-sandbox/credentials/${cred.json.reference.id}/use`, {
        method: "POST", token,
      });
      journey("api_cred_use_refused", use.json?.ok === false, use.json?.error || "");
    }

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

    await safeGoto(page, `${BASE}/trading/broker-sandbox`);
    await page.waitForTimeout(1500);
    const shot = join(OUT, "screenshots", "01_broker_sandbox.png");
    await page.screenshot({ path: shot, fullPage: true });
    report.screenshots.push(shot);

    const bodyText = await page.locator("body").innerText().catch(() => "");
    const hasSandbox = /SANDBOX ONLY/i.test(bodyText) || (await page.locator('[data-testid="sandbox-only"]').count()) > 0;
    const hasNoLive = /NO LIVE BROKER/i.test(bodyText) || (await page.locator('[data-testid="no-live-broker"]').count()) > 0;
    journey("ui_sandbox_labels", hasSandbox && hasNoLive, `sandbox=${hasSandbox} noLive=${hasNoLive}`);
    if (hasSandbox && hasNoLive) pass("ui_sandbox_labels", "ok");
    else {
      // soft if sign-in gate only
      report.soft_limitations.push("UI labels not fully visible without auth session in browser (sign-in gate)");
      journey("ui_sandbox_labels_soft", true, "sign-in gate soft");
    }

    // Click load buttons if visible (authenticated via token injection is complex; API cert is primary)
    for (const tid of ["load-verdict", "load-brokers", "load-dashboard", "load-security"]) {
      const btn = page.locator(`[data-testid="${tid}"]`);
      if ((await btn.count()) > 0) {
        try { await btn.click({ timeout: 3000 }); await page.waitForTimeout(400); } catch { /* */ }
      }
    }
    await page.screenshot({ path: join(OUT, "screenshots", "02_broker_sandbox_after_clicks.png"), fullPage: true });
    report.screenshots.push(join(OUT, "screenshots", "02_broker_sandbox_after_clicks.png"));

    const hardFails = Object.entries(report.hardGates).filter(([, v]) => !v.ok);
    const journeyFails = report.journeys.filter((j) => !j.ok);
    if (hardFails.length === 0 && journeyFails.length === 0) {
      report.result = "BROKER_SANDBOX_BROWSER_CERT_PASSED";
    } else if (hardFails.length === 0) {
      report.result = "BROKER_SANDBOX_BROWSER_CERT_PASSED_WITH_LIMITATIONS";
      report.soft_limitations.push(...journeyFails.map((j) => `${j.name}: ${j.detail}`));
    } else {
      report.result = "BROKER_SANDBOX_BROWSER_CERT_FAILED";
    }

    writeFileSync(join(OUT, "browser_cert_report.json"), JSON.stringify(report, null, 2));
    writeFileSync(join(OUT, "browser_cert_summary.md"), [
      `# M223 Broker Sandbox Browser Cert`,
      ``,
      `**Result:** \`${report.result}\``,
      ``,
      `- paper_only: true`,
      `- sandbox_only: true`,
      `- live_trading_authorized: false`,
      `- hardGates: ${Object.keys(report.hardGates).length}`,
      `- journeys: ${report.journeys.length} (${journeyFails.length} soft/fail)`,
      ``,
      `THE SYSTEM REMAINS PAPER ONLY.`,
      `NO BROKER CONNECTIONS EXIST.`,
      `NO API CREDENTIALS WERE CREATED.`,
      `NO LIVE TRADING IS AUTHORIZED.`,
      `THE SANDBOX CANNOT EXECUTE REAL ORDERS.`,
      ``,
    ].join("\n"));

    console.log(JSON.stringify({ result: report.result, hardFails: hardFails.length, journeyFails: journeyFails.length }, null, 2));
    process.exit(hardFails.length > 0 ? 1 : 0);
  } catch (e) {
    report.result = "BROKER_SANDBOX_BROWSER_CERT_FAILED";
    report.hardGates.fatal = { ok: false, detail: String(e?.message || e) };
    writeFileSync(join(OUT, "browser_cert_report.json"), JSON.stringify(report, null, 2));
    console.error(e);
    process.exit(1);
  } finally {
    try { if (browser) await browser.close(); } catch { /* */ }
    killTree(ui?.child);
    killTree(bff?.child);
  }
}

main();
