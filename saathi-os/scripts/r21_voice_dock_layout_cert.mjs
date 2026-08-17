#!/usr/bin/env node
/**
 * R2.1-D1 voice runtime dock layout certificate.
 *
 * Proves, in a real browser at fixed viewports, that the Live voice dock's
 * microphone control is inside the viewport, is the element a click at its
 * centre actually reaches (not the sidebar, status bar or another dock), is
 * reachable by keyboard, and that the dock introduces no horizontal overflow.
 *
 * Services are checkout-local production services on fixed loopback ports; the
 * platform database lives in an OS temporary directory and is removed after the
 * run. Evidence contains only geometry, booleans and synthetic screenshots.
 *
 * Synthetic only: this certifies layout and reachability, NOT microphone
 * behaviour. Real-microphone behaviour is owner-validated separately.
 */
import { execFileSync, spawn } from "node:child_process";
import { createServer } from "node:http";
import { existsSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";
import {
  certificateProvenance,
  readRuntimeIdentity,
  harnessWorktree,
} from "./lib/cert-provenance.mjs";

const HERE = dirname(fileURLToPath(import.meta.url));
const UI_ROOT = join(HERE, "..");
const REPO = join(UI_ROOT, "..");
const OUT =
  process.env.R21_EVIDENCE_DIR ||
  join(REPO, "docs", "evidence", "r2-1", "dock-layout");
const SCREENSHOTS = join(OUT, "screenshots");
const UI = "http://127.0.0.1:3000";
const API = "http://127.0.0.1:8765";
const PY = existsSync(join(REPO, ".venv", "bin", "python"))
  ? join(REPO, ".venv", "bin", "python")
  : "python3";
const BUILD = process.env.R21_BUILD !== "0";
const certDir = mkdtempSync(join(tmpdir(), "saathi-r21-dock-"));
const dbPath = join(certDir, "platform.db");
const artifactPath = join(certDir, "voice-artifacts");

const HARNESS_FILE = "saathi-os/scripts/r21_voice_dock_layout_cert.mjs";
const COMMAND = "npm --prefix saathi-os run cert:r21-dock";

/** Viewports the dock must stay reachable at. */
const VIEWPORTS = [
  { name: "desktop_1440", width: 1440, height: 900 },
  { name: "desktop_1280", width: 1280, height: 800 },
  { name: "laptop_1024", width: 1024, height: 768 },
  { name: "tablet_834", width: 834, height: 1112 },
  { name: "tablet_768", width: 768, height: 1024 },
  { name: "phone_390", width: 390, height: 844 },
  { name: "phone_360", width: 360, height: 740 },
];

mkdirSync(SCREENSHOTS, { recursive: true });

let runtimeIdentity = null;

const report = {
  schema: "r2_1.voice_dock_layout_cert.v1",
  provenance: null,
  capturedAt: new Date().toISOString(),
  mode: "production-build-loopback",
  scope: "layout and reachability only — no microphone behaviour is certified",
  hardGates: {},
  layout: {},
  accessibility: {},
  geometry: {},
  browserErrors: { page: [], console: [] },
  screenshots: [],
};

function gate(name, condition, detail = "", bucket = report.hardGates) {
  bucket[name] = { ok: Boolean(condition), detail: String(detail || "") };
  if (!condition) {
    throw new Error(`R2.1-D1 gate failed: ${name}${detail ? ` — ${detail}` : ""}`);
  }
}

const freePort = (port) =>
  new Promise((resolve) => {
    const server = createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => server.close(() => resolve(true)));
    server.listen(port, "127.0.0.1");
  });

async function waitHealthy(url, timeoutMs = 120000) {
  const started = Date.now();
  let detail = "";
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.status >= 200 && response.status < 500) return;
      detail = `status ${response.status}`;
    } catch (error) {
      detail = String(error?.message || error);
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  throw new Error(`health timeout: ${detail}`);
}

function spawnLogged(command, args, options) {
  const child = spawn(command, args, {
    ...options,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let log = "";
  const keep = (chunk) => {
    log = `${log}${chunk}`.slice(-12000);
  };
  child.stdout.on("data", keep);
  child.stderr.on("data", keep);
  return { child, log: () => log };
}

async function stopOwned(processInfo) {
  const child = processInfo?.child;
  if (!child || child.exitCode !== null) return;
  child.kill("SIGTERM");
  await Promise.race([
    new Promise((resolve) => child.once("exit", resolve)),
    new Promise((resolve) => setTimeout(resolve, 2500)),
  ]);
  if (child.exitCode === null) child.kill("SIGKILL");
}

async function api(path, { method = "GET", body, token } = {}) {
  const headers = { "content-type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  const response = await fetch(`${API}/api/v1/platform${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  return {
    status: response.status,
    payload: await response.json().catch(() => ({})),
  };
}

function observe(page) {
  page.on("pageerror", (error) => {
    report.browserErrors.page.push(String(error?.message || error).slice(0, 300));
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      report.browserErrors.console.push(message.text().slice(0, 300));
    }
  });
}

/** Measured in the page: dock geometry against the rest of the shell chrome. */
function measureDock() {
  const rect = (selector) => {
    const element = document.querySelector(selector);
    if (!element) return null;
    const r = element.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return null;
    return {
      x: Math.round(r.x),
      y: Math.round(r.y),
      width: Math.round(r.width),
      height: Math.round(r.height),
      right: Math.round(r.right),
      bottom: Math.round(r.bottom),
    };
  };
  const intersection = (a, b) => {
    if (!a || !b) return 0;
    const w = Math.min(a.right, b.right) - Math.max(a.x, b.x);
    const h = Math.min(a.bottom, b.bottom) - Math.max(a.y, b.y);
    return w > 0 && h > 0 ? Math.round(w * h) : 0;
  };

  const dock = rect(".voice-runtime-dock");
  const mic = rect(".voice-runtime-mic");
  const output = rect(".voice-output-dock");
  const statusBar = rect(".shell-statusbar");
  const sidebar = rect(".shell-sidebar");
  const tabBar = rect(".m-tabs");

  const micElement = document.querySelector(".voice-runtime-mic");
  let micHit = "MISSING";
  if (mic && micElement) {
    const cx = mic.x + mic.width / 2;
    const cy = mic.y + mic.height / 2;
    if (cx < 0 || cy < 0 || cx > window.innerWidth || cy > window.innerHeight) {
      micHit = "OFFSCREEN";
    } else {
      const top = document.elementFromPoint(cx, cy);
      micHit =
        top === micElement || micElement.contains(top)
          ? "MIC"
          : `${top?.tagName || "NONE"}.${top?.className || ""}`.slice(0, 60);
    }
  }

  return {
    viewport: { width: window.innerWidth, height: window.innerHeight },
    dock,
    mic,
    output,
    statusBar,
    sidebar,
    tabBar,
    micHit,
    micName: micElement?.getAttribute("aria-label") || "",
    micPosition: dock ? getComputedStyle(document.querySelector(".voice-runtime-dock")).position : "",
    micInViewport: Boolean(
      mic &&
        mic.x >= 0 &&
        mic.y >= 0 &&
        mic.right <= window.innerWidth &&
        mic.bottom <= window.innerHeight
    ),
    dockInViewport: Boolean(
      dock &&
        dock.x >= 0 &&
        dock.y >= 0 &&
        dock.right <= window.innerWidth &&
        dock.bottom <= window.innerHeight
    ),
    overlapOutput: intersection(dock, output),
    overlapStatusBar: intersection(dock, statusBar),
    overlapSidebar: intersection(dock, sidebar),
    overlapTabBar: intersection(dock, tabBar),
    dockArea: dock ? dock.width * dock.height : 0,
    horizontalOverflow:
      document.documentElement.scrollWidth - document.documentElement.clientWidth,
  };
}

async function certifyViewport(browser, token, viewport) {
  const { name, width, height } = viewport;
  const context = await browser.newContext({ viewport: { width, height } });
  await context.addInitScript((platformToken) => {
    localStorage.setItem("saathi_platform_token", platformToken);
  }, token);
  const page = await context.newPage();
  observe(page);
  await page.goto(`${UI}/command`, { waitUntil: "domcontentloaded" });
  await page.locator(".voice-runtime-dock").waitFor({ state: "visible", timeout: 20000 });
  await page.locator(".voice-runtime-mic").waitFor({ state: "visible", timeout: 20000 });

  const m = await page.evaluate(measureDock);
  report.geometry[name] = m;

  gate(`${name}_dock_is_fixed_chrome`, m.micPosition === "fixed", m.micPosition, report.layout);
  gate(`${name}_mic_inside_viewport`, m.micInViewport, JSON.stringify(m.mic), report.layout);
  gate(`${name}_dock_inside_viewport`, m.dockInViewport, JSON.stringify(m.dock), report.layout);
  gate(
    `${name}_mic_is_click_target`,
    m.micHit === "MIC",
    `top element at mic centre: ${m.micHit}`,
    report.layout
  );
  gate(
    `${name}_dock_clear_of_status_bar`,
    m.overlapStatusBar === 0,
    `overlap ${m.overlapStatusBar}px²`,
    report.layout
  );
  gate(
    `${name}_dock_clear_of_navigation`,
    m.overlapSidebar === 0 && m.overlapTabBar === 0,
    `sidebar ${m.overlapSidebar}px², tabbar ${m.overlapTabBar}px²`,
    report.layout
  );
  gate(
    `${name}_docks_do_not_materially_overlap`,
    m.dockArea > 0 && m.overlapOutput / m.dockArea <= 0.02,
    `output overlap ${m.overlapOutput}px² of ${m.dockArea}px²`,
    report.layout
  );
  gate(
    `${name}_no_horizontal_overflow`,
    m.horizontalOverflow <= 2,
    `${m.horizontalOverflow}px`,
    report.layout
  );
  gate(
    `${name}_mic_touch_target`,
    m.mic.width >= 44 && m.mic.height >= 44,
    `${m.mic.width}x${m.mic.height}`,
    report.accessibility
  );
  gate(
    `${name}_mic_accessible_name`,
    m.micName.length > 0,
    m.micName,
    report.accessibility
  );

  // Keyboard: the mic must be reachable by Tab and must show a focus ring.
  await page.evaluate(() => {
    document.body.setAttribute("tabindex", "-1");
    document.body.focus();
  });
  let presses = 0;
  let focused = false;
  while (presses < 120 && !focused) {
    await page.keyboard.press("Tab");
    presses += 1;
    focused = await page.evaluate(() =>
      Boolean(document.activeElement?.classList?.contains("voice-runtime-mic"))
    );
  }
  gate(
    `${name}_keyboard_reaches_mic`,
    focused,
    `${presses} tab stops`,
    report.accessibility
  );
  const focusRing = await page.evaluate(() => {
    const style = getComputedStyle(document.activeElement);
    return { width: style.outlineWidth, style: style.outlineStyle };
  });
  gate(
    `${name}_focus_is_visible`,
    focusRing.style !== "none" && parseFloat(focusRing.width) >= 1,
    JSON.stringify(focusRing),
    report.accessibility
  );
  report.geometry[name].keyboardTabStops = presses;

  const shot = `r21_dock_${name}.png`;
  await page.screenshot({ path: join(SCREENSHOTS, shot) });
  report.screenshots.push(`screenshots/${shot}`);
  await context.close();
}

async function main() {
  let backend;
  let frontend;
  let browser;
  try {
    gate("api_port_available", await freePort(8765));
    gate("ui_port_available", await freePort(3000));

    backend = spawnLogged(
      PY,
      ["-m", "uvicorn", "saathi.server:app", "--host", "127.0.0.1", "--port", "8765"],
      {
        cwd: REPO,
        env: {
          ...process.env,
          SAATHI_PLATFORM_DB: dbPath,
          SAATHI_VOICE_ARTIFACT_DIR: artifactPath,
          SAATHI_VOXCPM_ENABLED: "false",
          SAATHI_CORS_ORIGINS: `${UI},http://localhost:3000`,
          BAADAR_PASSWORD: "",
          BAADAR_PASSWORD_HASH: "",
          NO_PROXY: "127.0.0.1,localhost",
        },
      }
    );
    await waitHealthy(`${API}/api/v1/platform/health`);
    gate("backend_loopback", true);

    const boot = await api("/bootstrap", {
      method: "POST",
      body: {
        email: "owner@local",
        name: "R2.1 Owner",
        org_name: "R2.1 Org",
        workspace_name: "R2.1 Workspace",
      },
    });
    gate("local_bootstrap", boot.status === 200, `status ${boot.status}`);
    const login = await api("/auth/login", {
      method: "POST",
      body: { email: "owner@local" },
    });
    const token = login.payload?.token;
    gate("authenticated_sign_in", login.status === 200 && Boolean(token));

    if (BUILD) {
      execFileSync("npm", ["run", "build"], {
        cwd: UI_ROOT,
        stdio: "pipe",
        timeout: 300000,
        env: {
          ...process.env,
          NEXT_PUBLIC_SAATHI_API: API,
          NEXT_PUBLIC_LOCAL_API: API,
        },
      });
      gate("production_build", true);
    }
    frontend = spawnLogged("npm", ["run", "start"], {
      cwd: UI_ROOT,
      env: {
        ...process.env,
        NEXT_PUBLIC_SAATHI_API: API,
        NEXT_PUBLIC_LOCAL_API: API,
        NO_PROXY: "127.0.0.1,localhost",
      },
    });
    await waitHealthy(`${UI}/unlock`);
    gate("frontend_loopback", true);

    {
      const identity = await readRuntimeIdentity({ ui: UI, api: API });
      runtimeIdentity = { worktree: harnessWorktree(), ...identity };
      gate(
        "runtime_frontend_backend_sha_match",
        Boolean(identity.frontend?.frontendSha) &&
          identity.frontend?.frontendSha === identity.backend?.backendSha
      );
      gate(
        "runtime_matches_harness_worktree",
        identity.frontend?.worktreePath === runtimeIdentity.worktree.worktreePath &&
          identity.backend?.worktreePath === runtimeIdentity.worktree.worktreePath
      );
    }

    browser = await chromium.launch({ headless: true });
    for (const viewport of VIEWPORTS) {
      await certifyViewport(browser, token, viewport);
    }
    gate("no_page_errors", report.browserErrors.page.length === 0,
      report.browserErrors.page.slice(0, 2).join(" | "));
  } catch (error) {
    report.fatal = String(error?.stack || error).slice(0, 2500);
  } finally {
    if (browser) await browser.close().catch(() => {});
    await stopOwned(frontend);
    await stopOwned(backend);
    rmSync(certDir, { recursive: true, force: true });
  }

  const buckets = [report.hardGates, report.layout, report.accessibility];
  const failed =
    buckets.some((bucket) =>
      Object.values(bucket).some((value) => value?.ok === false)
    ) || Boolean(report.fatal);
  report.verdict = failed ? "FAIL" : "PASS";
  report.provenance = certificateProvenance({
    runtime: runtimeIdentity,
    ui: UI,
    api: API,
    command: COMMAND,
    harnessFile: HARNESS_FILE,
  });
  report.tempDatabaseRetained = false;
  writeFileSync(
    join(OUT, "R21_DOCK_LAYOUT_CERT.json"),
    `${JSON.stringify(report, null, 2)}\n`
  );
  console.log(
    `R2.1-D1 dock layout certificate ${report.verdict}: ` +
      `${Object.keys(report.hardGates).length} hard, ` +
      `${Object.keys(report.layout).length} layout, ` +
      `${Object.keys(report.accessibility).length} accessibility gates ` +
      `across ${VIEWPORTS.length} viewports`
  );
  if (report.fatal) console.error(report.fatal);
  if (failed) process.exitCode = 1;
}

await main();
