"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useReducer,
  useRef,
  useState,
} from "react";
import {
  ACTIVE_VOICE_STATES,
  DEFAULT_VOICE_PREFERENCES,
  INITIAL_VOICE_OUTPUT,
  VOICE_PREFERENCE_KEY,
  fetchVoiceAudio,
  normalizeVoicePreferences,
  voiceActions,
  voiceOutputReducer,
} from "@/lib/voice-output";
import { usePathname } from "next/navigation";
import {
  getToken,
  PLATFORM_CONTEXT_EVENT,
} from "@/lib/platform-client";

const VoiceOutputContext = createContext(null);
const TERMINAL = new Set([
  "completed",
  "cancelled",
  "failed",
  "unavailable",
  "expired",
]);
const POLL_INTERVAL_MS = 250;
const MAX_POLL_ATTEMPTS = 800;

function loadPreferences() {
  if (typeof window === "undefined") return DEFAULT_VOICE_PREFERENCES;
  try {
    return normalizeVoicePreferences(
      JSON.parse(localStorage.getItem(VOICE_PREFERENCE_KEY) || "{}")
    );
  } catch {
    return DEFAULT_VOICE_PREFERENCES;
  }
}

export function VoiceOutputProvider({ children }) {
  const [token, setToken] = useState("");
  const [preferences, setPreferences] = useState(DEFAULT_VOICE_PREFERENCES);
  const [metadata, setMetadata] = useState({
    loading: false,
    health: null,
    providers: [],
    profiles: [],
    error: "",
  });
  const [output, dispatch] = useReducer(
    voiceOutputReducer,
    INITIAL_VOICE_OUTPUT
  );
  const audioRef = useRef(null);
  const audioUrlRef = useRef("");
  const pollRef = useRef(null);
  const metadataRef = useRef(null);
  const operationRef = useRef(null);

  useEffect(() => {
    operationRef.current = output.operation;
  }, [output.operation]);

  const clearAudioElements = useCallback(() => {
    if (audioRef.current) {
      audioRef.current.pause();
      audioRef.current.removeAttribute("src");
      audioRef.current.load();
      audioRef.current = null;
    }
    if (audioUrlRef.current) {
      URL.revokeObjectURL(audioUrlRef.current);
      audioUrlRef.current = "";
    }
  }, []);

  const clearLocalAudio = useCallback(() => {
    if (pollRef.current) {
      pollRef.current.abort();
      pollRef.current = null;
    }
    clearAudioElements();
  }, [clearAudioElements]);

  const refreshMetadata = useCallback(async (activeToken) => {
    metadataRef.current?.abort();
    if (!activeToken) {
      setMetadata({
        loading: false,
        health: null,
        providers: [],
        profiles: [],
        error: "",
      });
      return;
    }
    setMetadata((current) => ({ ...current, loading: true, error: "" }));
    const controller = new AbortController();
    metadataRef.current = controller;
    try {
      const [health, providers, profiles] = await Promise.all([
        voiceActions.health(activeToken, controller.signal),
        voiceActions.providers(activeToken, controller.signal),
        voiceActions.profiles(activeToken, controller.signal),
      ]);
      setMetadata({
        loading: false,
        health: health.health || null,
        providers: providers.providers || [],
        profiles: profiles.profiles || [],
        error: "",
      });
    } catch (error) {
      if (error?.name !== "AbortError") {
        setMetadata({
          loading: false,
          health: null,
          providers: [],
          profiles: [],
          error: String(error?.message || error),
        });
      }
    } finally {
      if (metadataRef.current === controller) metadataRef.current = null;
    }
  }, []);

  useEffect(() => {
    setPreferences(loadPreferences());
    const activeToken = getToken();
    setToken(activeToken);
    refreshMetadata(activeToken);

    const onContext = (event) => {
      clearLocalAudio();
      dispatch({ type: "RESET" });
      setMetadata({
        loading: true,
        health: null,
        providers: [],
        profiles: [],
        error: "",
      });
      const nextToken = event?.detail?.token ?? getToken();
      setToken(nextToken);
      refreshMetadata(nextToken);
    };
    window.addEventListener(PLATFORM_CONTEXT_EVENT, onContext);
    return () => {
      window.removeEventListener(PLATFORM_CONTEXT_EVENT, onContext);
      metadataRef.current?.abort();
      clearLocalAudio();
    };
  }, [clearLocalAudio, refreshMetadata]);

  const updatePreferences = useCallback(
    (updates) => {
      setPreferences((current) => {
        const next = normalizeVoicePreferences({ ...current, ...updates });
        try {
          localStorage.setItem(VOICE_PREFERENCE_KEY, JSON.stringify(next));
        } catch {
          /* preference persistence is optional */
        }
        if (!next.enabled) {
          clearLocalAudio();
          dispatch({ type: "CANCELLED" });
        }
        return next;
      });
    },
    [clearLocalAudio]
  );

  const stop = useCallback(
    async ({ remote = true } = {}) => {
      const operation = operationRef.current;
      clearLocalAudio();
      if (
        remote &&
        token &&
        operation?.operationId &&
        ACTIVE_VOICE_STATES.has(operation.state)
      ) {
        await voiceActions.cancel(operation.operationId, token).catch(() => null);
      }
      dispatch({ type: "CANCELLED" });
    },
    [clearLocalAudio, token]
  );

  const prepareAudio = useCallback(
    async (operation, activeToken, signal) => {
      const blob = await fetchVoiceAudio(operation.operation_id, {
        token: activeToken,
        signal,
      });
      if (signal.aborted) return;
      clearAudioElements();
      const url = URL.createObjectURL(blob);
      const audio = new Audio(url);
      audio.preload = "auto";
      audio.onplaying = () => dispatch({ type: "PLAYING" });
      audio.onended = () => dispatch({ type: "ENDED" });
      audio.onerror = () =>
        dispatch({
          type: "FAILED",
          message: "The browser could not play the speech artifact.",
        });
      audioUrlRef.current = url;
      audioRef.current = audio;
      dispatch({ type: "READY", operation });
    },
    [clearAudioElements]
  );

  const poll = useCallback(
    async (operationId, activeToken, controller) => {
      for (let attempt = 0; attempt < MAX_POLL_ATTEMPTS; attempt += 1) {
        if (controller.signal.aborted) return;
        const payload = await voiceActions.operation(
          operationId,
          activeToken,
          controller.signal
        );
        const operation = payload.operation;
        // Surface terminal backend state immediately so the dock can update
        // even while audio preparation is still in flight.
        dispatch({ type: "OPERATION", operation });
        if (operation.state === "completed" && operation.audio_available) {
          try {
            await prepareAudio(operation, activeToken, controller.signal);
          } catch (error) {
            // Synthesis completed; keep that state if only playback prep failed.
            if (error?.name !== "AbortError") {
              dispatch({ type: "OPERATION", operation });
            }
          }
          return;
        }
        if (TERMINAL.has(operation.state)) return;
        await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
      }
      dispatch({
        type: "FAILED",
        message: "Speech exceeded the bounded client wait window.",
      });
    },
    [prepareAudio]
  );

  const speak = useCallback(
    async (
      text,
      {
        source = "assistant",
        language = "en-US",
        profileId = "",
      } = {}
    ) => {
      const approvedText = String(text || "").trim();
      if (!preferences.enabled || !token || !approvedText) return false;
      await stop();
      const controller = new AbortController();
      pollRef.current = controller;
      try {
        const payload = await voiceActions.speak(
          {
            text: approvedText.slice(0, 4_000),
            source,
            language,
            voice_profile_id: profileId || preferences.profileId,
            speaking_rate: preferences.speakingRate,
            // WAV is Chromium-playable; macOS provider converts from native AIFF.
            output_format: "wav",
            provider: "auto",
            idempotency_key: `voice-ui-${Date.now()}`,
          },
          token,
          controller.signal
        );
        dispatch({ type: "OPERATION", operation: payload.operation });
        await poll(payload.operation.operation_id, token, controller);
        return true;
      } catch (error) {
        if (error?.name !== "AbortError") {
          dispatch({
            type: "FAILED",
            unavailable: error?.status === 503,
            message: String(error?.message || "Speech is unavailable."),
          });
        }
        return false;
      } finally {
        if (pollRef.current === controller) pollRef.current = null;
      }
    },
    [poll, preferences, stop, token]
  );

  // The provider sits above the router in Shell, so it never unmounts on a
  // client-side navigation and the detached Audio element would keep playing
  // in the background of an unrelated page. Stop speech when the route changes
  // — never on first render, which would cancel a freshly-started utterance.
  const pathname = usePathname();
  const spokenPathRef = useRef(pathname);
  useEffect(() => {
    if (spokenPathRef.current === pathname) return;
    spokenPathRef.current = pathname;
    stop();
  }, [pathname, stop]);

  const play = useCallback(async () => {
    if (!audioRef.current || !output.audioReady) return false;
    try {
      audioRef.current.currentTime = 0;
      await audioRef.current.play();
      return true;
    } catch {
      dispatch({
        type: "FAILED",
        message: "Playback was blocked. Choose Play again or check browser audio.",
      });
      return false;
    }
  }, [output.audioReady]);

  const value = useMemo(
    () => ({
      token,
      preferences,
      metadata,
      output,
      enabled: preferences.enabled && Boolean(token),
      busy: ACTIVE_VOICE_STATES.has(output.state),
      updatePreferences,
      refresh: () => refreshMetadata(token),
      speak,
      play,
      stop,
    }),
    [
      metadata,
      output,
      play,
      preferences,
      refreshMetadata,
      speak,
      stop,
      token,
      updatePreferences,
    ]
  );

  return (
    <VoiceOutputContext.Provider value={value}>
      {children}
    </VoiceOutputContext.Provider>
  );
}

export function useVoiceOutput() {
  const context = useContext(VoiceOutputContext);
  if (!context) {
    throw new Error("useVoiceOutput must be used inside VoiceOutputProvider");
  }
  return context;
}
