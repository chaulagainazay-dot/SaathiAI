export const VOICE_TEST_PHRASES = Object.freeze({
  english: Object.freeze({
    id: "english",
    label: "English",
    locale: "en-US",
    text: "Hello Ajay. SaathiOS voice output is working correctly.",
  }),
  nepali: Object.freeze({
    id: "nepali",
    label: "Nepali",
    locale: "ne-NP",
    text: "नमस्ते अजय। साथी ओएसको आवाज परीक्षण भइरहेको छ।",
  }),
  mixed: Object.freeze({
    id: "mixed",
    label: "Mixed Nepali + English",
    locale: "en-US",
    text: "SaathiOS अहिले local private alpha mode मा चलिरहेको छ।",
  }),
});

const SAFE_LOCALE = /^[A-Za-z]{2,3}(?:-[A-Za-z0-9]{2,8}){0,2}$/;

export function normalizeLocale(value, fallback = "en-US") {
  const locale = String(value || "").trim();
  return SAFE_LOCALE.test(locale) ? locale : fallback;
}

export function normalizeVoiceList(values) {
  if (!Array.isArray(values)) return [];
  const seen = new Set();
  const result = [];
  for (const value of values) {
    const voiceURI = String(value?.voiceURI || "").trim().slice(0, 240);
    const name = String(value?.name || "Unnamed system voice").trim().slice(0, 160);
    const lang = normalizeLocale(value?.lang, "und");
    if (!voiceURI || seen.has(voiceURI)) continue;
    seen.add(voiceURI);
    result.push({
      voiceURI,
      name,
      lang,
      default: value?.default === true,
      localService: value?.localService === true,
    });
  }
  return result.sort((a, b) =>
    `${a.lang}:${a.name}:${a.voiceURI}`.localeCompare(`${b.lang}:${b.name}:${b.voiceURI}`)
  );
}

export function summarizeVoiceCapability(values) {
  const voices = normalizeVoiceList(values);
  const localVoices = voices.filter((voice) => voice.localService);
  const languages = Array.from(new Set(voices.map((voice) => voice.lang))).sort();
  const localLanguages = Array.from(new Set(localVoices.map((voice) => voice.lang))).sort();
  return {
    voices,
    localVoices,
    voiceCount: voices.length,
    localVoiceCount: localVoices.length,
    languages,
    localLanguages,
    hasNepaliVoice: voices.some((voice) => voice.lang.toLowerCase().startsWith("ne")),
    hasLocalNepaliVoice: localVoices.some((voice) => voice.lang.toLowerCase().startsWith("ne")),
  };
}

export function resolveLocalVoice(voices, preferredVoiceURI, preferredLocale = "en-US") {
  const localVoices = normalizeVoiceList(voices).filter((voice) => voice.localService);
  if (!localVoices.length) return null;
  const exact = localVoices.find((voice) => voice.voiceURI === preferredVoiceURI);
  if (exact) return exact;
  const locale = normalizeLocale(preferredLocale).toLowerCase();
  const language = locale.split("-")[0];
  return (
    localVoices.find((voice) => voice.lang.toLowerCase() === locale) ||
    localVoices.find((voice) => voice.lang.toLowerCase().split("-")[0] === language) ||
    localVoices.find((voice) => voice.default) ||
    localVoices[0]
  );
}

export function phraseCanUseLocalVoice(phraseId, capability) {
  if (phraseId === "nepali") return capability?.hasLocalNepaliVoice === true;
  return (capability?.localVoiceCount || 0) > 0;
}

export function safePermissionState(value) {
  return ["granted", "denied", "prompt"].includes(value) ? value : "unknown";
}

export function describeRecognitionError(value) {
  const code = String(value || "recognition_error").trim().toLowerCase();
  if (code === "network") {
    return "Browser speech recognition reported a network error. Its browser-managed service is unavailable here; use the text fallback or try a browser with speech recognition enabled. No audio is sent to SaathiOS by this settings test.";
  }
  if (["not-allowed", "service-not-allowed"].includes(code)) {
    return "Browser speech recognition is not allowed. Use the text fallback or review this browser's speech permission settings.";
  }
  if (code === "audio-capture") {
    return "Browser speech recognition could not use the microphone. Check microphone access or use the text fallback.";
  }
  return code === "" || code === "recognition_error"
    ? "Browser speech recognition failed. Use the text fallback."
    : "Browser speech recognition reported an unsupported error. Use the text fallback.";
}
