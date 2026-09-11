"use client";

/**
 * V-NEXT-1 — Canonical React publication of VoiceSessionManager.
 * Shell-level. Route change and logout force cleanup.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from "react";
import { usePathname } from "next/navigation";
import { PLATFORM_CONTEXT_EVENT } from "@/lib/platform-client";
import {
  getDefaultVoiceSessionManager,
  toCommandVoiceLabel,
  detectVoiceCapabilities,
} from "@/lib/voice-session";

const VoiceSessionContext = createContext(null);

export function VoiceSessionProvider({ children, manager: externalManager }) {
  // The shared process-wide manager, never a per-mount instance.
  //
  // This provider re-renders on every route change (it reads usePathname to
  // force mic cleanup). Constructing the manager here made its identity churn
  // with navigation, and a fresh manager re-subscribes and republishes a new
  // snapshot on each render. That starved React's navigation transition: click
  // handlers ran, synchronous state updates still committed, but no client-side
  // route change ever landed — every link and sidebar button in the shell was
  // silently inert while direct URL loads worked.
  //
  // Single voice session owner is the V-NEXT-1 contract anyway; there is
  // exactly one microphone. `externalManager` stays injectable for tests.
  const manager = useMemo(
    () => externalManager || getDefaultVoiceSessionManager(),
    [externalManager]
  );
  const [session, setSession] = useState(() => manager.getSnapshot());
  const pathname = usePathname();

  useEffect(() => {
    manager.refreshCapabilities();
    return manager.subscribe(setSession);
  }, [manager]);

  // Route change: never leave mic active on unrelated page
  const [lastPath, setLastPath] = useState(pathname);
  useEffect(() => {
    if (lastPath === pathname) return;
    setLastPath(pathname);
    manager.interrupt("ROUTE_CHANGE");
  }, [pathname, lastPath, manager]);

  useEffect(() => {
    const onCtx = () => {
      manager.close("LOGOUT");
    };
    window.addEventListener(PLATFORM_CONTEXT_EVENT, onCtx);
    return () => {
      window.removeEventListener(PLATFORM_CONTEXT_EVENT, onCtx);
      manager.close("SESSION_CLOSE");
    };
  }, [manager]);

  const value = useMemo(
    () => ({
      manager,
      session,
      commandLabel: toCommandVoiceLabel(session.state),
      capabilities: session.capabilities || detectVoiceCapabilities(),
      interrupt: (reason) => manager.interrupt(reason || "USER_CANCEL"),
      close: (reason) => manager.close(reason || "SESSION_CLOSE"),
      openSession: (opts) => manager.openSession(opts),
      beginInput: (opts) => manager.beginInput(opts),
      endInput: (reason) => manager.endInput(reason),
      beginOutput: (opts) => manager.beginOutput(opts),
      endOutput: (reason) => manager.endOutput(reason),
      setThinking: (on) => manager.setThinking(on),
      setTranscript: (t) => manager.setTranscript(t),
      setError: (e) => manager.setError(e),
    }),
    [manager, session]
  );

  return (
    <VoiceSessionContext.Provider value={value}>
      {children}
    </VoiceSessionContext.Provider>
  );
}

export function useVoiceSession() {
  const ctx = useContext(VoiceSessionContext);
  if (!ctx) {
    // Safe stub when outside provider (tests / isolated pages)
    return {
      manager: null,
      session: {
        state: "IDLE",
        capabilities: detectVoiceCapabilities(),
        error: "",
        transcriptPartial: "",
        transcriptFinal: "",
        assistantText: "",
      },
      commandLabel: "UNKNOWN",
      capabilities: detectVoiceCapabilities(),
      interrupt: async () => {},
      close: async () => {},
      openSession: () => {},
      beginInput: async () => {},
      endInput: () => {},
      beginOutput: async () => {},
      endOutput: async () => {},
      setThinking: () => {},
      setTranscript: () => {},
      setError: () => {},
    };
  }
  return ctx;
}
