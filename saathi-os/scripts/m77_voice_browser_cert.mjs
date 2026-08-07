#!/usr/bin/env node
/**
 * M77 Voice Output Foundation browser certificate.
 *
 * Starts checkout-local production services on fixed loopback ports. All auth
 * material and generated audio remain in memory or an OS temporary directory.
 * Evidence contains only booleans, counts, timing, and synthetic screenshots.
 */
import { execFileSync, spawn } from "node:child_process";
import { createHash } from "node:crypto";
import { createServer } from "node:http";
import {
  existsSync,
  mkdirSync,
  mkdtempSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "playwright";

const HERE = dirname(fileURLToPath(import.meta.url));
const UI_ROOT = join(HERE, "..");
const REPO = join(UI_ROOT, "..");
const OUT =
  process.env.M77_EVIDENCE_DIR ||
  join(REPO, "docs", "evidence", "m77", "browser");
const SCREENSHOTS = join(OUT, "screenshots");
const M64_OUT = join(OUT, "m64-regression");
const UI = "http://127.0.0.1:3000";
const API = "http://127.0.0.1:8765";
const PY = existsSync(join(REPO, ".venv", "bin", "python"))
  ? join(REPO, ".venv", "bin", "python")
  : "python3";
const BUILD = process.env.M77_BUILD !== "0";
const certDir = mkdtempSync(join(tmpdir(), "saathi-m77-"));
const dbPath = join(certDir, "platform.db");
const artifactPath = join(certDir, "voice-artifacts");
const legacyAccess = `m77-local-cert-${process.pid}`;
const legacySession = createHash("sha256")
  .update(`${legacyAccess}:baadar-session`)
  .digest("hex");
const privateLearnerResponse = "PRIVATE_LEARNER_RESPONSE_M77";

mkdirSync(SCREENSHOTS, { recursive: true });
mkdirSync(M64_OUT, { recursive: true });

const report = {
  schema: "m77.voice_browser_cert.v1",
  capturedAt: new Date().toISOString(),
  mode: "production-build-loopback",
  hardGates: {},
  responsive: {},
  accessibility: {},
  security: {},
  regressions: {},
  browserErrors: { page: [], console: [], overlay: 0 },
  network: {
    chatFixtureRequests: 0,
    voiceRequests: 0,
    tokensInUrls: 0,
    privatePathsInResponses: 0,
    tokenInResponses: 0,
    privateLearnerTextInSpeech: 0,
  },
  screenshots: [],
  timings: {},
};

function gate(name, condition, detail = "", bucket = report.hardGates) {
  bucket[name] = { ok: Boolean(condition), detail: String(detail || "") };
  if (!condition) {
    throw new Error(`M77 gate failed: ${name}${detail ? ` — ${detail}` : ""}`);
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
  child.stdout.on("data", (chunk) => {
    log = `${log}${chunk}`.slice(-12000);
  });
  child.stderr.on("data", (chunk) => {
    log = `${log}${chunk}`.slice(-12000);
  });
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

async function api(path, { method = "GET", body, token, range } = {}) {
  const headers = { "content-type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  if (range) headers.Range = range;
  const response = await fetch(`${API}/api/v1/platform${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
  });
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("json")
    ? await response.json().catch(() => ({}))
    : await response.arrayBuffer();
  return {
    status: response.status,
    payload,
    headers: Object.fromEntries(response.headers.entries()),
  };
}

function observe(page) {
  page.on("pageerror", (error) => {
    report.browserErrors.page.push(String(error?.message || error).slice(0, 500));
  });
  page.on("console", (message) => {
    if (message.type() === "error") {
      report.browserErrors.console.push(message.text().slice(0, 500));
    }
  });
}

async function noOverlay(page) {
  const count = await page
    .locator(
      "[data-nextjs-dialog], .vite-error-overlay, #webpack-dev-server-client-overlay"
    )
    .count();
  report.browserErrors.overlay += count;
  return count === 0;
}

function chatFixtureHeaders() {
  return {
    "access-control-allow-origin": UI,
    "access-control-allow-credentials": "true",
    "content-type": "application/json",
  };
}

async function routeChatFixtures(page) {
  const longText = Array.from(
    { length: 65 },
    () => "This is a synthetic bounded cancellation sentence."
  ).join(" ");
  await page.route("**/api/v1/chat/conversations**", async (route) => {
    const url = new URL(route.request().url());
    if (url.pathname === "/api/v1/chat/conversations") {
      report.network.chatFixtureRequests += 1;
      await route.fulfill({
        status: 200,
        headers: chatFixtureHeaders(),
        body: JSON.stringify({
          conversations: [
            {
              id: "conv_voice_cert",
              title: "Voice certification",
              pinned: false,
              folder: "",
            },
          ],
        }),
      });
      return;
    }
    if (url.pathname === "/api/v1/chat/conversations/conv_voice_cert") {
      report.network.chatFixtureRequests += 1;
      await route.fulfill({
        status: 200,
        headers: chatFixtureHeaders(),
        body: JSON.stringify({
          conversation: {
            id: "conv_voice_cert",
            title: "Voice certification",
            tokens_in: 0,
            tokens_out: 0,
          },
          messages: [
            {
              id: "msg_short",
              role: "assistant",
              content: "Saathi local English voice certification.",
              status: "complete",
              model: "local-fixture",
            },
            {
              id: "msg_cancel",
              role: "assistant",
              content: longText,
              status: "complete",
              model: "local-fixture",
            },
          ],
          memory_links: [],
          executions: [],
          agent_runs: [],
          checkpoints: [],
        }),
      });
      return;
    }
    await route.continue();
  });
}

async function routeVoxFallback(page, token) {
  await page.route(
    "**/api/v1/platform/voice/speech",
    async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      report.network.voiceRequests += 1;
      const body = route.request().postDataJSON();
      if (String(body.text || "").includes(privateLearnerResponse)) {
        report.network.privateLearnerTextInSpeech += 1;
      }
      // Drop inherited Content-Length: rewritten body length differs from the
      // original "auto" provider field and a stale length can hang the POST.
      const headers = { ...route.request().headers() };
      delete headers["content-length"];
      delete headers["Content-Length"];
      headers["content-type"] = "application/json";
      const response = await route.fetch({
        postData: JSON.stringify({ ...body, provider: "voxcpm" }),
        headers,
      });
      const responseText = await response.text();
      if (/\/Users\/|\/private\/var\/|voice-artifacts\//.test(responseText)) {
        report.network.privatePathsInResponses += 1;
      }
      if (responseText.includes(token)) report.network.tokenInResponses += 1;
      if (new URL(route.request().url()).search.includes(token)) {
        report.network.tokensInUrls += 1;
      }
      await route.fulfill({ response, body: responseText });
    }
  );
}

async function authContext(browser, token, viewport, reducedMotion = "no-preference") {
  const context = await browser.newContext({ viewport, reducedMotion });
  await context.addInitScript(
    ({ platformToken, sessionToken }) => {
      localStorage.setItem("saathi_platform_token", platformToken);
      localStorage.setItem("saathi_session", sessionToken);
    },
    { platformToken: token, sessionToken: legacySession }
  );
  return context;
}

async function screenshot(page, name) {
  await page.screenshot({ path: join(SCREENSHOTS, name), fullPage: true });
  report.screenshots.push(`screenshots/${name}`);
}

async function certifyAgentBrowser() {
  const session = `m77-${process.pid}`;
  const run = (args) =>
    execFileSync("agent-browser", ["--session", session, ...args], {
      encoding: "utf8",
      timeout: 30000,
      env: { ...process.env, NO_PROXY: "127.0.0.1,localhost" },
    });
  try {
    run(["open", `${UI}/unlock`]);
    run(["wait", "1000"]);
    const content = run([
      "eval",
      'document.body.innerText.trim().length > 0 ? "HAS_CONTENT" : "BLANK"',
    ]);
    const overlay = run([
      "eval",
      'document.querySelector("[data-nextjs-dialog], .vite-error-overlay, #webpack-dev-server-client-overlay") ? "ERROR_OVERLAY" : "OK"',
    ]);
    const snapshot = run(["snapshot", "-i"]);
    run([
      "screenshot",
      join(SCREENSHOTS, "m77_agent_browser_unlock.png"),
      "--annotate",
    ]);
    report.screenshots.push("screenshots/m77_agent_browser_unlock.png");
    gate("agent_browser_page_content", content.includes("HAS_CONTENT"));
    gate("agent_browser_no_overlay", overlay.includes("OK"));
    gate("agent_browser_interactive_snapshot", snapshot.trim().length > 30);
  } finally {
    try {
      run(["close"]);
    } catch {
      // Isolated browser cleanup is best effort.
    }
  }
}

async function certifyM64Regression() {
  execFileSync("node", ["scripts/m64_browser_cert.mjs"], {
    cwd: UI_ROOT,
    stdio: "pipe",
    timeout: 180000,
    env: {
      ...process.env,
      M64_EVIDENCE_DIR: M64_OUT,
      NO_PROXY: "127.0.0.1,localhost",
    },
  });
  const result = JSON.parse(
    readFileSync(join(M64_OUT, "M64_BROWSER_CERT.json"), "utf8")
  );
  gate("m64_shell_browser_regression", result.verdict === "PASS", "", report.regressions);
  report.regressions.m64HardGates = Object.keys(result.hardGates || {}).length;
  report.regressions.m64StateGates = Object.keys(result.stateGates || {}).length;
  report.regressions.m64ResponsiveGates = Object.keys(result.responsive || {}).length;
}

async function certifyVoiceJourney(browser, token) {
  const context = await authContext(browser, token, {
    width: 1440,
    height: 1000,
  });
  const page = await context.newPage();
  observe(page);
  await routeChatFixtures(page);
  await routeVoxFallback(page, token);

  const response = await page.goto(`${UI}/chat`, {
    waitUntil: "domcontentloaded",
  });
  gate("chat_http_200", response?.status() === 200);
  await page
    .locator('[data-chat-mode="full"] aside')
    .first()
    .getByText("Voice certification", { exact: false })
    .click();
  const speakButtons = page.getByRole("button", {
    name: "Speak assistant response",
  });
  await speakButtons.first().waitFor();
  gate("chat_fixtures_isolated", report.network.chatFixtureRequests >= 2);
  gate("assistant_speak_actions", (await speakButtons.count()) === 2);
  await speakButtons.first().focus();
  const focusVisible = await page.evaluate(() => {
    const style = getComputedStyle(document.activeElement);
    return (
      (style.outlineStyle !== "none" && style.outlineWidth !== "0px") ||
      style.boxShadow !== "none"
    );
  });
  gate("assistant_speak_visible_focus", focusVisible, "", report.accessibility);

  await speakButtons.first().click();
  try {
    await page
      .locator('.voice-output-dock[data-voice-state="completed"]')
      .waitFor({ timeout: 45000 });
  } catch (error) {
    const dockState = await page
      .locator(".voice-output-dock")
      .evaluate((el) => ({
        state: el.getAttribute("data-voice-state"),
        text: el.innerText.slice(0, 400),
      }))
      .catch(() => null);
    let apiOps = null;
    try {
      apiOps = await api("/voice/speech", { token });
    } catch (e) {
      apiOps = { error: String(e) };
    }
    let health = null;
    try {
      health = await api("/voice/health", { token });
    } catch (e) {
      health = { error: String(e) };
    }
    report.timings.completedWaitDiagnostics = {
      dock: dockState,
      apiOps: apiOps?.payload || apiOps,
      health: health?.payload || health,
    };
    throw error;
  }
  gate(
    "no_autoplay_after_synthesis",
    await page
      .getByRole("button", { name: "Play synthesized speech" })
      .isVisible()
  );
  gate(
    "fallback_label_visible",
    await page.getByText(/fallback used/i).isVisible()
  );
  gate(
    "macos_provider_visible",
    await page.getByText(/Provider: macOS system voice/i).isVisible()
  );
  const firstOperation = await api("/voice/speech", { token });
  const completedOperation = firstOperation.payload.operations[0];
  gate(
    "actual_fallback_operation",
    completedOperation.state === "completed" &&
      completedOperation.provider === "macos_system" &&
      completedOperation.fallback_used === true
  );
  const audioRange = await api(
    `/voice/speech/${completedOperation.operation_id}/audio`,
    { token, range: "bytes=0-3" }
  );
  gate(
    "authenticated_audio_range",
    audioRange.status === 206 &&
      audioRange.payload.byteLength === 4 &&
      /private, no-store/.test(audioRange.headers["cache-control"] || "")
  );

  await page.getByRole("button", { name: "Play synthesized speech" }).click();
  await page
    .locator('.voice-output-dock[data-voice-state="playing"]')
    .waitFor({ timeout: 5000 });
  gate("local_audio_playing", true);
  await page.getByRole("button", { name: "Stop speaking" }).click();
  await page
    .locator('.voice-output-dock[data-voice-state="cancelled"]')
    .waitFor();
  gate("playback_stop_control", true);

  await speakButtons.nth(1).click();
  await page
    .locator('.voice-output-dock[data-voice-state="synthesizing"]')
    .waitFor({ timeout: 10000 });
  const cancelStarted = Date.now();
  await page.getByRole("button", { name: "Stop speaking" }).click();
  await page
    .locator('.voice-output-dock[data-voice-state="cancelled"]')
    .waitFor({ timeout: 3000 });
  report.timings.browserCancelAcknowledgedMs = Date.now() - cancelStarted;
  gate(
    "browser_cancel_acknowledged",
    report.timings.browserCancelAcknowledgedMs < 500,
    `${report.timings.browserCancelAcknowledgedMs}ms`
  );
  await screenshot(page, "m77_chat_voice_desktop.png");
  gate("desktop_no_overlay", await noOverlay(page));

  await page.goto(`${UI}/ielts/submissions`, {
    waitUntil: "domcontentloaded",
  });
  await page.getByRole("heading", {
    name: "Practice history and feedback",
  }).waitFor();
  const readAloud = page.getByRole("button", {
    name: "Read IELTS feedback aloud",
  });
  gate("ielts_read_aloud_visible", (await readAloud.count()) === 1);
  await readAloud.click();
  await page
    .locator('.voice-output-dock[data-voice-state="completed"]')
    .waitFor({ timeout: 30000 });
  gate(
    "ielts_yeti_request",
    report.network.voiceRequests >= 3 &&
      report.network.privateLearnerTextInSpeech === 0
  );
  await page.getByRole("button", { name: "Play synthesized speech" }).click();
  await page
    .locator('.voice-output-dock[data-voice-state="playing"]')
    .waitFor({ timeout: 5000 });
  await page.getByRole("button", { name: "Stop speaking" }).click();
  gate("ielts_audio_play_stop", true);

  await readAloud.click();
  await page
    .locator('.voice-output-dock[data-voice-state="completed"]')
    .waitFor({ timeout: 30000 });
  await page.evaluate((value) => {
    window.dispatchEvent(
      new CustomEvent("saathi:platform-context", {
        detail: {
          token: value,
          orgId: "context-invalidation",
          workspaceId: "context-invalidation",
        },
      })
    );
  }, token);
  await page
    .locator('.voice-output-dock[data-voice-state="idle"]')
    .waitFor({ timeout: 5000 });
  gate("context_invalidation_clears_audio", true);
  await screenshot(page, "m77_ielts_read_aloud_desktop.png");
  gate("ielts_no_overlay", await noOverlay(page));

  return { context, page };
}

async function certifyUnavailable(browser, token) {
  const context = await authContext(browser, token, {
    width: 1100,
    height: 800,
  });
  const page = await context.newPage();
  observe(page);
  await routeChatFixtures(page);
  const unavailable = {
    operation_id: "speech_unavailable_fixture",
    state: "unavailable",
    requested_provider: "unavailable",
    provider: "unavailable",
    streaming_state: "unavailable",
    fallback_used: false,
    error_category: "provider_unavailable",
    audio_available: false,
  };
  await page.route("**/api/v1/platform/voice/speech", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ operation: unavailable }),
    })
  );
  await page.route(
    "**/api/v1/platform/voice/speech/speech_unavailable_fixture",
    (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ operation: unavailable }),
      })
  );
  await page.goto(`${UI}/chat`, { waitUntil: "domcontentloaded" });
  await page
    .locator('[data-chat-mode="full"] aside')
    .first()
    .getByText("Voice certification", { exact: false })
    .click();
  await page
    .getByRole("button", { name: "Speak assistant response" })
    .first()
    .click();
  await page
    .locator('.voice-output-dock[data-voice-state="unavailable"]')
    .waitFor({ timeout: 5000 });
  gate("provider_unavailable_state", await page.getByText(/Speech is unavailable/i).isVisible());
  await screenshot(page, "m77_voice_unavailable.png");
  await context.close();
}

async function certifyResponsive(browser, token, name, viewport, reducedMotion) {
  const context = await authContext(browser, token, viewport, reducedMotion);
  const page = await context.newPage();
  observe(page);
  await page.goto(`${UI}/ielts/submissions`, {
    waitUntil: "domcontentloaded",
  });
  await page.getByRole("button", {
    name: "Read IELTS feedback aloud",
  }).waitFor();
  gate(
    `${name}_no_horizontal_overflow`,
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth <=
        document.documentElement.clientWidth + 2
    ),
    "",
    report.responsive
  );
  gate(
    `${name}_dock_visible`,
    await page.getByRole("region", { name: "Speech output controls" }).isVisible(),
    "",
    report.responsive
  );
  if (reducedMotion === "reduce") {
    gate(
      `${name}_reduced_motion`,
      await page.evaluate(() => {
        const element = document.querySelector(".voice-output-dock");
        return getComputedStyle(element).transitionDuration === "0s";
      }),
      "",
      report.accessibility
    );
  }
  await screenshot(page, `m77_ielts_${name}.png`);
  gate(`${name}_no_overlay`, await noOverlay(page), "", report.responsive);
  await context.close();
}

async function main() {
  let backend;
  let frontend;
  let browser;
  let voiceContext;
  let voicePage;
  try {
    gate("api_port_available", await freePort(8765));
    gate("ui_port_available", await freePort(3000));
    backend = spawnLogged(
      PY,
      [
        "-m",
        "uvicorn",
        "saathi.server:app",
        "--host",
        "127.0.0.1",
        "--port",
        "8765",
      ],
      {
        cwd: REPO,
        env: {
          ...process.env,
          SAATHI_PLATFORM_DB: dbPath,
          SAATHI_VOICE_ARTIFACT_DIR: artifactPath,
          SAATHI_VOXCPM_ENABLED: "false",
          SAATHI_CORS_ORIGINS: `${UI},http://localhost:3000`,
          SAATHI_TOKEN: legacyAccess,
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
        name: "M77 Owner",
        org_name: "M77 Org",
        workspace_name: "M77 Workspace",
      },
    });
    gate("local_bootstrap", boot.status === 200);
    const login = await api("/auth/login", {
      method: "POST",
      body: { email: "owner@local" },
    });
    const token = login.payload?.token;
    gate("authenticated_sign_in", login.status === 200 && Boolean(token));
    const practice = await api("/ielts/practice", {
      method: "POST",
      token,
      body: {
        skill: "writing",
        task_type: "m77_original_fixture",
        prompt: "Explain one benefit of a quiet local park.",
        response: `${privateLearnerResponse}. A quiet park supports rest and community wellbeing.`,
        duration_seconds: 0,
        idempotency_key: "m77-ielts-feedback",
      },
    });
    gate(
      "ielts_feedback_seeded",
      practice.status === 200 &&
        practice.payload?.practice?.body?.feedback?.official === false
    );

    if (BUILD) {
      execFileSync("npm", ["run", "build"], {
        cwd: UI_ROOT,
        stdio: "pipe",
        timeout: 180000,
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

    await certifyAgentBrowser();

    browser = await chromium.launch({
      headless: true,
      args: ["--autoplay-policy=user-gesture-required"],
    });
    // Run the dedicated voice journey before the broad M64 shell regression so
    // multi-page shell mounts cannot race native voice discovery under load.
    ({ context: voiceContext, page: voicePage } = await certifyVoiceJourney(
      browser,
      token
    ));
    await certifyUnavailable(browser, token);
    await certifyResponsive(
      browser,
      token,
      "tablet",
      { width: 834, height: 1112 },
      "no-preference"
    );
    await certifyResponsive(
      browser,
      token,
      "mobile",
      { width: 390, height: 844 },
      "reduce"
    );
    await certifyM64Regression();

    gate(
      "voice_urls_have_no_tokens",
      report.network.tokensInUrls === 0,
      "",
      report.security
    );
    gate(
      "voice_responses_have_no_private_paths",
      report.network.privatePathsInResponses === 0,
      "",
      report.security
    );
    gate(
      "voice_responses_have_no_tokens",
      report.network.tokenInResponses === 0,
      "",
      report.security
    );
    gate(
      "ielts_private_response_not_spoken",
      report.network.privateLearnerTextInSpeech === 0,
      "",
      report.security
    );
    gate(
      "no_framework_overlay",
      report.browserErrors.overlay === 0
    );
    gate("no_page_errors", report.browserErrors.page.length === 0);
    gate("no_console_errors", report.browserErrors.console.length === 0);

    await voicePage.goto(`${UI}/security`, {
      waitUntil: "domcontentloaded",
    });
    await voicePage.getByRole("button", { name: /Sign out$/ }).click();
    await voicePage.waitForURL(`${UI}/unlock`);
    gate(
      "logout_clears_voice_client",
      (await voicePage.locator(".voice-output-dock").count()) === 0
    );
    const revoked = await api("/voice/health", { token });
    gate("logout_revokes_session", revoked.status === 401);
    await voiceContext.close();
    voiceContext = null;
  } catch (error) {
    report.fatal = String(error?.stack || error).slice(0, 2500);
  } finally {
    if (voiceContext) await voiceContext.close().catch(() => {});
    if (browser) await browser.close().catch(() => {});
    await stopOwned(frontend);
    await stopOwned(backend);
    rmSync(certDir, { recursive: true, force: true });
  }

  const buckets = [
    report.hardGates,
    report.responsive,
    report.accessibility,
    report.security,
  ];
  const failed =
    buckets.some((bucket) =>
      Object.values(bucket).some((value) => value?.ok === false)
    ) || Boolean(report.fatal);
  report.verdict = failed ? "FAIL" : "PASS";
  report.generatedAudioRetained = false;
  report.tempDatabaseRetained = false;
  writeFileSync(
    join(OUT, "M77_VOICE_BROWSER_CERT.json"),
    `${JSON.stringify(report, null, 2)}\n`
  );
  console.log(
    `M77 voice browser certificate ${report.verdict}: ` +
      `${Object.keys(report.hardGates).length} hard, ` +
      `${Object.keys(report.responsive).length} responsive, ` +
      `${Object.keys(report.accessibility).length} accessibility, ` +
      `${Object.keys(report.security).length} security gates`
  );
  if (report.fatal) console.error(report.fatal);
  if (failed) process.exitCode = 1;
}

await main();
