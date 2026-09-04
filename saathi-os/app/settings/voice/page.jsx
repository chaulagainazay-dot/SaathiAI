"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useVoiceOutput } from "@/components/voice/VoiceOutputProvider";
import { PLATFORM_CONTEXT_EVENT } from "@/lib/platform-client";
import {
  VOICE_TEST_PHRASES,
  phraseCanUseLocalVoice,
  resolveLocalVoice,
  safePermissionState,
  summarizeVoiceCapability,
} from "@/lib/voice-settings";
import {
  acquireInputClaim,
  openMicrophoneForClaim,
  subscribeInputOwner,
} from "@/lib/voice-session";

const card = {
  border: "1px solid var(--border-subtle, rgba(255,255,255,.1))",
  borderRadius: 16,
  padding: 18,
  background: "var(--surface-raised, rgba(16,22,38,.78))",
  display: "grid",
  gap: 12,
};
const row = { display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" };
const control = {
  border: "1px solid var(--border-subtle, rgba(255,255,255,.15))",
  background: "var(--surface-sunken, rgba(255,255,255,.05))",
  color: "inherit",
  borderRadius: 9,
  padding: "8px 10px",
};
const button = { ...control, cursor: "pointer", fontWeight: 650 };
const badge = (tone = "neutral") => ({
  borderRadius: 999,
  border: `1px solid ${tone === "ok" ? "#2dd4a855" : tone === "warn" ? "#f2b84b66" : "rgba(255,255,255,.16)"}`,
  background: tone === "ok" ? "#2dd4a818" : tone === "warn" ? "#f2b84b18" : "rgba(255,255,255,.05)",
  padding: "4px 9px",
  fontSize: 12,
});

function recognitionCtor() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

export default function VoiceSettingsPage() {
  const voiceOutput = useVoiceOutput();
  const [runtimeVoices, setRuntimeVoices] = useState([]);
  const [voicesLoaded, setVoicesLoaded] = useState(false);
  const [synthesisSupported, setSynthesisSupported] = useState(false);
  const [phraseId, setPhraseId] = useState("english");
  const [lastPhraseId, setLastPhraseId] = useState("");
  const [outputStatus, setOutputStatus] = useState("Idle — choose Play test to hear a local system voice.");
  const [permission, setPermission] = useState("unknown");
  const [inputStatus, setInputStatus] = useState("Microphone is off.");
  const [transcript, setTranscript] = useState("");
  const [recognitionSupported, setRecognitionSupported] = useState(false);
  const recognitionRef = useRef(null);
  const mediaRef = useRef(null);
  const utteranceRef = useRef(null);
  // R2.1-D6.5: settings capture is a *borrower* of the shared AudioInputOwner,
  // never a second owner. Both operations here take a claim, and the claim is
  // what stops the tracks and the recognizer — so preemption by the canonical
  // dock or by chat capture tears this surface down through the same path as
  // an explicit stop.
  const inputClaimRef = useRef(null);

  const capability = useMemo(() => summarizeVoiceCapability(runtimeVoices), [runtimeVoices]);
  const selectedVoice = useMemo(
    () => resolveLocalVoice(runtimeVoices, voiceOutput.preferences.browserVoiceURI, voiceOutput.preferences.locale),
    [runtimeVoices, voiceOutput.preferences.browserVoiceURI, voiceOutput.preferences.locale]
  );

  const stopTracks = useCallback(() => {
    mediaRef.current?.getTracks?.().forEach((track) => track.stop());
    mediaRef.current = null;
  }, []);

  /**
   * Give the microphone back.
   *
   * Releasing the claim stops the registered recognizer and every track the
   * claim opened; stopTracks() covers the local reference as well, so a
   * half-constructed test that never reached setRecognition still ends with
   * nothing capturing.
   */
  const releaseInputClaim = useCallback(() => {
    const claim = inputClaimRef.current;
    inputClaimRef.current = null;
    try { claim?.release?.(); } catch { /* already released */ }
    stopTracks();
  }, [stopTracks]);

  const stopInput = useCallback(() => {
    try { recognitionRef.current?.stop?.(); } catch { /* already stopped */ }
    recognitionRef.current = null;
    releaseInputClaim();
    setInputStatus("Microphone is off.");
  }, [releaseInputClaim]);

  const stopOutput = useCallback(async () => {
    window.speechSynthesis?.cancel();
    utteranceRef.current = null;
    await voiceOutput.stop({ remote: true });
    setOutputStatus("Voice output stopped.");
  }, [voiceOutput]);

  useEffect(() => {
    setSynthesisSupported(Boolean(window.speechSynthesis));
    setRecognitionSupported(Boolean(recognitionCtor()));
    let active = true;
    const synth = window.speechSynthesis;
    const refresh = () => {
      if (!active) return;
      const values = synth?.getVoices?.() || [];
      setRuntimeVoices(values);
      setVoicesLoaded(true);
    };
    refresh();
    synth?.addEventListener?.("voiceschanged", refresh);
    const timeout = window.setTimeout(refresh, 250);

    if (navigator.permissions?.query) {
      navigator.permissions.query({ name: "microphone" }).then((state) => {
        if (!active) return;
        setPermission(safePermissionState(state.state));
        state.onchange = () => active && setPermission(safePermissionState(state.state));
      }).catch(() => setPermission("unknown"));
    }

    const cleanup = () => {
      try { recognitionRef.current?.stop?.(); } catch { /* already stopped */ }
      recognitionRef.current = null;
      // Route change and unmount run this through the effect's teardown, and
      // logout runs it through PLATFORM_CONTEXT_EVENT. Releasing the claim is
      // what actually ends capture — dropping the local stream reference alone
      // would leave the registry believing this surface still owns the input.
      const claim = inputClaimRef.current;
      inputClaimRef.current = null;
      try { claim?.release?.(); } catch { /* already released */ }
      mediaRef.current?.getTracks?.().forEach((track) => track.stop());
      mediaRef.current = null;
      synth?.cancel?.();
    };
    const onContext = () => cleanup();
    window.addEventListener(PLATFORM_CONTEXT_EVENT, onContext);
    return () => {
      active = false;
      window.clearTimeout(timeout);
      synth?.removeEventListener?.("voiceschanged", refresh);
      window.removeEventListener(PLATFORM_CONTEXT_EVENT, onContext);
      cleanup();
    };
  }, []);

  useEffect(() => {
    if (!voicesLoaded || !selectedVoice) return;
    if (selectedVoice.voiceURI !== voiceOutput.preferences.browserVoiceURI) {
      voiceOutput.updatePreferences({
        browserVoiceURI: selectedVoice.voiceURI,
        locale: selectedVoice.lang,
      });
      setOutputStatus("The saved voice was unavailable; a local system fallback was selected.");
    }
  }, [selectedVoice, voiceOutput, voicesLoaded]);

  const playPhrase = useCallback(async (nextPhraseId) => {
    const phrase = VOICE_TEST_PHRASES[nextPhraseId];
    if (!phrase || !voiceOutput.preferences.enabled) {
      setOutputStatus("Voice output is disabled.");
      return;
    }
    if (!phraseCanUseLocalVoice(nextPhraseId, capability)) {
      setOutputStatus(nextPhraseId === "nepali"
        ? "No installed local Nepali voice was detected. Nepali playback was not attempted."
        : "No browser-reported local system voice is available.");
      return;
    }
    const synth = window.speechSynthesis;
    if (!synth || !selectedVoice) {
      setOutputStatus("Browser speech synthesis is unavailable.");
      return;
    }
    await voiceOutput.stop({ remote: true });
    synth.cancel();
    const utterance = new SpeechSynthesisUtterance(phrase.text);
    const rawVoice = synth.getVoices().find((item) => item.voiceURI === selectedVoice.voiceURI);
    if (!rawVoice || rawVoice.localService !== true) {
      setOutputStatus("The selected local voice disappeared. Refreshing the system voice list.");
      setRuntimeVoices(synth.getVoices());
      return;
    }
    utterance.voice = rawVoice;
    utterance.lang = nextPhraseId === "nepali" ? "ne-NP" : selectedVoice.lang;
    utterance.rate = voiceOutput.preferences.speakingRate;
    utterance.volume = voiceOutput.preferences.volume;
    utterance.onstart = () => setOutputStatus(`Playing ${phrase.label} test with ${selectedVoice.name}.`);
    utterance.onend = () => setOutputStatus(`${phrase.label} test completed.`);
    utterance.onerror = (event) => {
      if (["interrupted", "canceled"].includes(event.error)) {
        setOutputStatus("Voice output stopped.");
      } else {
        setOutputStatus(`Voice test failed safely: ${event.error || "browser playback error"}.`);
      }
    };
    utteranceRef.current = utterance;
    setLastPhraseId(nextPhraseId);
    synth.speak(utterance);
  }, [capability, selectedVoice, voiceOutput]);

  /**
   * Transient permission probe.
   *
   * It opens the device only to learn whether it can be opened and what the
   * browser actually applied, then hands the microphone straight back. The
   * claim is what guarantees that: released in `finally`, so a denial, a
   * device failure, a preemption mid-probe and a success all end with this
   * surface owning nothing.
   */
  const requestPermission = useCallback(async () => {
    if (!navigator.mediaDevices?.getUserMedia) {
      setPermission("unknown");
      setInputStatus("Microphone capture is unavailable. Use the text fallback.");
      return;
    }
    const claim = acquireInputClaim({ label: "settings.voice.permission-probe" });
    inputClaimRef.current = claim;
    try {
      // No constraint argument: the DEFAULT_MIC_CONSTRAINTS contract applies.
      const stream = await openMicrophoneForClaim(claim);
      // Bounded observation only: whether processing was applied, never the
      // device identifier or label.
      const applied = stream.getAudioTracks()[0]?.getSettings?.() || {};
      const flags = ["echoCancellation", "noiseSuppression", "autoGainControl"]
        .filter((key) => applied[key] === true);
      setPermission("granted");
      setInputStatus(
        `Microphone permission granted. Capture remains off. Browser applied: ${
          flags.length ? flags.join(", ") : "no processing reported"
        }.`
      );
    } catch (error) {
      const denied = /denied|not.?allowed|permission/i.test(String(error?.name || error?.message || ""));
      setPermission(denied ? "denied" : "unknown");
      setInputStatus(denied
        ? "Microphone permission was denied. Text fallback remains available."
        : "The microphone could not be opened. Text fallback remains available.");
    } finally {
      // Stops every track the claim opened and returns input ownership to idle.
      releaseInputClaim();
    }
  }, [releaseInputClaim]);

  const startInput = useCallback(async () => {
    if (!voiceOutput.preferences.inputEnabled) {
      setInputStatus("Voice input is disabled in preferences.");
      return;
    }
    const Ctor = recognitionCtor();
    if (!Ctor || !navigator.mediaDevices?.getUserMedia) {
      setInputStatus("Browser speech recognition is unavailable. Use the text fallback.");
      return;
    }
    let claim = null;
    try {
      await stopOutput();
      stopInput();
      // Acquiring preempts whoever holds the microphone — that is the registry
      // contract, and it is what keeps this from ever running concurrently
      // with the canonical dock or with chat capture.
      claim = acquireInputClaim({ label: "settings.voice.input-test" });
      inputClaimRef.current = claim;
      // No constraint argument: the DEFAULT_MIC_CONSTRAINTS contract applies.
      mediaRef.current = await openMicrophoneForClaim(claim);
      setPermission("granted");
      const recognition = new Ctor();
      // Bounded diagnostic: one utterance, never continuous, and deliberately
      // no onend restart. Nothing here submits a command or opens a backend
      // voice session — the transcript stays in page memory.
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = voiceOutput.preferences.locale;
      recognition.onstart = () => setInputStatus("Listening. Choose Stop microphone test at any time.");
      recognition.onresult = (event) => {
        // A result arriving after preemption belongs to a test this surface no
        // longer owns.
        if (!claim?.isActive?.()) return;
        let text = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          text += event.results[i][0]?.transcript || "";
        }
        setTranscript(text);
        setInputStatus("Transcript preview updated in memory only.");
      };
      recognition.onerror = (event) => {
        setInputStatus(`Microphone test failed safely: ${event.error || "recognition error"}.`);
        recognitionRef.current = null;
        releaseInputClaim();
      };
      recognition.onend = () => {
        recognitionRef.current = null;
        releaseInputClaim();
        setInputStatus((current) => current.startsWith("Microphone test failed") ? current : "Microphone test ended.");
      };
      // Registering on the claim is what lets a preemption stop this recognizer
      // rather than leave it running against a claim this surface has lost.
      claim.setRecognition(recognition);
      recognitionRef.current = recognition;
      recognition.start();
    } catch {
      setPermission("denied");
      recognitionRef.current = null;
      releaseInputClaim();
      setInputStatus("Microphone permission was denied or capture could not start. Text fallback remains available.");
    }
  }, [releaseInputClaim, stopInput, stopOutput, voiceOutput.preferences.inputEnabled, voiceOutput.preferences.locale]);

  /**
   * Preemption is not something this surface performs — it is something that
   * happens to it. When the canonical dock or chat capture acquires the shared
   * claim, the registry releases this one and stops its recognizer; without
   * this the page would keep displaying "Listening" over a microphone it no
   * longer holds.
   */
  useEffect(() => subscribeInputOwner(() => {
    const claim = inputClaimRef.current;
    if (!claim || claim.isActive()) return;
    inputClaimRef.current = null;
    recognitionRef.current = null;
    stopTracks();
    setInputStatus("Microphone test ended: another voice surface took the microphone.");
  }), [stopTracks]);

  const phrase = VOICE_TEST_PHRASES[phraseId];
  return (
    <div className="page shell-page" data-testid="voice-settings-page" style={{ maxWidth: 1180 }}>
      <header className="shell-page-header">
        <nav aria-label="Voice settings breadcrumb" style={row}>
          <Link href="/settings">Settings</Link><span aria-hidden="true">/</span>
          <Link href="/settings/voice" aria-current="page">Voice Settings</Link>
        </nav>
        <h1>Voice Settings</h1>
        <p style={{ color: "var(--text-muted)" }}>
          Discover and test browser-reported local system voices. Microphone access is always explicit and off by default at page load.
        </p>
        <div style={row} aria-label="Voice safety boundaries">
          <span style={badge("ok")}>LOCAL SYSTEM VOICES ONLY</span>
          <span style={badge()}>NO EXTERNAL VOICE PROVIDER</span>
          <span style={badge()}>NO BACKGROUND MICROPHONE</span>
          <span style={badge("warn")}>OWNER AUDIO REVIEW REQUIRED</span>
        </div>
      </header>

      <div style={{ display: "grid", gap: 16 }}>
        <section style={card} aria-labelledby="system-voice-status">
          <h2 id="system-voice-status">System voice status</h2>
          <div style={row}>
            <span style={badge(capability.localVoiceCount ? "ok" : "warn")}>Speech synthesis: {synthesisSupported ? "available" : "unavailable"}</span>
            <span style={badge()}>Detected voices: {voicesLoaded ? capability.voiceCount : "loading"}</span>
            <span style={badge()}>Local eligible voices: {voicesLoaded ? capability.localVoiceCount : "loading"}</span>
            <span style={badge()}>Languages: {voicesLoaded ? capability.languages.length : "loading"}</span>
            <span style={badge(capability.hasLocalNepaliVoice ? "ok" : "warn")}>Local Nepali voice: {capability.hasLocalNepaliVoice ? "detected" : "not detected"}</span>
          </div>
          <p style={{ color: "var(--text-muted)", margin: 0 }}>
            Counts come from this browser at runtime. SaathiOS does not hardcode installed voice or language totals. Voices not marked local by the browser are excluded from playback.
          </p>
        </section>

        <section style={card} aria-labelledby="voice-output-controls">
          <h2 id="voice-output-controls">Voice output controls</h2>
          <label style={row}>
            <input type="checkbox" checked={voiceOutput.preferences.enabled}
              onChange={(event) => voiceOutput.updatePreferences({ enabled: event.target.checked })} />
            Enable voice output
          </label>
          <label style={{ display: "grid", gap: 6 }}>
            <span>Local system voice</span>
            <select style={control} value={selectedVoice?.voiceURI || ""}
              disabled={!voiceOutput.preferences.enabled || capability.localVoiceCount === 0}
              onChange={(event) => {
                const next = capability.localVoices.find((item) => item.voiceURI === event.target.value);
                voiceOutput.updatePreferences({ browserVoiceURI: event.target.value, locale: next?.lang || "en-US" });
              }}>
              {!capability.localVoices.length && <option value="">No local system voice available</option>}
              {capability.localVoices.map((item) => <option key={item.voiceURI} value={item.voiceURI}>{item.name} · {item.lang}</option>)}
            </select>
          </label>
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: 12 }}>
            <label>Locale
              <input style={{ ...control, width: "100%" }} value={voiceOutput.preferences.locale}
                onChange={(event) => voiceOutput.updatePreferences({ locale: event.target.value })} />
            </label>
            <label>Rate · {voiceOutput.preferences.speakingRate.toFixed(1)}×
              <input style={{ width: "100%" }} type="range" min="0.5" max="2" step="0.1"
                value={voiceOutput.preferences.speakingRate}
                onChange={(event) => voiceOutput.updatePreferences({ speakingRate: Number(event.target.value) })} />
            </label>
            <label>Volume · {Math.round(voiceOutput.preferences.volume * 100)}%
              <input style={{ width: "100%" }} type="range" min="0" max="1" step="0.05"
                value={voiceOutput.preferences.volume}
                onChange={(event) => voiceOutput.updatePreferences({ volume: Number(event.target.value) })} />
            </label>
          </div>
          <div role="radiogroup" aria-label="Test phrase" style={row}>
            {Object.values(VOICE_TEST_PHRASES).map((item) => (
              <button key={item.id} type="button" style={button} aria-pressed={phraseId === item.id}
                onClick={() => setPhraseId(item.id)}>{item.label}</button>
            ))}
          </div>
          <p data-testid="voice-test-phrase" lang={phrase.locale}>{phrase.text}</p>
          {phraseId === "nepali" && !capability.hasLocalNepaliVoice && (
            <p role="status" style={{ color: "#f2b84b" }}>No installed local Nepali voice was detected. The phrase remains visible, but SaathiOS will not claim Nepali audio support.</p>
          )}
          <div style={row}>
            <button type="button" style={button} onClick={() => playPhrase(phraseId)}>Play test</button>
            <button type="button" style={button} onClick={stopOutput}>Stop test</button>
            <button type="button" style={button} disabled={!lastPhraseId} onClick={() => playPhrase(lastPhraseId)}>Replay last test</button>
          </div>
          <p role="status" aria-live="polite" data-testid="voice-output-status">{outputStatus}</p>
        </section>

        <section style={card} aria-labelledby="voice-input-controls">
          <h2 id="voice-input-controls">Voice input controls</h2>
          <div style={row}>
            <span style={badge(recognitionSupported ? "ok" : "warn")}>Speech recognition: {recognitionSupported ? "browser available" : "unavailable"}</span>
            <span style={badge(permission === "granted" ? "ok" : permission === "denied" ? "warn" : "neutral")}>Microphone permission: {permission}</span>
            <span style={badge()}>Capture: explicit test only</span>
            <span style={badge()}>Ownership: shared input claim</span>
          </div>
          <label style={row}>
            <input type="checkbox" checked={voiceOutput.preferences.inputEnabled}
              onChange={(event) => {
                if (!event.target.checked) stopInput();
                voiceOutput.updatePreferences({ inputEnabled: event.target.checked });
              }} />
            Enable voice input controls
          </label>
          <div style={row}>
            <button type="button" style={button} onClick={requestPermission}>Request microphone permission</button>
            <button type="button" style={button} onClick={startInput} disabled={!voiceOutput.preferences.inputEnabled}>Start microphone test</button>
            <button type="button" style={button} onClick={stopInput}>Stop microphone test</button>
          </div>
          <label style={{ display: "grid", gap: 6 }}>
            Transcript preview / text fallback
            <textarea style={{ ...control, minHeight: 90 }} value={transcript}
              onChange={(event) => setTranscript(event.target.value)}
              placeholder="Recognized words appear here, or type to verify the fallback." />
          </label>
          <p role="status" aria-live="polite">{inputStatus}</p>
        </section>

        <section style={card} aria-labelledby="interruption-behavior">
          <h2 id="interruption-behavior">Interruption behavior</h2>
          <p><strong>Push-to-interrupt:</strong> starting a microphone test stops current SaathiOS/browser playback before capture begins.</p>
          <p><strong>Stop:</strong> Stop test cancels speech; Stop microphone test stops recognition and releases acquired media tracks.</p>
          <p><strong>Shared microphone ownership:</strong> both microphone operations on this page borrow the
          same system-wide input claim the Live Voice dock and chat capture use. Starting one here stops
          whichever surface held the microphone, and a surface started elsewhere stops the test here. At most
          one capture is ever open.</p>
          <p style={{ color: "#f2b84b" }}><strong>Full acoustic barge-in is not implemented.</strong> The system does not continuously listen for speech over its own output.</p>
        </section>

        <section style={card} aria-labelledby="language-and-privacy">
          <h2 id="language-and-privacy">Language, privacy, and limitations</h2>
          <ul style={{ margin: 0, paddingLeft: 20, lineHeight: 1.7 }}>
            <li>Detected language tags: {capability.languages.length ? capability.languages.join(", ") : "none reported yet"}.</li>
            <li>Nepali audio is available only when this browser reports an eligible local Nepali voice.</li>
            <li>No voice recording or transcript is persisted by this settings test; the preview lives only in page memory.</li>
            <li>SaathiOS sends no settings-test audio or transcript to its API and configures no external voice provider.</li>
            <li>Browser speech recognition is browser-dependent. Review the browser&apos;s own speech-service privacy behavior before enabling it; use the text fallback when strict local processing cannot be verified.</li>
            <li>Saved preferences contain only enablement, voice identifier, locale, rate, and volume—never audio, transcript, credential, or account data.</li>
          </ul>
          <p style={{ margin: 0 }}><Link href="/chat">Open Chat</Link> · <Link href="/settings">Back to Settings</Link></p>
        </section>
      </div>
    </div>
  );
}
