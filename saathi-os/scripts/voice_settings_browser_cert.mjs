#!/usr/bin/env node
/**
 * Automated browser boundary check for /settings/voice.
 *
 * This harness never reads cookies or browser storage and never supplies an
 * owner credential. It is suitable for a local synthetic or already-approved
 * UI surface. Human audio quality remains an explicit owner review item.
 */
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { mkdir, writeFile } from "node:fs/promises";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..", "..");
const require = createRequire(join(here, "..", "package.json"));
const { chromium } = require("playwright");

const uiBase = process.env.VOICE_SETTINGS_UI_BASE || "http://127.0.0.1:3000";
const evidenceDir = join(root, "docs", "e2e-functional-audit", "browser");
const checks = [];
const requests = [];
const consoleErrors = [];
const forbiddenRequests = [];

function check(name, ok, detail = "") {
  checks.push({ name, ok: Boolean(ok), detail: String(detail).slice(0, 400) });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? ` — ${detail}` : ""}`);
}

async function main() {
  await mkdir(evidenceDir, { recursive: true });
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1200 }, colorScheme: "dark" });
  const page = await context.newPage();
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text().slice(0, 500));
  });
  page.on("request", (request) => {
    const url = new URL(request.url());
    requests.push({ method: request.method(), origin: url.origin, path: url.pathname, resource_type: request.resourceType() });
    if (!["127.0.0.1", "localhost"].includes(url.hostname)) forbiddenRequests.push(url.origin + url.pathname);
  });

  const response = await page.goto(`${uiBase}/settings/voice`, { waitUntil: "networkidle" });
  check("voice_settings_route_loads", response?.ok(), `status=${response?.status()}`);
  check("voice_settings_heading", await page.getByRole("heading", { name: "Voice Settings", exact: true }).count() === 1);
  check("runtime_voice_count_visible", await page.getByText(/Detected voices:/).count() > 0);
  check("local_voice_boundary_visible", await page.getByText("LOCAL SYSTEM VOICES ONLY", { exact: true }).count() === 1);
  check("privacy_boundary_visible", await page.getByText(/No voice recording or transcript is persisted/).count() === 1);
  check("output_controls_visible", await page.getByRole("button", { name: "Play test", exact: true }).count() === 1);
  check("input_controls_visible", await page.getByRole("button", { name: "Request microphone permission", exact: true }).count() === 1);
  check("nepali_phrase_visible", await page.getByText("नमस्ते अजय। साथी ओएसको आवाज परीक्षण भइरहेको छ।", { exact: true }).count() === 0);
  await page.getByRole("button", { name: "Nepali", exact: true }).click();
  check("nepali_phrase_selectable", await page.getByText("नमस्ते अजय। साथी ओएसको आवाज परीक्षण भइरहेको छ।", { exact: true }).count() === 1);
  await page.getByRole("button", { name: "Play test", exact: true }).click();
  const status = await page.getByTestId("voice-output-status").innerText();
  check("playback_or_safe_no_voice_result", /Playing|completed|No installed local Nepali voice|unavailable/i.test(status), status);

  const credentialControls = await page.locator('input[type="password"], input[name*="secret" i], input[name*="api" i]').count();
  check("no_credential_controls", credentialControls === 0, `count=${credentialControls}`);
  check("no_external_requests", forbiddenRequests.length === 0, `count=${forbiddenRequests.length}`);
  check("no_console_errors", consoleErrors.length === 0, `count=${consoleErrors.length}`);

  const screenshotName = "voice-settings-automated-boundary.png";
  await page.screenshot({ path: join(evidenceDir, screenshotName), fullPage: true });
  const verdict = checks.every((entry) => entry.ok)
    ? "SAATHIOS_VOICE_SETTINGS_AUTOMATED_BROWSER_BOUNDARY_PASSED_WITH_LIMITATIONS"
    : "SAATHIOS_VOICE_SETTINGS_AUTOMATED_BROWSER_BOUNDARY_FAILED";
  const evidence = {
    verdict,
    timestamp: new Date().toISOString(),
    browser_engine: "chromium",
    browser_version: browser.version(),
    ui_base: uiBase,
    route: "/settings/voice",
    checks,
    screenshots: [screenshotName],
    console_errors: consoleErrors,
    network_requests: requests,
    forbidden_external_requests: forbiddenRequests,
    limitations: [
      "Automated playback observes browser state only; owner hearing review remains required.",
      "This harness does not request microphone permission or inspect browser storage.",
    ],
  };
  await writeFile(join(evidenceDir, "VOICE_SETTINGS_AUTOMATED_BROWSER_CHECK.json"), JSON.stringify(evidence, null, 2) + "\n");
  await browser.close();
  console.log(verdict);
  if (!checks.every((entry) => entry.ok)) process.exitCode = 1;
}

main().catch((error) => {
  console.error(error?.stack || error);
  process.exitCode = 1;
});
