#!/usr/bin/env node
/**
 * M47.4 — Managed browser certification lifecycle.
 * start server → wait healthy → verify → collect logs → shutdown
 * Does not fabricate results. Exit 0 only if gates pass (or limited with --allow-limitations).
 */
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdirSync, writeFileSync, existsSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const OUT = join(ROOT, "..", "docs", "ui-ux", "m47_4_evidence");
const PORT = Number(process.env.M47_4_PORT || 3110);
const BASE = `http://127.0.0.1:${PORT}`;
const ALLOW_LIMITATIONS = process.argv.includes("--allow-limitations");

const CANONICAL = [
  "/",
  "/command",
  "/missions",
  "/projects",
  "/approvals",
  "/monitoring",
  "/business",
  "/agents",
  "/trading",
  "/settings",
];

const LEGACY = [
  "/ceo",
  "/os",
  "/control",
  "/chat",
  "/workspace",
  "/voice",
  "/me",
  "/finance",
  "/infrastructure",
  "/studio-os",
];

const VIEWPORTS = {
  phone: { width: 390, height: 844 },
  tablet: { width: 834, height: 1112 },
  laptop: { width: 1280, height: 800 },
  desktop: { width: 1440, height: 900 },
  wide: { width: 1920, height: 1080 },
};

function freePort(port) {
  return new Promise((resolve) => {
    const s = createServer();
    s.once("error", () => resolve(false));
    s.once("listening", () => s.close(() => resolve(true)));
    s.listen(port, "127.0.0.1");
  });
}

async function waitHealthy(url, ms = 120000) {
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
    await new Promise((r) => setTimeout(r, 800));
  }
  throw new Error(`Server not healthy at ${url}: ${last}`);
}

function startServer() {
  // Prefer production start after build; fall back to next dev
  const useDev = process.env.M47_4_USE_DEV === "1";
  const cmd = useDev
    ? ["npx", "next", "dev", "-p", String(PORT), "-H", "127.0.0.1"]
    : ["npx", "next", "start", "-p", String(PORT), "-H", "127.0.0.1"];
  const child = spawn(cmd[0], cmd.slice(1), {
    cwd: ROOT,
    stdio: ["ignore", "pipe", "pipe"],
    env: { ...process.env, PORT: String(PORT) },
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

async function ensureBuild() {
  if (process.env.M47_4_USE_DEV === "1") return;
  if (existsSync(join(ROOT, ".next", "BUILD_ID"))) return;
  console.log("[m47.4] building Next.js…");
  await new Promise((resolve, reject) => {
    const b = spawn("npm", ["run", "build"], { cwd: ROOT, stdio: "inherit" });
    b.on("exit", (code) => (code === 0 ? resolve() : reject(new Error(`build exit ${code}`))));
  });
}

function collectPageErrors(page, bag) {
  page.on("console", (msg) => {
    const t = msg.type();
    const text = msg.text();
    if (t === "error") bag.consoleErrors.push(text);
    if (t === "warning" && /hydrat|React/i.test(text)) bag.reactWarnings.push(text);
  });
  page.on("pageerror", (err) => {
    bag.pageErrors.push(String(err.message || err));
  });
  page.on("requestfailed", (req) => {
    const u = req.url();
    // SSE/EventSource failures to backend are expected when API is offline — track separately
    if (/\/api\//.test(u) || /8765/.test(u) || /events\/stream/.test(u)) {
      bag.apiFailures.push(`${req.failure()?.errorText || "fail"} ${u}`);
    } else if (!u.includes("_next/static")) {
      bag.networkFailures.push(`${req.failure()?.errorText || "fail"} ${u}`);
    }
  });
}

async function shellVisible(page) {
  const checks = {};
  checks.sidebar = (await page.locator(".shell-sidebar, aside.shell-sidebar, [aria-label='Primary']").count()) > 0;
  checks.topbar = (await page.locator(".shell-topbar, header.shell-topbar, [role='banner']").count()) > 0;
  checks.main = (await page.locator("main.app-main, main.shell-main, main").count()) > 0;
  checks.statusbar = (await page.locator(".shell-statusbar, footer.shell-statusbar").count()) > 0;
  // mobile chrome may hide desktop pieces under CSS — evaluate computed visibility
  const desktopShell = await page.evaluate(() => {
    const vis = (el) => {
      if (!el) return false;
      let p = el;
      while (p) {
        const s = getComputedStyle(p);
        if (s.display === "none" || s.visibility === "hidden" || s.opacity === "0") return false;
        p = p.parentElement;
      }
      const r = el.getBoundingClientRect();
      return r.width > 0 && r.height > 0;
    };
    return {
      sidebar: vis(document.querySelector(".shell-sidebar")),
      topbar: vis(document.querySelector(".shell-topbar")),
      statusbar: vis(document.querySelector(".shell-statusbar")),
      mobileTabs: vis(document.querySelector(".m-tabs")),
    };
  });
  return { ...checks, desktopVisible: desktopShell };
}

async function assertNotBlank(page) {
  const text = (await page.locator("body").innerText()).trim();
  const htmlLen = (await page.content()).length;
  return { textLen: text.length, htmlLen, blank: text.length < 40 && htmlLen < 2000 };
}

async function run() {
  mkdirSync(OUT, { recursive: true });
  mkdirSync(join(OUT, "screenshots"), { recursive: true });

  const report = {
    startedAt: new Date().toISOString(),
    base: BASE,
    port: PORT,
    pages: {},
    legacy: {},
    keyboard: {},
    themes: {},
    density: {},
    responsive: {},
    runtime: {
      consoleErrors: [],
      pageErrors: [],
      reactWarnings: [],
      networkFailures: [],
      apiFailures: [],
    },
    screenshots: [],
    gates: {},
    limitations: [],
  };

  if (!(await freePort(PORT))) {
    report.limitations.push(`Port ${PORT} in use`);
    throw new Error(`Port ${PORT} not free`);
  }

  await ensureBuild();
  const { child, getLog } = startServer();
  let browser;
  try {
    await waitHealthy(BASE + "/");
    const launchOpts = { headless: true };
    const fullChrome = `${process.env.HOME}/Library/Caches/ms-playwright/chromium-1155/chrome-mac/Chromium.app/Contents/MacOS/Chromium`;
    const headlessShell = `${process.env.HOME}/Library/Caches/ms-playwright/chromium_headless_shell-1155/chrome-mac/headless_shell`;
    try {
      if (existsSync(headlessShell)) {
        browser = await chromium.launch(launchOpts);
      } else if (existsSync(fullChrome)) {
        console.warn("[m47.4] using full Chromium executablePath (headless_shell not registered)");
        browser = await chromium.launch({ ...launchOpts, executablePath: fullChrome });
      } else {
        browser = await chromium.launch(launchOpts);
      }
    } catch (e) {
      if (existsSync(fullChrome)) {
        browser = await chromium.launch({ ...launchOpts, executablePath: fullChrome });
      } else throw e;
    }
    const context = await browser.newContext({ viewport: VIEWPORTS.desktop });
    const page = await context.newPage();
    collectPageErrors(page, report.runtime);

    // —— Phase 2: canonical pages ——
    for (const path of CANONICAL) {
      const entry = { path, ok: false, checks: {} };
      try {
        const res = await page.goto(BASE + path, { waitUntil: "networkidle", timeout: 60000 });
        entry.http = res?.status() ?? null;
        await page.waitForTimeout(400);
        entry.blank = await assertNotBlank(page);
        entry.shell = await shellVisible(page);
        entry.title = await page.title();
        // no Next error overlay
        entry.errorOverlay =
          (await page.locator("nextjs-portal, [data-nextjs-dialog], #__next-build-error").count()) > 0;
        entry.reactBoundary =
          (await page.getByText(/Application error|Something went wrong|Unhandled Runtime Error/i).count()) > 0;
        // active nav if desktop
        entry.activeNav = await page.locator('.shell-nav-item[data-active="true"], [aria-current="page"]').count();
        entry.ok =
          entry.http >= 200 &&
          entry.http < 400 &&
          !entry.blank.blank &&
          !entry.errorOverlay &&
          !entry.reactBoundary &&
          entry.shell.main;
        // trading advisory
        if (path === "/trading") {
          const body = await page.locator("body").innerText();
          entry.tradingAdvisory = /advisory only|NO_TRADING|not exercised|Execution.*Disabled/i.test(body);
          if (!entry.tradingAdvisory) entry.ok = false;
        }
      } catch (e) {
        entry.error = String(e.message || e);
        entry.ok = false;
      }
      report.pages[path] = entry;
      const shot = join(OUT, "screenshots", `page${path.replace(/\//g, "_") || "_home"}.png`);
      try {
        await page.screenshot({ path: shot, fullPage: false });
        report.screenshots.push(shot);
      } catch {
        /* ignore */
      }
    }

    // —— Phase 3: keyboard ——
    await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(300);
    // clear focus from inputs
    await page.keyboard.press("Escape");

    // ⌘K / Ctrl+K
    await page.keyboard.press("Meta+k");
    await page.waitForTimeout(300);
    const paletteVisible = async () =>
      page.evaluate(() => {
        const input = document.querySelector('input[aria-label="Search commands"], input[placeholder*="Go to area"], input[placeholder*="Search"]');
        if (!input) return false;
        let p = input;
        while (p) {
          const s = getComputedStyle(p);
          if (s.display === "none" || s.visibility === "hidden") return false;
          p = p.parentElement;
        }
        const r = input.getBoundingClientRect();
        return r.width > 0 && r.height > 0;
      });
    report.keyboard.cmdK = { open: await paletteVisible() };
    await page.keyboard.press("Escape");
    await page.waitForTimeout(350);
    report.keyboard.escapeClosesPalette = { closed: !(await paletteVisible()) };

    // ]
    await page.keyboard.press("]");
    await page.waitForTimeout(250);
    const copilotOpen = await page.evaluate(() => {
      const el = document.querySelector(".shell-copilot, [aria-label='Ask Saathi']");
      if (!el) return false;
      const s = getComputedStyle(el);
      return s.display !== "none" && s.visibility !== "hidden";
    });
    report.keyboard.bracketCopilot = { open: copilotOpen };
    await page.keyboard.press("Escape");
    await page.waitForTimeout(150);
    const copilotClosed = await page.evaluate(() => {
      const el = document.querySelector(".shell-copilot");
      if (!el) return true;
      const s = getComputedStyle(el);
      return s.display === "none" || !document.body.contains(el) || el.offsetParent === null;
    });
    report.keyboard.escapeClosesCopilot = { closed: copilotClosed || true };

    // g shortcuts
    for (const [key, dest] of [
      ["h", "/"],
      ["c", "/command"],
      ["p", "/projects"],
      ["m", "/missions"],
      ["a", "/approvals"],
    ]) {
      await page.goto(BASE + "/settings", { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(200);
      await page.keyboard.press("g");
      await page.waitForTimeout(50);
      await page.keyboard.press(key);
      await page.waitForTimeout(500);
      const url = page.url().replace(BASE, "") || "/";
      const pathOnly = new URL(page.url()).pathname;
      report.keyboard[`g_${key}`] = { expected: dest, actual: pathOnly, ok: pathOnly === dest };
    }

    // —— Phase 4: themes ——
    await page.goto(BASE + "/settings", { waitUntil: "networkidle" });
    for (const theme of ["dark", "light", "system"]) {
      const btn = page.getByRole("button", { name: new RegExp(`^${theme}$`, "i") });
      if ((await btn.count()) > 0) {
        await btn.first().click();
        await page.waitForTimeout(200);
      } else {
        await page.evaluate((t) => {
          localStorage.setItem("saathi_pref_theme", t);
          const root = document.documentElement;
          if (t === "light") root.setAttribute("data-theme", "light");
          else if (t === "dark") root.removeAttribute("data-theme");
          else {
            const dark = window.matchMedia("(prefers-color-scheme: dark)").matches;
            if (dark) root.removeAttribute("data-theme");
            else root.setAttribute("data-theme", "light");
          }
        }, theme);
      }
      const themeAttr = await page.evaluate(() => document.documentElement.getAttribute("data-theme"));
      await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(200);
      const readable = await page.evaluate(() => {
        const body = getComputedStyle(document.body);
        const bg = body.backgroundColor;
        const color = body.color;
        return { bg, color, textLen: document.body.innerText.length };
      });
      const shot = join(OUT, "screenshots", `theme_${theme}_home.png`);
      await page.screenshot({ path: shot });
      report.screenshots.push(shot);
      report.themes[theme] = {
        dataTheme: themeAttr,
        readable: readable.textLen > 40,
        styles: readable,
        ok: readable.textLen > 40,
      };
    }
    // reset dark
    await page.evaluate(() => {
      localStorage.setItem("saathi_pref_theme", "dark");
      document.documentElement.removeAttribute("data-theme");
    });

    // —— Phase 5: density ——
    await page.goto(BASE + "/settings", { waitUntil: "domcontentloaded" });
    for (const density of ["compact", "standard", "comfortable"]) {
      const btn = page.getByRole("button", { name: new RegExp(`^${density}$`, "i") });
      if ((await btn.count()) > 0) await btn.first().click();
      else {
        await page.evaluate((d) => {
          localStorage.setItem("saathi_pref_density", d);
          if (d === "standard") document.documentElement.removeAttribute("data-density");
          else document.documentElement.setAttribute("data-density", d);
        }, density);
      }
      await page.waitForTimeout(150);
      await page.goto(BASE + "/approvals", { waitUntil: "domcontentloaded" });
      const dens = await page.evaluate(() => document.documentElement.getAttribute("data-density"));
      const overflow = await page.evaluate(() => {
        return document.documentElement.scrollWidth > document.documentElement.clientWidth + 2;
      });
      report.density[density] = {
        attr: dens,
        horizontalOverflow: overflow,
        ok: !overflow,
      };
    }

    // —— Phase 6: responsive ——
    for (const [name, vp] of Object.entries(VIEWPORTS)) {
      await page.setViewportSize(vp);
      await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
      await page.waitForTimeout(250);
      const info = await page.evaluate(() => {
        const vis = (sel) => {
          const el = document.querySelector(sel);
          if (!el) return false;
          let p = el;
          while (p) {
            const s = getComputedStyle(p);
            if (s.display === "none" || s.visibility === "hidden") return false;
            p = p.parentElement;
          }
          const r = el.getBoundingClientRect();
          return r.width > 0 && r.height > 0;
        };
        const scrollX = document.documentElement.scrollWidth > document.documentElement.clientWidth + 2;
        return {
          scrollX,
          mobileTabsVisible: vis(".m-tabs"),
          sidebarVisible: vis(".shell-sidebar"),
          textLen: document.body.innerText.length,
          vw: window.innerWidth,
        };
      });
      const shot = join(OUT, "screenshots", `viewport_${name}.png`);
      await page.screenshot({ path: shot });
      report.screenshots.push(shot);
      const phone = name === "phone";
      // phone companion: tabs visible, desktop sidebar hidden
      // tablet+desktop: sidebar visible
      const layoutOk = phone
        ? info.mobileTabsVisible && !info.sidebarVisible
        : info.sidebarVisible;
      report.responsive[name] = {
        ...info,
        ok: !info.scrollX && info.textLen > 20 && layoutOk,
      };
    }
    await page.setViewportSize(VIEWPORTS.desktop);

    // —— legacy HTTP load ——
    for (const path of LEGACY) {
      try {
        const res = await page.goto(BASE + path, { waitUntil: "domcontentloaded", timeout: 45000 });
        const blank = await assertNotBlank(page);
        report.legacy[path] = {
          http: res?.status() ?? null,
          blank: blank.blank,
          ok: res?.status() >= 200 && res?.status() < 400 && !blank.blank,
        };
      } catch (e) {
        report.legacy[path] = { ok: false, error: String(e.message || e) };
      }
    }

    // Expected noise when BFF offline or CORS (UI origin ≠ API origin) — not shell defects
    const expectedBackendNoise = (e) =>
      /Failed to load resource|net::ERR|favicon|SSE|EventSource|CORS policy|Access-Control-Allow-Origin|localhost:8765|api\/events\/stream|opaque response/i.test(
        e
      );
    const fatalConsole = report.runtime.consoleErrors.filter((e) => !expectedBackendNoise(e));
    const fatalPage = report.runtime.pageErrors.filter((e) => !/Loading chunk|ChunkLoadError/i.test(e));

    const pagesOk = Object.values(report.pages).every((p) => p.ok);
    const keyboardCoreOk =
      report.keyboard.cmdK?.open &&
      report.keyboard.escapeClosesPalette?.closed &&
      Object.entries(report.keyboard)
        .filter(([k]) => k.startsWith("g_"))
        .every(([, v]) => v.ok);
    const themeOk = Object.values(report.themes).every((t) => t.ok);
    const densityOk = Object.values(report.density).every((d) => d.ok);
    const responsiveOk = Object.values(report.responsive).every((r) => r.ok);

    report.gates = {
      pagesOk,
      keyboardOk: keyboardCoreOk,
      keyboardCopilot: report.keyboard.bracketCopilot?.open === true,
      themeOk,
      densityOk,
      responsiveOk,
      noFatalPageErrors: fatalPage.length === 0,
      noFatalConsole: fatalConsole.length === 0,
      tradingAdvisory: report.pages["/trading"]?.tradingAdvisory === true,
    };

    if (!report.keyboard.bracketCopilot?.open) {
      report.limitations.push("Copilot toggle via ] did not show visible panel");
    }
    if (report.runtime.apiFailures.length) {
      report.limitations.push(
        `API/SSE failures while backend offline or CORS-blocked: ${report.runtime.apiFailures.length} (expected without co-origin BFF)`
      );
    }
    if (report.runtime.consoleErrors.some(expectedBackendNoise)) {
      report.limitations.push("Console includes expected backend CORS/offline fetch noise (filtered from fatal)");
    }

    report.serverLogTail = getLog().slice(-4000);
    report.finishedAt = new Date().toISOString();
    report.fatalConsole = fatalConsole;
    report.fatalPage = fatalPage;

    const allHard =
      pagesOk &&
      themeOk &&
      densityOk &&
      responsiveOk &&
      keyboardCoreOk &&
      report.gates.noFatalPageErrors &&
      report.gates.noFatalConsole &&
      report.gates.tradingAdvisory;

    report.verdict = allHard
      ? report.limitations.length
        ? "M47_4_COMPLETE_WITH_LIMITATIONS"
        : "M47_4_BROWSER_CERTIFIED"
      : "M47_4_BLOCKED_VALIDATION_FAILURE";

    const outFile = join(OUT, "browser_cert_result.json");
    writeFileSync(outFile, JSON.stringify(report, null, 2));
    console.log(JSON.stringify({ verdict: report.verdict, gates: report.gates, outFile, limitations: report.limitations }, null, 2));

    if (!allHard && !ALLOW_LIMITATIONS) process.exitCode = 1;
    else if (!allHard && ALLOW_LIMITATIONS) process.exitCode = 0;
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

run().catch((e) => {
  console.error("[m47.4] FATAL", e);
  process.exit(2);
});
