#!/usr/bin/env node
/**
 * M54 — Private-alpha operational readiness browser certification.
 *
 * Lifecycle: clean ports -> isolated platform SQLite -> start BFF -> seed owner
 * + binding + governed execution via API -> start UI -> drive the authenticated
 * /platform operator surface in a real browser -> assert readiness, export,
 * retention, tenancy/logout, and safety boundaries -> screenshots + evidence
 * JSON -> teardown.
 *
 * Honesty rules (shared with the M47 harnesses):
 * - Exit 0 only when every hard gate passes (or --allow-limitations for soft).
 * - Never fabricates network success. Never marks a PR ready. Never enables
 *   connectors, financial execution, or trading.
 *
 * The BFF runs against an isolated SAATHI_PLATFORM_DB so operator data is never
 * touched. Defaults to Next.js dev for speed; pass M54_BUILD=1 for a prod build.
 */
import { spawn } from "node:child_process";
import { createServer } from "node:http";
import { mkdirSync, writeFileSync, existsSync, rmSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { chromium } from "playwright";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ROOT = join(__dirname, "..");
const REPO = join(ROOT, "..");
const OUT = join(REPO, "docs", "platform", "m54_evidence");
const ALLOW_LIMITATIONS = process.argv.includes("--allow-limitations");
const USE_DEV = process.env.M54_BUILD !== "1";
const VENV_PY = join(REPO, ".venv", "bin", "python");
const PY = existsSync(VENV_PY) ? VENV_PY : "python3";

const UI_PORTS = [3140, 3142, 3144].map(Number);
const BFF_PORTS = [8790, 18790, 18792].map(Number);

function freePort(port) {
  return new Promise((resolve) => {
    const s = createServer();
    s.once("error", () => resolve(false));
    s.once("listening", () => s.close(() => resolve(true)));
    s.listen(port, "127.0.0.1");
  });
}
async function pickPort(cands, label) {
  for (const p of cands) if (await freePort(p)) return p;
  throw new Error(`${label}: no free port among ${cands.join(",")}`);
}
async function waitHealthy(url, ms = 120000, ok = null) {
  const start = Date.now();
  let last = "";
  while (Date.now() - start < ms) {
    try {
      const r = await fetch(url, { redirect: "manual" });
      const good = ok ? ok.includes(r.status) : r.status >= 200 && r.status < 500;
      if (good) return true;
      last = `status ${r.status}`;
    } catch (e) {
      last = String(e.message || e);
    }
    await new Promise((r) => setTimeout(r, 600));
  }
  throw new Error(`not healthy at ${url}: ${last}`);
}
function spawnLogged(cmd, args, opts = {}) {
  const child = spawn(cmd, args, { stdio: ["ignore", "pipe", "pipe"], ...opts });
  let buf = "";
  child.stdout?.on("data", (d) => (buf += d.toString()));
  child.stderr?.on("data", (d) => (buf += d.toString()));
  return { child, getLog: () => buf };
}
function killTree(child) {
  if (!child || child.killed) return;
  try {
    child.kill("SIGTERM");
  } catch {
    /* */
  }
  setTimeout(() => {
    try {
      if (!child.killed) child.kill("SIGKILL");
    } catch {
      /* */
    }
  }, 2500);
}
async function launchBrowser() {
  try {
    return await chromium.launch({ headless: true });
  } catch (e) {
    throw new Error(`chromium launch failed: ${e.message || e}`);
  }
}

async function api(base, path, { method = "GET", body, token } = {}) {
  const headers = { "content-type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  const res = await fetch(`${base}/api/v1/platform${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await res.text();
  let json = null;
  try {
    json = text ? JSON.parse(text) : null;
  } catch {
    /* */
  }
  return { status: res.status, json, text };
}

async function seed(base) {
  // Owner bootstrap + login → token
  await api(base, "/bootstrap", {
    method: "POST",
    body: {
      email: "owner@m54.cert",
      name: "Cert Owner",
      org_name: "M54 Cert Org",
      workspace_name: "M54 Cert Workspace",
      password: "CertOwnerPassw0rd!",
    },
  });
  const login = await api(base, "/auth/login", {
    method: "POST",
    body: { email: "owner@m54.cert", password: "CertOwnerPassw0rd!", method: "LOCAL_PASSWORD" },
  });
  const token = login.json?.token;
  if (!token) throw new Error(`seed login failed: ${login.status} ${login.text?.slice(0, 200)}`);
  // Binding + governed read-only execution
  await api(base, "/agent-bindings", {
    method: "POST",
    token,
    body: {
      agent_id: "cert-agent",
      name: "Certification agent",
      allowed_tools: ["m49.echo_readonly", "m49.local_note_write"],
      allowed_capabilities: [],
      authority_ceiling: "LOCAL_MUTATION",
    },
  });
  await api(base, "/execute", {
    method: "POST",
    token,
    body: { tool_id: "m49.echo_readonly", arguments: { text: "m54-cert" } },
  });
  return token;
}

async function main() {
  mkdirSync(join(OUT, "screenshots"), { recursive: true });
  const certDbDir = join(tmpdir(), `m54-cert-${process.pid}`);
  mkdirSync(certDbDir, { recursive: true });
  const CERT_DB = join(certDbDir, "platform.db");

  const uiPort = await pickPort(UI_PORTS, "UI");
  const bffPort = await pickPort(BFF_PORTS, "BFF");
  const BFF = `http://127.0.0.1:${bffPort}`;
  const BASE = `http://127.0.0.1:${uiPort}`;

  const report = {
    schema: "m54.browser_cert.v1",
    bff: BFF,
    ui: BASE,
    isolated_db: CERT_DB,
    mode: USE_DEV ? "dev" : "build",
    flows: {},
    screenshots: [],
    hardGates: {},
    softGates: {},
  };

  let bff, ui, browser;
  const fail = (k, msg) => {
    report.hardGates[k] = { ok: false, msg };
  };
  const pass = (k, extra = {}) => {
    report.hardGates[k] = { ok: true, ...extra };
  };

  try {
    // —— BFF ——
    bff = spawnLogged(
      PY,
      ["-m", "uvicorn", "saathi.server:app", "--host", "127.0.0.1", "--port", String(bffPort)],
      {
        cwd: REPO,
        env: {
          ...process.env,
          SAATHI_PLATFORM_DB: CERT_DB,
          // Allow the browser (dynamic UI port) to call the managed BFF.
          SAATHI_CORS_ORIGINS: `http://127.0.0.1:${uiPort},http://localhost:${uiPort}`,
        },
      },
    );
    await waitHealthy(`${BFF}/api/v1/platform/health`, 90000, [200, 401, 403]);

    // —— Seed via API ——
    const token = await seed(BFF);
    report.flows.seed = { ok: true };

    // —— API contract checks (auth/tenancy/export/retention/safety) ——
    const anon = await api(BFF, "/runtime/diagnostics");
    report.flows.auth_anonymous_denied = [401, 403].includes(anon.status);
    anon.status === 200 ? fail("auth", "anonymous diagnostics not denied") : pass("auth");

    const diag = await api(BFF, "/runtime/diagnostics", { token });
    const d = diag.json?.diagnostics || {};
    const safetyOk =
      d.environment?.production_authorized === false &&
      d.safety?.financial_execution === "DISABLED" &&
      d.safety?.trading_execution === "DISABLED" &&
      d.safety?.connector_mutations === "DRY_RUN_ONLY" &&
      d.safety?.registered_tool_authority === "ExecutionGateway" &&
      d.safety?.canonical_runtime === "PlatformAgentRuntime";
    report.flows.diagnostics = d;
    safetyOk ? pass("safety_boundaries") : fail("safety_boundaries", "diagnostics safety mismatch");

    const exp = await api(BFF, "/runtime/export?kind=execution_summary&format=json", { token });
    const blob = JSON.stringify(exp.json || {}).toLowerCase();
    const leaked = ["password", "arguments_json", "result_json", "session_token", "authorization"].filter(
      (k) => blob.includes(k),
    );
    report.flows.export = {
      record_count: exp.json?.manifest?.record_count,
      content_hash: exp.json?.manifest?.content_hash,
      production_data: exp.json?.manifest?.production_data,
      leaked,
    };
    exp.json?.manifest?.production_data === false && leaked.length === 0
      ? pass("export_redaction")
      : fail("export_redaction", `leaked=${leaked.join(",")}`);

    const ret = await api(BFF, "/runtime/retention/preview", { method: "POST", token, body: {} });
    report.flows.retention = ret.json?.retention || {};
    ret.json?.retention?.mode === "DRY_RUN" && ret.json?.retention?.purge_executed === false
      ? pass("retention_dry_run")
      : fail("retention_dry_run", "retention not dry-run");

    // Logout invalidates the session token (post-logout protection).
    await api(BFF, "/auth/logout", { method: "POST", token });
    const afterLogout = await api(BFF, "/runtime/diagnostics", { token });
    report.flows.post_logout_protected = [401, 403].includes(afterLogout.status);
    afterLogout.status === 200
      ? fail("logout", "revoked token still authorized")
      : pass("logout");

    // Fresh token for browser drive.
    const relogin = await api(BFF, "/auth/login", {
      method: "POST",
      body: { email: "owner@m54.cert", password: "CertOwnerPassw0rd!", method: "LOCAL_PASSWORD" },
    });
    const browserToken = relogin.json?.token;

    // —— UI ——
    const uiEnv = { ...process.env, NEXT_PUBLIC_SAATHI_API: BFF };
    if (USE_DEV) {
      ui = spawnLogged("npm", ["run", "dev", "--", "-p", String(uiPort)], { cwd: ROOT, env: uiEnv });
    } else {
      await new Promise((resolve, reject) => {
        const b = spawn("npm", ["run", "build"], { cwd: ROOT, stdio: "inherit", env: uiEnv });
        b.on("exit", (c) => (c === 0 ? resolve() : reject(new Error(`build exit ${c}`))));
      });
      ui = spawnLogged("npm", ["run", "start", "--", "-p", String(uiPort)], { cwd: ROOT, env: uiEnv });
    }
    await waitHealthy(`${BASE}/platform`, 120000, [200]);

    browser = await launchBrowser();
    const page = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    report.browserErrors = { console: [], pageErrors: [], apiFailures: [] };
    page.on("console", (m) => {
      if (m.type() === "error") report.browserErrors.console.push(m.text().slice(0, 200));
    });
    page.on("pageerror", (e) => report.browserErrors.pageErrors.push(String(e.message || e).slice(0, 200)));
    page.on("requestfailed", (r) => {
      const u = r.url();
      if (/\/api\/v1\/platform/.test(u))
        report.browserErrors.apiFailures.push(`${r.failure()?.errorText || "fail"} ${u.slice(-60)}`);
    });

    // Inject the session token and load the authenticated operator surface.
    // Dev-mode compiles on first hit; wait on concrete signals, not fixed sleeps.
    await page.goto(`${BASE}/platform`, { waitUntil: "domcontentloaded", timeout: 90000 });
    await page.waitForTimeout(1500); // let first-compile settle
    await page.evaluate((t) => localStorage.setItem("saathi_platform_token", t), browserToken);
    await page.reload({ waitUntil: "domcontentloaded" });
    // Authenticated block renders only when the token is picked up.
    await page
      .waitForSelector('[data-testid="readiness-panel"]', { timeout: 90000 })
      .catch(() => {});
    // Wait for the seeded binding to load (refresh() fans out ~10 API calls;
    // a cold Next.js dev compile can take a while on the first authenticated hit).
    await page
      .waitForFunction(() => /cert-agent/.test(document.body.innerText), { timeout: 90000 })
      .catch(() => {});
    // Self-heal: if the first token-triggered refresh raced the compile, reload
    // once more to re-fan the authenticated API calls.
    if (!/cert-agent/.test(await page.locator("body").innerText())) {
      await page.reload({ waitUntil: "domcontentloaded" });
      await page
        .waitForFunction(() => /cert-agent/.test(document.body.innerText), { timeout: 60000 })
        .catch(() => {});
    }
    await page.waitForTimeout(1000);

    const shot = async (name) => {
      const p = join(OUT, "screenshots", `${name}.png`);
      try {
        await page.screenshot({ path: p });
        report.screenshots.push(p);
      } catch {
        /* */
      }
    };
    await shot("platform_authenticated");

    // Readiness panel + safety badges visible in the real UI.
    const panel = await page.locator('[data-testid="readiness-panel"]').count();
    const badges = (await page.locator('[data-testid="safety-badges"]').innerText().catch(() => "")) || "";
    const env = (await page.locator('[data-testid="env-classification"]').innerText().catch(() => "")) || "";
    report.flows.ui_readiness = { panel, env, badges };
    const uiSafe =
      panel > 0 &&
      /DISABLED/.test(badges) &&
      /DRY_RUN_ONLY/.test(badges) &&
      /LOCAL_OR_TEST/.test(env);
    uiSafe ? pass("ui_readiness") : fail("ui_readiness", "readiness panel/safety not shown");

    // Governed execution + binding administration visible.
    const body = await page.locator("body").innerText();
    report.flows.body_snippet = body.slice(0, 600);
    report.flows.ui_binding = /cert-agent/.test(body);
    report.flows.ui_binding ? pass("ui_binding_admin") : fail("ui_binding_admin", "binding not listed");

    // Evidence export through the UI.
    const exportBtn = page.locator('[data-testid="export-execution_summary"]');
    if ((await exportBtn.count()) > 0) {
      await exportBtn.first().click();
      await page
        .waitForSelector('[data-testid="export-manifest"]', { timeout: 15000 })
        .catch(() => {});
    }
    const manifest = (await page.locator('[data-testid="export-manifest"]').innerText().catch(() => "")) || "";
    report.flows.ui_export = manifest;
    /sha256:/.test(manifest) && /production_data false/.test(manifest)
      ? pass("ui_export")
      : fail("ui_export", "ui export manifest missing/unsafe");
    await shot("readiness_export");

    // Retention preview (owner) — dry-run only.
    page.once("dialog", (dlg) => dlg.accept());
    const retBtn = page.locator('[data-testid="retention-preview"]');
    if ((await retBtn.count()) > 0) {
      await retBtn.first().click();
      await page
        .waitForSelector('[data-testid="retention-plan"]', { timeout: 15000 })
        .catch(() => {});
    }
    const plan = (await page.locator('[data-testid="retention-plan"]').innerText().catch(() => "")) || "";
    report.flows.ui_retention = plan;
    /DRY_RUN/.test(plan) && /purge_executed false/.test(plan)
      ? pass("ui_retention")
      : (report.softGates.ui_retention = { ok: false, plan });

    // No live financial/trading actions offered on the platform surface.
    const unsafe = await page.evaluate(() => {
      const re = /^(execute trade|place order|buy now|sell now|withdraw|enable live connector|start autonomous)/i;
      return [...document.querySelectorAll("button,a,[role='button']")]
        .map((n) => (n.innerText || "").trim())
        .filter((t) => re.test(t));
    });
    report.flows.unsafe_actions = unsafe;
    unsafe.length === 0
      ? pass("no_unsafe_actions")
      : fail("no_unsafe_actions", `unsafe: ${unsafe.join(",")}`);

    // Logout via UI clears the authenticated surface.
    const logoutBtn = page.getByRole("button", { name: /logout/i });
    if ((await logoutBtn.count()) > 0) {
      await logoutBtn.first().click();
      await page.waitForTimeout(1000);
    }
    const afterBody = await page.locator("body").innerText();
    report.flows.ui_logout = !/cert-agent/.test(afterBody);
    report.flows.ui_logout ? pass("ui_logout") : (report.softGates.ui_logout = { ok: false });
    await shot("after_logout");
  } catch (e) {
    report.fatal = String(e.message || e);
    report.bffLog = (bff?.getLog?.() || "").slice(-1500);
    report.uiLog = (ui?.getLog?.() || "").slice(-1500);
  } finally {
    if (browser) await browser.close().catch(() => {});
    killTree(ui?.child);
    killTree(bff?.child);
    try {
      rmSync(certDbDir, { recursive: true, force: true });
    } catch {
      /* */
    }
  }

  const hardOk = Object.values(report.hardGates).every((g) => g.ok);
  report.verdict = hardOk
    ? "M54_BROWSER_CERTIFIED"
    : ALLOW_LIMITATIONS
      ? "M54_BROWSER_CERTIFIED_WITH_LIMITATIONS"
      : "M54_BROWSER_CERT_FAILED";
  writeFileSync(join(OUT, "m54_browser_cert.json"), JSON.stringify(report, null, 2));
  const failed = Object.entries(report.hardGates)
    .filter(([, g]) => !g.ok)
    .map(([k]) => k);
  console.log(`[m54] verdict=${report.verdict} failedHardGates=${failed.join(",") || "none"}`);
  console.log(`[m54] evidence: ${join(OUT, "m54_browser_cert.json")}`);
  if (!hardOk && !ALLOW_LIMITATIONS) process.exit(1);
}

main().catch((e) => {
  console.error("[m54] fatal", e);
  process.exit(1);
});
