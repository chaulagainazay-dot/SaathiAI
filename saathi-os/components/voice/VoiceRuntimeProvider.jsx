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
  const recognitionRef = useRef(null);
  const sessionIdRef = useRef("");
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
    setToken(getToken());
    const onContext = (event) => {
      hardReset();
      setToken(event?.detail?.token ?? getToken());
    };
    window.addEventListener(PLATFORM_CONTEXT_EVENT, onContext);
    return () => {
      window.removeEventListener(PLATFORM_CONTEXT_EVENT, onContext);
      cleanupLocal();
    };
  }, [cleanupLocal, hardReset]);

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
    async (activeToken) => {
      if (sessionIdRef.current) return sessionIdRef.current;
      const created = await voiceRuntimeActions.createSession(activeToken, {
        input_mode: "toggle",
        stt_provider: getRecognitionCtor() ? "browser" : "auto",
        voice_profile_id: "yeti_teacher",
        yeti_mode: "general",
      });
      dispatch({ type: "SESSION", session: created.session });
      sessionIdRef.current = created.session.session_id;
      return created.session.session_id;
    },
    []
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
      await voiceSession?.beginInput?.({ label: "VoiceRuntimeProvider", stopOutputFirst: true });
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
        inputProvider: "browser",
        outputProvider: "platform",
      });
      await voiceOutput?.stop?.();
      const sessionId = await ensureSession(activeToken);
      await startBrowserRecognition(activeToken, sessionId);
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
