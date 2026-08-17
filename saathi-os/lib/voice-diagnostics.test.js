import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import {
  BARGE_IN_CLASSES,
  MIC_PERMISSION_STATES,
  VOICE_ERROR_CATEGORIES,
  buildVoiceDiagnostics,
  classifyVoiceError,
  deriveBargeInClass,
  deriveCleanupState,
  deriveOwnershipIntegrity,
  deriveTtsLane,
  deriveVadLane,
  toEvidenceRecord,
  truncateForDisplay,
} from "./voice-diagnostics.js";

/** Comments describe the boundary; only executable source may be judged by it. */
function stripComments(source) {
  return source.replace(/\/\*[\s\S]*?\*\//g, "").replace(/^\s*\/\/.*$/gm, "");
}

const PANEL = stripComments(
  readFileSync(
    new URL("../components/voice/VoiceDiagnosticsPanel.jsx", import.meta.url),
    "utf8"
  )
);
const PAGE = readFileSync(
  new URL("../app/settings/voice/diagnostics/page.jsx", import.meta.url),
  "utf8"
);

test("error classification is bounded and never leaks the raw message", () => {
  assert.equal(classifyVoiceError(""), "none");
  assert.equal(classifyVoiceError("NotAllowedError: Permission denied"), "permission");
  assert.equal(classifyVoiceError("Microphone API unavailable"), "device");
  assert.equal(classifyVoiceError("no-speech"), "recognition");
  assert.equal(classifyVoiceError("VAD arm failed"), "vad");
  assert.equal(classifyVoiceError("fetch failed"), "network");
  assert.equal(classifyVoiceError("Voice session is closed"), "session");
  assert.equal(classifyVoiceError("something entirely new"), "unknown");
  // Anything unrecognized must collapse to a bounded category, so an authorization
  // header or a filesystem path can never reach the panel or the evidence package.
  for (const raw of ["Authorization: <redacted>", "/opt/app/data/store"]) {
    assert.ok(VOICE_ERROR_CATEGORIES.includes(classifyVoiceError(raw)));
  }
});

test("transcript display is truncated and whitespace-normalized", () => {
  assert.equal(truncateForDisplay("  hello   world \n"), "hello world");
  const long = "a".repeat(400);
  const out = truncateForDisplay(long);
  assert.equal(out.length, 241);
  assert.ok(out.endsWith("…"));
  assert.equal(truncateForDisplay(null), "");
});

test("VAD lane reflects armed / speech / silence / failure truthfully", () => {
  assert.equal(deriveVadLane(null), "idle");
  assert.equal(deriveVadLane({ armed: false, vad: { state: "running" } }), "idle");
  assert.equal(deriveVadLane({ armed: true, vadFailed: true }), "error");
  assert.equal(
    deriveVadLane({ armed: true, speechDetected: true, vad: { state: "speech" } }),
    "speech"
  );
  assert.equal(deriveVadLane({ armed: true, vad: { state: "silence" } }), "silence");
});

test("barge-in classification maps interrupt classes without inventing confirmation", () => {
  assert.equal(deriveBargeInClass({}), "none");
  assert.equal(deriveBargeInClass({ interruptClass: "REAL_INTERRUPTION" }), "confirmed");
  assert.equal(
    deriveBargeInClass({ interruptClass: "FALSE_INTERRUPTION" }),
    "false_positive"
  );
  assert.equal(
    deriveBargeInClass({ interruptClass: "UNKNOWN_INTERRUPTION" }),
    "detected"
  );
  assert.equal(
    deriveBargeInClass({ pipelineHealth: { turns: { pendingFalseInterrupt: true } } }),
    "detected"
  );
  for (const key of ["none", "confirmed", "false_positive", "detected"]) {
    assert.ok(BARGE_IN_CLASSES.includes(key));
  }
});

test("TTS lane distinguishes speaking, interrupted, and completed", () => {
  assert.equal(deriveTtsLane({ outputState: "speaking" }), "speaking");
  assert.equal(deriveTtsLane({ state: "INTERRUPTED" }), "interrupted");
  assert.equal(deriveTtsLane({ outputState: "held" }), "held");
  assert.equal(deriveTtsLane({ assistantText: "hello" }), "completed");
  assert.equal(deriveTtsLane({}), "idle");
});

test("cleanup state is clean only when every resource is released", () => {
  const held = deriveCleanupState({
    session: { pipelineHealth: { active: true } },
    inputOwner: { claimId: "in-1", hasMediaStream: true, hasRecognition: true },
    outputOwner: { claimId: "out-1" },
    vadHealth: { armed: true, tap: { running: true } },
  });
  assert.equal(held.clean, false);
  assert.equal(held.label, "resources held");
  assert.equal(held.sttPipelineActive, true);

  const clean = deriveCleanupState({
    session: { pipelineHealth: { active: false } },
    inputOwner: {},
    outputOwner: {},
    vadHealth: { armed: false, tap: null },
  });
  assert.equal(clean.clean, true);
  assert.equal(clean.label, "clean");
});

test("duplicate microphone owner is surfaced, not hidden", () => {
  const ok = deriveOwnershipIntegrity({
    session: { inputClaimId: "in-7" },
    inputOwner: { claimId: "in-7" },
    outputOwner: {},
  });
  assert.equal(ok.duplicateInputOwner, false);
  assert.equal(ok.label, "single owner");

  const split = deriveOwnershipIntegrity({
    session: { inputClaimId: "in-7" },
    inputOwner: { claimId: "in-9" },
    outputOwner: {},
  });
  assert.equal(split.duplicateInputOwner, true);
  assert.equal(split.label, "DUPLICATE INPUT OWNER");
});

test("diagnostics view exposes every state the owner protocol requires", () => {
  const view = buildVoiceDiagnostics({
    session: {
      state: "LISTENING",
      sessionId: "vs-1",
      inputState: "listening",
      outputState: "idle",
      inputClaimId: "in-3",
      transcriptPartial: "hello saa",
      lastTurn: {
        text: "hello saathi",
        reason: "stt_final",
        isExecutable: true,
        isBackchannel: false,
        authority: "none",
      },
      capabilities: {
        speechRecognitionAvailable: true,
        acousticBargeInAvailable: true,
        fullDuplexAvailable: false,
        wakeWordAvailable: false,
      },
      pipelineHealth: {
        active: true,
        selectedMode: "browser_streaming",
        turns: { finalizedTurns: 1, realInterrupts: 0, falseInterrupts: 0 },
      },
      lastBargeInLatencyMs: 84,
      error: "",
    },
    inputOwner: { claimId: "in-3", hasMediaStream: true, hasRecognition: true },
    outputOwner: {},
    vadHealth: {
      armed: true,
      speechDetected: true,
      vad: { state: "speech", lastRms: 0.042, threshold: 0.018, framesProcessed: 120 },
      tap: { running: true, frames: 120 },
      latencyMs: { last: 84 },
    },
    permission: "granted",
    deviceLabel: "MacBook Pro Microphone",
    telemetry: { counts: { input_started: 1 } },
  });

  assert.equal(view.permission, "granted");
  assert.equal(view.deviceLabel, "MacBook Pro Microphone");
  assert.equal(view.sessionState, "LISTENING");
  assert.equal(view.vadLane, "speech");
  assert.ok(view.rms > 0);
  assert.equal(view.speechRecognitionAvailable, true);
  assert.equal(view.partialTranscript, "hello saa");
  assert.equal(view.finalTranscript, "hello saathi");
  assert.equal(view.turnReason, "stt_final");
  assert.equal(view.turnAuthority, "none");
  assert.equal(view.bargeInLatencyMs, 84);
  assert.equal(view.errorCategory, "none");
  assert.equal(view.cleanup.clean, false);
  assert.equal(view.ownership.duplicateInputOwner, false);
  assert.equal(view.capabilityClaims.fullDuplex, false);
  assert.equal(view.capabilityClaims.wakeWord, false);
  assert.equal(view.telemetryCounts.input_started, 1);
});

test("unknown permission values fail closed", () => {
  const view = buildVoiceDiagnostics({ permission: "allowed-probably" });
  assert.equal(view.permission, "unknown");
  assert.ok(MIC_PERMISSION_STATES.includes(view.permission));
});

test("evidence record carries outcomes but never transcript text", () => {
  const view = buildVoiceDiagnostics({
    session: {
      transcriptPartial: "my private sentence",
      lastTurn: { text: "my private sentence", reason: "stt_final", authority: "none" },
    },
    permission: "granted",
    deviceLabel: "MacBook Pro Microphone",
  });
  const record = toEvidenceRecord(view);
  const serialized = JSON.stringify(record);
  assert.ok(!serialized.includes("private"));
  assert.ok(!serialized.includes("MacBook"));
  assert.equal(record.deviceLabelPresent, true);
  assert.equal(record.finalTranscriptChars, "my private sentence".length);
  assert.equal(record.turnAuthority, "none");
});

test("diagnostics panel is a passive observer: no capture, no recognizer, no execution", () => {
  assert.ok(!/getUserMedia/.test(PANEL), "panel must not open a microphone");
  assert.ok(!/SpeechRecognition|getRecognitionCtor/.test(PANEL), "panel must not construct a recognizer");
  assert.ok(!/speechSynthesis|SpeechSynthesisUtterance/.test(PANEL), "panel must not speak");
  assert.ok(
    !/beginInput|openSession|toggleMic|startStreamingPipeline|armVad|forceRelease/.test(PANEL),
    "panel must not drive the voice session"
  );
  assert.ok(
    !/\b(execute[A-Za-z]*|approve[A-Za-z]*|submitCommand|dispatchCommand|gateway[A-Za-z]*)\s*\(/i.test(
      PANEL
    ),
    "panel must not invoke command, approval, or gateway paths"
  );
  assert.ok(!/\bfetch\s*\(|apiFetch|platform-client/.test(PANEL), "panel must not call the API");
  assert.ok(/subscribeInputOwner/.test(PANEL) && /getBargeInHealth/.test(PANEL));
});

test("diagnostics page states its read-only and privacy boundaries", () => {
  for (const claim of [
    "READ-ONLY OBSERVER",
    "NO SECOND MICROPHONE",
    "NO RAW AUDIO STORED",
    "NO EXECUTION AUTHORITY",
  ]) {
    assert.ok(PAGE.includes(claim), `page must state: ${claim}`);
  }
  assert.ok(!/getUserMedia/.test(PAGE));
  assert.ok(/VoiceDiagnosticsPanel/.test(PAGE));
});
