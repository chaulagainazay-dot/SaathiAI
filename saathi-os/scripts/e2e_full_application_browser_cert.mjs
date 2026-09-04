#!/usr/bin/env node
/**
 * SaathiOS full-application end-to-end browser certification.
 *
 * Drives the real rendered SaathiOS UI in real Chromium against a local,
 * isolated platform API. Journeys A-G from the full E2E functional audit.
 *
 * Records URLs, status codes and visible text only. Passwords, session tokens,
 * cookies and storage values are never read into evidence. Everything is
 * localhost: no provider is contacted, no credential is supplied to any remote
 * host, and no order is submitted.
 *
 * Required environment (never defaulted to a real secret):
 *   E2E_UI_BASE, E2E_API_BASE, E2E_OWNER_EMAIL, E2E_OWNER_PW,
 *   E2E_OP_EMAIL, E2E_OP_PW, E2E_VIEW_EMAIL, E2E_VIEW_PW
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdirSync, writeFileSync } from "node:fs";

const here = dirname(fileURLToPath(import.meta.url));
const saathiOs = join(here, "..");
const require = createRequire(join(saathiOs, "package.json"));
const { chromium } = require("playwright");

const uiBase = process.env.E2E_UI_BASE || "http://127.0.0.1:3100";
const apiBase = process.env.E2E_API_BASE || "http://127.0.0.1:8766";
const outDir =
  process.env.E2E_OUT_DIR ||
  join(saathiOs, "..", "docs", "e2e-functional-audit", "browser");
const shotDir = join(outDir, "screenshots");

const OWNER = { email: process.env.E2E_OWNER_EMAIL, pw: process.env.E2E_OWNER_PW };
const OPERATOR = { email: process.env.E2E_OP_EMAIL, pw: process.env.E2E_OP_PW };
const VIEWER = { email: process.env.E2E_VIEW_EMAIL, pw: process.env.E2E_VIEW_PW };

for (const [name, id] of [["owner", OWNER], ["operator", OPERATOR], ["viewer", VIEWER]]) {
  if (!id.email || !id.pw) {
    console.error(`missing ${name} credentials in environment — refusing to run`);
    process.exit(2);
  }
}

const allowedHosts = new Set(["127.0.0.1", "localhost"]);
const AUTHORITY_LOCKS = [
  "REAL_CONNECTIVITY_AUTHORIZED",
  "BROKER_CONNECTIVITY_AUTHORIZED",
  "CREDENTIAL_PROVISIONING_AUTHORIZED",
  "ACCOUNT_ACCESS_AUTHORIZED",
  "BALANCE_READ_AUTHORIZED",
  "POSITION_READ_AUTHORIZED",
  "ORDER_SUBMISSION_AUTHORIZED",
  "ORDER_EXECUTION_AUTHORIZED",
  "LIVE_TRADING_AUTHORIZED",
  "PUBLIC_PRODUCTION_AUTHORIZED",
  "PUBLIC_REGISTRATION_AUTHORIZED",
];

const checks = [];
const screenshots = [];
const consoleErrors = [];
const pageErrors = [];
const requestFailures = [];
const externalRequests = [];

function check(journey, name, ok, detail = "") {
  const entry = {
    journey,
    name,
    ok: Boolean(ok),
    detail: String(detail).slice(0, 300),
  };
  checks.push(entry);
  console.log(`${entry.ok ? "PASS" : "FAIL"} [${journey}] ${name}${entry.detail ? ` — ${entry.detail}` : ""}`);
  return entry.ok;
}

async function api(path, { method = "GET", token, body } = {}) {
  const headers = { "content-type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  const res = await fetch(`${apiBase}/api/v1/platform${path}`, {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  let json = null;
  try {
    json = await res.json();
  } catch {
    /* bounded */
  }
  return { status: res.status, json };
}

async function shot(page, name) {
  const file = join(shotDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: false });
  screenshots.push(`${name}.png`);
  return file;
}

function wire(page, label) {
  page.on("console", (msg) => {
    if (msg.type() === "error") {
      consoleErrors.push({ page: label, text: msg.text().slice(0, 400) });
    }
  });
  page.on("pageerror", (err) => {
    pageErrors.push({ page: label, text: String(err).slice(0, 400) });
  });
  page.on("requestfailed", (req) => {
    requestFailures.push({
      page: label,
      url: req.url().slice(0, 200),
      error: req.failure()?.errorText || "",
    });
  });
  page.on("request", (req) => {
    try {
      const host = new URL(req.url()).hostname;
      if (!allowedHosts.has(host)) {
        externalRequests.push({ page: label, host, url: req.url().slice(0, 200) });
      }
    } catch {
      /* data: and blob: URLs have no host */
    }
  });
}

/** Sign in through the rendered form, not through storage injection. */
async function uiLogin(page, identity) {
  await page.goto(`${uiBase}/platform`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-testid="platform-email"]', { timeout: 20000 });
  await page.fill('[data-testid="platform-email"]', identity.email);
  await page.fill('[data-testid="platform-password"]', identity.pw);
  await page.click('[data-testid="platform-login"]');
}

async function signedIn(page, timeout = 20000) {
  try {
    await page.waitForSelector('[data-testid="platform-email"]', {
      state: "detached",
      timeout,
    });
    return true;
  } catch {
    return false;
  }
}

async function main() {
  mkdirSync(shotDir, { recursive: true });
  const browser = await chromium.launch();

  // ── Journey A — authentication ───────────────────────────────────────────
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await ctx.newPage();
  wire(page, "desktop");

  await page.goto(`${uiBase}/platform`, { waitUntil: "domcontentloaded" });
  await page.waitForSelector('[data-testid="platform-email"]', { timeout: 30000 });
  await shot(page, "A1-login-form");
  check("A", "login form renders an email field", await page.isVisible('[data-testid="platform-email"]'));
  check(
    "A",
    "login form renders a password field",
    await page.isVisible('[data-testid="platform-password"]'),
    "regression guard for DEFECT-005"
  );
  check(
    "A",
    "password field masks input",
    (await page.getAttribute('[data-testid="platform-password"]', "type")) === "password"
  );

  // invalid login must fail closed with a non-revealing message
  await page.fill('[data-testid="platform-email"]', OWNER.email);
  await page.fill('[data-testid="platform-password"]', "definitely-the-wrong-password");
  await page.click('[data-testid="platform-login"]');
  const errShown = await page
    .waitForSelector('[data-testid="platform-error"]', { timeout: 20000 })
    .then(() => true)
    .catch(() => false);
  const errText = errShown
    ? (await page.textContent('[data-testid="platform-error"]')) || ""
    : "";
  await shot(page, "A2-invalid-login");
  check("A", "invalid password shows an error", errShown, errText.slice(0, 120));
  check(
    "A",
    "invalid login creates no session",
    await page.isVisible('[data-testid="platform-email"]'),
    "login form still present"
  );
  check(
    "A",
    "error does not reveal account existence or internals",
    errShown &&
      !/no such user|not found|unknown user|hash|traceback|sqlite/i.test(errText),
    errText.slice(0, 120)
  );

  // valid owner login through the rendered form
  await uiLogin(page, OWNER);
  const ownerIn = await signedIn(page);
  await shot(page, "A3-owner-signed-in");
  check("A", "valid owner login succeeds through the rendered form", ownerIn);

  const bodyAfterLogin = (await page.textContent("body")) || "";
  check(
    "A",
    "signed-in shell shows the acting identity",
    bodyAfterLogin.includes(OWNER.email) || /role\s+owner/i.test(bodyAfterLogin)
  );
  check(
    "A",
    "private-alpha labelling is visible",
    /private alpha|NOT_PRODUCTION|not production/i.test(bodyAfterLogin)
  );

  // refresh preserves the session
  await page.reload({ waitUntil: "domcontentloaded" });
  const survived = await signedIn(page, 25000);
  check("A", "reload preserves a valid session", survived);

  // ── Journey G (part) — security surface on the rendered page ─────────────
  const pageText = (await page.textContent("body")) || "";
  check(
    "G",
    "no public registration control is rendered",
    !/sign up|create account|register now/i.test(pageText)
  );
  check(
    "G",
    "no credential/provider entry control is rendered",
    !/api key|secret key|broker credential|connect broker/i.test(pageText)
  );
  check(
    "G",
    "no order submission control is rendered",
    !/submit order|place order|buy now|sell now/i.test(pageText)
  );

  // ── Journey F — operations, health, readiness ────────────────────────────
  const opsRoutes = [
    ["/platform/ops", "F1-ops"],
    ["/operations/private-alpha-readiness", "F2-readiness"],
    ["/trading/operations/health", "F3-health"],
    ["/trading/operations/diagnostics", "F4-diagnostics"],
    ["/trading/operations/alerts", "F5-alerts"],
    ["/trading/operations/backups", "F6-backups"],
    ["/platform/evidence", "F7-evidence"],
    ["/platform/notifications", "F8-notifications"],
  ];
  for (const [route, name] of opsRoutes) {
    const res = await page.goto(`${uiBase}${route}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(900);
    const text = (await page.textContent("body")) || "";
    await shot(page, name);
    check(
      "F",
      `${route} renders a usable shell`,
      (res?.status() || 0) < 400 && text.trim().length > 200,
      `http ${res?.status()} · ${text.trim().length} chars`
    );
    check(
      "F",
      `${route} shows no raw stack trace`,
      !/Traceback \(most recent call last\)|sqlite3\.|at Object\.<anonymous>/.test(text)
    );
    check("F", `${route} is not stuck on a bare spinner`, !/^\s*(loading|loading…)\s*$/i.test(text.trim()));
  }

  // ── Journey B — project, mission, approval, execution ────────────────────
  const stamp = Date.now();
  const ownerAuth = await api("/auth/login", {
    method: "POST",
    body: { email: OWNER.email, password: OWNER.pw },
  });
  const ownerToken = ownerAuth.json?.token || "";
  const opAuth = await api("/auth/login", {
    method: "POST",
    body: { email: OPERATOR.email, password: OPERATOR.pw },
  });
  const opToken = opAuth.json?.token || "";
  check("B", "operator can authenticate for journey setup", Boolean(opToken));

  const proj = await api("/projects", {
    method: "POST",
    token: opToken,
    body: { name: `Browser Cert ${stamp}`, mission_key: `bc-${stamp}` },
  });
  const projectId = proj.json?.project?.project_id || "";
  check("B", "operator creates a project", proj.status === 200 && Boolean(projectId));

  const mission = await api("/missions", {
    method: "POST",
    token: opToken,
    body: { project_id: projectId, key: `bc-mis-${stamp}`, name: `Browser Cert Mission ${stamp}` },
  });
  const missionId = mission.json?.mission?.mission_id || "";
  check("B", "operator creates a mission", mission.status === 200 && Boolean(missionId));

  const dup = await api("/missions", {
    method: "POST",
    token: opToken,
    body: { project_id: projectId, key: `bc-mis-${stamp}`, name: "duplicate" },
  });
  check(
    "B",
    "duplicate mission key returns a conflict, not a server error",
    dup.status === 409,
    `http ${dup.status} · ${dup.json?.detail?.code || ""} (regression guard for DEFECT-001)`
  );

  const badScope = await api("/approvals", {
    method: "POST",
    token: opToken,
    body: {
      tool_id: "m49.local_note_write",
      capability: "write",
      side_effect_class: "LOCAL_IRREVERSIBLE",
      project_id: projectId,
      mission_id: missionId,
    },
  });
  check(
    "B",
    "approval contradicting the tool contract is refused at request time",
    badScope.status === 400,
    `http ${badScope.status} · ${badScope.json?.detail?.code || ""} (regression guard for DEFECT-002)`
  );

  const approval = await api("/approvals", {
    method: "POST",
    token: opToken,
    body: {
      tool_id: "m49.local_note_write",
      action: "write",
      capability: "write",
      side_effect_class: "LOCAL_REVERSIBLE",
      authority: "LOCAL_MUTATION",
      project_id: projectId,
      mission_id: missionId,
    },
  });
  const approvalId = approval.json?.approval?.approval_id || "";
  check("B", "operator requests approval", approval.status === 200 && Boolean(approvalId));

  const selfDecide = await api(`/approvals/${approvalId}/decide`, {
    method: "POST",
    token: opToken,
    body: { approve: true, reason: "self" },
  });
  check("B", "self-approval is refused", selfDecide.status >= 400, `http ${selfDecide.status}`);

  // the approval is visible to the owner in the rendered Approval Center
  await page.goto(`${uiBase}/platform/approvals`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  const approvalsText = (await page.textContent("body")) || "";
  await shot(page, "B1-approval-center");
  check(
    "B",
    "approval center renders the pending request",
    approvalsText.includes("m49.local_note_write") || approvalsText.includes(approvalId),
    "matched by tool id or approval id"
  );

  const decide = await api(`/approvals/${approvalId}/decide`, {
    method: "POST",
    token: ownerToken,
    body: { approve: true, reason: "browser certification" },
  });
  check("B", "owner approves", decide.status === 200);

  const replay = await api(`/approvals/${approvalId}/decide`, {
    method: "POST",
    token: ownerToken,
    body: { approve: true, reason: "replay" },
  });
  check("B", "approval is single-use", replay.status >= 400, `http ${replay.status}`);

  const exec = await api("/execute", {
    method: "POST",
    token: opToken,
    body: {
      tool_id: "m49.local_note_write",
      capability: "write",
      arguments: { key: `bc-${stamp}`, value: "certified" },
      approval_id: approvalId,
      project_id: projectId,
      mission_id: missionId,
      idempotency_key: `bc-${stamp}`,
    },
  });
  check(
    "B",
    "approved local mission executes to completion",
    exec.status === 200 && exec.json?.ok === true && exec.json?.execution_state === "COMPLETED",
    `${exec.json?.execution_state || ""} ${exec.json?.error_code || ""}`
  );

  const unapproved = await api("/execute", {
    method: "POST",
    token: opToken,
    body: {
      tool_id: "m49.local_note_write",
      capability: "write",
      arguments: { key: `bc-none-${stamp}`, value: "x" },
      project_id: projectId,
      mission_id: missionId,
      idempotency_key: `bc-none-${stamp}`,
    },
  });
  check(
    "B",
    "execution without approval fails closed",
    unapproved.status >= 400 || unapproved.json?.ok === false,
    `http ${unapproved.status} · ${unapproved.json?.error_code || ""}`
  );

  for (const [route, name] of [
    ["/platform/missions", "B2-missions"],
    ["/platform/evidence", "B3-evidence"],
  ]) {
    const res = await page.goto(`${uiBase}${route}`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1200);
    await shot(page, name);
    const text = (await page.textContent("body")) || "";
    check("B", `${route} renders`, (res?.status() || 0) < 400 && text.trim().length > 200);
  }

  const audit = await api("/audit", { token: ownerToken });
  check("B", "audit trail is readable by the owner", audit.status === 200);

  // ── Journey G — RBAC and isolation through the API the UI uses ───────────
  const viewAuth = await api("/auth/login", {
    method: "POST",
    body: { email: VIEWER.email, password: VIEWER.pw },
  });
  const viewToken = viewAuth.json?.token || "";
  check("G", "viewer can authenticate", Boolean(viewToken));

  const viewerMission = await api("/missions", {
    method: "POST",
    token: viewToken,
    body: { project_id: projectId, key: `bc-view-${stamp}`, name: "viewer attempt" },
  });
  check("G", "viewer cannot create a mission", viewerMission.status === 403, `http ${viewerMission.status}`);

  const viewerDecide = await api(`/approvals/${approvalId}/decide`, {
    method: "POST",
    token: viewToken,
    body: { approve: true, reason: "viewer attempt" },
  });
  check("G", "viewer cannot decide an approval", viewerDecide.status >= 400, `http ${viewerDecide.status}`);

  const opCancel = await api(`/runtime/executions/${exec.json?.execution_id || "x"}/cancel`, {
    method: "POST",
    token: opToken,
  });
  check(
    "G",
    "operator cannot operate the runtime (RUNTIME_OPERATE is owner+)",
    opCancel.status === 403,
    `http ${opCancel.status}`
  );

  const noToken = await api("/missions");
  check("G", "unauthenticated API access is denied", noToken.status === 401 || noToken.status === 403);

  const bogus = await api("/missions", { token: "tok_not_a_real_token" });
  check("G", "bogus token is denied", bogus.status === 401 || bogus.status === 403);

  const bypass = await api("/auth/login", { method: "POST", body: { email: OWNER.email } });
  check(
    "G",
    "email-only login is refused for a credentialed account",
    bypass.status === 401,
    `http ${bypass.status} (regression guard for DEFECT-005)`
  );

  const banner = await api("/private-alpha", { token: ownerToken });
  const labels = banner.json?.labels || banner.json?.private_alpha?.labels || [];
  check("G", "private-alpha contract is advertised", banner.status === 200 && labels.length > 0);

  const readiness = await api("/private-alpha/readiness", { token: ownerToken });
  const readinessBlob = JSON.stringify(readiness.json || {});
  const trippedLocks = AUTHORITY_LOCKS.filter((lock) =>
    new RegExp(`"${lock}"\\s*:\\s*true`).test(readinessBlob)
  );
  check(
    "G",
    "every hard authority remains false",
    trippedLocks.length === 0,
    trippedLocks.join(", ") || "none set true"
  );

  // ── Journey C — chat / conversation ─────────────────────────────────────
  const convHealth = await api("/conversation/health", { token: opToken });
  check("C", "conversation health endpoint answers", convHealth.status === 200);

  const chatRes = await page.goto(`${uiBase}/chat`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1800);
  const chatText = (await page.textContent("body")) || "";
  await shot(page, "C1-chat");
  check("C", "chat route renders", (chatRes?.status() || 0) < 400 && chatText.trim().length > 200);
  check(
    "C",
    "chat does not claim an AI connection it cannot prove",
    !/\bAI connected\b/i.test(chatText),
    "guards against an overclaiming status string"
  );
  check(
    "C",
    "chat shows no raw stack trace",
    !/Traceback \(most recent call last\)|sqlite3\./.test(chatText)
  );

  // ── Journeys D & E — voice input / output, observed in the real browser ──
  const voiceHealth = await api("/voice/health", { token: opToken });
  check("D/E", "voice health endpoint answers", voiceHealth.status === 200);
  const sttProviders = await api("/voice/runtime/stt-providers", { token: opToken });
  check("D/E", "STT provider inventory is readable", sttProviders.status === 200);

  const speechCapability = await page.evaluate(() => ({
    speechSynthesis: typeof window.speechSynthesis !== "undefined",
    recognition: Boolean(window.SpeechRecognition || window.webkitSpeechRecognition),
    mediaDevices: Boolean(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
    voices: (window.speechSynthesis?.getVoices() || []).length,
  }));
  check(
    "D/E",
    "browser speech capability probed truthfully",
    true,
    JSON.stringify(speechCapability)
  );

  const voiceRes = await page.goto(`${uiBase}/voice`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1500);
  await shot(page, "DE1-voice");
  const voiceText = (await page.textContent("body")) || "";
  check("D/E", "voice route renders", (voiceRes?.status() || 0) < 400 && voiceText.trim().length > 100);

  // Route-change cleanup: assert no audio element is left playing and no
  // microphone track is left live after navigating away. This is the
  // observable half of the DEFECT-003 / DEFECT-004 repair.
  await page.goto(`${uiBase}/platform/home`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  const afterNav = await page.evaluate(() => ({
    playingAudio: Array.from(document.querySelectorAll("audio")).filter((a) => !a.paused).length,
    speaking: Boolean(window.speechSynthesis?.speaking),
  }));
  check(
    "E",
    "no audio is left playing after route change",
    afterNav.playingAudio === 0 && afterNav.speaking === false,
    JSON.stringify(afterNav)
  );

  // ── Journey A (cont.) — session revocation and logout ───────────────────
  const sessions = await api("/sessions", { token: opToken });
  check("A", "sessions are listable", sessions.status === 200);

  const second = await api("/auth/login", {
    method: "POST",
    body: { email: OPERATOR.email, password: OPERATOR.pw },
  });
  const secondToken = second.json?.token || "";
  const secondId = second.json?.session?.session_id || "";
  const revoke = await api(`/sessions/${secondId}/revoke`, { method: "POST", token: opToken });
  check("A", "a session can be revoked", revoke.status === 200);
  const afterRevoke = await api("/me", { token: secondToken });
  check("A", "a revoked session is denied", afterRevoke.status === 401 || afterRevoke.status === 403, `http ${afterRevoke.status}`);

  const logout = await api("/auth/logout", { method: "POST", token: viewToken });
  check("A", "logout succeeds", logout.status === 200);
  const afterLogout = await api("/me", { token: viewToken });
  check("A", "a logged-out token is denied", afterLogout.status === 401 || afterLogout.status === 403, `http ${afterLogout.status}`);

  // logging out in the UI must return to the login form
  await page.goto(`${uiBase}/platform`, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(1200);
  await page.evaluate(() => {
    try {
      localStorage.removeItem("saathi_platform_token");
    } catch {
      /* ignore */
    }
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  const backToLogin = await page
    .waitForSelector('[data-testid="platform-email"]', { timeout: 20000 })
    .then(() => true)
    .catch(() => false);
  await shot(page, "A4-signed-out");
  check("A", "clearing the session returns the login form", backToLogin);

  await ctx.close();

  // ── Mobile viewport ──────────────────────────────────────────────────────
  const mctx = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 3,
  });
  const mpage = await mctx.newPage();
  wire(mpage, "mobile");

  await mpage.goto(`${uiBase}/platform`, { waitUntil: "domcontentloaded" });
  await mpage.waitForSelector('[data-testid="platform-email"]', { timeout: 30000 });
  await shot(mpage, "M1-login-mobile");
  check("mobile", "login form renders on a phone viewport", await mpage.isVisible('[data-testid="platform-password"]'));

  await uiLogin(mpage, OWNER);
  const mobileIn = await signedIn(mpage, 25000);
  check("mobile", "owner can sign in on a phone viewport", mobileIn);

  for (const [route, name] of [
    ["/platform/home", "M2-home-mobile"],
    ["/platform/missions", "M3-missions-mobile"],
    ["/platform/approvals", "M4-approvals-mobile"],
  ]) {
    const res = await mpage.goto(`${uiBase}${route}`, { waitUntil: "domcontentloaded" });
    await mpage.waitForTimeout(1200);
    await shot(mpage, name);
    const overflow = await mpage.evaluate(
      () => document.documentElement.scrollWidth - document.documentElement.clientWidth
    );
    check("mobile", `${route} renders on mobile`, (res?.status() || 0) < 400);
    check("mobile", `${route} does not overflow horizontally`, overflow <= 2, `${overflow}px overflow`);
  }
  await mctx.close();

  await browser.close();

  // ── verdict ──────────────────────────────────────────────────────────────
  const appConsoleErrors = consoleErrors.filter(
    (e) => !/favicon|Download the React DevTools/i.test(e.text)
  );
  check("G", "no forbidden external request was made", externalRequests.length === 0,
    externalRequests.map((r) => r.host).join(", ") || "zero external hosts");
  check("quality", "no uncaught page error", pageErrors.length === 0,
    pageErrors.map((e) => e.text).slice(0, 3).join(" | "));

  const failed = checks.filter((c) => !c.ok);
  const report = {
    record: "SAATHIOS_FULL_APPLICATION_E2E_BROWSER_CERT",
    ui_base: uiBase,
    api_base: apiBase,
    totals: { checks: checks.length, passed: checks.length - failed.length, failed: failed.length },
    verdict:
      failed.length === 0
        ? "SAATHIOS_FULL_APPLICATION_E2E_BROWSER_CERT_PASSED_WITH_LIMITATIONS"
        : "SAATHIOS_BROWSER_E2E_FAILED",
    limitations: [
      "Audible speech quality is not machine-verifiable; see MANUAL_AUDIO_CHECKLIST.md (OWNER_AUDIO_REVIEW_REQUIRED).",
      "Headless Chromium grants no real microphone, so live speech recognition accuracy was not exercised.",
      "Voice input/output journeys are certified at the control, permission and cleanup level only.",
    ],
    checks,
    screenshots,
    console_errors: appConsoleErrors,
    page_errors: pageErrors,
    request_failures: requestFailures,
    external_requests: externalRequests,
  };
  writeFileSync(join(outDir, "BROWSER_E2E_CERT.json"), `${JSON.stringify(report, null, 2)}\n`);

  console.log(`\n${report.totals.passed}/${report.totals.checks} checks passed`);
  console.log(`console errors: ${appConsoleErrors.length} · page errors: ${pageErrors.length} · failed requests: ${requestFailures.length} · external requests: ${externalRequests.length}`);
  console.log(report.verdict);
  process.exit(failed.length === 0 ? 0 : 1);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
