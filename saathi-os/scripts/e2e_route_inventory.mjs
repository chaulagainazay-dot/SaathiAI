#!/usr/bin/env node
/**
 * SaathiOS full route inventory sweep.
 *
 * Visits every static route in the rendered application as a signed-in owner and
 * records what actually happened: HTTP status, rendered text length, whether a
 * stack trace or endless spinner is visible, and any console/page error the route
 * produced. Output feeds ROUTE_INVENTORY.json.
 *
 * Localhost only. No credential is written to the output.
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync, readdirSync, statSync } from "node:fs";

const here = dirname(fileURLToPath(import.meta.url));
const saathiOs = join(here, "..");
const require = createRequire(join(saathiOs, "package.json"));
const { chromium } = require("playwright");

const uiBase = process.env.E2E_UI_BASE || "http://127.0.0.1:3100";
const outDir = process.env.E2E_OUT_DIR || join(saathiOs, "..", "docs", "e2e-functional-audit");
const OWNER = { email: process.env.E2E_OWNER_EMAIL, pw: process.env.E2E_OWNER_PW };
if (!OWNER.email || !OWNER.pw) {
  console.error("missing owner credentials in environment — refusing to run");
  process.exit(2);
}

/** Collect static routes from the app directory, skipping dynamic segments. */
function collectRoutes(dir, prefix = "") {
  const routes = [];
  for (const entry of readdirSync(dir)) {
    const full = join(dir, entry);
    if (statSync(full).isDirectory()) {
      if (entry.startsWith("[")) continue; // dynamic segment — needs a real id
      routes.push(...collectRoutes(full, `${prefix}/${entry}`));
    } else if (/^page\.(jsx|tsx|js)$/.test(entry)) {
      routes.push(prefix || "/");
    }
  }
  return routes;
}

const routes = [...new Set(collectRoutes(join(saathiOs, "app")))].sort();

async function main() {
  mkdirSync(outDir, { recursive: true });
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();

  const perRouteConsole = new Map();
  let current = "";
  page.on("console", (msg) => {
    if (msg.type() !== "error") return;
    if (/favicon|Download the React DevTools/i.test(msg.text())) return;
    if (!perRouteConsole.has(current)) perRouteConsole.set(current, []);
    perRouteConsole.get(current).push(msg.text().slice(0, 300));
  });
  page.on("pageerror", (err) => {
    if (!perRouteConsole.has(current)) perRouteConsole.set(current, []);
    perRouteConsole.get(current).push(`PAGEERROR ${String(err).slice(0, 300)}`);
  });

  // sign in through the rendered form
  await page.goto(`${uiBase}/platform`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-testid="platform-email"]', { timeout: 30000 });
  await page.fill('[data-testid="platform-email"]', OWNER.email);
  await page.fill('[data-testid="platform-password"]', OWNER.pw);
  await page.click('[data-testid="platform-login"]');
  await page
    .waitForSelector('[data-testid="platform-email"]', { state: "detached", timeout: 25000 })
    .catch(() => {});

  const results = [];
  for (const route of routes) {
    current = route;
    let status = 0;
    let text = "";
    try {
      const res = await page.goto(`${uiBase}${route}`, {
        waitUntil: "domcontentloaded",
        timeout: 30000,
      });
      status = res?.status() || 0;
      await page.waitForTimeout(700);
      text = (await page.textContent("body")) || "";
    } catch (err) {
      results.push({
        route,
        status,
        chars: 0,
        classification: "IMPLEMENTED_BROKEN",
        note: String(err).slice(0, 200),
        console_errors: perRouteConsole.get(route) || [],
      });
      continue;
    }

    const trimmed = text.trim();
    const stackTrace = /Traceback \(most recent call last\)|sqlite3\.|at Object\.<anonymous>/.test(text);
    const bareSpinner = /^(loading|loading…|…)$/i.test(trimmed);
    const errs = perRouteConsole.get(route) || [];

    let classification = "IMPLEMENTED_AND_WORKING";
    let note = "";
    if (status >= 400) {
      classification = "IMPLEMENTED_BROKEN";
      note = `http ${status}`;
    } else if (stackTrace) {
      classification = "IMPLEMENTED_BROKEN";
      note = "raw stack trace visible";
    } else if (bareSpinner || trimmed.length < 150) {
      classification = "PARTIALLY_IMPLEMENTED";
      note = `only ${trimmed.length} rendered chars`;
    } else if (errs.some((e) => e.startsWith("PAGEERROR"))) {
      classification = "IMPLEMENTED_BROKEN";
      note = "uncaught page error";
    } else if (/not available|unavailable|module is not enabled|coming soon/i.test(text)) {
      classification = "INTENTIONALLY_UNAVAILABLE";
      note = "route renders an explicit availability gate";
    }

    results.push({
      route,
      status,
      chars: trimmed.length,
      classification,
      note,
      console_errors: errs,
    });
    console.log(`${classification.padEnd(26)} ${String(status).padStart(3)} ${String(trimmed.length).padStart(6)}  ${route}`);
  }

  await ctx.close();
  await browser.close();

  const counts = results.reduce((acc, r) => {
    acc[r.classification] = (acc[r.classification] || 0) + 1;
    return acc;
  }, {});
  const report = {
    record: "SAATHIOS_E2E_ROUTE_INVENTORY",
    ui_base: uiBase,
    note:
      "Static routes only. Dynamic segments ([id]) are exercised by the browser certification with real ids, not by this sweep.",
    totals: { routes: results.length, ...counts },
    routes: results,
  };
  writeFileSync(join(outDir, "ROUTE_INVENTORY.json"), `${JSON.stringify(report, null, 2)}\n`);
  console.log(`\n${results.length} routes`, counts);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
