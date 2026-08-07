/**
 * M64 authenticated module-shell browser certificate.
 *
 * Requires the checkout-local backend and production frontend on loopback.
 * Evidence contains booleans/counts and UI-only screenshots; authentication
 * material stays in memory and is never logged or written.
 */
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const HERE = dirname(fileURLToPath(import.meta.url));
const ROOT = join(HERE, "..", "..");
const OUT = process.env.M64_EVIDENCE_DIR || join(ROOT, "docs", "platform", "m64_evidence");
const UI = "http://127.0.0.1:3000";
const API = "http://127.0.0.1:8765";
const MODULES_URL = "**/api/v1/platform/modules";
mkdirSync(OUT, { recursive: true });

const report = {
  schema: "m64.browser_cert.v1",
  mode: "production-build-loopback",
  hardGates: {},
  stateGates: {},
  responsive: {},
  accessibility: {},
  screenshots: [],
  browserErrors: {
    page: 0,
    console: 0,
    expectedTopbarCors: 0,
    unexpectedConsole: 0,
    consoleCategories: {},
    overlay: 0,
  },
};

function check(name, condition, bucket = report.hardGates) {
  bucket[name] = !!condition;
  if (!condition) throw new Error(`M64 browser gate failed: ${name}`);
}

function corsHeaders(status = 200) {
  return {
    "access-control-allow-origin": UI,
    "access-control-allow-credentials": "true",
    "content-type": "application/json",
    "x-m64-status": String(status),
  };
}

async function loginToken() {
  const response = await fetch(`${API}/api/v1/platform/auth/login`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ email: "owner@local" }),
  });
  const body = await response.json().catch(() => ({}));
  check("sign_in", response.ok && typeof body.token === "string" && body.token.length > 0);
  return body.token;
}

async function authContext(browser, token, viewport) {
  const context = await browser.newContext({ viewport });
  await context.addInitScript((value) => {
    localStorage.setItem("saathi_platform_token", value);
  }, token);
  return context;
}

function observe(page) {
  let pendingTopbarResourceFailure = 0;
  const onPageError = () => {
    report.browserErrors.page += 1;
  };
  const onConsole = (message) => {
    if (message.type() !== "error") return;
    report.browserErrors.console += 1;
    const text = message.text();
    if (/connectors\/approvals\/pending.*CORS|connectors\/approvals\/pending.*blocked/i.test(text)) {
      pendingTopbarResourceFailure += 1;
      report.browserErrors.expectedTopbarCors += 1;
      report.browserErrors.consoleCategories.topbar_approvals_cors =
        (report.browserErrors.consoleCategories.topbar_approvals_cors || 0) + 1;
      return;
    }
    if (pendingTopbarResourceFailure > 0 && /Failed to load resource.*ERR_FAILED/i.test(text)) {
      pendingTopbarResourceFailure -= 1;
      report.browserErrors.expectedTopbarCors += 1;
      report.browserErrors.consoleCategories.topbar_approvals_cors =
        (report.browserErrors.consoleCategories.topbar_approvals_cors || 0) + 1;
      return;
    }
    report.browserErrors.unexpectedConsole += 1;
    const category =
      /\b401\b/.test(text) ? "http_401"
      : /\b403\b/.test(text) ? "http_403"
      : /\b404\b/.test(text) ? "http_404"
      : /\b5\d\d\b/.test(text) ? "http_5xx"
      : /Failed to fetch|NetworkError|ERR_/i.test(text) ? "network"
      : /hydration|nextjs|react/i.test(text) ? "framework"
      : "other";
    report.browserErrors.consoleCategories[category] =
      (report.browserErrors.consoleCategories[category] || 0) + 1;
  };
  page.on("pageerror", onPageError);
  page.on("console", onConsole);
  return () => {
    page.off("pageerror", onPageError);
    page.off("console", onConsole);
  };
}

async function noOverlay(page) {
  const count = await page
    .locator("[data-nextjs-dialog], .vite-error-overlay, #webpack-dev-server-client-overlay")
    .count();
  report.browserErrors.overlay += count;
  return count === 0;
}

async function openApps(page) {
  const response = await page.goto(`${UI}/apps`, { waitUntil: "domcontentloaded" });
  check("apps_http_200", response?.status() === 200);
  await page.getByRole("heading", { name: "Applications", exact: true }).waitFor();
  await page.getByRole("link", { name: /Trading Status: Available/ }).waitFor();
}

async function screenshot(page, filename) {
  await page.screenshot({ path: join(OUT, filename), fullPage: true });
  report.screenshots.push(filename);
}

async function certifyHealthy(browser, token) {
  const context = await authContext(browser, token, { width: 1440, height: 1000 });
  const page = await context.newPage();
  const stopObserving = observe(page);
  await openApps(page);

  const appNav = page.locator(".shell-sidebar-nav");
  check("backend_navigation_trading", await appNav.getByRole("button", { name: "Trading", exact: true }).isEnabled());
  check("backend_navigation_ielts", await appNav.getByRole("button", { name: "IELTSAlert", exact: true }).isEnabled());
  for (const name of ["HCG POS", "Travel", "Finance"]) {
    check(`placeholder_${name.toLowerCase().replaceAll(" ", "_")}`, await appNav.getByRole("button", { name, exact: true }).isDisabled());
  }
  check("trading_actionable_card", await page.locator('main a[href="/trading"]').count() === 1);
  check("ielts_actionable_card", await page.locator('main a[href="/ielts"]').count() === 1);
  check("no_placeholder_card_links", await page.locator('main a[href="/finance"], main a[href="/pos"], main a[href="/travel"]').count() === 0);
  check("truthful_placeholder_statuses", await page.getByText("Coming soon", { exact: true }).count() === 3);

  await page.getByRole("button", { name: "Open command palette" }).click();
  await page.getByRole("textbox", { name: "Search commands" }).fill("Trading");
  check("command_palette_trading", await page.getByText("Open Trading", { exact: true }).count() === 1);
  check("command_palette_filters_placeholders", await page.getByText("Open Finance", { exact: true }).count() === 0);
  await page.keyboard.press("Escape");

  let focused = false;
  for (let index = 0; index < 8 && !focused; index += 1) {
    await page.keyboard.press("Tab");
    focused = await page.evaluate(() => {
      const element = document.activeElement;
      if (!element || !element.matches("button,a,input")) return false;
      const style = getComputedStyle(element);
      return (
        (style.outlineStyle !== "none" && style.outlineWidth !== "0px") ||
        style.boxShadow !== "none"
      );
    });
  }
  check("visible_keyboard_focus", focused, report.accessibility);
  check("semantic_statuses", await page.locator('[role="status"]').count() >= 5, report.accessibility);
  check("semantic_links_buttons", await page.locator("a,button").count() > 10, report.accessibility);
  check("desktop_no_overlay", await noOverlay(page));
  await screenshot(page, "m64_apps_desktop.png");
  stopObserving();

  await appNav.getByRole("button", { name: "Trading", exact: true }).click();
  await page.waitForURL(`${UI}/trading`);
  check("trading_route_opens", page.url() === `${UI}/trading`);
  check("trading_paper_boundary", await page.getByText(/paper/i).count() > 0);

  await page.goto(`${UI}/finance`, { waitUntil: "domcontentloaded" });
  await page.getByText("This application is registered but not implemented.", { exact: true }).waitFor();
  check("placeholder_route_guard", true);
  await screenshot(page, "m64_placeholder_guard.png");

  const unknown = await page.goto(`${UI}/apps/not-a-real-module`, { waitUntil: "domcontentloaded" });
  check("unknown_route_safe", unknown?.status() === 404 || await page.getByText(/not found/i).count() > 0);

  await context.close();
}

async function certifyResponsive(browser, token, name, viewport) {
  const context = await authContext(browser, token, viewport);
  const page = await context.newPage();
  observe(page);
  await openApps(page);
  check(`${name}_content`, await page.getByRole("link", { name: /Trading Status: Available/ }).isVisible(), report.responsive);
  check(`${name}_no_horizontal_overflow`, await page.evaluate(() => document.documentElement.scrollWidth <= document.documentElement.clientWidth + 1), report.responsive);
  check(`${name}_no_overlay`, await noOverlay(page), report.responsive);
  await screenshot(page, `m64_apps_${name}.png`);
  await context.close();
}

async function certifyContextSwitch(browser, token) {
  const context = await authContext(browser, token, { width: 1280, height: 900 });
  const page = await context.newPage();
  let calls = 0;
  await page.route(MODULES_URL, async (route) => {
    calls += 1;
    if (calls > 1) await new Promise((resolve) => setTimeout(resolve, 500));
    const response = await route.fetch();
    await route.fulfill({ response });
  });
  await openApps(page);
  const switchPromise = page.evaluate((value) => {
    window.dispatchEvent(new CustomEvent("saathi:platform-context", {
      detail: { token: value, orgId: "cert-org", workspaceId: "cert-workspace" },
    }));
  }, token);
  await switchPromise;
  await page.waitForTimeout(100);
  check("context_switch_clears_actionable_state", await page.locator('main a[href="/trading"]').count() === 0, report.stateGates);
  await page.getByRole("link", { name: /Trading Status: Available/ }).waitFor();
  check("context_switch_refetches", calls >= 2, report.stateGates);
  await context.close();
}

async function certifyResponseState(browser, token, name, handler, assertion) {
  const context = await authContext(browser, token, { width: 1100, height: 800 });
  const page = await context.newPage();
  await page.route(MODULES_URL, handler);
  await page.goto(`${UI}/apps`, { waitUntil: "domcontentloaded" });
  await assertion(page);
  check(`${name}_no_actionable_trading`, await page.locator('main a[href="/trading"]').count() === 0, report.stateGates);
  await context.close();
}

async function certifyFailureStates(browser, token) {
  await certifyResponseState(
    browser,
    token,
    "session_expired",
    (route) => route.fulfill({ status: 401, headers: corsHeaders(401), body: JSON.stringify({ detail: { code: "AUTH_REQUIRED" } }) }),
    async (page) => {
      await page.getByText("Your session expired. Module state was cleared.", { exact: true }).waitFor();
      check("session_expired_banner", true, report.stateGates);
    }
  );
  await certifyResponseState(
    browser,
    token,
    "permission_restricted",
    (route) => route.fulfill({ status: 403, headers: corsHeaders(403), body: JSON.stringify({ detail: { code: "PERMISSION_DENIED" } }) }),
    async (page) => {
      await page.getByText("You do not have permission to view platform modules.", { exact: true }).waitFor();
      check("permission_restricted_banner", true, report.stateGates);
    }
  );
  await certifyResponseState(
    browser,
    token,
    "malformed",
    (route) => route.fulfill({
      status: 200,
      headers: corsHeaders(200),
      body: JSON.stringify({
        contract_version: "m64.1",
        installed: [{ id: "malformed" }],
        navigation: { group: "applications", label: "Applications", modules: [] },
        dashboard_cards: [],
      }),
    }),
    async (page) => {
      await page.getByRole("heading", { name: "Applications", exact: true }).waitFor();
      await page.getByText(/Backend-authoritative module discovery · m64\.1/).waitFor();
      check("malformed_response_fails_closed", await page.locator('main [aria-label^="Status:"]').count() === 0, report.stateGates);
    }
  );

  let attempts = 0;
  await certifyResponseState(
    browser,
    token,
    "offline",
    (route) => {
      attempts += 1;
      return route.abort("connectionrefused");
    },
    async (page) => {
      await page.getByText("Platform backend unavailable.", { exact: true }).waitFor({ timeout: 8000 });
      check("bounded_retry_count", attempts === 4, report.stateGates);
    }
  );
}

async function certifyLogout(browser, token) {
  const context = await authContext(browser, token, { width: 1280, height: 900 });
  const page = await context.newPage();
  await page.goto(`${UI}/security`, { waitUntil: "domcontentloaded" });
  await page.getByRole("button", { name: /Sign out$/ }).waitFor();
  await page.getByRole("button", { name: /Sign out$/ }).click();
  await page.waitForFunction(
    () => !localStorage.getItem("saathi_platform_token"),
    undefined,
    { timeout: 10000 }
  );
  check("logout_removes_actionable_navigation", await page.locator(".shell-sidebar-nav").getByRole("button", { name: "Trading", exact: true }).count() === 0, report.stateGates);
  await context.close();

  const unauthenticated = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const apps = await unauthenticated.newPage();
  await apps.goto(`${UI}/apps`, { waitUntil: "domcontentloaded" });
  await apps.getByText("Sign in to load your applications.", { exact: true }).waitFor();
  check("logout_clears_module_state", await apps.locator('main a[href="/trading"]').count() === 0, report.stateGates);
  await unauthenticated.close();
}

const browser = await chromium.launch({ headless: true });
try {
  const token = await loginToken();
  await certifyHealthy(browser, token);
  await certifyResponsive(browser, token, "tablet", { width: 820, height: 1100 });
  await certifyResponsive(browser, token, "mobile", { width: 390, height: 844 });
  await certifyContextSwitch(browser, token);
  await certifyFailureStates(browser, token);
  await certifyLogout(browser, token);

  check("no_page_errors", report.browserErrors.page === 0);
  check("no_unexpected_console_errors", report.browserErrors.unexpectedConsole === 0);
  check("no_framework_overlays", report.browserErrors.overlay === 0);
  report.verdict = "PASS";
} catch (error) {
  report.verdict = "FAIL";
  report.failedGate = String(error?.message || error).slice(0, 240);
  throw error;
} finally {
  writeFileSync(join(OUT, "M64_BROWSER_CERT.json"), `${JSON.stringify(report, null, 2)}\n`);
  await browser.close();
}

console.log(
  `M64 browser certificate PASS: ${Object.keys(report.hardGates).length} hard, ` +
  `${Object.keys(report.stateGates).length} state, ` +
  `${Object.keys(report.responsive).length} responsive, ` +
  `${Object.keys(report.accessibility).length} accessibility gates`
);
