/**
 * Voice resource admission for 8 GB Apple Silicon hosts.
 * Does NOT lower existing local LLM memory gates.
 */

/** @typedef {"LOCAL_STT_ALLOWED"|"LOCAL_STT_DEGRADED"|"LOCAL_STT_BLOCKED_RESOURCE_PRESSURE"} SttAdmission */

export const VOICE_RESOURCE_POLICY = Object.freeze({
  // Soft budgets — guidance for concurrent voice + LLM
  maxConcurrentHeavyLocalModels: 1,
  preferUnloadSttWhenLlmActive: true,
  browserSttAlwaysLightweight: true,
  neverLowerLlmMemoryGate: true,
});

/**
 * Admit streaming STT mode given host signals.
 * @param {object} [signals]
 * @param {number|null} [signals.reclaimableMib]
 * @param {boolean} [signals.localLlmActive]
 * @param {boolean} [signals.browserSttAvailable]
 * @param {boolean} [signals.heavyLocalSttRequested]
 */
export function admitStreamingStt(signals = {}) {
  const {
    reclaimableMib = null,
    localLlmActive = false,
    browserSttAvailable = false,
    heavyLocalSttRequested = false,
  } = signals;

  // Browser STT is lightweight — always allowed as PLATFORM_MANAGED_UNKNOWN path
  if (browserSttAvailable && !heavyLocalSttRequested) {
    return {
      admission: "LOCAL_STT_ALLOWED",
      mode: "browser_streaming",
      reason: "Browser SpeechRecognition is lightweight; privacy PLATFORM_MANAGED_UNKNOWN",
      policy: VOICE_RESOURCE_POLICY,
    };
  }

  if (heavyLocalSttRequested) {
    if (localLlmActive && VOICE_RESOURCE_POLICY.preferUnloadSttWhenLlmActive) {
      return {
        admission: "LOCAL_STT_BLOCKED_RESOURCE_PRESSURE",
        mode: "none",
        reason: "Heavy local STT blocked while local LLM active; LLM memory gate not lowered",
        policy: VOICE_RESOURCE_POLICY,
      };
    }
    if (reclaimableMib != null && reclaimableMib < 1500) {
      return {
        admission: "LOCAL_STT_BLOCKED_RESOURCE_PRESSURE",
        mode: "none",
        reason: `Insufficient reclaimable headroom (${reclaimableMib} MiB) for heavy local STT`,
        policy: VOICE_RESOURCE_POLICY,
      };
    }
    return {
      admission: "LOCAL_STT_DEGRADED",
      mode: "heavy_local_not_installed",
      reason: "Heavy local STT (whisper.cpp/faster-whisper) not installed on host",
      policy: VOICE_RESOURCE_POLICY,
    };
  }

  return {
    admission: "LOCAL_STT_DEGRADED",
    mode: "text_or_manual",
    reason: "No streaming STT adapter available",
    policy: VOICE_RESOURCE_POLICY,
  };
}
