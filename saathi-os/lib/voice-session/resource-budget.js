/**
 * Voice resource admission for 8 GB Apple Silicon hosts.
 * Does NOT lower existing local LLM memory gates.
 *
 * V-NEXT-2B.1 expands local STT states:
 *   LOCAL_STT_READY
 *   LOCAL_STT_READY_DEGRADED
 *   LOCAL_STT_BLOCKED_MEMORY
 *   LOCAL_STT_BLOCKED_MODEL_LOAD
 *   LOCAL_STT_UNAVAILABLE
 * (legacy aliases retained for callers)
 */

/** @typedef {"LOCAL_STT_READY"|"LOCAL_STT_READY_DEGRADED"|"LOCAL_STT_BLOCKED_MEMORY"|"LOCAL_STT_BLOCKED_MODEL_LOAD"|"LOCAL_STT_UNAVAILABLE"|"LOCAL_STT_ALLOWED"|"LOCAL_STT_DEGRADED"|"LOCAL_STT_BLOCKED_RESOURCE_PRESSURE"} SttAdmission */

export const VOICE_RESOURCE_POLICY = Object.freeze({
  // Soft budgets — guidance for concurrent voice + LLM
  maxConcurrentHeavyLocalModels: 1,
  preferUnloadSttWhenLlmActive: true,
  browserSttAlwaysLightweight: true,
  neverLowerLlmMemoryGate: true,
  // Local Whisper tiny/base budgets on 8 GB (MiB)
  minReclaimableForTinyMib: 600,
  minReclaimableForBaseMib: 900,
  minReclaimableForSmallMib: 1500,
  preferredLocalModel: "base",
  fallbackLocalModel: "tiny",
  /**
   * V-NEXT-2B.1 measurement result: no local model met the locked Nepali gate.
   * Do not auto-select local as PRIMARY until this flips after owner live re-qual.
   * English-optimized local path remains available when explicitly requested.
   */
  multilingualLocalSttQualified: false,
  englishOptimizedLocalModel: "base",
});

/**
 * Map model id to minimum reclaimable headroom.
 * @param {string} modelId
 */
export function minReclaimableForModel(modelId = "base") {
  const id = String(modelId || "base").toLowerCase();
  if (id.includes("small")) return VOICE_RESOURCE_POLICY.minReclaimableForSmallMib;
  if (id.includes("tiny")) return VOICE_RESOURCE_POLICY.minReclaimableForTinyMib;
  return VOICE_RESOURCE_POLICY.minReclaimableForBaseMib;
}

/**
 * Admit streaming STT mode given host signals.
 * @param {object} [signals]
 * @param {number|null} [signals.reclaimableMib]
 * @param {boolean} [signals.localLlmActive]
 * @param {boolean} [signals.browserSttAvailable]
 * @param {boolean} [signals.heavyLocalSttRequested]
 * @param {boolean} [signals.localSttAvailable]
 * @param {boolean} [signals.localSttModelLoaded]
 * @param {boolean} [signals.localSttModelCorrupt]
 * @param {string} [signals.preferredModel]
 * @param {boolean} [signals.forceBrowser]
 */
export function admitStreamingStt(signals = {}) {
  const {
    reclaimableMib = null,
    localLlmActive = false,
    browserSttAvailable = false,
    heavyLocalSttRequested = false,
    localSttAvailable = false,
    localSttModelLoaded = true,
    localSttModelCorrupt = false,
    preferredModel = VOICE_RESOURCE_POLICY.preferredLocalModel,
    forceBrowser = false,
  } = signals;

  const policy = VOICE_RESOURCE_POLICY;

  // Explicit browser-only path
  if (forceBrowser && browserSttAvailable) {
    return {
      admission: "LOCAL_STT_READY_DEGRADED",
      legacyAdmission: "LOCAL_STT_ALLOWED",
      mode: "browser_streaming",
      modelId: null,
      privacyClass: "PLATFORM_MANAGED_UNKNOWN",
      reason: "Browser STT forced; privacy PLATFORM_MANAGED_UNKNOWN",
      policy,
    };
  }

  // Prefer qualified local STT when available and admitted.
  // If multilingual gate has not passed, only admit local when explicitly requested
  // as heavyLocalSttRequested (experimental EN-optimized) — never silent primary.
  const multilingualOk = policy.multilingualLocalSttQualified === true;
  if (localSttAvailable && !forceBrowser && (multilingualOk || heavyLocalSttRequested)) {
    if (localSttModelCorrupt) {
      return {
        admission: "LOCAL_STT_BLOCKED_MODEL_LOAD",
        legacyAdmission: "LOCAL_STT_BLOCKED_RESOURCE_PRESSURE",
        mode: browserSttAvailable ? "browser_fallback" : "text_or_manual",
        modelId: preferredModel,
        privacyClass: browserSttAvailable ? "PLATFORM_MANAGED_UNKNOWN" : "UNAVAILABLE",
        reason: "Local STT model corrupt or failed integrity check",
        policy,
      };
    }
    if (!localSttModelLoaded) {
      return {
        admission: "LOCAL_STT_BLOCKED_MODEL_LOAD",
        legacyAdmission: "LOCAL_STT_DEGRADED",
        mode: browserSttAvailable ? "browser_fallback" : "text_or_manual",
        modelId: preferredModel,
        privacyClass: browserSttAvailable ? "PLATFORM_MANAGED_UNKNOWN" : "UNAVAILABLE",
        reason: "Local STT model missing or failed to load",
        policy,
      };
    }
    if (localLlmActive && policy.preferUnloadSttWhenLlmActive) {
      // Do not kill LLM — degrade STT to browser if possible
      return {
        admission: "LOCAL_STT_BLOCKED_MEMORY",
        legacyAdmission: "LOCAL_STT_BLOCKED_RESOURCE_PRESSURE",
        mode: browserSttAvailable ? "browser_fallback" : "text_or_manual",
        modelId: null,
        privacyClass: browserSttAvailable ? "PLATFORM_MANAGED_UNKNOWN" : "UNAVAILABLE",
        reason:
          "Heavy local STT blocked while local LLM active; LLM memory gate not lowered; browser fallback if available",
        policy,
      };
    }
    const need = minReclaimableForModel(preferredModel);
    if (reclaimableMib != null && reclaimableMib < need) {
      // Try tiny as degraded local
      const tinyNeed = policy.minReclaimableForTinyMib;
      if (reclaimableMib >= tinyNeed && preferredModel !== "tiny") {
        return {
          admission: "LOCAL_STT_READY_DEGRADED",
          legacyAdmission: "LOCAL_STT_DEGRADED",
          mode: "local_streaming",
          modelId: "tiny",
          privacyClass: "LOCAL_CONFIRMED",
          reason: `Degraded to tiny: reclaimable ${reclaimableMib} MiB < ${need} for ${preferredModel}`,
          policy,
        };
      }
      return {
        admission: "LOCAL_STT_BLOCKED_MEMORY",
        legacyAdmission: "LOCAL_STT_BLOCKED_RESOURCE_PRESSURE",
        mode: browserSttAvailable ? "browser_fallback" : "text_or_manual",
        modelId: null,
        privacyClass: browserSttAvailable ? "PLATFORM_MANAGED_UNKNOWN" : "UNAVAILABLE",
        reason: `Insufficient reclaimable headroom (${reclaimableMib} MiB) for local STT model ${preferredModel}`,
        policy,
      };
    }
    return {
      admission: "LOCAL_STT_READY",
      legacyAdmission: "LOCAL_STT_ALLOWED",
      mode: "local_streaming",
      modelId: preferredModel,
      privacyClass: "LOCAL_CONFIRMED",
      reason: `Local STT admitted (${preferredModel})`,
      policy,
    };
  }

  // Legacy heavy-local request without installed engine
  if (heavyLocalSttRequested && !localSttAvailable) {
    if (localLlmActive && policy.preferUnloadSttWhenLlmActive) {
      return {
        admission: "LOCAL_STT_BLOCKED_MEMORY",
        legacyAdmission: "LOCAL_STT_BLOCKED_RESOURCE_PRESSURE",
        mode: browserSttAvailable ? "browser_fallback" : "none",
        modelId: null,
        privacyClass: browserSttAvailable ? "PLATFORM_MANAGED_UNKNOWN" : "UNAVAILABLE",
        reason: "Heavy local STT blocked while local LLM active; LLM memory gate not lowered",
        policy,
      };
    }
    if (reclaimableMib != null && reclaimableMib < policy.minReclaimableForBaseMib) {
      return {
        admission: "LOCAL_STT_BLOCKED_MEMORY",
        legacyAdmission: "LOCAL_STT_BLOCKED_RESOURCE_PRESSURE",
        mode: browserSttAvailable ? "browser_fallback" : "none",
        modelId: null,
        privacyClass: browserSttAvailable ? "PLATFORM_MANAGED_UNKNOWN" : "UNAVAILABLE",
        reason: `Insufficient reclaimable headroom (${reclaimableMib} MiB) for heavy local STT`,
        policy,
      };
    }
    return {
      admission: "LOCAL_STT_UNAVAILABLE",
      legacyAdmission: "LOCAL_STT_DEGRADED",
      mode: browserSttAvailable ? "browser_fallback" : "heavy_local_not_installed",
      modelId: null,
      privacyClass: browserSttAvailable ? "PLATFORM_MANAGED_UNKNOWN" : "UNAVAILABLE",
      reason: "Heavy local STT requested but engine not available on host",
      policy,
    };
  }

  // Browser STT is lightweight — compatibility path
  if (browserSttAvailable) {
    return {
      admission: "LOCAL_STT_READY_DEGRADED",
      legacyAdmission: "LOCAL_STT_ALLOWED",
      mode: "browser_streaming",
      modelId: null,
      privacyClass: "PLATFORM_MANAGED_UNKNOWN",
      reason: "Browser SpeechRecognition compatibility path; privacy PLATFORM_MANAGED_UNKNOWN",
      policy,
    };
  }

  return {
    admission: "LOCAL_STT_UNAVAILABLE",
    legacyAdmission: "LOCAL_STT_DEGRADED",
    mode: "text_or_manual",
    modelId: null,
    privacyClass: "UNAVAILABLE",
    reason: "No streaming STT adapter available",
    policy,
  };
}

/**
 * Resolve STT engine hierarchy for UI / pipeline.
 * Never silently selects a cloud provider.
 *
 * @param {object} admission result of admitStreamingStt
 */
export function resolveSttHierarchy(admission = {}) {
  const mode = admission.mode || "text_or_manual";
  const chain = [];
  if (mode === "local_streaming") {
    chain.push({
      role: "PRIMARY_LOCAL_STT",
      engine: "local_whisper",
      modelId: admission.modelId,
      privacyClass: "LOCAL_CONFIRMED",
    });
    chain.push({
      role: "BROWSER_COMPATIBILITY_FALLBACK",
      engine: "browser_speech_recognition",
      privacyClass: "PLATFORM_MANAGED_UNKNOWN",
    });
  } else if (mode === "browser_streaming" || mode === "browser_fallback") {
    chain.push({
      role: "BROWSER_COMPATIBILITY_FALLBACK",
      engine: "browser_speech_recognition",
      privacyClass: "PLATFORM_MANAGED_UNKNOWN",
    });
  }
  chain.push({
    role: "TEXT_FALLBACK",
    engine: "manual_text",
    privacyClass: "LOCAL_CONFIRMED",
  });
  return {
    primary: chain[0] || null,
    chain,
    cloudFallback: false,
  };
}

/**
 * Human-readable command strip label.
 * @param {object} health pipeline or stt health
 */
export function formatVoiceInputLabel(health = {}) {
  const privacy = health.privacyClass || health.stt?.privacyClass || "";
  const adapter = health.adapter || health.stt?.adapter || health.mode || "";
  const model = health.modelId || health.stt?.modelId || "";
  const engine = health.engineId || health.stt?.engineId || "";
  const degraded =
    health.admissionState === "LOCAL_STT_READY_DEGRADED" ||
    health.degraded ||
    health.admission === "LOCAL_STT_READY_DEGRADED";

  if (privacy === "LOCAL_CONFIRMED" || adapter === "local_streaming_stt" || String(adapter).includes("local")) {
    const modelLabel = model ? ` [${model}]` : engine ? ` [${engine}]` : "";
    return {
      title: "VOICE INPUT",
      line: `Local · Whisper${modelLabel}${degraded ? " · degraded" : ""}`,
      privacyClass: "LOCAL_CONFIRMED",
      local: true,
    };
  }
  if (String(adapter).includes("browser") || privacy === "PLATFORM_MANAGED_UNKNOWN") {
    return {
      title: "VOICE INPUT",
      line: "Browser · Privacy unknown",
      privacyClass: "PLATFORM_MANAGED_UNKNOWN",
      local: false,
    };
  }
  if (String(adapter).includes("mock")) {
    return {
      title: "VOICE INPUT",
      line: "Mock · Local test",
      privacyClass: "LOCAL_CONFIRMED",
      local: true,
    };
  }
  return {
    title: "VOICE INPUT",
    line: "Unavailable · Text fallback",
    privacyClass: "UNAVAILABLE",
    local: false,
  };
}
