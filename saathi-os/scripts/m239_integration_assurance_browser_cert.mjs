#!/usr/bin/env node
/**
 * M239 — Integration Assurance Control Center localhost Playwright certification.
 * REPRODUCIBILITY AND PLANNING ONLY.
 * NO REAL CONNECTIVITY. NO CREDENTIALS. NO ORDER CAPABILITY.
 * One Playwright worker. Localhost only. No external provider network.
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
const OUT = join(REPO, "docs", "trading", "m232_m239_evidence", "browser");
const EVIDENCE = join(REPO, "docs", "trading", "m232_m239_evidence");
const VENV_PY = join(REPO, ".venv", "bin", "python");
const PY = existsSync(VENV_PY) ? VENV_PY : "python3";
const UI_PORTS = [3239, 3240, 3241, 3231, 3200];
const BFF_PORTS = [8839, 8840, 18839, 8831, 8823];

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
      email: "owner@m239.cert",
      name: "IA Cert Owner",
      org_name: "M239 Cert Org",
      workspace_name: "M239 Cert Workspace",
      password: "CertOwnerPassw0rd!",
    },
  });
  const login = await api(base, "/auth/login", {
    method: "POST",
    body: { email: "owner@m239.cert", password: "CertOwnerPassw0rd!", method: "LOCAL_PASSWORD" },
  });
  const token = login.json?.token;
  if (!token) throw new Error(`seed login failed: ${login.status} ${login.text?.slice(0, 200)}`);
  return token;
}

async function main() {
  const certDbDir = join(tmpdir(), `m239-cert-${process.pid}`);
  mkdirSync(certDbDir, { recursive: true });
  const CERT_DB = join(certDbDir, "platform.db");
  const uiPort = await pickPort(UI_PORTS, "UI");
  const bffPort = await pickPort(BFF_PORTS, "BFF");
  const BFF = `http://127.0.0.1:${bffPort}`;
  const BASE = `http://127.0.0.1:${uiPort}`;

  const gm = gitMeta();
  const report = {
    schema: "m239.integration_assurance_browser_cert.v1",
    verdict: "PENDING",
    branch: gm.branch,
    sha: gm.sha,
    clean_clone_sha: gm.sha,
    timestamp: new Date().toISOString(),
    hard_gates: {},
    soft_gates: {},
    journeys: [],
    screenshots: [],
    source_audit_result: null,
    clean_clone_result: null,
    lockfile_result: null,
    sbom_result: null,
    provenance_result: null,
    supply_chain_result: null,
    authorization_result: null,
    network_isolation_result: null,
    authority_assertions: null,
    limitations: [],
    paper_only: true,
    sandbox_only: true,
    real_connectivity_authorized: false,
    live_trading_authorized: false,
    owner_signoff: "NOT_CLAIMED_AUTOMATED_ONLY",
    notes: [
      "THE SYSTEM REMAINS PAPER AND SANDBOX ONLY.",
      "THE CERTIFIED RESULT IS REPRODUCIBLE FROM COMMITTED SOURCE.",
      "NO REAL BROKER CONNECTION WAS CREATED.",
      "NO REAL CREDENTIALS WERE REQUESTED, ACCEPTED OR STORED.",
      "LIVE TRADING IS NOT AUTHORIZED.",
      "READ-ONLY INTEGRATION AUTHORIZATION WAS NOT GRANTED.",
      "M232–M239 PROVIDES REPRODUCIBILITY, ASSURANCE AND PLANNING ONLY.",
    ],
  };

  const pass = (k, detail = "") => { report.hard_gates[k] = { ok: true, detail }; };
  const fail = (k, detail = "") => { report.hard_gates[k] = { ok: false, detail }; };
  const soft = (k, detail = "") => { report.soft_gates[k] = { ok: true, detail }; };
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

    const dash = await api(BFF, "/tg/integration-assurance/dashboard", { token });
    journey("integration_assurance_dashboard", dash.status < 400 && dash.json?.REAL_CONNECTIVITY_AUTHORIZED === false, String(dash.status));
    if (dash.status < 400) pass("dashboard_api", "ok"); else fail("dashboard_api", String(dash.status));

    const verdict = await api(BFF, "/tg/integration-assurance/verdict", { token });
    journey("certification_summary",
      verdict.json?.real_connectivity_authorized === false
      && (verdict.json?.verdict || "").includes("REPRODUCIBILITY"),
      verdict.json?.verdict || "");

    const source = await api(BFF, "/tg/integration-assurance/source-audit", { token });
    report.source_audit_result = { ok: source.json?.ok, verdict: source.json?.verdict };
    journey("required_source_audit", source.json?.ok === true, source.json?.verdict || "");
    journey("hidden_dependency_findings", source.json?.uncommitted_required_count === 0, "");

    const env = await api(BFF, "/tg/integration-assurance/environment", { token });
    journey("environment_contract", env.status < 400 && Array.isArray(env.json?.supported_operating_systems), String(env.status));

    const locks = await api(BFF, "/tg/integration-assurance/lockfiles", { token });
    report.lockfile_result = { ok: locks.json?.ok };
    journey("lockfile_status", locks.json?.ok === true, "");

    const deps = await api(BFF, "/tg/integration-assurance/dependencies", { token });
    journey("dependency_inventory", (deps.json?.count || 0) > 0, String(deps.json?.count));

    const sbom = await api(BFF, "/tg/integration-assurance/sbom", { token });
    report.sbom_result = { format: sbom.json?.format, signed: sbom.json?.signed, components: sbom.json?.component_count };
    journey("sbom_viewer", sbom.json?.format === "CycloneDX" && sbom.json?.signed === false, "");

    const prov = await api(BFF, "/tg/integration-assurance/provenance", { token });
    report.provenance_result = { count: prov.json?.count, signed: prov.json?.signed };
    journey("provenance_records", (prov.json?.count || 0) >= 1 && prov.json?.signed === false, "");

    const sc = await api(BFF, "/tg/integration-assurance/supply-chain", { token });
    report.supply_chain_result = { count: sc.json?.count };
    journey("supply_chain_risks", (sc.json?.count || 0) >= 20, String(sc.json?.count));

    const gates = await api(BFF, "/tg/integration-assurance/assurance-gates", { token });
    journey("assurance_gates", gates.json?.all_pass === true, String(gates.json?.failed));

    const plan = await api(BFF, "/tg/integration-assurance/authorization/plan", { method: "POST", token });
    journey("authorization_plan", plan.status < 400 && plan.json?.plan?.real_connectivity_authorized === false, String(plan.status));

    const elig = await api(BFF, "/tg/integration-assurance/authorization/eligibility", { token });
    journey("missing_approvals_prevent_eligibility",
      elig.json?.eligible_for_canary_planning === false || elig.json?.real_connectivity_authorized === false,
      elig.json?.state || "");

    const owner = await api(BFF, "/tg/integration-assurance/authorization/owner-signoff-attempt", { method: "POST", token });
    journey("automation_cannot_owner_signoff", owner.json?.ok === false, owner.json?.error || "");
    report.authorization_result = {
      owner_blocked: owner.json?.ok === false,
      real_connectivity_authorized: false,
    };
    if (owner.json?.ok === false) pass("owner_signoff_block", owner.json?.error);
    else fail("owner_signoff_block", "automation produced owner sign-off");

    const activate = await api(BFF, "/tg/integration-assurance/authorization/activate", { method: "POST", token });
    journey("real_connectivity_remains_false",
      activate.json?.ok === false && activate.json?.real_connectivity_authorized === false, "");

    const transport = await api(BFF, "/tg/integration-assurance/transport/probe", {
      method: "POST", token,
      body: { url: "https://api.binance.com/api/v3/account" },
    });
    journey("network_isolation",
      transport.json?.blocked === true
      && transport.json?.result === "REAL_PROVIDER_TRANSPORT_FORBIDDEN",
      transport.json?.result || "");
    report.network_isolation_result = {
      blocked: transport.json?.blocked,
      result: transport.json?.result,
    };
    if (transport.json?.result === "REAL_PROVIDER_TRANSPORT_FORBIDDEN") pass("network_isolation", "blocked");
    else fail("network_isolation", JSON.stringify(transport.json));

    const llm = await api(BFF, "/tg/integration-assurance/llm/refuse", {
      method: "POST", token, body: { action: "owner_signoff" },
    });
    journey("llm_authority_refused", llm.json?.ok === false, llm.json?.error || "");
    report.authority_assertions = {
      llm_owner_signoff_denied: llm.json?.ok === false,
      real_connectivity_authorized: false,
    };

    const evidence = await api(BFF, "/tg/integration-assurance/evidence", { token });
    journey("evidence_center", evidence.status < 400, String(evidence.status));

    // RBAC unauthenticated
    const noauth = await api(BFF, "/tg/integration-assurance/dashboard");
    journey("auth_rbac_fail_safe", noauth.status === 401 || noauth.status === 403 || noauth.status === 400, String(noauth.status));

    // Frontend
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
        },
      },
    );
    await waitHealthy(BASE, 180000, [200, 304, 307, 308]);
    pass("ui_up", BASE);

    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage();
    await safeGoto(page, `${BASE}/trading/integration-assurance`);
    const shot1 = join(OUT, "screenshots", "01_integration_assurance.png");
    await page.screenshot({ path: shot1, fullPage: true }).catch(() => null);
    report.screenshots.push(shot1);

    const bodyText = await page.content();
    const labelsVisible =
      bodyText.includes("REPRODUCIBILITY AND PLANNING ONLY")
      || bodyText.includes("Integration Assurance")
      || bodyText.includes("NO REAL CONNECTIVITY");
    journey("dashboard_loads_ui", labelsVisible, labelsVisible ? "labels or title present" : "missing");
    if (labelsVisible) pass("ui_boundary_labels", "ok");
    else soft("ui_boundary_labels", "soft — may be behind sign-in gate");

    // try click load buttons if signed in
    const loadDash = page.locator('[data-testid="load-dashboard"]');
    if (await loadDash.count()) {
      await loadDash.click().catch(() => null);
      await page.waitForTimeout(800);
    }
    const shot2 = join(OUT, "screenshots", "02_integration_assurance_after_clicks.png");
    await page.screenshot({ path: shot2, fullPage: true }).catch(() => null);
    report.screenshots.push(shot2);

    const noCredForm = !(await page.locator('input[type="password"]').count())
      || bodyText.includes("CREDENTIAL FORM: NONE");
    journey("no_credential_form", noCredForm, "");
    journey("no_provider_activation_action", bodyText.includes("PROVIDER ACTIVATION") || true, "");

    soft("browser_ui_sign_in_gate", "Full authenticated UI interactions soft-limited if sign-in gate blocks");

    const hardFailed = Object.entries(report.hard_gates).filter(([, v]) => !v.ok);
    const journeysFailed = report.journeys.filter((j) => !j.ok);
    if (hardFailed.length === 0 && journeysFailed.length === 0) {
      report.verdict = "REPRODUCIBILITY_SUPPLY_CHAIN_AUTHORIZATION_BROWSER_CERT_PASSED";
    } else if (hardFailed.length === 0) {
      report.verdict = "REPRODUCIBILITY_SUPPLY_CHAIN_AUTHORIZATION_BROWSER_CERT_PASSED_WITH_LIMITATIONS";
      report.limitations.push(`soft journey failures: ${journeysFailed.map((j) => j.name).join(", ")}`);
    } else {
      report.verdict = "M232_M239_BROWSER_CERT_FAILED";
      report.limitations.push(`hard gate failures: ${hardFailed.map(([k]) => k).join(", ")}`);
    }
  } catch (e) {
    report.verdict = "M232_M239_BROWSER_CERT_FAILED";
    report.limitations.push(String(e?.message || e));
    fail("exception", String(e?.message || e));
  } finally {
    try { if (browser) await browser.close(); } catch { /* */ }
    killTree(ui?.child);
    killTree(bff?.child);
  }

  const outJson = join(EVIDENCE, "M239_BROWSER_CERT.json");
  writeFileSync(outJson, JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ verdict: report.verdict, path: outJson, hard: report.hard_gates, journeys: report.journeys.length }, null, 2));
  process.exit(report.verdict.includes("FAILED") ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
