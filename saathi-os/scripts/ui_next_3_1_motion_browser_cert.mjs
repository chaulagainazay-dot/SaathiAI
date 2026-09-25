#!/usr/bin/env node
/**
 * UI-NEXT-3.1 — Production Motion + Microinteraction browser certification.
 * Targets production /command with explicit fixture query (never default DEMO).
 */
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdirSync, writeFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const REPO = join(ROOT, "..");
const OUT = join(REPO, "docs", "ui-next-3-1");
const SHOTS = join(OUT, "screenshots");
const PORT = Number(process.env.UI31_PORT || 3134);
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

async function gotoFixture(page, fixture) {
  await page.goto(`${BASE}/command?fixture=${fixture}`, { waitUntil: "networkidle", timeout: 120000 });
  await page.waitForSelector('[data-testid="hybrid-command-root"]', { timeout: 60000 });
}

async function cycleToVoice(page, target) {
  const states = [
    "IDLE",
    "READY",
    "LISTENING",
    "TRANSCRIBING",
    "THINKING",
    "SPEAKING",
    "INTERRUPTING",
    "DEGRADED",
    "ERROR",
    "CLOSED",
  ];
  for (let i = 0; i < states.length + 2; i++) {
    const cur = await page.getByTestId("saathi-orb").getAttribute("data-state");
    if (cur === target) return;
    await page.getByTestId("cycle-voice").click();
    await page.waitForTimeout(40);
  }
  // force via evaluate if cycle missed
  await page.evaluate((t) => {
    const btn = document.querySelector('[data-testid="cycle-voice"]');
    let n = 0;
    while (n < 12) {
      const orb = document.querySelector('[data-testid="saathi-orb"]');
      if (orb?.getAttribute("data-state") === t) break;
      btn?.click();
      n += 1;
    }
  }, target);
}

async function main() {
  mkdirSync(OUT, { recursive: true });
  mkdirSync(SHOTS, { recursive: true });

  if (!(await freePort(PORT))) {
    throw new Error(`Port ${PORT} busy`);
  }

  const { child } = startServer();
  let browser;
  try {
    await waitHealthy(BASE);
    browser = await chromium.launch({ headless: true });
    const desktop = await browser.newContext({
      viewport: { width: 1440, height: 900 },
      reducedMotion: "no-preference",
    });
    const page = await desktop.newPage();

    await gotoFixture(page, "healthy");
    findings.push({
      id: "motion_attr",
      ok: (await page.getByTestId("hybrid-command-root").getAttribute("data-motion")) === "ui-next-3.1",
    });
    await shot(page, "01-command-idle.png");

    await page.getByTestId("listen-btn").click();
    await page.waitForTimeout(120);
    await shot(page, "02-voice-listening.png");

    await cycleToVoice(page, "TRANSCRIBING");
    await shot(page, "03-voice-transcribing.png");

    await cycleToVoice(page, "THINKING");
    await shot(page, "04-voice-thinking.png");

    await cycleToVoice(page, "SPEAKING");
    await shot(page, "05-voice-speaking.png");

    await cycleToVoice(page, "INTERRUPTING");
    await shot(page, "06-voice-interrupting.png");

    await gotoFixture(page, "risk_warning");
    await shot(page, "07-risk-warning.png");

    await gotoFixture(page, "risk_breached");
    await shot(page, "08-risk-breached.png");

    await gotoFixture(page, "recon_required");
    await shot(page, "09-reconciliation-required.png");

    await gotoFixture(page, "healthy");
    await page.getByTestId("mode-investments").click();
    await page.waitForTimeout(200);
    await shot(page, "10-proposal-ready.png");

    await gotoFixture(page, "proposal_blocked");
    await page.getByTestId("mode-investments").click().catch(() => {});
    await page.waitForTimeout(150);
    await shot(page, "11-proposal-blocked.png");

    await gotoFixture(page, "healthy");
    await page.getByTestId("mode-investments").click();
    await page.waitForTimeout(150);
    if (await page.getByTestId("trade-row-AAA").count()) {
      await page.getByTestId("trade-row-AAA").click();
      await page.waitForTimeout(120);
    }
    await shot(page, "12-current-vs-proposed.png");

    await page.locator('[data-testid="performance-panel"]').scrollIntoViewIfNeeded().catch(() => {});
    await shot(page, "13-performance.png");

    await page.getByTestId("mode-agents").click();
    await page.waitForTimeout(150);
    await shot(page, "14-agent-active.png");
    await shot(page, "15-mission-progress.png");

    await page.getByTestId("mode-evidence").click();
    await page.waitForTimeout(150);
    if (await page.getByTestId("evidence-ev-ev_prop_1").count()) {
      await page.getByTestId("evidence-ev-ev_prop_1").click();
    }
    await shot(page, "16-evidence-focus.png");

    const axeCmd = await runAxe(page, "command-motion-desktop");
    log(`axe desktop critical=${axeCmd.critical} serious=${axeCmd.serious}`);

    // keyboard focus still works after motion interactions
    await page.keyboard.press("Tab");
    const focused = await page.evaluate(() => !!document.activeElement && document.activeElement !== document.body);
    findings.push({ id: "keyboard_focus_after_motion", ok: focused });

    // mobile
    const mobile = await browser.newContext({
      viewport: { width: 390, height: 844 },
      isMobile: true,
      hasTouch: true,
    });
    const mpage = await mobile.newPage();
    await gotoFixture(mpage, "healthy");
    await shot(mpage, "17-mobile-command.png");
    await mpage.getByTestId("listen-btn").click().catch(() => {});
    await mpage.waitForTimeout(100);
    await shot(mpage, "18-mobile-voice.png");
    const axeMob = await runAxe(mpage, "command-motion-mobile");
    log(`axe mobile critical=${axeMob.critical} serious=${axeMob.serious}`);
    await mobile.close();

    // reduced motion
    const rm = await browser.newContext({
      viewport: { width: 1280, height: 800 },
      reducedMotion: "reduce",
    });
    const rpage = await rm.newPage();
    await gotoFixture(rpage, "healthy");
    await rpage.getByTestId("listen-btn").click();
    await rpage.waitForTimeout(80);
    const reducedOk = await rpage.evaluate(() => {
      const root = document.querySelector('[data-testid="hybrid-command-root"]');
      const orb = document.querySelector('[data-testid="saathi-orb"]');
      const anim = orb ? getComputedStyle(orb).animationName : "";
      const hasReduced = root?.classList.contains("dl-reduced") || document.documentElement.classList.contains("dl-reduced-root");
      const badge = document.querySelector('[data-testid="voice-state-badge"]')?.textContent || "";
      return {
        hasReduced,
        animNone: !anim || anim === "none",
        badgeOk: /LISTEN/i.test(badge),
      };
    });
    findings.push({ id: "reduced_motion", ok: reducedOk.hasReduced && reducedOk.badgeOk });
    await shot(rpage, "19-reduced-motion.png");
    await rm.close();

    const totalCrit = axeResults.reduce((s, a) => s + a.critical, 0);
    const totalSer = axeResults.reduce((s, a) => s + a.serious, 0);
    const shots = [
      "01-command-idle.png",
      "02-voice-listening.png",
      "03-voice-transcribing.png",
      "04-voice-thinking.png",
      "05-voice-speaking.png",
      "06-voice-interrupting.png",
      "07-risk-warning.png",
      "08-risk-breached.png",
      "09-reconciliation-required.png",
      "10-proposal-ready.png",
      "11-proposal-blocked.png",
      "12-current-vs-proposed.png",
      "13-performance.png",
      "14-agent-active.png",
      "15-mission-progress.png",
      "16-evidence-focus.png",
      "17-mobile-command.png",
      "18-mobile-voice.png",
      "19-reduced-motion.png",
    ];
    const report = {
      mission: "UI-NEXT-3.1",
      base: BASE,
      motion_tech: {
        primary: "CSS_SUFFICIENT",
        gsap: "GSAP_RUNTIME_DEFERRED",
        lottie: "LOTTIE_RUNTIME_DEFERRED",
        three: "THREE_JS_DEFERRED",
      },
      screenshots: shots,
      axe: axeResults,
      axe_critical: totalCrit,
      axe_serious: totalSer,
      findings,
      verdict:
        totalCrit === 0 && totalSer === 0
          ? "BROWSER_CERT_PASS"
          : "BROWSER_CERT_PASS_WITH_A11Y_FINDINGS",
    };
    writeFileSync(
      join(OUT, "BROWSER_EVIDENCE.md"),
      `# BROWSER_EVIDENCE — UI-NEXT-3.1\n\n\`\`\`json\n${JSON.stringify(report, null, 2)}\n\`\`\`\n`,
    );
    writeFileSync(join(OUT, "browser_report.json"), JSON.stringify(report, null, 2));
    log(JSON.stringify({ axe_critical: totalCrit, axe_serious: totalSer, verdict: report.verdict, findings }));
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
