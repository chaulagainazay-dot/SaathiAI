"use client";

/**
 * Browser recognition has exactly one owner.
 *
 * This provider used to construct its own `SpeechRecognition` while
 * `beginInput()` started the VoiceSessionManager's streaming pipeline, which
 * constructs one too. Two recognizers ran against one microphone: two result
 * streams, two `onend` restart loops, two claims on the same capture, and a
 * final transcript that could arrive from either. Ownership now sits entirely
 * with the pipeline — the authority path that also owns turn coordination,
 * privacy classification and teardown — and this provider subscribes to it.
 *
 * The capability gate stays truthful. If the browser has no native speech
 * recognition, voice reports unavailable: no microphone is opened for a
 * session that cannot transcribe, and the deterministic mock adapter is never
 * substituted in a product surface.
 */

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
import { getToken, setToken as setPlatformToken, ensurePlatformSession, PLATFORM_CONTEXT_EVENT } from "@/lib/platform-client";
import { exchangePlatformSession, hasSessionToken } from "@/lib/api";
import { withPlatformSessionRecovery } from "@/lib/voice-session/platform-session-recovery";
import { useVoiceOutput } from "./VoiceOutputProvider";
import {
  INITIAL_VOICE_RUNTIME,
  getRecognitionCtor,
  micButtonLabel,
  voiceRuntimeActions,
  voiceRuntimeReducer,
} from "@/lib/voice-runtime";
import {
  openMicrophoneForClaim,
  forceReleaseInput,
  createTurnBinding,
  createSessionFinalizer,
  evaluateRecognitionSupport,
  RECOGNITION_UNSUPPORTED_MESSAGE,
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
  const sessionIdRef = useRef("");
  const ensureSessionFlightRef = useRef(null);
  const authEpochRef = useRef(0);
  const mediaStreamRef = useRef(null);
  const inputClaimRef = useRef(null);
  // The binding to the authoritative transcript stream, one generation at a
  // time. Submission rules live in the binding, not here.
  const bindingRef = useRef(null);
  // Read the token from a ref in teardown paths: cleanup runs during logout,
  // when the state value has already moved on but the *old* token is the one
  // that can still terminate the old session.
  const tokenRef = useRef("");
  tokenRef.current = token;
  const voiceOutput = useVoiceOutput();
  const voiceSession = useVoiceSession();

  // Terminal cleanup of backend sessions. `POST /stop` only moves input_state;
  // a session leaves LISTENING through `POST /finish`, and nothing used to
  // call it — so every abandoned session stayed active until the per-user
  // budget refused new ones.
  const finalizerRef = useRef(null);
  if (!finalizerRef.current) {
    finalizerRef.current = createSessionFinalizer({
      finish: (activeToken, sessionId, options) =>
        voiceRuntimeActions.finish(activeToken, sessionId, options),
      onPendingChange: (pending) => dispatch({ type: "CLEANUP_PENDING", pending }),
    });
  }

  /** Terminate the backend session this surface is abandoning. */
  const finalizeBackendSession = useCallback((reason, overrideToken, keepalive = false) => {
    const sessionId = sessionIdRef.current;
    if (!sessionId) return "skipped";
    const outcome = finalizerRef.current.finalize({
      token: overrideToken || tokenRef.current || getToken(),
      sessionId,
      reason,
      keepalive,
    });
    // The id is abandoned either way; a failed request stays pending in the
    // finalizer rather than pretending the session was closed.
    sessionIdRef.current = "";
    return outcome;
  }, []);
  const invalidateSessionCreation = useCallback((reason = "SESSION_INVALIDATED") => {
    authEpochRef.current += 1;
    ensureSessionFlightRef.current = null;
    if (sessionIdRef.current) finalizeBackendSession(reason, tokenRef.current || getToken());
  }, [finalizeBackendSession]);
  // Read the session through a ref inside teardown paths. `voiceSession` is a
  // fresh object on every published snapshot, so a cleanup callback that closes
  // over it directly changes identity whenever voice state changes — and the
  // effect it belongs to then re-runs its own cleanup, which publishes again.
  const voiceSessionRef = useRef(voiceSession);
  voiceSessionRef.current = voiceSession;

  useEffect(() => {
    sessionIdRef.current = runtime.sessionId;
  }, [runtime.sessionId]);

  const detachPipelineSubscriptions = useCallback(() => {
    try {
      bindingRef.current?.detach();
    } catch {
      /* ignore */
    }
    bindingRef.current = null;
  }, []);

  const cleanupLocal = useCallback(() => {
    detachPipelineSubscriptions();
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
      // The manager owns the recognizer; ending input is what stops capture.
      voiceSessionRef.current?.endInput?.("USER_CANCEL");
    } catch {
      /* ignore */
    }
  }, [detachPipelineSubscriptions]);

  const hardReset = useCallback(() => {
    invalidateSessionCreation("SESSION_CLOSE");
    cleanupLocal();
    finalizeBackendSession("SESSION_CLOSE");
    forceReleaseInput("SESSION_CLOSE");
    try {
      voiceSessionRef.current?.interrupt?.("SESSION_CLOSE");
    } catch {
      /* ignore */
    }
    dispatch({ type: "RESET" });
    setBusy(false);
  }, [cleanupLocal, finalizeBackendSession, invalidateSessionCreation]);

  useEffect(() => {
    setToken(getToken());
    if (hasSessionToken() && !getToken()) {
      void ensurePlatformSession();
    }
    const onContext = (event) => {
      // Finalize with the outgoing token: after a logout or workspace switch
      // the new token cannot terminate the previous context's session.
      invalidateSessionCreation("LOGOUT");
      finalizeBackendSession("LOGOUT", tokenRef.current);
      hardReset();
      setToken(event?.detail?.token ?? getToken());
    };
    // A hard navigation or a closed tab runs no React cleanup, so the session
    // would be stranded with nothing left to send the terminal request. This
    // is the last moment the page can still speak; keepalive lets the request
    // outlive it.
    const onPageHide = () => {
      invalidateSessionCreation("PAGE_HIDE");
      finalizeBackendSession("PAGE_HIDE", tokenRef.current, true);
    };
    window.addEventListener(PLATFORM_CONTEXT_EVENT, onContext);
    window.addEventListener("pagehide", onPageHide);
    return () => {
      window.removeEventListener(PLATFORM_CONTEXT_EVENT, onContext);
      window.removeEventListener("pagehide", onPageHide);
      cleanupLocal();
      invalidateSessionCreation("UNMOUNT");
      finalizeBackendSession("UNMOUNT");
    };
  }, [cleanupLocal, finalizeBackendSession, hardReset, invalidateSessionCreation]);

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

  // Engine faults are published by the manager, which reports one fault once.
  // Mirror it into runtime state a single time so a repeated publish of the
  // same message cannot restart the reducer.
  const mirroredErrorRef = useRef("");
  const publishedError = voiceSession?.session?.error || "";
  useEffect(() => {
    if (!publishedError || publishedError === mirroredErrorRef.current) return;
    mirroredErrorRef.current = publishedError;
    dispatch({ type: "ERROR", error: publishedError, message: publishedError });
  }, [publishedError]);

  // A recognition attempt that ended in a fatal engine fault has already
  // released the microphone locally by the time this runs — the manager owns
  // that half. What it cannot do is end the *backend* session, because it has
  // no token and no session id by design. This is that half.
  //
  // The callback runs synchronously inside the manager's teardown, which is
  // what makes it correct: `finalizeBackendSession` reads the id of the
  // session that just failed and clears it in the same tick, so a retry
  // starting immediately afterwards cannot have its own new id finished by an
  // older failure. A failed request stays pending in the finalizer rather than
  // reporting a clean close, and it cannot disturb the published fault.
  const voiceManager = voiceSession?.manager || null;
  useEffect(() => {
    if (!voiceManager?.onTerminalInput) return undefined;
    return voiceManager.onTerminalInput(() => {
      finalizeBackendSession("RECOGNITION_ERROR");
    });
  }, [voiceManager, finalizeBackendSession]);

  const ensureSession = useCallback(
    async (activeToken) => {
      if (sessionIdRef.current) return sessionIdRef.current;
      if (ensureSessionFlightRef.current) return ensureSessionFlightRef.current.promise;
      const epoch = authEpochRef.current;
      // The current backend validates known session fields but has no
      // idempotency contract; this stable client id documents the request
      // boundary for a future server-side key without changing that schema.
      const requestId = `voice-session-${epoch}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
      const promise = (async () => {
      // D17: the derived platform session carries a one-hour idle TTL, and the
      // owner may press the microphone long after the tab last spoke to the
      // backend. If creation is refused with the bounded SESSION_INVALID code —
      // and only then — exchange the still-valid canonical session for a fresh
      // derived one and retry this creation exactly once. The microphone is not
      // opened until after this returns.
      const created = await withPlatformSessionRecovery(
        activeToken,
        (tok) => voiceRuntimeActions.createSession(tok, {
          idempotency_key: requestId,
          input_mode: "toggle",
          stt_provider: getRecognitionCtor() ? "browser" : "auto",
          voice_profile_id: "yeti_teacher",
          yeti_mode: "general",
        }),
        {
          exchange: exchangePlatformSession,
          storeToken: (t) => { setPlatformToken(t); setToken(t); },
          clearToken: () => setPlatformToken(""),
        },
      );
      const sessionId = created?.session?.session_id;
      if (!sessionId) throw new Error("VOICE_SESSION_CREATE_INVALID");
      if (epoch !== authEpochRef.current || ensureSessionFlightRef.current?.epoch !== epoch) {
        finalizerRef.current.finalize({ token: activeToken, sessionId, reason: "SESSION_INVALIDATED" });
        return null;
      }
      dispatch({ type: "SESSION", session: created.session });
      sessionIdRef.current = sessionId;
      return sessionId;
      })();
      ensureSessionFlightRef.current = { epoch, promise };
      void promise.then(() => {
        if (ensureSessionFlightRef.current?.promise === promise) ensureSessionFlightRef.current = null;
      }, () => {
        if (ensureSessionFlightRef.current?.promise === promise) ensureSessionFlightRef.current = null;
      });
      return promise;
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

  /** One finalized turn → one backend submission → one spoken answer. */
  const runFinalTurn = useCallback(
    async (activeToken, sessionId, text) => {
      setBusy(true);
      voiceSessionRef.current?.setTranscript?.({ final: text, partial: "" });
      voiceSessionRef.current?.setThinking?.(true);
      try {
        await submitFinalTranscript(activeToken, sessionId, text);
      } catch (error) {
        dispatch({ type: "ERROR", error: String(error?.message || error) });
        voiceSessionRef.current?.setError?.(String(error?.message || error));
      } finally {
        setBusy(false);
        voiceSessionRef.current?.setThinking?.(false);
        dispatch({ type: "LOCAL_RECORDING", recording: false });
        cleanupLocal();
      }
    },
    [cleanupLocal, submitFinalTranscript]
  );

  /**
   * Subscribe to the authoritative pipeline for this input generation.
   *
   * Restarting replaces the subscription rather than adding one: the previous
   * generation is detached first, so five talk cycles leave one subscription,
   * not five. Every event is checked against the epoch it was opened with, so
   * a late event from a session the user already ended submits nothing.
   */
  const attachPipelineSubscriptions = useCallback(
    ({ manager, activeToken, sessionId, epoch }) => {
      detachPipelineSubscriptions();
      bindingRef.current = createTurnBinding({
        manager,
        epoch,
        onPartial: (partial) => {
          // Display and backend partial only. A partial is never executable
          // and never a submission: it produces no turn on the server.
          voiceRuntimeActions
            .transcript(activeToken, sessionId, {
              text: partial.text,
              is_final: false,
              partial: true,
            })
            .then((res) => dispatch({ type: "SESSION", session: res.session }))
            .catch(() => dispatch({ type: "LOCAL_RECORDING", recording: true }));
        },
        onBackchannel: () => {
          // Finalized, shown, and deliberately not submitted.
          dispatch({ type: "LOCAL_RECORDING", recording: false });
        },
        onFinalTurn: (turn) => {
          void runFinalTurn(activeToken, sessionId, turn.text);
        },
      });
    },
    [detachPipelineSubscriptions, runFinalTurn]
  );

  /**
   * Open capture. The manager builds and owns the recognizer; this only gates,
   * claims the microphone for VAD, and subscribes.
   */
  const startListening = useCallback(
    async (activeToken, sessionId) => {
      const manager = voiceSession?.manager || null;
      if (!manager) {
        throw new Error("Voice session is unavailable in this context.");
      }
      // Truthful gate: no microphone is opened for a session that cannot
      // produce a transcript, and no stand-in adapter is substituted.
      const gate = evaluateRecognitionSupport({
        recognitionCtor: getRecognitionCtor(),
      });
      if (!gate.supported) throw new Error(gate.reason);

      // V-NEXT-1: exclusive input claim, and the single streaming recognizer,
      // both via VoiceSessionManager.
      await voiceSession.beginInput({
        label: "VoiceRuntimeProvider",
        stopOutputFirst: true,
      });

      // Re-check against what the engine actually selected. The deterministic
      // adapter exists for tests; reaching it from a product surface would
      // publish invented speech as if it had been heard.
      const engineState = manager.getPipeline()?.getEngineState?.() || null;
      const engineGate = evaluateRecognitionSupport({
        recognitionCtor: getRecognitionCtor(),
        engineState,
      });
      if (!engineState || !engineGate.supported) {
        voiceSession.endInput("ERROR");
        throw new Error(engineGate.reason || RECOGNITION_UNSUPPORTED_MESSAGE);
      }

      const claim = manager.getInputClaim?.() || null;
      if (!claim) {
        voiceSession.endInput("ERROR");
        throw new Error("Voice input ownership was lost.");
      }
      inputClaimRef.current = claim;

      try {
        // No constraint argument: the DEFAULT_MIC_CONSTRAINTS contract applies.
        mediaStreamRef.current = await openMicrophoneForClaim(claim);
      } catch {
        await voiceRuntimeActions.listen(activeToken, sessionId, {
          mode: "toggle",
          permission_granted: false,
        });
        cleanupLocal();
        throw new Error("Microphone permission is required to talk.");
      }

      await voiceRuntimeActions.listen(activeToken, sessionId, {
        mode: "toggle",
        permission_granted: true,
      });

      attachPipelineSubscriptions({
        manager,
        activeToken,
        sessionId,
        epoch: manager.getInputEpoch?.() ?? 0,
      });

      try {
        await manager.armVad?.({ bargeInMode: false });
      } catch {
        /* VAD optional */
      }
      dispatch({ type: "LOCAL_RECORDING", recording: true, listening: true });
    },
    [attachPipelineSubscriptions, cleanupLocal, voiceSession]
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
      await startListening(activeToken, sessionId);
    } catch (error) {
      dispatch({ type: "ERROR", error: String(error?.message || error) });
    } finally {
      setBusy(false);
    }
  }, [startListening, token, voiceOutput, voiceSession]);

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
        // `/stop` ends capture but leaves the conversation in LISTENING. The
        // user pressing stop has ended the conversation, so terminate it.
        finalizeBackendSession("USER_STOP", activeToken);
      }
      dispatch({ type: "SESSION_CLOSED" });
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
      // Flush terminal requests that failed earlier, before adding another
      // session to the per-user budget. Kept above the output stop so the
      // awaited stop() stays immediately adjacent to opening the session.
      finalizerRef.current.retryPending({ token: activeToken });
      await voiceOutput?.stop?.();
      const sessionId = await ensureSession(activeToken);
      await startListening(activeToken, sessionId);
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
    finalizeBackendSession,
    interrupt,
    refreshHistory,
    runtime.recording,
    runtime.speaking,
    startListening,
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
    pendingCleanup: runtime.pendingCleanup || [],
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
