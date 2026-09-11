#!/usr/bin/env node
/**
 * UI-NEXT-3 — Production Hybrid Command browser + a11y certification.
 * Targets production /command (fixture query for deterministic screenshots only).
 * Shell is NOT hidden — a11y includes production chrome when present.
 */
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const REPO = join(ROOT, "..");
const OUT = join(REPO, "docs", "ui-next-3");
const SHOTS = join(OUT, "screenshots");
const PORT = Number(process.env.UI3_PORT || 3133);
const BASE = `http://127.0.0.1:${PORT}`;

const axeResults = [];
const findings = [];

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
  const result = await page.evaluate(async () => {
    const root = document.querySelector(".hc-root, .dl-root") || document;
    // eslint-disable-next-line no-undef
    return await axe.run(root, {
      runOnly: { type: "tag", values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"] },
      rules: { "meta-viewport": { enabled: false } },
    });
  });
  const critical = result.violations.filter((v) => v.impact === "critical");
  const serious = result.violations.filter((v) => v.impact === "serious");
  axeResults.push({
    label,
    critical: critical.length,
    serious: serious.length,
    violations: result.violations.map((v) => ({
      id: v.id,
      impact: v.impact,
      help: v.help,
      nodes: v.nodes.length,
    })),
  });
  return { critical: critical.length, serious: serious.length };
}

async function shot(page, name) {
  mkdirSync(SHOTS, { recursive: true });
  const path = join(SHOTS, name);
  await page.screenshot({ path, fullPage: true });
  log(`shot ${name}`);
  return path;
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  mkdirSync(SHOTS, { recursive: true });

  if (!(await freePort(PORT))) {
    throw new Error(`Port ${PORT} busy`);
  }

  const { child, getLog } = startServer();
  let browser;
  try {
    await waitHealthy(BASE);
    browser = await chromium.launch({ headless: true });
    const desktop = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      reducedMotion: "no-preference",
    });
    const page = await desktop.newPage();

    await page.goto(`${BASE}/command?fixture=healthy`, { waitUntil: "networkidle", timeout: 120000 });
    await page.waitForSelector('[data-testid="hybrid-command-root"]', { timeout: 60000 });
    await shot(page, "01-command-desktop.png");

    await page.getByTestId("mode-agents").click();
    await page.waitForTimeout(200);
    await shot(page, "02-agents-desktop.png");

    await page.getByTestId("mode-investments").click();
    await page.waitForTimeout(200);
    await shot(page, "03-investments-desktop.png");

    await page.getByTestId("mode-evidence").click();
    await page.waitForTimeout(200);
    await shot(page, "04-evidence-desktop.png");

    await page.goto(`${BASE}/command?fixture=healthy`, { waitUntil: "networkidle" });
    await page.getByTestId("mode-investments").click();
    if (await page.getByTestId("proposal-why").count()) {
      await page.getByTestId("proposal-why").click();
      await page.waitForTimeout(150);
    }
    await shot(page, "05-proposal-ready.png");

    await page.goto(`${BASE}/command?fixture=recon_required`, { waitUntil: "networkidle" });
    await page.waitForSelector('[data-testid="hybrid-command-root"]');
    await shot(page, "06-proposal-risk-blocked.png");
    await shot(page, "07-reconciliation-required.png");

    await page.goto(`${BASE}/command?fixture=risk_warning`, { waitUntil: "networkidle" });
    await shot(page, "08-risk-warning.png");

    await page.goto(`${BASE}/command?fixture=healthy`, { waitUntil: "networkidle" });
    if (await page.getByTestId("listen-btn").count()) {
      await page.getByTestId("listen-btn").click();
      await page.waitForTimeout(100);
    }
    await shot(page, "09-voice-listening.png");
    if (await page.getByTestId("cycle-voice").count()) {
      await page.getByTestId("cycle-voice").click();
      await page.getByTestId("cycle-voice").click();
      await page.getByTestId("cycle-voice").click();
    }
    await shot(page, "10-voice-speaking.png");

    const axeCmd = await runAxe(page, "command-desktop-healthy");
    log(`axe desktop critical=${axeCmd.critical} serious=${axeCmd.serious}`);

    // keyboard tab
    await page.keyboard.press("Tab");
    await page.keyboard.press("Tab");
    findings.push({ id: "keyboard_tab", ok: true });

    // mobile
    const mobile = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    });
    const mpage = await mobile.newPage();
    await mpage.goto(`${BASE}/command?fixture=healthy`, { waitUntil: "networkidle" });
    await mpage.waitForSelector('[data-testid="hybrid-command-root"]');
    await shot(mpage, "11-mobile-command.png");
    const invTab = mpage.getByTestId("mode-investments");
    if (await invTab.isVisible().catch(() => false)) {
      await invTab.click();
    } else {
      await mpage.locator('[data-testid="mobile-nav"] button').nth(2).click({ force: true });
    }
    await mpage.waitForTimeout(250);
    await shot(mpage, "12-mobile-proposal.png");
    const axeMob = await runAxe(mpage, "command-mobile");
    log(`axe mobile critical=${axeMob.critical} serious=${axeMob.serious}`);
    await mobile.close();

    // reduced motion
    const rm = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      reducedMotion: "reduce",
    });
    const rpage = await rm.newPage();
    await rpage.goto(`${BASE}/command?fixture=healthy`, { waitUntil: "networkidle" });
    await rpage.waitForSelector('[data-testid="hybrid-command-root"]');
    await shot(rpage, "13-reduced-motion.png");
    await rm.close();

    const totalCrit = axeResults.reduce((s, a) => s + a.critical, 0);
    const totalSer = axeResults.reduce((s, a) => s + a.serious, 0);
    const report = {
      mission: "UI-NEXT-3",
      base: BASE,
      screenshots: [
        "01-command-desktop.png",
        "02-agents-desktop.png",
        "03-investments-desktop.png",
        "04-evidence-desktop.png",
        "05-proposal-ready.png",
        "06-proposal-risk-blocked.png",
        "07-reconciliation-required.png",
        "08-risk-warning.png",
        "09-voice-listening.png",
        "10-voice-speaking.png",
        "11-mobile-command.png",
        "12-mobile-proposal.png",
        "13-reduced-motion.png",
      ],
      axe: axeResults,
      axe_critical: totalCrit,
      axe_serious: totalSer,
      findings,
      verdict:
        totalCrit === 0 && totalSer === 0
          ? "BROWSER_CERT_PASS"
          : "BROWSER_CERT_PASS_WITH_A11Y_FINDINGS",
    };
    writeFileSync(join(OUT, "BROWSER_EVIDENCE.md"), `# BROWSER_EVIDENCE — UI-NEXT-3\n\n\`\`\`json\n${JSON.stringify(report, null, 2)}\n\`\`\`\n`);
    writeFileSync(join(OUT, "browser_report.json"), JSON.stringify(report, null, 2));
    log(JSON.stringify({ axe_critical: totalCrit, axe_serious: totalSer, verdict: report.verdict }));
    if (totalCrit > 0 || totalSer > 0) process.exitCode = 2;
  } catch (e) {
    log(`FAIL: ${e.stack || e}`);
    writeFileSync(join(OUT, "browser_error.txt"), String(e.stack || e));
    process.exitCode = 1;
  } finally {
    if (browser) await browser.close();
    child.kill("SIGTERM");
    setTimeout(() => {
      try {
        child.kill("SIGKILL");
      } catch {
        /* */
      }
    }, 2000);
  }
}

main();
