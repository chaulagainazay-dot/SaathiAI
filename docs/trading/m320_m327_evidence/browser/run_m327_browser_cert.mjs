#!/usr/bin/env node
/**
 * M327 interactive browser certification.
 *
 * This harness renders the actual local Control Center routes against the
 * local platform API. It records URLs and status codes only; request headers,
 * cookies, browser storage values, and the platform session token are never
 * inspected or emitted.
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const repo = join(here, "../../../..");
const saathiOs = join(repo, "saathi-os");
const require = createRequire(join(saathiOs, "package.json"));
const { chromium } = require("playwright");

const uiBase = process.env.M327_UI_BASE || "http://127.0.0.1:3327";
const apiBase = process.env.M327_API_BASE || "http://127.0.0.1:8327";
const screenshotDir = process.env.M327_SCREENSHOT_DIR || here;
const platformPrefix = `${apiBase}/api/v1/platform`;

const allowedHosts = new Set(["127.0.0.1", "localhost"]);
const forbiddenDomainPattern =
  /(?:binance|alpaca|interactivebrokers|ibkr|coinbase|kraken|oauth|broker|exchange|market.?data|trading)/i;
const hardAuthorityKeys = [
  "REAL_CONNECTIVITY_AUTHORIZED",
  "BROKER_CONNECTIVITY_AUTHORIZED",
  "OAUTH_AUTHORIZED",
  "CREDENTIAL_PROVISIONING_AUTHORIZED",
  "CREDENTIAL_VALIDATION_AUTHORIZED",
  "AUTHENTICATION_AUTHORIZED",
  "ACCOUNT_ACCESS_AUTHORIZED",
  "BALANCE_READ_AUTHORIZED",
  "POSITION_READ_AUTHORIZED",
  "ORDER_HISTORY_AUTHORIZED",
  "ORDER_SUBMISSION_AUTHORIZED",
  "ORDER_EXECUTION_AUTHORIZED",
  "TRANSFER_AUTHORIZED",
  "WITHDRAWAL_AUTHORIZED",
  "CANARY_ACTIVATION_AUTHORIZED",
  "LIVE_TRADING_AUTHORIZED",
  "AUTOMATED_INVESTMENT_AUTHORITY",
];
const allowedSessionStates = [
  "DISCONNECTED",
  "MOCK_READY",
  "REPLAY_READY",
  "UNAVAILABLE",
  "FAULTED",
  "CLOSED",
];
const forbiddenSessionStates = [
  "AUTHENTICATED",
  "LOGGED_IN",
  "ACCOUNT_CONNECTED",
  "BROKER_CONNECTED",
  "TRADING_READY",
  "EXECUTION_READY",
  "LIVE",
];

const checks = [];
const screenshots = [];
const networkRequests = [];
const consoleErrors = [];
const pageErrors = [];
const requestFailures = [];

function check(name, ok, detail = "") {
  const entry = { name, ok: Boolean(ok), detail };
  checks.push(entry);
  console.log(`${entry.ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
  return entry.ok;
}

async function platform(path, { method = "GET", token, body } = {}) {
  const headers = { "content-type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  const response = await fetch(`${platformPrefix}${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    // The caller records a bounded, non-secret text excerpt on malformed JSON.
  }
  return { status: response.status, json, text: text.slice(0, 300) };
}

async function seedPlatformOperator() {
  const password = process.env.M327_PLATFORM_PASSWORD || `M327Browser${process.pid}a!`;
  const email = process.env.M327_PLATFORM_EMAIL || `m327-browser-${process.pid}@local.invalid`;
  const bootstrap = await platform("/bootstrap", {
    method: "POST",
    body: {
      email,
      name: "M327 Browser Cert Operator",
      org_name: "M327 Local Certification",
      workspace_name: "Offline Provider Contracts",
      password,
    },
  });
  check("platform_bootstrap_local_only", bootstrap.status < 400, `status=${bootstrap.status}`);

  const login = await platform("/auth/login", {
    method: "POST",
    body: { email, password, method: "LOCAL_PASSWORD" },
  });
  const token = login.json?.token;
  check("platform_operator_session_local_only", Boolean(token), `status=${login.status}`);
  if (!token) throw new Error(`local platform login failed (${login.status})`);
  return token;
}

async function screenshot(page, name, locator = null) {
  const path = join(screenshotDir, name);
  if (locator) {
    await locator.screenshot({ path });
  } else {
    await page.screenshot({ path, fullPage: true });
  }
  screenshots.push(name);
  check(`screenshot_${name}`, true, name);
}

async function pageText(page) {
  return (await page.locator("body").innerText()).replace(/\s+/g, " ").trim();
}

async function certifyForbiddenControls(page, routeName) {
  const credentialControls = await page.locator([
    'input[type="password"]',
    'input[name*="api" i]',
    'input[id*="api" i]',
    'input[name*="secret" i]',
    'input[id*="secret" i]',
    'textarea[name*="secret" i]',
    'textarea[id*="secret" i]',
  ].join(",")).count();
  const oauthControls = await page.getByRole("button", { name: /oauth|authorize provider|provider login/i }).count()
    + await page.getByRole("link", { name: /oauth|authorize provider|provider login/i }).count();
  const accountControls = await page.getByRole("button", { name: /link account|account linking|connect account/i }).count()
    + await page.getByRole("link", { name: /link account|account linking|connect account/i }).count();
  const orderControls = await page.getByRole("button", {
    name: /^(?:submit order|place order|paper order|live order|transfer|withdraw|activate canary|enable execution)$/i,
  }).count()
    + await page.getByRole("link", {
      name: /^(?:submit order|place order|paper order|live order|transfer|withdraw|activate canary|enable execution)$/i,
    }).count();
  const liveConnectControls = await page.getByRole("button", {
    name: /live connect|connect provider|connect broker|connect exchange/i,
  }).count()
    + await page.getByRole("link", {
      name: /live connect|connect provider|connect broker|connect exchange/i,
    }).count();

  check(`${routeName}_credential_controls_absent`, credentialControls === 0, `count=${credentialControls}`);
  check(`${routeName}_oauth_controls_absent`, oauthControls === 0, `count=${oauthControls}`);
  check(`${routeName}_account_controls_absent`, accountControls === 0, `count=${accountControls}`);
  check(`${routeName}_order_controls_absent`, orderControls === 0, `count=${orderControls}`);
  check(`${routeName}_live_connect_controls_absent`, liveConnectControls === 0, `count=${liveConnectControls}`);
}

async function main() {
  const startedAt = new Date().toISOString();
  const platformToken = await seedPlatformOperator();
  let browser;

  try {
    browser = await chromium.launch({ headless: true });
    const browserVersion = browser.version();
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1100 },
      colorScheme: "dark",
    });

    // This is the existing SaathiOS operator session, not a provider credential.
    // Its value is never read back, logged, or included in evidence.
    await context.addInitScript((token) => {
      window.localStorage.setItem("saathi_platform_token", token);
    }, platformToken);

    const page = await context.newPage();
    page.on("console", (message) => {
      if (message.type() === "error") {
        consoleErrors.push({ type: message.type(), text: message.text().slice(0, 500) });
      }
    });
    page.on("pageerror", (error) => pageErrors.push(String(error).slice(0, 500)));
    page.on("request", (request) => {
      const url = new URL(request.url());
      networkRequests.push({
        method: request.method(),
        url: `${url.origin}${url.pathname}`,
        resource_type: request.resourceType(),
        status: null,
      });
    });
    page.on("response", (response) => {
      const url = new URL(response.url());
      const key = `${response.request().method()} ${url.origin}${url.pathname}`;
      const target = [...networkRequests].reverse().find(
        (entry) => `${entry.method} ${entry.url}` === key && entry.status === null,
      );
      if (target) target.status = response.status();
    });
    page.on("requestfailed", (request) => {
      const url = new URL(request.url());
      requestFailures.push({
        method: request.method(),
        url: `${url.origin}${url.pathname}`,
        error: request.failure()?.errorText || "request failed",
      });
    });

    await page.goto(`${uiBase}/trading/provider-contracts`, {
      waitUntil: "domcontentloaded",
      timeout: 90000,
    });
    await page.getByTestId("provider-contracts-page").waitFor({ state: "visible" });
    await page.getByTestId("pc-load-overview").click();
    await page.getByTestId("pc-provider-list").waitFor({ state: "visible" });
    await page.getByTestId("pc-session-card").waitFor({ state: "visible" });

    let text = await pageText(page);
    check("provider_page_loaded", text.includes("Credentialless Provider Contracts"));
    check("offline_provider_selection_visible", await page.getByTestId("pc-provider-select").isVisible());
    check("provider_contract_information_visible", text.includes("Offline Providers"));
    for (const banner of [
      "OFFLINE MOCK DATA",
      "NO PROVIDER CONNECTION",
      "NO ACCOUNT ACCESS",
      "NO ORDER EXECUTION",
    ]) {
      check(`provider_banner_${banner.replace(/\s+/g, "_").toLowerCase()}`, text.includes(banner));
    }
    for (const authority of hardAuthorityKeys) {
      check(`authority_${authority.toLowerCase()}_false`, text.includes(`${authority}=false`));
    }

    const sessionText = await page.getByTestId("pc-session-card").innerText();
    for (const state of allowedSessionStates) {
      check(`session_allowed_${state.toLowerCase()}_visible`, sessionText.includes(state));
    }
    for (const state of forbiddenSessionStates) {
      check(`session_forbidden_${state.toLowerCase()}_absent`, !sessionText.includes(state));
    }
    check(
      "session_authentication_semantics_absent",
      sessionText.includes("authentication_state_exists=false"),
    );
    await certifyForbiddenControls(page, "provider_page");
    await screenshot(page, "provider-contracts-overview-rerun.png");
    await screenshot(
      page,
      "offline-authority-boundary-rerun.png",
      page.getByTestId("pc-maturity-card"),
    );

    await page.getByTestId("pc-provider-select").selectOption("saathi.mock.market.v1");
    await page.getByTestId("pc-mock-quote").click();
    await page.getByTestId("pc-mock-response").waitFor({ state: "visible" });
    const mockOne = await page.getByTestId("pc-mock-response").innerText();
    await page.getByTestId("pc-mock-quote").click();
    await page.waitForTimeout(150);
    const mockTwo = await page.getByTestId("pc-mock-response").innerText();
    check("deterministic_mock_succeeds", mockOne.includes("source_type") && mockOne.includes("MOCK"));
    check("deterministic_mock_repeatable", mockOne === mockTwo);
    check("mock_synthetic_provenance_visible", /live[\"=:\\s]+false/i.test(mockOne));
    await screenshot(
      page,
      "deterministic-mock-result-rerun.png",
      page.getByTestId("pc-mock-response"),
    );

    await page.goto(`${uiBase}/trading/provider-contracts/capabilities`, {
      waitUntil: "domcontentloaded",
      timeout: 90000,
    });
    await page.getByTestId("provider-capabilities-page").waitFor({ state: "visible" });
    await page.getByTestId("pc-load-capabilities").click();
    await page.getByTestId("pc-capability-catalog").waitFor({ state: "visible" });
    await page.getByTestId("pc-negotiate-capabilities").click();
    await page.getByTestId("pc-negotiation-result").waitFor({ state: "visible" });
    text = await pageText(page);
    check("capability_page_loaded", text.includes("Provider Capability Contracts"));
    check("offline_capabilities_visible", text.includes("SUPPORTED_OFFLINE"));
    check("balances_forbidden_visible", /balances.*FORBIDDEN_BY_GOVERNANCE/i.test(text));
    check("positions_forbidden_visible", /positions.*FORBIDDEN_BY_GOVERNANCE/i.test(text));
    check("orders_forbidden_visible", /orders.*FORBIDDEN_BY_GOVERNANCE/i.test(text));
    check("transfers_forbidden_visible", /transfers.*FORBIDDEN_BY_GOVERNANCE/i.test(text));
    check("capability_presence_not_authority", text.includes("Declaration does not grant permission"));
    check("capability_negotiation_does_not_execute", text.includes("executes=false"));
    await certifyForbiddenControls(page, "capability_page");
    await screenshot(page, "capability-matrix-rerun.png");

    await page.goto(`${uiBase}/trading/provider-contracts/replay`, {
      waitUntil: "domcontentloaded",
      timeout: 90000,
    });
    await page.getByTestId("provider-replay-page").waitFor({ state: "visible" });
    await page.getByTestId("pc-load-replay-fixtures").click();
    await page.getByTestId("pc-replay-fixtures").waitFor({ state: "visible" });
    text = await pageText(page);
    check("replay_page_loaded", text.includes("Deterministic Provider Replay"));
    check("replay_fixtures_visible", text.includes("Recorded Request / Response Fixtures"));
    check("replay_provenance_visible", text.includes("source_type=REPLAY"));
    check("replay_synthetic_offline_visible", text.includes("live=false") && text.includes("synthetic=true"));
    check("replay_integrity_visible", text.includes("integrity_valid=true"));
    await certifyForbiddenControls(page, "replay_page");
    await screenshot(page, "replay-fixtures-rerun.png");

    await page.getByTestId("pc-run-replay").click();
    await page.getByTestId("pc-replay-result").waitFor({ state: "visible" });
    const replayOne = await page.getByTestId("pc-replay-result").innerText();
    await page.getByTestId("pc-run-replay").click();
    await page.waitForTimeout(150);
    const replayTwo = await page.getByTestId("pc-replay-result").innerText();
    check("deterministic_replay_succeeds", replayOne.includes("fixture_id="));
    check("deterministic_replay_repeatable", replayOne === replayTwo);
    check("replay_real_connectivity_false", replayOne.includes("real_connectivity=false"));
    await screenshot(
      page,
      "deterministic-replay-result-rerun.png",
      page.getByTestId("pc-replay-result"),
    );

    const missingFixture = await platform("/tg/provider-contracts/requests", {
      method: "POST",
      token: platformToken,
      body: {
        provider_id: "saathi.replay.market.v1",
        operation: "quotes.get",
        params: { symbol: "MISSING" },
        idempotency_key: "m327:browser:missing:fixture:v1",
      },
    });
    const missingCode = String(
      missingFixture.json?.error?.code
      || missingFixture.json?.code
      || missingFixture.json?.detail?.code
      || "",
    );
    check(
      "missing_replay_fixture_fails_closed",
      missingFixture.json?.ok === false && /fixture.*missing/i.test(missingCode),
      `status=${missingFixture.status}; code=${missingCode || "unknown"}`,
    );

    const certification = await platform("/tg/provider-contracts/certify", {
      method: "POST",
      token: platformToken,
    });
    check("provider_contract_certification_api", certification.status < 400 && certification.json?.ok === true);
    const authorityValues = Object.fromEntries(
      hardAuthorityKeys.map((key) => [key, certification.json?.authority_values?.[key] ?? false]),
    );
    check(
      "certification_authority_values_false",
      hardAuthorityKeys.every((key) => authorityValues[key] === false),
    );

    await context.close();

    const forbiddenExternalRequests = networkRequests.filter((entry) => {
      const url = new URL(entry.url);
      return !allowedHosts.has(url.hostname) || forbiddenDomainPattern.test(url.hostname);
    });
    check("browser_network_localhost_only", forbiddenExternalRequests.length === 0,
      `forbidden=${forbiddenExternalRequests.length}`);
    check("browser_request_failures_absent", requestFailures.length === 0,
      `count=${requestFailures.length}`);
    check("uncaught_page_errors_absent", pageErrors.length === 0, `count=${pageErrors.length}`);
    check("invalidating_console_errors_absent", consoleErrors.length === 0,
      `count=${consoleErrors.length}`);

    const failures = checks.filter((entry) => !entry.ok);
    const report = {
      schema: "m327.browser_certification.rerun.v1",
      verdict: failures.length === 0
        ? "PROVIDER_CONTRACTS_MOCK_CONNECTIVITY_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
        : "M327_BROWSER_CERT_UI_FAILED",
      ok: failures.length === 0,
      timestamp: startedAt,
      branch: process.env.M327_BRANCH || "milestone/m320-m327-provider-contracts",
      head_sha: process.env.M327_HEAD_SHA || "unknown",
      browser_engine: "chromium",
      browser_version: browserVersion,
      application_mode: "local Next.js development server + local Uvicorn platform API",
      tested_routes: [
        "/trading/provider-contracts",
        "/trading/provider-contracts/capabilities",
        "/trading/provider-contracts/replay",
      ],
      checks,
      screenshots,
      console_errors: consoleErrors,
      page_errors: pageErrors,
      request_failures: requestFailures,
      network_requests: networkRequests,
      forbidden_external_requests: forbiddenExternalRequests,
      credential_controls_present: checks.some(
        (entry) => entry.name.endsWith("credential_controls_absent") && !entry.ok,
      ),
      oauth_controls_present: checks.some(
        (entry) => entry.name.endsWith("oauth_controls_absent") && !entry.ok,
      ),
      account_controls_present: checks.some(
        (entry) => entry.name.endsWith("account_controls_absent") && !entry.ok,
      ),
      order_controls_present: checks.some(
        (entry) => entry.name.endsWith("order_controls_absent") && !entry.ok,
      ),
      authority_values: authorityValues,
      maturity: "MOCK_CONNECTIVITY_ONLY",
      maximum_state: "MOCK_PROVIDER_READY_NO_REAL_CONNECTIVITY",
      browser_storage_inspection: "NOT_PERFORMED_BY_BROWSER_CONTROL_SAFETY_POLICY",
      provider_credentials_injected: false,
      limitations: [
        "The in-app browser runtime remained unavailable; the project-pinned Playwright Chromium runtime was used.",
        "A synthetic local SaathiOS platform-operator session was used only to pass the existing Control Center SignInGate; it is not a provider, broker, or exchange credential.",
        "Browser cookies and storage values were not inspected under browser-control safety rules.",
        "All application and API traffic was bound to localhost.",
      ],
      failures: failures.map((entry) => entry.name),
    };
    console.log("M327_BROWSER_CERT_RESULT_BEGIN");
    console.log(JSON.stringify(report, null, 2));
    console.log("M327_BROWSER_CERT_RESULT_END");
    process.exitCode = report.ok ? 0 : 1;
  } finally {
    if (browser) await browser.close().catch(() => {});
  }
}

main().catch((error) => {
  console.error("M327_BROWSER_CERT_RUNTIME_ERROR", String(error?.stack || error));
  process.exitCode = 1;
});
