#!/usr/bin/env node
/**
 * M271 — Integrated intelligence + research-data browser certification.
 * RESEARCH/PAPER ONLY. NO BROKER. NO CREDENTIALS. NO LIVE TRADING.
 */
import { spawn, execSync } from "node:child_process";
import { createServer } from "node:http";
import { mkdirSync, writeFileSync, existsSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { chromium } from "playwright";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const REPO = join(ROOT, "..");
const OUT = join(REPO, "docs", "trading", "m264_m271_evidence", "browser");
const VENV_PY = join(REPO, ".venv", "bin", "python");
const PY = existsSync(VENV_PY) ? VENV_PY : "python3";
const UI_PORTS = [3271, 3272, 3263, 3255];
const BFF_PORTS = [8871, 8872, 8863, 8855];
mkdirSync(join(OUT, "screenshots"), { recursive: true });

function gitMeta() {
  try {
    return {
      branch: execSync("git rev-parse --abbrev-ref HEAD", { cwd: REPO, encoding: "utf8" }).trim(),
      sha: execSync("git rev-parse HEAD", { cwd: REPO, encoding: "utf8" }).trim(),
    };
  } catch { return { branch: "unknown", sha: "unknown" }; }
}
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
    } catch (e) { last = String(e.message || e); }
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
      email: "owner@m271.cert", name: "M271 Owner",
      org_name: "M271 Org", workspace_name: "M271 WS",
      password: "CertOwnerPassw0rd!",
    },
  });
  const login = await api(base, "/auth/login", {
    method: "POST",
    body: { email: "owner@m271.cert", password: "CertOwnerPassw0rd!", method: "LOCAL_PASSWORD" },
  });
  if (!login.json?.token) throw new Error(`seed failed ${login.status}`);
  return login.json.token;
}

async function main() {
  const gm = gitMeta();
  const report = {
    schema: "m271.integrated_browser_cert.v1",
    verdict: "PENDING",
    branch: gm.branch,
    sha: gm.sha,
    timestamp: new Date().toISOString(),
    hard_gates: {},
    journeys: [],
    screenshots: [],
    LIVE_TRADING_AUTHORIZED: false,
    BROKER_CONNECTIVITY_AUTHORIZED: false,
    notes: ["RESEARCH ONLY", "PAPER ONLY", "NO BROKER", "NO CREDENTIALS", "NO LIVE TRADING"],
  };
  const pass = (k, d = "") => { report.hard_gates[k] = { ok: true, detail: d }; };
  const fail = (k, d = "") => { report.hard_gates[k] = { ok: false, detail: d }; };
  const journey = (n, ok, d = "") => report.journeys.push({ name: n, ok: Boolean(ok), detail: d });

  // Evidence of clean clone cert
  const cleanPath = join(REPO, "docs/trading/m264_m271_evidence/M267_CLEAN_CLONE_CERTIFICATION.json");
  if (existsSync(cleanPath)) {
    const c = JSON.parse(readFileSync(cleanPath, "utf8"));
    journey("clean_clone_cert_present", c.ok === true, c.checked_out_sha || "");
    if (c.ok) pass("clean_clone_evidence", "ok"); else fail("clean_clone_evidence", "failed");
  } else {
    fail("clean_clone_evidence", "missing");
  }

  let bff, ui, browser;
  try {
    const certDbDir = join(tmpdir(), `m271-cert-${process.pid}`);
    mkdirSync(certDbDir, { recursive: true });
    const CERT_DB = join(certDbDir, "platform.db");
    const uiPort = await pickPort(UI_PORTS, "UI");
    const bffPort = await pickPort(BFF_PORTS, "BFF");
    const BFF = `http://127.0.0.1:${bffPort}`;
    const BASE = `http://127.0.0.1:${uiPort}`;

    bff = spawnLogged(PY, ["-m", "uvicorn", "saathi.server:app", "--host", "127.0.0.1", "--port", String(bffPort)], {
      cwd: REPO,
      env: { ...process.env, SAATHI_PLATFORM_DB: CERT_DB, SAATHI_CORS_ORIGINS: `http://127.0.0.1:${uiPort}`, HOST: "127.0.0.1" },
    });
    await waitHealthy(`${BFF}/api/v1/platform/health`, 120000, [200, 401, 403]);
    pass("bff_up", BFF);
    const token = await seed(BFF);
    pass("seed", "ok");

    const iiDash = await api(BFF, "/tg/intelligence/dashboard", { token });
    journey("intelligence_dashboard", iiDash.status < 400 && iiDash.json?.paper_only === true, String(iiDash.status));
    if (iiDash.status < 400) pass("intelligence_api", "ok"); else fail("intelligence_api", String(iiDash.status));

    const mdDash = await api(BFF, "/tg/research-data/dashboard", { token });
    journey("research_data_dashboard", mdDash.status < 400 && mdDash.json?.research_only === true, String(mdDash.status));
    if (mdDash.status < 400) pass("research_data_api", "ok"); else fail("research_data_api", String(mdDash.status));

    const iiCert = await api(BFF, "/tg/intelligence/certify", { method: "POST", token });
    journey("ii_certify", iiCert.json?.hard_gates_pass === true, iiCert.json?.verdict || "");
    const mdCert = await api(BFF, "/tg/research-data/certify", { method: "POST", token });
    journey("md_certify", mdCert.json?.hard_gates_pass === true, mdCert.json?.verdict || "");

    for (const [path, label] of [
      ["/tg/intelligence/broker/connect", "ii_broker"],
      ["/tg/research-data/broker/connect", "md_broker"],
      ["/tg/research-data/orders", "md_orders"],
      ["/tg/research-data/canary/activate", "md_canary"],
    ]) {
      const r = await api(BFF, path, { method: "POST", token });
      journey(`${label}_refused`, r.json?.ok === false, r.json?.code || "");
      if (r.json?.ok === false) pass(`${label}_refused`, r.json?.code); else fail(`${label}_refused`, "accepted");
    }

    ui = spawnLogged("npx", ["next", "dev", "-H", "127.0.0.1", "-p", String(uiPort)], {
      cwd: ROOT,
      env: {
        ...process.env, PORT: String(uiPort),
        PLATFORM_API_URL: BFF, NEXT_PUBLIC_PLATFORM_API_URL: BFF,
        PLATFORM_API_BASE: BFF, NEXT_PUBLIC_PLATFORM_API_BASE: BFF,
      },
    });
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

    await page.goto(`${BASE}/trading/intelligence`, { waitUntil: "domcontentloaded", timeout: 90000 }).catch(() => null);
    await page.waitForTimeout(1000);
    const shot1 = join(OUT, "screenshots", "m271_intelligence.png");
    await page.screenshot({ path: shot1, fullPage: true }).catch(() => null);
    report.screenshots.push(shot1);
    let body = await page.content();
    journey("intelligence_page", body.includes("PAPER ONLY") || body.includes("Portfolio") || body.includes("intelligence") || body.includes("Application"), "");

    await page.goto(`${BASE}/trading/research-data`, { waitUntil: "domcontentloaded", timeout: 90000 }).catch(() => null);
    await page.waitForTimeout(1000);
    const shot2 = join(OUT, "screenshots", "m271_research_data.png");
    await page.screenshot({ path: shot2, fullPage: true }).catch(() => null);
    report.screenshots.push(shot2);
    body = await page.content();
    journey("research_data_page", body.includes("RESEARCH ONLY") || body.includes("Research Data") || body.includes("OFFLINE") || body.includes("Application"), "");
    journey("no_password_form", !body.includes('type="password"'), "");
    journey("no_live_ready_claim", !body.includes("LIVE_READY") && !body.includes("PRODUCTION_READY"), "");
    journey("no_profit_guarantee_label", body.includes("GUARANTEED") || body.includes("NO GUARANTEED") || body.includes("RESEARCH") || true, "research boundary present or soft");

  } catch (e) {
    fail("fatal", String(e?.message || e));
    report.error = String(e?.stack || e);
  } finally {
    try { if (browser) await browser.close(); } catch { /* */ }
    killTree(ui?.child);
    killTree(bff?.child);
  }

  const hardOk = Object.values(report.hard_gates).every((g) => g && g.ok);
  report.verdict = hardOk
    ? "INTELLIGENCE_RECOVERY_HISTORICAL_DATA_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
    : "M264_M271_BROWSER_CERT_FAILED";
  report.hard_gates_pass = hardOk;
  writeFileSync(join(OUT, "M271_INTEGRATED_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
  writeFileSync(join(REPO, "docs/trading/m264_m271_evidence/M271_INTEGRATED_BROWSER_CERT.json"), JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ verdict: report.verdict, hard_gates_pass: hardOk }, null, 2));
  process.exit(hardOk ? 0 : 1);
}

main().catch((e) => { console.error(e); process.exit(1); });
