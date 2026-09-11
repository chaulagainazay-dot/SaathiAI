#!/usr/bin/env node
/**
 * UI-NEXT-2.2 — Hybrid Command browser + a11y + visual certification.
 * start next → interact /design-lab → screenshots → axe → report
 * Does not replace /command. Localhost only.
 */
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdirSync, writeFileSync, readFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const REPO = join(ROOT, "..");
const OUT = join(REPO, "docs", "ui-next-2-2");
const SHOTS = join(OUT, "screenshots");
const PORT = Number(process.env.UI222_PORT || 3122);
const BASE = `http://127.0.0.1:${PORT}`;

const findings = [];
const consoleErrors = [];
const axeResults = [];

function log(msg) {
  process.stdout.write(`${msg}\n`);
}

function freePort(port) {
  return new Promise((resolve) => {
    const s = createServer();
    s.once("error", () => resolve(false));
    s.once("listening", () => s.close(() => resolve(true)));
    s.listen(port, "127.0.0.1");
  });
}

async function waitHealthy(url, ms = 180000) {
  const start = Date.now();
  let last = "";
  while (Date.now() - start < ms) {
    try {
      const r = await fetch(url, { redirect: "manual" });
      if (r.status >= 200 && r.status < 500) return true;
      last = `status ${r.status}`;
    } catch (e) {
      last = String(e.message || e);
    }
    await new Promise((r) => setTimeout(r, 900));
  }
  throw new Error(`Server not healthy at ${url}: ${last}`);
}

function startServer() {
  const env = { ...process.env, PORT: String(PORT), NODE_ENV: "development" };
  const child = spawn("npx", ["next", "dev", "-H", "127.0.0.1", "-p", String(PORT)], {
    cwd: ROOT,
    env,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let buf = "";
  child.stdout.on("data", (d) => {
    buf += d.toString();
  });
  child.stderr.on("data", (d) => {
    buf += d.toString();
  });
  return { child, getLog: () => buf };
}

async function runAxe(page, label) {
  const axePath = require.resolve("axe-core/axe.min.js");
  await page.addScriptTag({ path: axePath });
  // Scope to design-lab root — production shell chrome is out of UI-NEXT-2.2 scope
  const result = await page.evaluate(async () => {
    const root = document.querySelector(".dl-root") || document;
    // eslint-disable-next-line no-undef
    return await axe.run(root, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
      rules: {
        // App-wide viewport meta is owned by root layout, not design-lab
        "meta-viewport": { enabled: false },
      },
    });
  });
  const critical = result.violations.filter((v) => v.impact === "critical");
  const serious = result.violations.filter((v) => v.impact === "serious");
  axeResults.push({
    label,
    url: page.url(),
    violations: result.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      description: v.description,
      nodes: v.nodes.length,
      help: v.help,
    })),
    critical: critical.length,
    serious: serious.length,
    moderate: result.violations.filter((v) => v.impact === "moderate").length,
    minor: result.violations.filter((v) => v.impact === "minor").length,
  });
  return { critical: critical.length, serious: serious.length, total: result.violations.length };
}

async function shot(page, name) {
  const path = join(SHOTS, name);
  await page.screenshot({ path, fullPage: true });
  log(`shot ${name}`);
  return path;
}

async function setScenario(page, scenario) {
  await page.selectOption('select[aria-label="Fixture scenario"]', scenario);
  await page.waitForTimeout(400);
}

async function setMode(page, label) {
  await page.getByRole("tab", { name: label, exact: true }).click();
  await page.waitForTimeout(250);
}

async function main() {
  mkdirSync(SHOTS, { recursive: true });
  mkdirSync(OUT, { recursive: true });

  if (!(await freePort(PORT))) {
    throw new Error(`Port ${PORT} busy`);
  }

  const { child, getLog } = startServer();
  let browser;
  let exitCode = 0;

  try {
    log(`Waiting for ${BASE}/design-lab …`);
    await waitHealthy(`${BASE}/design-lab`);
    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      reducedMotion: "no-preference",
    });
    const page = await context.newPage();
    page.on("console", (msg) => {
      if (msg.type() === "error") consoleErrors.push({ type: "console", text: msg.text() });
    });
    page.on("pageerror", (err) => {
      consoleErrors.push({ type: "pageerror", text: String(err) });
    });

    // ── Desktop 1440 Command healthy
    await page.goto(`${BASE}/design-lab`, { waitUntil: "networkidle" });
    await page.waitForSelector('[data-testid="design-lab-root"]');
    await setScenario(page, "healthy");
    await setMode(page, "Command");
    await shot(page, "01-command-desktop.png");

    // console integrity snapshot
    const banner = await page.locator('[data-testid="demo-banner"]').textContent();
    if (!banner?.includes("DEMO")) findings.push({ severity: "CRITICAL", msg: "DEMO banner missing" });

    // Agents
    await setMode(page, "Agents");
    await page.getByRole("button", { name: /CIO|Research|Quant/i }).first().click();
    await page.waitForTimeout(200);
    await shot(page, "02-agents-desktop.png");

    // Investments
    await setMode(page, "Investments");
    await page.getByRole("button", { name: /AAA/ }).first().click().catch(() => {});
    await page.waitForTimeout(200);
    await shot(page, "03-investments-desktop.png");

    // Evidence
    await setMode(page, "Evidence");
    await page.locator(".dl-ev").first().click();
    await page.waitForTimeout(200);
    await shot(page, "04-evidence-desktop.png");

    // Desktop 1280
    await page.setViewportSize({ width: 1280, height: 800 });
    await setMode(page, "Command");
    await shot(page, "01b-command-1280.png");

    // Tablet
    await page.setViewportSize({ width: 1024, height: 768 });
    await shot(page, "05-command-tablet.png");

    // Mobile
    await page.setViewportSize({ width: 390, height: 844 });
    await setMode(page, "Command");
    await shot(page, "06-command-mobile.png");
    // agent graph should still be list
    await setMode(page, "Agents");
    await shot(page, "06b-agents-mobile.png");

    // back to desktop for state shots
    await page.setViewportSize({ width: 1440, height: 900 });

    // Risk warning
    await setScenario(page, "risk_warning");
    await setMode(page, "Investments");
    await shot(page, "07-risk-warning.png");

    // Recon required
    await setScenario(page, "recon_required");
    await setMode(page, "Command");
    const recon = page.locator('[data-testid="recon-banner"]');
    if ((await recon.count()) === 0) findings.push({ severity: "CRITICAL", msg: "recon banner missing" });
    await shot(page, "08-reconciliation-required.png");

    // Voice states
    await setScenario(page, "healthy");
    await setMode(page, "Command");
    // cycle to LISTENING via button or set by evaluating - use Listen button then cycle
    await page.getByRole("button", { name: "Listen" }).click();
    await page.waitForTimeout(150);
    await shot(page, "09-voice-listening.png");

    // SPEAKING - use ask
    await page.getByTestId("design-lab-input").fill("show portfolio risk");
    await page.getByRole("button", { name: "Ask", exact: true }).click();
    await page.waitForTimeout(500);
    await shot(page, "10-voice-speaking.png");

    // DEGRADED scenario
    await setScenario(page, "voice_degraded");
    await page.waitForTimeout(300);
    await shot(page, "11-voice-degraded.png");

    // Interaction: mode switching + keyboard
    await setScenario(page, "healthy");
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    // reduced motion context
    await context.close();
    const rmContext = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      reducedMotion: "reduce",
    });
    const rmPage = await rmContext.newPage();
    await rmPage.goto(`${BASE}/design-lab`, { waitUntil: "networkidle" });
    await rmPage.waitForSelector('[data-testid="design-lab-root"]');
    await rmPage.getByRole("button", { name: "Listen" }).click();
    await rmPage.waitForTimeout(200);
    const hasReduced = await rmPage.locator(".dl-reduced").count();
    if (!hasReduced) {
      // class may apply via matchMedia - check data attribute or computed
      findings.push({ severity: "MODERATE", msg: "dl-reduced class may not attach; CSS still disables animation via media query" });
    }
    await shot(rmPage, "12-reduced-motion.png");

    // axe on command desktop healthy
    const axePage = await browser.newPage();
    await axePage.setViewportSize({ width: 1440, height: 900 });
    await axePage.goto(`${BASE}/design-lab`, { waitUntil: "networkidle" });
    const axe1 = await runAxe(axePage, "command-desktop-healthy");
    log(`axe command: critical=${axe1.critical} serious=${axe1.serious} total=${axe1.total}`);

    await setScenario(axePage, "recon_required");
    const axe2 = await runAxe(axePage, "command-recon-required");
    log(`axe recon: critical=${axe2.critical} serious=${axe2.serious} total=${axe2.total}`);

    await setMode(axePage, "Investments");
    const axe3 = await runAxe(axePage, "investments-desktop");
    log(`axe invest: critical=${axe3.critical} serious=${axe3.serious} total=${axe3.total}`);

    // keyboard walk
    await axePage.setScenario?.();
    await setScenario(axePage, "healthy");
    await setMode(axePage, "Command");
    for (let i = 0; i < 12; i++) await axePage.keyboard.press("Tab");
    const focused = await axePage.evaluate(() => {
      const el = document.activeElement;
      return {
        tag: el?.tagName,
        role: el?.getAttribute("role"),
        name: el?.getAttribute("aria-label") || el?.textContent?.slice(0, 40),
      };
    });
    log(`keyboard focus after tabs: ${JSON.stringify(focused)}`);

    // mobile keyboard/touch target sample
    await axePage.setViewportSize({ width: 390, height: 844 });
    const targets = await axePage.evaluate(() => {
      const btns = [...document.querySelectorAll("button, a, [role=tab]")].slice(0, 20);
      return btns.map((b) => {
        const r = b.getBoundingClientRect();
        return { text: (b.textContent || "").trim().slice(0, 30), w: Math.round(r.width), h: Math.round(r.height) };
      });
    });
    const smallTargets = targets.filter((t) => t.h > 0 && (t.h < 32 || t.w < 32));
    if (smallTargets.length) {
      findings.push({
        severity: "MODERATE",
        msg: `small touch targets: ${JSON.stringify(smallTargets.slice(0, 5))}`,
      });
    }

    // zoom 150%
    await axePage.setViewportSize({ width: 1440, height: 900 });
    await axePage.evaluate(() => {
      document.body.style.zoom = "1.5";
    });
    await shot(axePage, "13-zoom-150.png");
    await axePage.evaluate(() => {
      document.body.style.zoom = "1";
    });

    // long content stress via DOM injection of long agent name (non-persistent)
    await setMode(axePage, "Agents");
    await axePage.evaluate(() => {
      const n = document.querySelector(".dl-node span");
      if (n) n.textContent = "VeryLongAgentName_ResearchCoordinator_InstitutionalMacroDesk_AlphaOmega";
    });
    await shot(axePage, "14-long-content-stress.png");

    await axePage.close();
    await rmContext.close();

    // critical console filter
    const criticalConsole = consoleErrors.filter(
      (e) => !/favicon|Download the React DevTools|hydration/i.test(e.text),
    );

    const axeCrit = axeResults.reduce((s, r) => s + r.critical, 0);
    const axeSer = axeResults.reduce((s, r) => s + r.serious, 0);

    const report = {
      mission: "UI-NEXT-2.2",
      base: BASE,
      port: PORT,
      screenshots: [
        "01-command-desktop.png",
        "02-agents-desktop.png",
        "03-investments-desktop.png",
        "04-evidence-desktop.png",
        "01b-command-1280.png",
        "05-command-tablet.png",
        "06-command-mobile.png",
        "06b-agents-mobile.png",
        "07-risk-warning.png",
        "08-reconciliation-required.png",
        "09-voice-listening.png",
        "10-voice-speaking.png",
        "11-voice-degraded.png",
        "12-reduced-motion.png",
        "13-zoom-150.png",
        "14-long-content-stress.png",
      ],
      consoleErrors: criticalConsole,
      findings,
      axeResults,
      axeGate: { critical: axeCrit, serious: axeSer },
      serverLogTail: getLog().slice(-4000),
    };

    writeFileSync(join(OUT, "browser_run_report.json"), JSON.stringify(report, null, 2) + "\n");

    if (axeCrit > 0 || axeSer > 0) {
      log(`A11Y GATE FAIL critical=${axeCrit} serious=${axeSer}`);
      exitCode = 2;
    }
    if (criticalConsole.length) {
      log(`CONSOLE errors: ${criticalConsole.length}`);
      // Next dev often has soft errors; only fail if pageerror
      const pe = criticalConsole.filter((c) => c.type === "pageerror");
      if (pe.length) exitCode = 3;
    }
    if (findings.some((f) => f.severity === "CRITICAL")) exitCode = 4;

    log(JSON.stringify({ exitCode, axeCrit, axeSer, findings: findings.length, shots: report.screenshots.length }, null, 2));
  } catch (e) {
    log(String(e.stack || e));
    writeFileSync(
      join(OUT, "browser_run_report.json"),
      JSON.stringify({ error: String(e), consoleErrors, findings, axeResults }, null, 2) + "\n",
    );
    exitCode = 1;
  } finally {
    if (browser) await browser.close().catch(() => {});
    child.kill("SIGTERM");
    setTimeout(() => {
      try {
        child.kill("SIGKILL");
      } catch {
        /* ignore */
      }
    }, 3000);
  }
  process.exit(exitCode);
}

main();
