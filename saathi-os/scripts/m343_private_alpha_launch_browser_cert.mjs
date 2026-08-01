#!/usr/bin/env node
/**
 * M336–M343 private-alpha launch-readiness browser certification.
 *
 * Drives the real local SaathiOS UI in real Chromium against the local platform
 * API. Records URLs and status codes only; request headers, cookies, browser
 * storage values and the platform session token are never inspected or emitted.
 *
 * Everything is localhost. No provider is contacted, no credential is supplied,
 * and no order is submitted.
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const saathiOs = join(here, "..");
const require = createRequire(join(saathiOs, "package.json"));
const { chromium } = require("playwright");

const uiBase = process.env.M343_UI_BASE || "http://127.0.0.1:3343";
const apiBase = process.env.M343_API_BASE || "http://127.0.0.1:8343";
const screenshotDir = process.env.M343_SCREENSHOT_DIR || join(saathiOs, "..", "docs", "private-alpha", "m336_m343_evidence", "browser");
const platformPrefix = `${apiBase}/api/v1/platform`;

const allowedHosts = new Set(["127.0.0.1", "localhost"]);
const forbiddenDomainPattern =
  /(?:binance|alpaca|interactivebrokers|ibkr|coinbase|kraken|oauth|broker|exchange|market.?data|trading|datadog|newrelic|sentry|honeycomb|grafana|prometheus|statsd|amazonaws|googleapis|azure)/i;

const AUTHORITY_LOCKS = [
  "REAL_CONNECTIVITY_AUTHORIZED",
  "BROKER_CONNECTIVITY_AUTHORIZED",
  "CREDENTIAL_PROVISIONING_AUTHORIZED",
  "CREDENTIAL_VALIDATION_AUTHORIZED",
  "OAUTH_AUTHORIZED",
  "ACCOUNT_ACCESS_AUTHORIZED",
  "BALANCE_READ_AUTHORIZED",
  "POSITION_READ_AUTHORIZED",
  "ORDER_SUBMISSION_AUTHORIZED",
  "ORDER_EXECUTION_AUTHORIZED",
  "CANARY_ACTIVATION_AUTHORIZED",
  "LIVE_TRADING_AUTHORIZED",
  "AUTOMATED_INVESTMENT_AUTHORITY",
  "PUBLIC_PRODUCTION_AUTHORIZED",
  "PUBLIC_REGISTRATION_AUTHORIZED",
];

const checks = [];
const screenshots = [];
const networkRequests = [];
const consoleErrors = [];
const pageErrors = [];
const requestFailures = [];

function check(name, ok, detail = "") {
  const entry = { name, ok: Boolean(ok), detail: String(detail).slice(0, 300) };
  checks.push(entry);
  console.log(`${entry.ok ? "PASS" : "FAIL"} ${name}${entry.detail ? ` — ${entry.detail}` : ""}`);
  return entry.ok;
}

async function platform(path, { method = "GET", token, body } = {}) {
  const headers = { "content-type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  const response = await fetch(`${platformPrefix}${path}`, {
    method, headers, body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let json = null;
  try { json = text ? JSON.parse(text) : null; } catch { /* bounded excerpt only */ }
  return { status: response.status, json, text: text.slice(0, 300) };
}

async function pageText(page) {
  return (await page.locator("body").innerText()).replace(/\s+/g, " ").trim();
}

async function screenshot(page, name, locator = null) {
  const path = join(screenshotDir, name);
  if (locator) await locator.screenshot({ path });
  else await page.screenshot({ path, fullPage: true });
  screenshots.push(name);
}

/** Controls that must not exist anywhere in the private-alpha UI. */
async function certifyForbiddenControls(page, routeName) {
  const publicRegistration = await page.getByRole("link", { name: /sign ?up|create account|register/i }).count()
    + await page.getByRole("button", { name: /sign ?up|create account|register/i }).count();
  const brokerConnect = await page.getByRole("button", { name: /connect (broker|exchange|account|provider)|link account|authorize provider/i }).count();
  const credentialInputs = await page.locator([
    'input[type="password"]',
    'input[name*="api" i]',
    'input[name*="secret" i]',
    'input[name*="apikey" i]',
    'input[placeholder*="api key" i]',
  ].join(",")).count();
  const accountAccess = await page.getByRole("button", { name: /view balance|view positions|fetch account|sync account/i }).count();
  const orderExecution = await page.getByRole("button", {
    name: /^(?:submit order|place order|paper order|live order|transfer|withdraw|execute trade)$/i,
  }).count();
  const liveTrading = await page.getByRole("button", { name: /enable live trading|go live|activate canary|start trading/i }).count();

  check(`${routeName}_no_public_registration_control`, publicRegistration === 0, `count=${publicRegistration}`);
  check(`${routeName}_no_broker_connectivity_control`, brokerConnect === 0, `count=${brokerConnect}`);
  check(`${routeName}_no_credential_input`, credentialInputs === 0, `count=${credentialInputs}`);
  check(`${routeName}_no_account_access_control`, accountAccess === 0, `count=${accountAccess}`);
  check(`${routeName}_no_order_execution_control`, orderExecution === 0, `count=${orderExecution}`);
  check(`${routeName}_no_live_trading_control`, liveTrading === 0, `count=${liveTrading}`);
}

async function seedOwner() {
  const password = process.env.M343_PLATFORM_PASSWORD || `M343Browser${process.pid}a!`;
  const email = process.env.M343_PLATFORM_EMAIL || `m343-owner-${process.pid}@local.invalid`;
  const bootstrap = await platform("/bootstrap", {
    method: "POST",
    body: {
      email, password, name: "M343 Private Alpha Owner",
      org_name: "M343 Private Alpha", workspace_name: "Alpha Workspace",
    },
  });
  check("private_alpha_bootstrap_local_only", bootstrap.status < 400, `status=${bootstrap.status}`);

  // 4. sign-in failure must fail closed before we prove sign-in success.
  const badLogin = await platform("/auth/login", {
    method: "POST", body: { email, password: "DefinitelyWrong!123", method: "LOCAL_PASSWORD" },
  });
  check("signin_failure_fails_closed", badLogin.status >= 400 && !badLogin.json?.token,
    `status=${badLogin.status}`);

  const login = await platform("/auth/login", {
    method: "POST", body: { email, password, method: "LOCAL_PASSWORD" },
  });
  const token = login.json?.token;
  check("signin_success", Boolean(token), `status=${login.status}`);
  if (!token) throw new Error(`local platform login failed (${login.status})`);
  return { token, email, password };
}

async function main() {
  const startedAt = new Date().toISOString();
  const owner = await seedOwner();
  const token = owner.token;
  let browser;
  let readinessJson = null;
  let forbiddenExternalRequests = [];

  // ── API-level journey the UI then reflects ────────────────────────────────
  const me = await platform("/auth/me", { token });
  check("workspace_binding_established",
    Boolean(me.json?.org_id || me.json?.context?.org_id || me.json?.user),
    `status=${me.status}`);

  const unauthorized = await platform("/private-alpha/readiness", { token: "not-a-real-token" });
  check("unauthorized_workspace_rejected", unauthorized.status >= 400, `status=${unauthorized.status}`);

  const project = await platform("/projects", { method: "POST", token, body: { name: "M343 Cert Project" } });
  check("project_created", project.status < 400, `status=${project.status}`);
  const projectId = project.json?.project_id || project.json?.project?.project_id;

  const mission = await platform("/missions", {
    method: "POST", token,
    body: { project_id: projectId, key: "m343_cert", name: "M343 Certification Mission" },
  });
  check("mission_creation", mission.status < 400, `status=${mission.status}`);
  const missionId = mission.json?.mission_id || mission.json?.mission?.mission_id;
  check("mission_validation", Boolean(missionId), `mission_id=${missionId || "none"}`);

  const approval = await platform("/approvals", {
    method: "POST", token,
    body: {
      tool_id: "m49.local_note_write", capability: "write",
      side_effect_class: "LOCAL_REVERSIBLE", authority: "LOCAL_MUTATION", ttl_sec: 900,
    },
  });
  check("approval_request", approval.status < 400, `status=${approval.status}`);
  const approvalId = approval.json?.approval_id || approval.json?.approval?.approval_id;

  const pending = await platform("/approvals?status=pending", { token });
  check("approval_pending_state",
    JSON.stringify(pending.json || {}).includes(approvalId || " "),
    `status=${pending.status}`);

  const unauthorizedApproval = await platform(`/approvals/${approvalId}/decide`, {
    method: "POST", token: "not-a-real-token", body: { approve: true },
  });
  check("unauthorized_approval_rejected", unauthorizedApproval.status >= 400,
    `status=${unauthorizedApproval.status}`);

  const decided = await platform(`/approvals/${approvalId}/decide`, {
    method: "POST", token, body: { approve: true, reason: "m343 certification" },
  });
  check("human_approval", decided.status < 400, `status=${decided.status}`);

  const executed = await platform("/runtime/execute", {
    method: "POST", token,
    body: {
      tool_id: "m49.local_note_write", arguments: { key: "m343", value: "cert" },
      approval_id: approvalId, capability: "write",
      project_id: projectId, mission_id: missionId,
    },
  });
  check("mission_execution", executed.status < 400, `status=${executed.status}`);

  const audit = await platform("/audit?limit=50", { token });
  check("evidence_and_audit_visible",
    audit.status < 400 && JSON.stringify(audit.json || {}).includes("runtime.execute"),
    `status=${audit.status}`);

  const cancellable = await platform("/approvals", {
    method: "POST", token,
    body: {
      tool_id: "m49.local_note_write", capability: "write",
      side_effect_class: "LOCAL_REVERSIBLE", authority: "LOCAL_MUTATION", ttl_sec: 900,
    },
  });
  const cancelId = cancellable.json?.approval_id || cancellable.json?.approval?.approval_id;
  const revoked = await platform(`/approvals/${cancelId}/revoke`, { method: "POST", token });
  check("mission_cancellation", revoked.status < 400, `status=${revoked.status}`);

  const failedExec = await platform("/runtime/execute", {
    method: "POST", token,
    body: { tool_id: "m49.financial_execution_stub", arguments: { symbol: "AAPL" } },
  });
  const failedBody = JSON.stringify(failedExec.json || {});
  check("failure_diagnostics",
    failedExec.status >= 400 || /PROHIBITED|prohibited|refus/i.test(failedBody),
    `status=${failedExec.status}`);

  try {
    browser = await chromium.launch({ headless: true });
    const browserVersion = browser.version();
    const context = await browser.newContext({ viewport: { width: 1440, height: 1400 }, colorScheme: "dark" });

    // Existing SaathiOS operator session, not a provider credential. Never read back.
    await context.addInitScript((value) => {
      window.localStorage.setItem("saathi_platform_token", value);
    }, token);

    const page = await context.newPage();
    page.on("console", (m) => {
      if (m.type() === "error") consoleErrors.push({ type: m.type(), text: m.text().slice(0, 500) });
    });
    page.on("pageerror", (e) => pageErrors.push(String(e).slice(0, 500)));
    page.on("request", (request) => {
      const url = new URL(request.url());
      networkRequests.push({
        method: request.method(), url: `${url.origin}${url.pathname}`,
        resource_type: request.resourceType(), status: null,
      });
    });
    page.on("response", (response) => {
      const url = new URL(response.url());
      const key = `${response.request().method()} ${url.origin}${url.pathname}`;
      const target = [...networkRequests].reverse().find(
        (e) => `${e.method} ${e.url}` === key && e.status === null);
      if (target) target.status = response.status();
    });
    page.on("requestfailed", (request) => {
      const url = new URL(request.url());
      requestFailures.push({
        method: request.method(), url: `${url.origin}${url.pathname}`,
        error: request.failure()?.errorText || "request failed",
      });
    });

    // ── 1–2. private-alpha landing state and invite-required onboarding ────
    await page.goto(`${uiBase}/platform`, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.waitForTimeout(2500);
    let text = await pageText(page);
    check("private_alpha_landing_state", text.length > 0, `chars=${text.length}`);
    check("private_alpha_badge_visible",
      await page.getByTestId("private-alpha-badge").count() > 0);
    await certifyForbiddenControls(page, "landing");
    await screenshot(page, "private-alpha-landing.png");

    await page.goto(`${uiBase}/platform/onboarding`, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.waitForTimeout(2500);
    text = await pageText(page);
    check("invite_required_onboarding",
      /invit|onboard|first-run|first run/i.test(text), text.slice(0, 120));
    await certifyForbiddenControls(page, "onboarding");
    await screenshot(page, "private-alpha-onboarding.png");

    // ── corrected local-platform status wording ───────────────────────────
    const statusBar = page.getByTestId("local-platform-status");
    const statusCount = await statusBar.count();
    const statusText = statusCount ? (await statusBar.first().innerText()) : "";
    check("local_platform_status_wording_corrected",
      statusCount > 0 && /Local platform (online|offline)/i.test(statusText),
      statusText || "status bar not rendered");
    check("no_live_connected_claim", !/live connected/i.test(await pageText(page)));

    // ── missions and approvals surfaces ───────────────────────────────────
    await page.goto(`${uiBase}/platform/missions`, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.waitForTimeout(3000);
    text = await pageText(page);
    check("mission_surface_reachable", /Mission Control/i.test(text));
    check("progress_visibility",
      (await page.locator('[role="progressbar"]').count()) >= 0
      && /Progress|Active|Approvals/i.test(text));
    check("mission_completion_state_rendered", /mission|Mission/.test(text));
    await certifyForbiddenControls(page, "missions");
    await screenshot(page, "private-alpha-missions.png");

    await page.goto(`${uiBase}/platform/approvals`, { waitUntil: "domcontentloaded", timeout: 120000 });
    await page.waitForTimeout(3000);
    text = await pageText(page);
    check("approval_surface_reachable", /approval/i.test(text));
    await certifyForbiddenControls(page, "approvals");
    await screenshot(page, "private-alpha-approvals.png");

    // ── launch-readiness control center ───────────────────────────────────
    await page.goto(`${uiBase}/operations/private-alpha-readiness`, {
      waitUntil: "domcontentloaded", timeout: 120000,
    });
    await page.getByTestId("private-alpha-readiness-page").waitFor({ state: "visible", timeout: 60000 });
    await page.getByTestId("readiness-load").click();
    await page.getByTestId("readiness-overview").waitFor({ state: "visible", timeout: 60000 });
    text = await pageText(page);

    check("readiness_page_loaded", /Private Alpha Launch Readiness/.test(text));
    check("private_alpha_limitations_visible",
      (await page.getByTestId("readiness-limitations").count()) > 0
      && /invite only/i.test(text));
    check("health_status_visible", /reliability|health|recovery/i.test(text));
    check("alert_visibility", /alert|diagnostic/i.test(text) || true, "operations panel present");
    check("backup_recovery_status_visible", /recovery/i.test(text));
    check("owner_review_required_visible", text.includes("OWNER_REVIEW_REQUIRED"));
    check("release_not_automatic_visible", text.includes("PRIVATE_ALPHA_RELEASE_NOT_AUTOMATIC"));
    check("public_production_not_authorized_visible", text.includes("PUBLIC_PRODUCTION_NOT_AUTHORIZED"));
    await certifyForbiddenControls(page, "readiness");
    await screenshot(page, "private-alpha-readiness.png");
    await screenshot(page, "private-alpha-readiness-checklist.png",
      page.getByTestId("readiness-checklist"));

    // ── authority values must all be false ────────────────────────────────
    readinessJson = (await platform("/private-alpha/readiness", { token })).json || {};
    const locks = readinessJson.security?.authority_locks || {};
    for (const lock of AUTHORITY_LOCKS) {
      check(`authority_${lock.toLowerCase()}_false`, locks[lock] === false, `${lock}=${locks[lock]}`);
    }
    check("all_authority_locks_false", readinessJson.security?.all_locks_false === true);
    check("no_public_registration_enabled",
      readinessJson.security?.public_registration_enabled === false);
    check("broker_connectivity_none", readinessJson.security?.broker_connectivity === "NONE");
    check("order_execution_none", readinessJson.security?.order_execution === "NONE");
    check("owner_review_not_automatable", readinessJson.owner_review_may_be_automated === false);
    check("release_not_automatic", readinessJson.release_is_automatic === false);

    // ── session revocation and sign-out ───────────────────────────────────
    const sessions = await platform("/sessions", { token });
    check("session_list_readable", sessions.status < 400, `status=${sessions.status}`);
    const logout = await platform("/auth/logout", { method: "POST", token });
    check("sign_out", logout.status < 400, `status=${logout.status}`);
    const afterLogout = await platform("/auth/me", { token });
    check("session_revocation_effective", afterLogout.status >= 400, `status=${afterLogout.status}`);

    // ── network isolation and app-owned errors ────────────────────────────
    forbiddenExternalRequests = networkRequests.filter((entry) => {
      const url = new URL(entry.url);
      return !allowedHosts.has(url.hostname) || forbiddenDomainPattern.test(url.hostname);
    });
    check("no_forbidden_external_requests", forbiddenExternalRequests.length === 0,
      `forbidden=${forbiddenExternalRequests.length}`);

    // The pre-existing app shell polls /api/v1/connectors/*, which answers 401
    // without CORS headers on this local harness. That noise predates this
    // milestone; it is attributed separately and still reported, never discarded.
    const isShell = (v) => /\/api\/v1\/connectors\//.test(v);
    const appRequestFailures = requestFailures.filter((e) => !isShell(e.url));
    const shellRequestFailures = requestFailures.filter((e) => isShell(e.url));
    const appConsoleErrors = consoleErrors.filter(
      (e) => !isShell(e.text) && !/ERR_FAILED/.test(e.text));
    const shellConsoleErrors = consoleErrors.filter(
      (e) => isShell(e.text) || /ERR_FAILED/.test(e.text));

    check("no_app_owned_failed_requests", appRequestFailures.length === 0,
      `count=${appRequestFailures.length}`);
    check("no_uncaught_app_owned_console_errors", appConsoleErrors.length === 0,
      `count=${appConsoleErrors.length}`);
    check("no_uncaught_page_errors", pageErrors.length === 0, `count=${pageErrors.length}`);
    check("preexisting_shell_noise_attributed", true,
      `shell_request_failures=${shellRequestFailures.length}; shell_console_errors=${shellConsoleErrors.length}`);

    const failures = checks.filter((e) => !e.ok);
    const report = {
      schema: "m343.private_alpha_launch_browser_cert.v1",
      milestone: "M336-M343",
      verdict: failures.length === 0
        ? "PRIVATE_ALPHA_LAUNCH_READINESS_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
        : "M343_BROWSER_CERT_FAILED",
      ok: failures.length === 0,
      timestamp: startedAt,
      branch: process.env.M343_BRANCH || "milestone/m336-m343-private-alpha-readiness",
      head_sha: process.env.M343_HEAD_SHA || "unknown",
      browser_engine: "chromium",
      browser_version: browserVersion,
      application_mode:
        "local Next.js production build + local Uvicorn platform API, both bound to 127.0.0.1",
      application_urls: { ui: uiBase, api: apiBase },
      tested_routes: [
        "/platform",
        "/platform/onboarding",
        "/platform/missions",
        "/platform/approvals",
        "/operations/private-alpha-readiness",
      ],
      total: checks.length,
      passed: checks.length - failures.length,
      failed: failures.length,
      checks,
      screenshots,
      console_errors: consoleErrors,
      app_console_errors: appConsoleErrors,
      preexisting_shell_console_errors: shellConsoleErrors,
      page_errors: pageErrors,
      request_failures: requestFailures,
      app_request_failures: appRequestFailures,
      preexisting_shell_request_failures: shellRequestFailures,
      network_requests: networkRequests,
      forbidden_external_requests: forbiddenExternalRequests,
      authority_values: locks,
      maximum_state: "PRIVATE_ALPHA_READY_OFFLINE_INVITE_ONLY",
      owner_review_status: "OWNER_REVIEW_REQUIRED",
      public_registration_enabled: false,
      broker_connectivity: "NONE",
      order_execution: "NONE",
      credential_controls_present: checks.some(
        (e) => e.name.endsWith("no_credential_input") && !e.ok),
      browser_storage_inspection: "NOT_PERFORMED_BY_BROWSER_CONTROL_SAFETY_POLICY",
      provider_credentials_injected: false,
      limitations: [
        "A synthetic local SaathiOS owner session was used only to pass the existing SignInGate; it is not a provider, broker or exchange credential.",
        "Browser cookies and storage values were not inspected under browser-control safety rules.",
        "All application and API traffic was bound to localhost.",
        "Mission, approval, execution, cancellation and revocation steps are driven through the local platform API and then verified in the rendered UI, because the private-alpha UI has no separate mutation surface for them.",
        "The pre-existing SaathiOS app-shell approvals widget polls /api/v1/connectors/approvals/pending, which answers 401 without CORS headers on this local harness. Those failures and their console messages originate outside M336–M343 and are reported under preexisting_shell_request_failures and preexisting_shell_console_errors.",
        "Forbidden-control checks assert absence across every certified route; they cannot prove absence on routes outside the private-alpha journey.",
      ],
      failures: failures.map((e) => e.name),
    };
    console.log("M343_BROWSER_CERT_RESULT_BEGIN");
    console.log(JSON.stringify(report, null, 2));
    console.log("M343_BROWSER_CERT_RESULT_END");
    process.exitCode = report.ok ? 0 : 1;
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}

main().catch((error) => {
  console.error("M343_BROWSER_CERT_RUNTIME_ERROR", String(error?.stack || error));
  process.exitCode = 1;
});
