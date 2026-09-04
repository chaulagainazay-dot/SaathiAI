/**
 * R2.1 — Owner-validation diagnostics view model.
 *
 * Read-only projection over the canonical VoiceSessionManager snapshot plus the
 * input/output owner singletons. This module never acquires a microphone, never
 * constructs a SpeechRecognition instance, and never invokes a command,
 * approval, or ExecutionGateway path. It observes what the production voice
 * runtime already published.
 *
 * Privacy: raw audio is never captured or stored here. Transcript text stays in
 * page memory, is truncated for display, and is cleared by the owner on demand.
 */

/** Permission values the panel is allowed to display. */
export const MIC_PERMISSION_STATES = Object.freeze([
  "unknown",
  "requested",
  "granted",
  "denied",
]);

/** Bounded error categories — never a raw provider string. */
export const VOICE_ERROR_CATEGORIES = Object.freeze([
  "none",
  "permission",
  "device",
  "recognition",
  "vad",
  "network",
  "session",
  "unknown",
]);

/** Barge-in classification surfaced to the owner. */
export const BARGE_IN_CLASSES = Object.freeze([
  "none",
  "detected",
  "confirmed",
  "false_positive",
  "unknown",
]);

export const MAX_TRANSCRIPT_DISPLAY_CHARS = 240;

/**
 * Clamp free text for display. Never used for authority decisions.
 * @param {unknown} text
 * @param {number} [limit]
 */
export function truncateForDisplay(text, limit = MAX_TRANSCRIPT_DISPLAY_CHARS) {
  const value = String(text ?? "").replace(/\s+/g, " ").trim();
  if (!value) return "";
  return value.length <= limit ? value : `${value.slice(0, limit)}…`;
}

/**
 * Map an arbitrary runtime error string onto a bounded category.
 * The raw message is deliberately discarded so nothing provider-specific,
 * path-specific, or credential-shaped can reach committed evidence.
 * @param {unknown} raw
 * @returns {typeof VOICE_ERROR_CATEGORIES[number]}
 */
export function classifyVoiceError(raw) {
  const value = String(raw ?? "").toLowerCase();
  if (!value.trim()) return "none";
  if (/not-allowed|permission|denied|insecure/.test(value)) return "permission";
  if (/device|notfound|no microphone|microphone api|audio-capture/.test(value)) {
    return "device";
  }
  if (/speech|recognition|no-speech|aborted|language-not-supported/.test(value)) {
    return "recognition";
  }
  if (/vad|barge/.test(value)) return "vad";
  if (/network|fetch|timeout|offline/.test(value)) return "network";
  if (/session|claim|closed|sign in/.test(value)) return "session";
  return "unknown";
}

/**
 * Derive the VAD lane label from published health.
 * @param {object|null} vadHealth barge-in controller health()
 */
export function deriveVadLane(vadHealth) {
  const vad = vadHealth?.vad || null;
  if (!vadHealth?.armed) return "idle";
  if (vadHealth?.vadFailed) return "error";
  if (vadHealth?.speechDetected || vad?.speechActive) return "speech";
  if (vad?.state === "running" || vad?.state === "silence") return "silence";
  return vad?.state || "idle";
}

/**
 * Derive barge-in classification from the turn coordinator's published class.
 * @param {object} session
 */
export function deriveBargeInClass(session) {
  const turns = session?.pipelineHealth?.turns || null;
  const raw = session?.interruptClass || turns?.lastInterruptClass || "";
  if (raw === "REAL_INTERRUPTION") return "confirmed";
  if (raw === "FALSE_INTERRUPTION") return "false_positive";
  if (raw === "UNKNOWN_INTERRUPTION") return "detected";
  if (turns?.pendingFalseInterrupt) return "detected";
  return "none";
}

/**
 * Derive the output/TTS lane from ownership plus interrupt history.
 * @param {object} session
 */
export function deriveTtsLane(session) {
  if (session?.outputState === "speaking") return "speaking";
  if (session?.state === "INTERRUPTED") return "interrupted";
  if (session?.outputState === "held") return "held";
  if (session?.assistantText) return "completed";
  return "idle";
}

/**
 * Cleanup state — proves teardown released every owned resource.
 * @param {object} args
 */
export function deriveCleanupState({ session, inputOwner, outputOwner, vadHealth }) {
  const micHeld = Boolean(inputOwner?.claimId);
  const streamHeld = Boolean(inputOwner?.hasMediaStream);
  const recognitionHeld = Boolean(inputOwner?.hasRecognition);
  const outputHeld = Boolean(outputOwner?.claimId);
  const vadArmed = Boolean(vadHealth?.armed);
  const tapRunning = Boolean(vadHealth?.tap?.running);
  const pipelineActive = Boolean(session?.pipelineHealth?.active);
  const anyHeld =
    micHeld || streamHeld || recognitionHeld || outputHeld || vadArmed || tapRunning || pipelineActive;
  return {
    micClaimHeld: micHeld,
    mediaStreamHeld: streamHeld,
    recognitionHeld,
    outputClaimHeld: outputHeld,
    vadArmed,
    audioTapRunning: tapRunning,
    sttPipelineActive: pipelineActive,
    clean: !anyHeld,
    label: anyHeld ? "resources held" : "clean",
  };
}

/**
 * Count how many distinct microphone owners are visible. The V-NEXT-1 contract
 * allows at most one; anything else is a defect the owner must see.
 * @param {object} args
 */
export function deriveOwnershipIntegrity({ session, inputOwner, outputOwner }) {
  const sessionInputClaim = session?.inputClaimId || null;
  const singletonClaim = inputOwner?.claimId || null;
  const mismatch = Boolean(
    sessionInputClaim && singletonClaim && sessionInputClaim !== singletonClaim
  );
  return {
    inputClaimId: singletonClaim,
    sessionInputClaimId: sessionInputClaim,
    outputClaimId: outputOwner?.claimId || session?.outputClaimId || null,
    duplicateInputOwner: mismatch,
    label: mismatch ? "DUPLICATE INPUT OWNER" : singletonClaim ? "single owner" : "no owner",
  };
}

/**
 * Build the full read-only diagnostics view model.
 *
 * @param {object} args
 * @param {object} args.session VoiceSessionManager snapshot
 * @param {object} [args.inputOwner] getInputOwnerSnapshot()
 * @param {object} [args.outputOwner] getOutputOwnerSnapshot()
 * @param {object} [args.vadHealth] manager.getBargeInHealth()
 * @param {string} [args.permission] mic permission state
 * @param {string} [args.deviceLabel] input device label reported by the browser
 * @param {object} [args.telemetry] getVoiceTelemetrySnapshot()
 */
export function buildVoiceDiagnostics({
  session = {},
  inputOwner = {},
  outputOwner = {},
  vadHealth = null,
  permission = "unknown",
  deviceLabel = "",
  telemetry = null,
} = {}) {
  const health = vadHealth || session.vadHealth || null;
  const turns = session?.pipelineHealth?.turns || null;
  const capabilities = session?.capabilities || {};
  const safePermission = MIC_PERMISSION_STATES.includes(permission)
    ? permission
    : "unknown";

  return {
    permission: safePermission,
    deviceLabel: truncateForDisplay(deviceLabel, 80),
    sessionState: session?.state || "IDLE",
    sessionId: session?.sessionId || "",
    inputState: session?.inputState || "idle",
    outputState: session?.outputState || "idle",
    ownership: deriveOwnershipIntegrity({ session, inputOwner, outputOwner }),
    vadLane: deriveVadLane(health),
    rms: Number(health?.vad?.lastRms ?? 0),
    vadThreshold: Number(health?.vad?.threshold ?? 0),
    vadFrames: Number(health?.vad?.framesProcessed ?? 0),
    tapFrames: Number(health?.tap?.frames ?? 0),
    speechRecognitionAvailable: Boolean(capabilities.speechRecognitionAvailable),
    sttEngineLabel: session?.sttEngine?.mode || session?.pipelineHealth?.selectedMode || "none",
    sttDegraded: Boolean(session?.sttDegraded),
    partialTranscript: truncateForDisplay(session?.transcriptPartial),
    finalTranscript: truncateForDisplay(
      session?.lastTurn?.text || session?.transcriptFinal
    ),
    turnReason: session?.lastTurn?.reason || turns?.lastInterruptClass || "",
    turnIsExecutable: Boolean(session?.lastTurn?.isExecutable),
    turnIsBackchannel: Boolean(session?.lastTurn?.isBackchannel),
    turnAuthority: session?.lastTurn?.authority || "none",
    finalizedTurns: Number(turns?.finalizedTurns ?? 0),
    realInterrupts: Number(turns?.realInterrupts ?? 0),
    falseInterrupts: Number(turns?.falseInterrupts ?? 0),
    bargeInClass: deriveBargeInClass(session),
    bargeInLatencyMs:
      session?.lastBargeInLatencyMs ?? health?.latencyMs?.last ?? null,
    ttsLane: deriveTtsLane(session),
    errorCategory: classifyVoiceError(session?.error),
    cleanup: deriveCleanupState({
      session,
      inputOwner,
      outputOwner,
      vadHealth: health,
    }),
    telemetryCounts: telemetry?.counts ? { ...telemetry.counts } : {},
    capabilityClaims: {
      fullDuplex: Boolean(capabilities.fullDuplexAvailable),
      wakeWord: Boolean(capabilities.wakeWordAvailable),
      acousticBargeIn: Boolean(capabilities.acousticBargeInAvailable),
    },
  };
}

/**
 * Sanitized export for the evidence package. Transcript text is dropped —
 * only its presence and length survive, so committed evidence can prove a
 * transcript existed without recording what the owner said.
 * @param {ReturnType<typeof buildVoiceDiagnostics>} view
 */
export function toEvidenceRecord(view) {
  return {
    permission: view.permission,
    deviceLabelPresent: Boolean(view.deviceLabel),
    sessionState: view.sessionState,
    inputState: view.inputState,
    outputState: view.outputState,
    duplicateInputOwner: view.ownership.duplicateInputOwner,
    vadLane: view.vadLane,
    rmsNonZero: Number(view.rms) > 0,
    speechRecognitionAvailable: view.speechRecognitionAvailable,
    partialTranscriptChars: view.partialTranscript.length,
    finalTranscriptChars: view.finalTranscript.length,
    turnReason: view.turnReason,
    turnIsExecutable: view.turnIsExecutable,
    turnIsBackchannel: view.turnIsBackchannel,
    turnAuthority: view.turnAuthority,
    finalizedTurns: view.finalizedTurns,
    realInterrupts: view.realInterrupts,
    falseInterrupts: view.falseInterrupts,
    bargeInClass: view.bargeInClass,
    bargeInLatencyMs: view.bargeInLatencyMs,
    ttsLane: view.ttsLane,
    errorCategory: view.errorCategory,
    cleanupClean: view.cleanup.clean,
    capabilityClaims: view.capabilityClaims,
  };
}
