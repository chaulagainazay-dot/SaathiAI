#!/usr/bin/env node
/**
 * Guided owner audio review for SaathiOS.
 *
 * Automation may set the review up and walk the owner through it. It must never
 * answer for them. This script prints instructions, checks that the local app is
 * actually reachable on loopback, and writes a template with every answer left
 * as AWAITING_OWNER_INPUT. It does not listen, score, or infer anything.
 *
 * Usage:
 *   node scripts/audio_review_session.mjs
 *   E2E_UI_BASE=http://127.0.0.1:3000 node scripts/audio_review_session.mjs
 */
import { writeFileSync, mkdirSync, existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const saathiOs = join(here, "..");
const outDir = process.env.E2E_OUT_DIR || join(saathiOs, "..", "docs", "e2e-functional-audit");

const uiBase = process.env.E2E_UI_BASE || "http://127.0.0.1:3000";
const apiBase = process.env.E2E_API_BASE || "http://127.0.0.1:8765";

const PHRASES = {
  english: "Hello Ajay. SaathiOS voice output is working correctly.",
  nepali: "नमस्ते अजय। साथी ओएसको आवाज परीक्षण भइरहेको छ।",
  mixed: "SaathiOS अहिले local private alpha mode मा चलिरहेको छ।",
};

const CHECKS = [
  ["english_audible", "English speech is audible"],
  ["english_understandable", "English speech is understandable"],
  ["nepali_audible_or_safe_fallback", "Nepali is audible, or a clear fallback is shown (silence is a defect)"],
  ["mixed_language_acceptable", "Mixed Nepali/English is handled acceptably"],
  ["stop_halts_speech", "Stop halts speech immediately, not at end of sentence"],
  ["replay_does_not_overlap", "Replay does not overlap the previous playback"],
  ["new_response_cancels_old_speech", "A new response cancels the old speech"],
  ["route_change_stops_speech", "Navigating to another page stops speech"],
  ["logout_stops_speech", "Logging out stops speech"],
  ["microphone_indicator_accurate", "The browser microphone indicator matches the app's state"],
  ["microphone_stops_and_releases", "Stopping the mic releases it (browser indicator goes out)"],
  ["no_hidden_recording", "No recording happens without a visible indicator"],
  ["microphone_start_interrupts_output", "Pressing the mic while audio plays stops the audio first (VOICE_INPUT_INTERRUPTS_OUTPUT)"],
  ["volume_acceptable", "Volume is comfortable at normal system volume"],
  ["persona_label_correct", "Persona name and avatar are correct and consistent"],
];

async function reachable(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(4000) });
    return res.status;
  } catch {
    return 0;
  }
}

const ui = await reachable(`${uiBase}/platform`);
const api = await reachable(`${apiBase}/api/v1/platform/health`);

const line = "─".repeat(72);
console.log(`\n${line}\nSaathiOS — guided owner audio review\n${line}\n`);

console.log("1. Local services");
console.log(`   UI  ${uiBase}   ${ui ? `reachable (HTTP ${ui})` : "NOT REACHABLE"}`);
console.log(`   API ${apiBase}  ${api ? `reachable (HTTP ${api})` : "NOT REACHABLE"}`);
if (!ui || !api) {
  console.log("\n   Start them first, from the repo root:");
  console.log("     .venv/bin/python -m saathi.server        # binds 127.0.0.1");
  console.log("     cd saathi-os && npm start                # binds 127.0.0.1:3000");
  console.log("\n   Both bind loopback only. That is intentional — see");
  console.log("   docs/private-alpha/LAN_TESTING_POLICY.md.\n");
}

console.log("\n2. Open this in a NORMAL Chromium browser (not headless), with audio on:");
console.log(`   ${uiBase}/platform`);
console.log("\n   Sign in with your private-alpha account, then open the chat or voice");
console.log("   surface and enable voice output.\n");

console.log("3. Speak / play these phrases:\n");
console.log(`   English : ${PHRASES.english}`);
console.log(`   Nepali  : ${PHRASES.nepali}`);
console.log(`   Mixed   : ${PHRASES.mixed}\n`);

console.log("4. Then exercise, in this order:");
console.log("   a. play a response, press Stop mid-sentence");
console.log("   b. play a response, then trigger another before it finishes");
console.log("   c. play a response, then navigate to a different page");
console.log("   d. play a response, then log out");
console.log("   e. play a response, then press the microphone button while it speaks");
console.log("   f. start the microphone, then navigate away — watch the browser mic indicator\n");

console.log(`5. Record your answers in:\n   ${join(outDir, "OWNER_AUDIO_REVIEW_TEMPLATE.json")}`);
console.log("   Replace each AWAITING_OWNER_INPUT with true, false, or a short note.");
console.log("   Set reviewed_by, reviewed_at, browser and voices_available.\n");
console.log("   Nothing in this file is filled in by automation. Until you complete");
console.log("   it, the mission verdict keeps OWNER_AUDIO_REVIEW_REQUIRED.\n");
console.log(line);

const templatePath = join(outDir, "OWNER_AUDIO_REVIEW_TEMPLATE.json");
mkdirSync(outDir, { recursive: true });

if (existsSync(templatePath) && !process.env.E2E_FORCE_TEMPLATE) {
  console.log(`\nTemplate already exists, left untouched: ${templatePath}`);
  console.log("Set E2E_FORCE_TEMPLATE=1 to regenerate a blank one.\n");
} else {
  const template = {
    record: "SAATHIOS_OWNER_AUDIO_REVIEW",
    status: "AWAITING_OWNER_INPUT",
    note:
      "Automation prepared this file and must not fill it in. Audible quality is a human judgement. Replace each AWAITING_OWNER_INPUT with true, false, or a short note.",
    ui_base: uiBase,
    api_base: apiBase,
    reviewed_by: "AWAITING_OWNER_INPUT",
    reviewed_at: "AWAITING_OWNER_INPUT",
    browser_and_os: "AWAITING_OWNER_INPUT",
    voices_available: "AWAITING_OWNER_INPUT (run speechSynthesis.getVoices().length in the console)",
    phrases: PHRASES,
    checks: Object.fromEntries(
      CHECKS.map(([key, label]) => [key, { check: label, result: "AWAITING_OWNER_INPUT", note: "" }])
    ),
    surface_tested: {
      check: "Which voice surface did you test — platform voice runtime, or chat VoiceControl? They differ; see VOICE_INTERRUPTION_DECISION.json.",
      result: "AWAITING_OWNER_INPUT",
    },
    verdict: "AWAITING_OWNER_INPUT (accepted_for_private_alpha | defects_raised)",
    defects_raised: [],
  };
  writeFileSync(templatePath, `${JSON.stringify(template, null, 2)}\n`);
  console.log(`\nWrote blank template: ${templatePath}\n`);
}
