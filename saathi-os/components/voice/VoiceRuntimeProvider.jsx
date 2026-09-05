"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useReducer,
  useRef,
  useState,
} from "react";
import { usePathname } from "next/navigation";
import { getToken, PLATFORM_CONTEXT_EVENT } from "@/lib/platform-client";
import { useVoiceOutput } from "./VoiceOutputProvider";
import {
  INITIAL_VOICE_RUNTIME,
  getRecognitionCtor,
  micButtonLabel,
  voiceRuntimeActions,
  voiceRuntimeReducer,
} from "@/lib/voice-runtime";
import {
  acquireInputClaim,
  openMicrophoneForClaim,
  forceReleaseInput,
  createLocalStreamingStt,
} from "@/lib/voice-session";
import { useVoiceSession } from "./VoiceSessionProvider";

const VoiceRuntimeContext = createContext(null);

export function VoiceRuntimeProvider({ children }) {
  const [token, setToken] = useState("");
  const [runtime, dispatch] = useReducer(
    voiceRuntimeReducer,
    INITIAL_VOICE_RUNTIME
  );
  const [busy, setBusy] = useState(false);
  const [inputMode, setInputMode] = useState("BROWSER");
  const recognitionRef = useRef(null);
  const sessionIdRef = useRef("");
  const sessionCreateRef = useRef(null);
  const sessionEpochRef = useRef(0);
  const mediaStreamRef = useRef(null);
  const inputClaimRef = useRef(null);
  const voiceOutput = useVoiceOutput();
  const voiceSession = useVoiceSession();
  // Read the session through a ref inside teardown paths. `voiceSession` is a
  // fresh object on every published snapshot, so a cleanup callback that closes
  // over it directly changes identity whenever voice state changes — and the
  // effect it belongs to then re-runs its own cleanup, which publishes again.
  const voiceSessionRef = useRef(voiceSession);
  voiceSessionRef.current = voiceSession;

  useEffect(() => {
    sessionIdRef.current = runtime.sessionId;
  }, [runtime.sessionId]);

  const cleanupLocal = useCallback(() => {
    try {
      recognitionRef.current?.stop?.();
    } catch {
      /* ignore */
    }
    recognitionRef.current = null;
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    if (inputClaimRef.current) {
      try {
        inputClaimRef.current.release();
      } catch {
        /* ignore */
      }
      inputClaimRef.current = null;
    }
    try {
      voiceSessionRef.current?.endInput?.("USER_CANCEL");
    } catch {
      /* ignore */
    }
  }, []);

  const hardReset = useCallback(() => {
    sessionEpochRef.current += 1;
    sessionCreateRef.current = null;
    sessionIdRef.current = "";
    cleanupLocal();
    forceReleaseInput("SESSION_CLOSE");
    try {
      voiceSessionRef.current?.interrupt?.("SESSION_CLOSE");
    } catch {
      /* ignore */
    }
    dispatch({ type: "RESET" });
    setBusy(false);
  }, [cleanupLocal]);

  useEffect(() => {
    try {
      const saved = window.localStorage.getItem("saathi_voice_input_mode_v1");
      if (saved === "LOCAL" || saved === "BROWSER") setInputMode(saved);
    } catch { /* optional preference */ }
    setToken(getToken());
    const onContext = (event) => {
      hardReset();
      setToken(event?.detail?.token ?? getToken());
    };
    window.addEventListener(PLATFORM_CONTEXT_EVENT, onContext);
    return () => {
      window.removeEventListener(PLATFORM_CONTEXT_EVENT, onContext);
      sessionEpochRef.current += 1;
      sessionCreateRef.current = null;
      cleanupLocal();
    };
  }, [cleanupLocal, hardReset]);

  const encodePcm = useCallback((pcm) => {
    const bytes = new Uint8Array(pcm.length * 2);
    const view = new DataView(bytes.buffer);
    for (let i = 0; i < pcm.length; i += 1) {
      const sample = Math.max(-1, Math.min(1, Number(pcm[i]) || 0));
      view.setInt16(i * 2, sample < 0 ? sample * 32768 : sample * 32767, true);
    }
    let binary = "";
    const step = 0x8000;
    for (let i = 0; i < bytes.length; i += step) binary += String.fromCharCode(...bytes.subarray(i, i + step));
    return btoa(binary);
  }, []);

  const setLocalMode = useCallback((mode) => {
    const next = mode === "LOCAL" ? "LOCAL" : "BROWSER";
    setInputMode(next);
    try { window.localStorage.setItem("saathi_voice_input_mode_v1", next); } catch { /* optional */ }
  }, []);

  // Shell mounts this provider above the router, so a client-side navigation
  // does not unmount it and the microphone stream would stay hot on an
  // unrelated page. Release capture on route change; skip the first render.
  const pathname = usePathname();
  const listeningPathRef = useRef(pathname);
  useEffect(() => {
    if (listeningPathRef.current === pathname) return;
    listeningPathRef.current = pathname;
    hardReset();
  }, [pathname, hardReset]);

  const ensureSession = useCallback(
    (activeToken) => {
      if (sessionIdRef.current) return sessionIdRef.current;
      if (sessionCreateRef.current) return sessionCreateRef.current.promise;
      const epoch = sessionEpochRef.current;
      const promise = (async () => {
        const created = await voiceRuntimeActions.createSession(activeToken, {
          input_mode: "toggle",
          stt_provider: inputMode === "LOCAL" ? "whisper_compatible" : (getRecognitionCtor() ? "browser" : "auto"),
          voice_profile_id: "yeti_teacher",
          yeti_mode: "general",
        });
        const id = created?.session?.session_id;
        if (!id) throw new Error("Voice session is unavailable.");
        if (epoch !== sessionEpochRef.current) {
          // A request that finishes after logout/route teardown must not become
          // active. Finish the server row through the normal bounded endpoint.
          try { await voiceRuntimeActions.finish(activeToken, id); } catch { /* best effort */ }
          throw new Error("Voice session creation was cancelled.");
        }
        dispatch({ type: "SESSION", session: created.session });
        sessionIdRef.current = id;
        return id;
      })();
      sessionCreateRef.current = { epoch, promise };
      promise.then(
        () => { if (sessionCreateRef.current?.promise === promise) sessionCreateRef.current = null; },
        () => { if (sessionCreateRef.current?.promise === promise) sessionCreateRef.current = null; },
      );
      return promise;
    },
    [inputMode]
  );

  const refreshHistory = useCallback(
    async (activeToken) => {
      try {
        const listed = await voiceRuntimeActions.listSessions(activeToken);
        dispatch({ type: "HISTORY", history: listed.sessions || [] });
      } catch {
        /* non-fatal */
      }
    },
    []
  );

  const speakAssistantText = useCallback(
    async (text) => {
      if (!text || !voiceOutput?.speak) return;
      try {
        // User already pressed the mic — that is the explicit activation gesture.
        // Never autoplay on page load (this path only runs after a final transcript).
        const ok = await voiceOutput.speak(text, {
          profileId: "yeti_teacher",
          source: "voice_runtime",
        });
        if (ok && voiceOutput.play) {
          await voiceOutput.play();
        }
      } catch {
        /* SpeechService path may be busy; UI still shows transcript */
      }
    },
    [voiceOutput]
  );

  const submitFinalTranscript = useCallback(
    async (activeToken, sessionId, text) => {
      const result = await voiceRuntimeActions.transcript(activeToken, sessionId, {
        text,
        is_final: true,
        partial: false,
      });
      dispatch({ type: "SESSION", session: result.session });
      const assistant = result.turn?.assistant_text || "";
      if (assistant) {
        await speakAssistantText(assistant);
      }
      await refreshHistory(activeToken);
      return result;
    },
    [refreshHistory, speakAssistantText]
  );

  const startBrowserRecognition = useCallback(
    async (activeToken, sessionId) => {
      const Ctor = getRecognitionCtor();
      if (!Ctor) {
        throw new Error(
          "Browser speech recognition is unavailable. Use a Chromium browser or install a local STT provider."
        );
      }
      // V-NEXT-1: exclusive input claim via VoiceSessionManager (single owner).
      await voiceSession?.beginInput?.({
        label: "VoiceRuntimeProvider",
        stopOutputFirst: true,
        startPipeline: false,
      });
      let claim = voiceSession?.manager?.getInputClaim?.() || null;
      if (!claim) {
        claim = acquireInputClaim({ label: "VoiceRuntimeProvider" });
      }
      inputClaimRef.current = claim;

      try {
        mediaStreamRef.current = await openMicrophoneForClaim(claim, { audio: true });
      } catch {
        await voiceRuntimeActions.listen(activeToken, sessionId, {
          mode: "toggle",
          permission_granted: false,
        });
        claim.release();
        inputClaimRef.current = null;
        throw new Error("Microphone permission is required to talk.");
      }

      await voiceRuntimeActions.listen(activeToken, sessionId, {
        mode: "toggle",
        permission_granted: true,
      });

      const recognition = new Ctor();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = "en-US";

      recognition.onresult = async (event) => {
        if (!claim.isActive()) return;
        let interim = "";
        let finalText = "";
        for (let i = event.resultIndex; i < event.results.length; i += 1) {
          const piece = event.results[i][0]?.transcript || "";
          if (event.results[i].isFinal) finalText += piece;
          else interim += piece;
        }
        if (interim) {
          voiceSession?.setTranscript?.({ partial: interim });
          try {
            const partial = await voiceRuntimeActions.transcript(
              activeToken,
              sessionId,
              { text: interim, is_final: false, partial: true }
            );
            dispatch({ type: "SESSION", session: partial.session });
          } catch {
            dispatch({
              type: "LOCAL_RECORDING",
              recording: true,
            });
          }
        }
        if (finalText.trim()) {
          setBusy(true);
          voiceSession?.setTranscript?.({ final: finalText.trim(), partial: "" });
          voiceSession?.setThinking?.(true);
          try {
            await submitFinalTranscript(activeToken, sessionId, finalText.trim());
          } catch (error) {
            dispatch({
              type: "ERROR",
              error: String(error?.message || error),
            });
            voiceSession?.setError?.(String(error?.message || error));
          } finally {
            setBusy(false);
            voiceSession?.setThinking?.(false);
            dispatch({ type: "LOCAL_RECORDING", recording: false });
            cleanupLocal();
          }
        }
      };

      recognition.onerror = (event) => {
        dispatch({
          type: "ERROR",
          error: event?.error || "speech_recognition_error",
          message: "Speech recognition failed. Retry with the microphone button.",
        });
        cleanupLocal();
        setBusy(false);
      };

      recognition.onend = () => {
        dispatch({ type: "LOCAL_RECORDING", recording: false });
      };

      claim.setRecognition(recognition);
      recognitionRef.current = recognition;
      recognition.start();
      try {
        await voiceSession?.manager?.armVad?.({ bargeInMode: false });
      } catch { /* VAD optional */ }
      dispatch({ type: "LOCAL_RECORDING", recording: true, listening: true });
    },
    [cleanupLocal, submitFinalTranscript, voiceSession]
  );

  const startLocalRecognition = useCallback(async (activeToken, sessionId) => {
    const factory = () => createLocalStreamingStt({
      modelId: "tiny",
      engineId: "faster-whisper",
      sampleRate: 16000,
      minSamplesForPartial: 16000 * 30,
      partialEveryMs: 30_000,
      transcribeFn: async ({ pcm, sampleRate, language, isFinal }) => {
        if (!isFinal) return { text: "", isFinal: false, language };
        const result = await voiceRuntimeActions.stt(activeToken, sessionId, {
          audio_base64: encodePcm(pcm),
          sample_rate: sampleRate,
          language: language || "en",
        });
        return result.transcript || { text: "", isFinal: true, language };
      },
    });
    await voiceSession?.beginInput({ label: "VoiceRuntimeProvider", stopOutputFirst: true, startPipeline: false });
    await voiceSession?.manager?.startStreamingPipeline?.({ sttMode: "local", localSttFactory: factory });
    await voiceSession?.armVad?.({ bargeInMode: false });
    dispatch({ type: "LOCAL_RECORDING", recording: true, listening: true });
  }, [encodePcm, voiceSession]);

  const interrupt = useCallback(async () => {
    const activeToken = token || getToken();
    const sessionId = sessionIdRef.current;
    if (!activeToken || !sessionId) return;
    setBusy(true);
    try {
      await voiceSession?.interrupt?.("USER_CANCEL");
      await voiceOutput?.stop?.();
      const result = await voiceRuntimeActions.interrupt(activeToken, sessionId);
      dispatch({ type: "SESSION", session: result.session });
      // Immediately resume listening after barge-in (manual interrupt path)
      await startBrowserRecognition(activeToken, sessionId);
    } catch (error) {
      dispatch({ type: "ERROR", error: String(error?.message || error) });
    } finally {
      setBusy(false);
    }
  }, [startBrowserRecognition, token, voiceOutput, voiceSession]);

  const localFinalRef = useRef("");
  useEffect(() => {
    const manager = voiceSession?.manager;
    if (inputMode !== "LOCAL" || !manager?.setTurnFinalHandler) return undefined;
    const unset = manager.setTurnFinalHandler((turn) => {
      const text = String(turn?.text || "").trim();
      const activeToken = token || getToken();
      const sid = sessionIdRef.current;
      const key = `${sid}:${turn?.utteranceId || turn?.sequence || ""}`;
      const hasIdentity = Boolean(turn?.utteranceId || turn?.sequence);
      if (!text || !activeToken || !sid || (hasIdentity && localFinalRef.current === key)) return;
      localFinalRef.current = key;
      setBusy(true);
      void submitFinalTranscript(activeToken, sid, text).finally(() => setBusy(false));
    });
    return unset;
  }, [inputMode, submitFinalTranscript, token, voiceSession]);

  const toggleMic = useCallback(async () => {
    const activeToken = token || getToken();
    if (!activeToken) {
      dispatch({
        type: "ERROR",
        error: "Sign in required",
        message: "Sign in to use live voice.",
      });
      return;
    }
    if (runtime.recording) {
      localFinalRef.current = "";
      cleanupLocal();
      if (sessionIdRef.current) {
        try {
          await voiceRuntimeActions.stop(activeToken, sessionIdRef.current);
        } catch {
          /* ignore */
        }
      }
      dispatch({ type: "LOCAL_RECORDING", recording: false });
      return;
    }
    if (runtime.speaking) {
      await interrupt();
      return;
    }
    setBusy(true);
    try {
      // VOICE_INPUT_INTERRUPTS_OUTPUT via canonical VoiceSessionManager.
      // Manual mic-start interrupt — not acoustic barge-in / full duplex.
      // Source contract: await voiceOutput.stop immediately before ensureSession.
      await voiceSession?.openSession?.({
        sessionId: sessionIdRef.current || undefined,
        inputProvider: inputMode.toLowerCase(),
        outputProvider: "platform",
      });
      await voiceOutput?.stop?.();
      const sessionId = await ensureSession(activeToken);
      if (inputMode === "LOCAL") {
        await startLocalRecognition(activeToken, sessionId);
      } else {
        await startBrowserRecognition(activeToken, sessionId);
      }
      await refreshHistory(activeToken);
    } catch (error) {
      dispatch({
        type: "ERROR",
        error: String(error?.message || error),
        message: String(error?.message || error),
      });
      cleanupLocal();
    } finally {
      setBusy(false);
    }
  }, [
    cleanupLocal,
    ensureSession,
    interrupt,
    refreshHistory,
    runtime.recording,
    runtime.speaking,
    startBrowserRecognition,
    startLocalRecognition,
    inputMode,
    token,
    voiceSession,
    voiceOutput,
  ]);

  const retry = useCallback(async () => {
    hardReset();
    await toggleMic();
  }, [hardReset, toggleMic]);

  const value = {
    token,
    runtime,
    busy,
    toggleMic,
    interrupt,
    retry,
    hardReset,
    inputMode,
    setInputMode: setLocalMode,
    micLabel: micButtonLabel(runtime),
  };

  return (
    <VoiceRuntimeContext.Provider value={value}>
      {children}
    </VoiceRuntimeContext.Provider>
  );
}

export function useVoiceRuntime() {
  const context = useContext(VoiceRuntimeContext);
  if (!context) {
    throw new Error("useVoiceRuntime must be used inside VoiceRuntimeProvider");
  }
  return context;
}
