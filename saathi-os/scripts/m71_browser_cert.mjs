#!/usr/bin/env node
/**
 * M71 authenticated Autonomous Mission Runtime dashboard certification.
 * Starts isolated loopback services and never writes auth material to evidence.
 */
import { spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import { existsSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { chromium } from "playwright";

const HERE = dirname(fileURLToPath(import.meta.url));
const UI_ROOT = join(HERE, "..");
const REPO = join(UI_ROOT, "..");
const OUT = process.env.M71_EVIDENCE_DIR || join(REPO, "docs", "platform", "m71_evidence");
const BUILD = process.env.M71_BUILD === "1";
const PY = existsSync(join(REPO, ".venv", "bin", "python"))
  ? join(REPO, ".venv", "bin", "python")
  : "python3";

const freePort = (port) =>
  new Promise((resolve) => {
    const server = createServer();
    server.once("error", () => resolve(false));
    server.once("listening", () => server.close(() => resolve(true)));
    server.listen(port, "127.0.0.1");
  });

async function pickPort(candidates, label) {
  for (const port of candidates) if (await freePort(port)) return port;
  throw new Error(`${label}: no isolated loopback port available`);
}

async function waitHealthy(url, timeoutMs) {
  const started = Date.now();
  let last = "";
  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.status >= 200 && response.status < 500) return;
      last = `status ${response.status}`;
    } catch (error) {
      last = String(error?.message || error);
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  throw new Error(`health timeout ${url}: ${last}`);
}

function spawnLogged(command, args, options) {
  const child = spawn(command, args, {
    ...options,
    stdio: ["ignore", "pipe", "pipe"],
  });
  let log = "";
  child.stdout.on("data", (chunk) => {
    log += String(chunk);
  });
  child.stderr.on("data", (chunk) => {
    log += String(chunk);
  });
  return { child, log: () => log };
}

function stop(child) {
  if (!child || child.killed) return;
  try {
    child.kill("SIGTERM");
  } catch {
    return;
  }
  setTimeout(() => {
    try {
      if (!child.killed) child.kill("SIGKILL");
    } catch {
      // best-effort cleanup of this harness-owned child only
    }
  }, 2500);
}

async function api(base, path, { method = "GET", body, token } = {}) {
  const headers = { "content-type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  const response = await fetch(`${base}/api/v1/platform${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const payload = await response.json().catch(() => ({}));
  return { status: response.status, payload };
}

const report = {
  schema: "m71.browser_cert.v1",
  mode: BUILD ? "production-build-loopback" : "dev-loopback",
  hardGates: {},
  responsive: {},
  accessibility: {},
  browserErrors: { page: [], console: [], hydration: [] },
  screenshots: [],
};

function gate(name, condition, detail = "", bucket = report.hardGates) {
  bucket[name] = { ok: Boolean(condition), detail: String(detail || "") };
  if (!condition) throw new Error(`M71 gate failed: ${name}${detail ? ` — ${detail}` : ""}`);
}

async function main() {
  mkdirSync(join(OUT, "screenshots"), { recursive: true });
  const uiPort = await pickPort([3221, 3223, 13221], "UI");
  const apiPort = await pickPort([8871, 18871, 18873], "API");
  const UI = `http://127.0.0.1:${uiPort}`;
  const API = `http://127.0.0.1:${apiPort}`;
  report.ui = UI;
  report.api = API;
  const certDir = join(tmpdir(), `saathi-m71-${process.pid}`);
  const dbPath = join(certDir, "platform.db");
  mkdirSync(certDir, { recursive: true });
  const cors = `${UI},http://localhost:${uiPort}`;
  const certPassword = `M71-Cert-${process.pid}-A9!`;
  const legacyAccess = `m71-cert-access-${process.pid}`;
  const legacySession = createHash("sha256")
    .update(`${legacyAccess}:baadar-session`)
    .digest("hex");
  let backend;
  let frontend;
  let browser;

  try {
    backend = spawnLogged(
      PY,
      ["-m", "uvicorn", "saathi.server:app", "--host", "127.0.0.1", "--port", String(apiPort)],
      {
        cwd: REPO,
        env: {
          ...process.env,
          SAATHI_PLATFORM_DB: dbPath,
          SAATHI_CORS_ORIGINS: cors,
          SAATHI_TOKEN: legacyAccess,
          BAADAR_PASSWORD: "",
          BAADAR_PASSWORD_HASH: "",
        },
      }
    );
    await waitHealthy(`${API}/api/v1/platform/health`, 90000);
    gate("backend_loopback", true);

    await api(API, "/bootstrap", {
      method: "POST",
      body: {
        email: "owner@m71.cert",
        name: "M71 Owner",
        org_name: "M71 Org",
        workspace_name: "M71 Workspace",
        password: certPassword,
      },
    });
    const login = await api(API, "/auth/login", {
      method: "POST",
      body: {
        email: "owner@m71.cert",
        password: certPassword,
        method: "LOCAL_PASSWORD",
      },
    });
    const token = login.payload?.token;
    gate("authenticated_login", login.status === 200 && Boolean(token));
    const project = await api(API, "/projects", {
      method: "POST",
      token,
      body: { name: "Autonomous Mission Runtime" },
    });
    const mission = await api(API, "/missions", {
      method: "POST",
      token,
      body: {
        project_id: project.payload.project.project_id,
        key: "M71-CERT",
        name: "Mission Dashboard Certification",
      },
    });
    const missionId = mission.payload.mission.mission_id;
    const definition = {
      objective: "Certify the backend-driven autonomous mission dashboard.",
      max_parallel_tasks: 2,
      budget: {
        estimated_effort: 8,
        max_elapsed_seconds: 1800,
        max_token_estimate: 5000,
        max_commits: 3,
        max_tests: 5,
        max_browser_runs: 3,
        max_cycles: 20,
        max_no_progress_cycles: 3,
      },
      goals: [
        {
          title: "Dashboard",
          phases: [
            {
              title: "Certification",
              milestones: [
                {
                  title: "Browser journey",
                  tasks: [
                    {
                      id: "execute",
                      title: "Execute governed check",
                      agent_type: "TestAgent",
                      tool_id: "m49.echo_readonly",
                      arguments: { text: "m71-browser" },
                      priority: 90,
                      estimated_effort: 2,
                      token_estimate: 200,
                      verification: ["browser-cert"],
                    },
                    {
                      id: "document",
                      title: "Record certification",
                      agent_type: "DocumentationAgent",
                      tool_id: "m49.echo_readonly",
                      arguments: { text: "m71-docs" },
                      depends_on: ["execute"],
                      priority: 60,
                      estimated_effort: 1,
                      token_estimate: 100,
                      verification: [],
                    },
                  ],
                },
              ],
            },
          ],
        },
      ],
    };
    const planned = await api(API, `/missions/${missionId}/runtime/plan`, {
      method: "PUT",
      token,
      body: { definition },
    });
    gate("runtime_plan_api", planned.status === 200 && planned.payload?.tasks?.length === 2);
    const run = await api(API, `/missions/${missionId}/runtime/run`, {
      method: "POST",
      token,
      body: { max_cycles: 1, timeout_sec: 30 },
    });
    gate(
      "governed_run_waits_for_verification",
      run.status === 200 && run.payload?.stop_condition === "BLOCKED_EXTERNAL_INPUT"
    );
    const detailBefore = await api(API, `/missions/${missionId}/runtime`, { token });
    const firstTask = detailBefore.payload.tasks.find((task) => task.title === "Execute governed check");
    const evidence = await api(API, `/missions/${missionId}/runtime/evidence`, {
      method: "POST",
      token,
      body: {
        task_id: firstTask.node_id,
        evidence_type: "test",
        status: "PASS",
        summary: "Browser certification verification is recorded.",
        reference: "m71-browser-cert",
        check_name: "browser-cert",
      },
    });
    gate("evidence_api", evidence.status === 200 && evidence.payload?.evidence?.status === "PASS");
    const checkpoint = await api(API, `/missions/${missionId}/runtime/checkpoints`, {
      method: "POST",
      token,
      body: {
        latest_commit: "a628b43",
        rollback_sha: "072fea7",
        test_status: "PASS",
        browser_status: "IN_PROGRESS",
        known_blockers: [],
      },
    });
    gate("checkpoint_api", checkpoint.status === 200 && checkpoint.payload?.checkpoint?.snapshot_hash?.length === 64);
    const dashboard = await api(API, "/mission-runtimes/dashboard", { token });
    gate(
      "dashboard_summary_api",
      dashboard.status === 200
        && dashboard.payload?.mission_runtimes?.[0]?.mission_id === missionId
    );
    const noAuth = await api(API, `/missions/${missionId}/runtime`);
    gate("unauthenticated_rejected", noAuth.status === 401);

    const uiEnv = {
      ...process.env,
      NEXT_PUBLIC_SAATHI_API: API,
      NEXT_PUBLIC_LOCAL_API: API,
    };
    if (BUILD) {
      const build = spawn("npm", ["run", "build"], {
        cwd: UI_ROOT,
        stdio: "inherit",
        env: uiEnv,
      });
      await new Promise((resolve, reject) => {
        build.on("exit", (code) =>
          code === 0 ? resolve() : reject(new Error(`Next build exited ${code}`))
        );
      });
      gate("production_build", true);
      frontend = spawnLogged(
        "npm",
        ["run", "start", "--", "-p", String(uiPort)],
        { cwd: UI_ROOT, env: uiEnv }
      );
    } else {
      frontend = spawnLogged(
        "npm",
        ["run", "dev", "--", "-p", String(uiPort)],
        { cwd: UI_ROOT, env: uiEnv }
      );
    }
    await waitHealthy(`${UI}/platform/missions`, 150000);
    gate("frontend_loopback", true);

    browser = await chromium.launch({ headless: true });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    await context.addInitScript((value) => {
      localStorage.setItem("saathi_platform_token", value);
    }, token);
    await context.addInitScript((value) => {
      localStorage.setItem("saathi_session", value);
    }, legacySession);
    const page = await context.newPage();
    page.on("pageerror", (error) => report.browserErrors.page.push(String(error?.message || error)));
    page.on("console", (message) => {
      if (message.type() !== "error") return;
      const text = message.text();
      report.browserErrors.console.push(text);
      if (/hydration|react error|nextjs/i.test(text)) report.browserErrors.hydration.push(text);
    });

    await page.goto(`${UI}/platform/missions`, { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Mission Control" }).waitFor();
    await page.getByText("Mission Dashboard Certification", { exact: true }).waitFor();
    gate("mission_control_backend_runtime", await page.getByText(/HEALTHY|AT_RISK/).count() > 0);
    const listShot = join(OUT, "screenshots", "m71_mission_control.png");
    await page.screenshot({ path: listShot, fullPage: true });
    report.screenshots.push("screenshots/m71_mission_control.png");

    await page.goto(`${UI}/platform/missions/${missionId}`, { waitUntil: "domcontentloaded" });
    await page.getByRole("heading", { name: "Mission Dashboard Certification" }).waitFor();
    await page.getByText("Autonomous runtime", { exact: true }).waitFor();
    await page.getByText("Dependency-aware task graph", { exact: true }).waitFor();
    await page.getByText("Mission evidence", { exact: true }).waitFor();
    await page.getByText("Recovery checkpoints", { exact: true }).waitFor();
    gate("runtime_health_visible", await page.getByText(/HEALTHY|AT_RISK/).count() > 0);
    gate("progress_semantics", await page.locator('[role="progressbar"][aria-label="Mission completion"]').count() === 1);
    gate("agent_visible", await page.getByText(/TestAgent/).count() > 0);
    gate("evidence_visible", await page.getByText("Browser certification verification is recorded.", { exact: true }).count() === 1);
    gate("checkpoint_visible", await page.getByText(/mcp_/).count() > 0);
    gate("test_status_visible", await page.getByText("PASS", { exact: true }).count() > 0);
    gate(
      "no_browser_execution_authority",
      await page.getByRole("button", { name: /run mission|execute mission|approve automatically/i }).count() === 0
    );
    const detailShot = join(OUT, "screenshots", "m71_mission_detail.png");
    await page.screenshot({ path: detailShot, fullPage: true });
    report.screenshots.push("screenshots/m71_mission_detail.png");

    const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } });
    await mobile.addInitScript((value) => {
      localStorage.setItem("saathi_platform_token", value);
    }, token);
    await mobile.addInitScript((value) => {
      localStorage.setItem("saathi_session", value);
    }, legacySession);
    const mobilePage = await mobile.newPage();
    await mobilePage.goto(`${UI}/platform/missions/${missionId}`, { waitUntil: "domcontentloaded" });
    await mobilePage.getByText("Autonomous runtime", { exact: true }).waitFor();
    const overflow = await mobilePage.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2
    );
    gate("mobile_no_horizontal_overflow", !overflow, "", report.responsive);
    gate(
      "mobile_runtime_content",
      await mobilePage.getByText("Dependency-aware task graph", { exact: true }).count() === 1,
      "",
      report.responsive
    );
    const mobileShot = join(OUT, "screenshots", "m71_mission_mobile.png");
    await mobilePage.screenshot({ path: mobileShot, fullPage: true });
    report.screenshots.push("screenshots/m71_mission_mobile.png");
    await mobile.close();

    gate("semantic_progress", await page.locator('[role="progressbar"][aria-valuenow]').count() >= 1, "", report.accessibility);
    gate(
      "semantic_section_headings",
      await page.getByRole("heading").count() >= 4,
      "",
      report.accessibility
    );
    gate("no_page_errors", report.browserErrors.page.length === 0);
    gate("no_hydration_errors", report.browserErrors.hydration.length === 0);
    gate("no_console_errors", report.browserErrors.console.length === 0);
  } catch (error) {
    report.fatal = String(error?.stack || error).slice(0, 2000);
  } finally {
    if (browser) await browser.close().catch(() => {});
    stop(frontend?.child);
    stop(backend?.child);
  }

  const failed = Object.values(report.hardGates).some((item) => !item.ok)
    || Object.values(report.responsive).some((item) => !item.ok)
    || Object.values(report.accessibility).some((item) => !item.ok)
    || Boolean(report.fatal);
  report.verdict = failed ? "FAIL" : "PASS";
  writeFileSync(join(OUT, "M71_BROWSER_CERT.json"), `${JSON.stringify(report, null, 2)}\n`);
  console.log(
    `M71 browser certificate ${report.verdict}: `
      + `${Object.keys(report.hardGates).length} hard, `
      + `${Object.keys(report.responsive).length} responsive, `
      + `${Object.keys(report.accessibility).length} accessibility gates`
  );
  if (report.fatal) console.error(report.fatal);
  if (failed) process.exitCode = 1;
}

await main();
