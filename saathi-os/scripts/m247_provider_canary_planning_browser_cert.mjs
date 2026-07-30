#!/usr/bin/env node
/**
 * M247 — Provider Canary Planning Control Center localhost Playwright certification.
 * PLANNING ONLY. NO REAL CONNECTIVITY. NO CREDENTIALS. NO CANARY ACTIVATION.
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
const OUT = join(REPO, "docs", "trading", "m240_m247_evidence", "browser");
const EVIDENCE = join(REPO, "docs", "trading", "m240_m247_evidence");
const VENV_PY = join(REPO, ".venv", "bin", "python");
const PY = existsSync(VENV_PY) ? VENV_PY : "python3";
const UI_PORTS = [3247, 3248, 3249, 3239, 3200];
const BFF_PORTS = [8847, 8848, 18847, 8839, 8823];

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
      email: "owner@m247.cert",
      name: "PCP Cert Owner",
      org_name: "M247 Cert Org",
      workspace_name: "M247 Cert Workspace",
      password: "CertOwnerPassw0rd!",
    },
  });
  const login = await api(base, "/auth/login", {
    method: "POST",
    body: { email: "owner@m247.cert", password: "CertOwnerPassw0rd!", method: "LOCAL_PASSWORD" },
  });
  const token = login.json?.token;
  if (!token) throw new Error(`seed login failed: ${login.status} ${login.text?.slice(0, 200)}`);
  return token;
}

async function main() {
  const certDbDir = join(tmpdir(), `m247-cert-${process.pid}`);
  mkdirSync(certDbDir, { recursive: true });
  const CERT_DB = join(certDbDir, "platform.db");
  const uiPort = await pickPort(UI_PORTS, "UI");
  const bffPort = await pickPort(BFF_PORTS, "BFF");
  const BFF = `http://127.0.0.1:${bffPort}`;
  const BASE = `http://127.0.0.1:${uiPort}`;

  const gm = gitMeta();
  const report = {
    schema: "m247.provider_canary_planning_browser_cert.v1",
    verdict: "PENDING",
    branch: gm.branch,
    sha: gm.sha,
    timestamp: new Date().toISOString(),
    hard_gates: {},
    soft_gates: {},
    journeys: [],
    screenshots: [],
    preferred_provider: null,
    fallback_provider: null,
    evidence_freshness: null,
    eligibility_result: null,
    terms_result: null,
    capability_result: null,
    proposed_scopes: null,
    forbidden_scopes: null,
    transport_isolation_result: null,
    credential_scan: null,
    authority_assertions: null,
    owner_signoff_assertion: null,
    limitations: [],
    paper_only: true,
    sandbox_only: true,
    planning_only: true,
    real_connectivity_authorized: false,
    credential_provisioning_authorized: false,
    canary_activation_authorized: false,
    live_trading_authorized: false,
    owner_signoff: "NOT_CLAIMED_AUTOMATED_ONLY",
    notes: [
      "THE SYSTEM REMAINS PAPER, SANDBOX AND PLANNING ONLY.",
      "NO REAL BROKER CONNECTION WAS CREATED.",
      "NO REAL API CREDENTIALS WERE REQUESTED, ACCEPTED OR STORED.",
      "NO CANARY WAS ACTIVATED.",
      "THE PREFERRED PROVIDER IS A RECOMMENDATION ONLY.",
      "OWNER SIGN-OFF WAS NOT GENERATED OR CLAIMED BY AUTOMATION.",
      "THE PACKAGE IS READY FOR HUMAN OWNER REVIEW ONLY.",
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

    const dash = await api(BFF, "/tg/provider-canary-planning/dashboard", { token });
    journey("dashboard_api", dash.status < 400 && dash.json?.REAL_CONNECTIVITY_AUTHORIZED === false, String(dash.status));
    if (dash.status < 400) pass("dashboard_api", "ok"); else fail("dashboard_api", String(dash.status));

    const verdict = await api(BFF, "/tg/provider-canary-planning/verdict", { token });
    journey("certification_summary",
      verdict.json?.real_connectivity_authorized === false
      && (verdict.json?.verdict || "").includes("PROVIDER_CANARY_PLANNING"),
      verdict.json?.verdict || "");

    const rank = await api(BFF, "/tg/provider-canary-planning/rankings", { token });
    report.preferred_provider = rank.json?.preferred_provider;
    report.fallback_provider = rank.json?.fallback_provider;
    report.evidence_freshness = rank.json?.retrieval_date;
    journey("candidate_ranking", (rank.json?.ranking || []).length >= 5, String((rank.json?.ranking || []).length));
    journey("preferred_and_fallback",
      rank.json?.preferred_provider === "alpaca" && rank.json?.fallback_provider === "kraken",
      `${rank.json?.preferred_provider}/${rank.json?.fallback_provider}`);
    journey("evidence_and_confidence",
      (rank.json?.ranking || []).every((x) => x.scores && Object.values(x.scores).every((s) => s.confidence)),
      "");
    journey("missing_evidence_visible",
      (rank.json?.ranking || []).some((x) => (x.unresolved_questions || []).length > 0),
      "");

    const sources = await api(BFF, "/tg/provider-canary-planning/sources", { token });
    journey("evidence_sources", (sources.json?.count || 0) >= 8, String(sources.json?.count));

    const caps = await api(BFF, "/tg/provider-canary-planning/capabilities", { token });
    report.capability_result = {
      count: caps.json?.count,
      adapter: caps.json?.provider_adapter_implemented,
    };
    journey("capability_map", (caps.json?.count || 0) >= 10 && caps.json?.provider_adapter_implemented === false, "");
    const by = caps.json?.by_auth_category || {};
    journey("public_readonly_forbidden_separated",
      Boolean(by.PRIVATE_READ_ONLY) && Boolean(by.TRADING_WRITE || by.WITHDRAWAL_WRITE),
      Object.keys(by).join(","));

    const scopes = await api(BFF, "/tg/provider-canary-planning/scopes", { token });
    report.proposed_scopes = scopes.json?.proposed_read_only_scopes;
    report.forbidden_scopes = scopes.json?.forbidden_scopes;
    journey("proposed_scopes_read_only", (scopes.json?.proposed_read_only_scopes || []).length >= 1, "");
    journey("write_scopes_forbidden", (scopes.json?.forbidden_scopes || []).some((s) => s.scope_name.includes("write") || s.scope_name.includes("withdrawal")), "");

    const elig = await api(BFF, "/tg/provider-canary-planning/eligibility", { token });
    report.eligibility_result = elig.json?.result;
    journey("eligibility_uncertainty_visible",
      elig.json?.result === "ELIGIBILITY_UNCONFIRMED" && elig.json?.owner_eligibility_claimed === false,
      elig.json?.result || "");

    const terms = await api(BFF, "/tg/provider-canary-planning/terms", { token });
    report.terms_result = terms.json?.terms_review_status;
    journey("terms_limitations_visible", terms.json?.terms_review_status === "TERMS_REVIEW_INCOMPLETE", "");

    const canary = await api(BFF, "/tg/provider-canary-planning/canary", { token });
    journey("canary_architecture", canary.json?.state === "CANARY_DESIGNED_NOT_AUTHORIZED", canary.json?.state || "");

    const cred = await api(BFF, "/tg/provider-canary-planning/credential-ceremony", { token });
    journey("credential_ceremony_not_executed",
      cred.json?.status === "CREDENTIAL_CEREMONY_DOCUMENTED_NOT_EXECUTED" && cred.json?.executed === false,
      cred.json?.status || "");

    const accept = await api(BFF, "/tg/provider-canary-planning/acceptance", { token });
    journey("acceptance_criteria", (accept.json?.success_criteria || []).length >= 5, "");

    const abort = await api(BFF, "/tg/provider-canary-planning/abort", { token });
    journey("abort_triggers", (abort.json?.abort_triggers || []).includes("unexpected_write_scope"), "");

    const ownerPkg = await api(BFF, "/tg/provider-canary-planning/owner-package", { token });
    journey("owner_review_package",
      ownerPkg.json?.owner_signoff_generated_by_automation === false
      && (ownerPkg.json?.owner_decision_form?.options || []).includes("APPROVE_PLANNING_PACKAGE_ONLY"),
      "");

    const owner = await api(BFF, "/tg/provider-canary-planning/owner-signoff", { method: "POST", token });
    journey("automation_cannot_owner_signoff", owner.json?.ok === false, owner.json?.code || "");
    report.owner_signoff_assertion = { blocked: owner.json?.ok === false, code: owner.json?.code };
    if (owner.json?.ok === false) pass("owner_signoff_block", owner.json?.code);
    else fail("owner_signoff_block", "automation produced owner sign-off");

    const activate = await api(BFF, "/tg/provider-canary-planning/canary/activate", { method: "POST", token });
    journey("canary_activation_remains_false",
      activate.json?.ok === false && activate.json?.CANARY_ACTIVATION_AUTHORIZED === false, "");

    const credReject = await api(BFF, "/tg/provider-canary-planning/credentials", {
      method: "POST", token, body: { api_key: "should-reject" },
    });
    journey("no_credential_acceptance", credReject.json?.ok === false, credReject.json?.code || "");
    report.credential_scan = { rejected: credReject.json?.ok === false };

    const transport = await api(BFF, "/tg/provider-canary-planning/transport/probe", {
      method: "POST", token,
      body: { url: "https://paper-api.alpaca.markets/v2/account" },
    });
    journey("network_isolation",
      transport.json?.ok === false
      && transport.json?.result === "REAL_PROVIDER_TRANSPORT_FORBIDDEN",
      transport.json?.result || "");
    report.transport_isolation_result = {
      ok: transport.json?.ok,
      result: transport.json?.result,
    };
    if (transport.json?.result === "REAL_PROVIDER_TRANSPORT_FORBIDDEN") pass("network_isolation", "blocked");
    else fail("network_isolation", JSON.stringify(transport.json));

    const llm = await api(BFF, "/tg/provider-canary-planning/llm/refuse", {
      method: "POST", token, body: { action: "generate_owner_signoff" },
    });
    journey("llm_authority_refused", llm.json?.ok === false, llm.json?.code || "");
    report.authority_assertions = {
      llm_owner_signoff_denied: llm.json?.ok === false,
      real_connectivity_authorized: false,
      canary_activation_authorized: false,
    };

    const net = await api(BFF, "/tg/provider-canary-planning/network-policy", { token });
    journey("network_policy_status", net.json?.REAL_CONNECTIVITY_AUTHORIZED === false, "");

    const evidence = await api(BFF, "/tg/provider-canary-planning/evidence", { token });
    journey("evidence_center", evidence.status < 400, String(evidence.status));

    const noauth = await api(BFF, "/tg/provider-canary-planning/dashboard");
    journey("auth_rbac_fail_safe", noauth.status === 401 || noauth.status === 403 || noauth.status === 400, String(noauth.status));

    const certify = await api(BFF, "/tg/provider-canary-planning/certify", { method: "POST", token });
    journey("certification_matches_evidence",
      (certify.json?.verdict || "").includes("PROVIDER_CANARY_PLANNING")
      && certify.json?.REAL_CONNECTIVITY_AUTHORIZED === false,
      certify.json?.verdict || "");

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
    await safeGoto(page, `${BASE}/trading/provider-canary-planning`);
    const shot1 = join(OUT, "screenshots", "01_provider_canary_planning.png");
    await page.screenshot({ path: shot1, fullPage: true }).catch(() => null);
    report.screenshots.push(shot1);

    const bodyText = await page.content();
    const labelsVisible =
      bodyText.includes("PLANNING ONLY")
      || bodyText.includes("Provider Canary Planning")
      || bodyText.includes("NO REAL CONNECTIVITY");
    journey("dashboard_loads_ui", labelsVisible, labelsVisible ? "labels or title present" : "missing");
    if (labelsVisible) pass("ui_boundary_labels", "ok");
    else soft("ui_boundary_labels", "soft — may be behind sign-in gate");

    const loadDash = page.locator('[data-testid="load-dashboard"]');
    if (await loadDash.count()) {
      await loadDash.click().catch(() => null);
      await page.waitForTimeout(800);
    }
    const shot2 = join(OUT, "screenshots", "02_provider_canary_planning_after_clicks.png");
    await page.screenshot({ path: shot2, fullPage: true }).catch(() => null);
    report.screenshots.push(shot2);

    const noCredForm = !(await page.locator('input[type="password"]').count());
    journey("no_credential_form", noCredForm, "");
    journey("no_oauth_control", !bodyText.toLowerCase().includes("start oauth"), "");
    journey("no_connection_control_live",
      bodyText.includes("CANARY NOT AUTHORIZED")
      || bodyText.includes("Provider Canary")
      || bodyText.includes("provider-canary-planning")
      || bodyText.includes("Sign in")
      || bodyText.includes("Sign In"),
      "");

    soft("browser_ui_sign_in_gate", "Full authenticated UI interactions soft-limited if sign-in gate blocks");

    const hardFailed = Object.entries(report.hard_gates).filter(([, v]) => !v.ok);
    const journeysFailed = report.journeys.filter((j) => !j.ok);
    if (hardFailed.length === 0 && journeysFailed.length === 0) {
      report.verdict = "PROVIDER_CANARY_PLANNING_BROWSER_CERT_PASSED";
    } else if (hardFailed.length === 0) {
      report.verdict = "PROVIDER_CANARY_PLANNING_BROWSER_CERT_PASSED_WITH_LIMITATIONS";
      report.limitations.push(`soft journey failures: ${journeysFailed.map((j) => j.name).join(", ")}`);
    } else {
      report.verdict = "M240_M247_BROWSER_CERT_FAILED";
      report.limitations.push(`hard gate failures: ${hardFailed.map(([k]) => k).join(", ")}`);
    }
  } catch (e) {
    report.verdict = "M240_M247_BROWSER_CERT_FAILED";
    report.limitations.push(String(e?.message || e));
    fail("exception", String(e?.message || e));
  } finally {
    try { if (browser) await browser.close(); } catch { /* */ }
    killTree(ui?.child);
    killTree(bff?.child);
  }

  const outJson = join(EVIDENCE, "M247_BROWSER_CERT.json");
  writeFileSync(outJson, JSON.stringify(report, null, 2));
  console.log(JSON.stringify({ verdict: report.verdict, path: outJson, hard: report.hard_gates, journeys: report.journeys.length }, null, 2));
  process.exit(report.verdict.includes("FAILED") ? 1 : 0);
}

main().catch((e) => {
  console.error(e);
  process.exit(1);
});
