"use client";
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { applyAllPreferences, loadPreferences, savePreference, DEFAULTS } from "@/lib/preferences";

const ShellChromeCtx = createContext(null);

export function ShellChromeProvider({ children }) {
  const [ready, setReady] = useState(false);
  const [prefs, setPrefs] = useState(DEFAULTS);
  const [copilotOpen, setCopilotOpen] = useState(false);
  const [sidebarExpanded, setSidebarExpanded] = useState(true);

  useEffect(() => {
    const loaded = loadPreferences();
    setPrefs(loaded);
    setCopilotOpen(!!loaded.copilotOpen);
    setSidebarExpanded(loaded.sidebarExpanded !== false);
    applyAllPreferences(loaded);
    setReady(true);

    // system theme listener
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    const onChange = () => {
      const p = loadPreferences();
      if (p.theme === "system") applyAllPreferences(p);
    };
    mq?.addEventListener?.("change", onChange);
    return () => mq?.removeEventListener?.("change", onChange);
  }, []);

  const updatePref = useCallback((key, value) => {
    setPrefs((prev) => {
      const next = { ...prev, [key]: value };
      savePreference(key, value);
      applyAllPreferences(next);
      return next;
    });
  }, []);

  const toggleSidebar = useCallback(() => {
    setSidebarExpanded((v) => {
      const next = !v;
      savePreference("sidebarExpanded", next);
      return next;
    });
  }, []);

  const openCopilot = useCallback(() => {
    setCopilotOpen(true);
    savePreference("copilotOpen", true);
  }, []);

  const closeCopilot = useCallback(() => {
    setCopilotOpen(false);
    savePreference("copilotOpen", false);
  }, []);

  const toggleCopilot = useCallback(() => {
    setCopilotOpen((v) => {
      const next = !v;
      savePreference("copilotOpen", next);
      return next;
    });
  }, []);

  const value = useMemo(
    () => ({
      ready,
      prefs,
      updatePref,
      sidebarExpanded,
      toggleSidebar,
      setSidebarExpanded,
      copilotOpen,
      openCopilot,
      closeCopilot,
      toggleCopilot,
    }),
    [ready, prefs, updatePref, sidebarExpanded, toggleSidebar, copilotOpen, openCopilot, closeCopilot, toggleCopilot]
  );

  return <ShellChromeCtx.Provider value={value}>{children}</ShellChromeCtx.Provider>;
}

export function useShellChrome() {
  const ctx = useContext(ShellChromeCtx);
  if (!ctx) {
    return {
      ready: false,
      prefs: DEFAULTS,
      updatePref: () => {},
      sidebarExpanded: true,
      toggleSidebar: () => {},
      setSidebarExpanded: () => {},
      copilotOpen: false,
      openCopilot: () => {},
      closeCopilot: () => {},
      toggleCopilot: () => {},
    };
  }
  return ctx;
}
