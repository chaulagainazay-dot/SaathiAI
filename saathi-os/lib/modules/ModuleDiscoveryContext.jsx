"use client";
/**
 * M64 — one shell-wide authenticated module-discovery owner.
 *
 * Sidebar, command palette, route boundary, and Applications dashboard consume
 * the same request/state. Token and context events invalidate the old response
 * before a replacement request, preventing cross-session or cross-tenant flashes.
 */
import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  getToken,
  PLATFORM_CONTEXT_EVENT,
  TOKEN_KEY,
} from "../platform-client.js";
import { useModuleDiscovery } from "./useModuleDiscovery.js";

const ModuleDiscoveryCtx = createContext(null);

const EMPTY_SESSION = { token: "", orgId: "", workspaceId: "" };

export function ModuleDiscoveryProvider({ children }) {
  const [session, setSession] = useState(EMPTY_SESSION);

  useEffect(() => {
    setSession({ ...EMPTY_SESSION, token: getToken() });

    const onContext = (event) => {
      const detail = event?.detail || {};
      setSession({
        token: detail.token ?? getToken(),
        orgId: detail.orgId || "",
        workspaceId: detail.workspaceId || "",
      });
    };
    const onStorage = (event) => {
      if (event.key === TOKEN_KEY) {
        setSession({ ...EMPTY_SESSION, token: event.newValue || "" });
      }
    };
    window.addEventListener(PLATFORM_CONTEXT_EVENT, onContext);
    window.addEventListener("storage", onStorage);
    return () => {
      window.removeEventListener(PLATFORM_CONTEXT_EVENT, onContext);
      window.removeEventListener("storage", onStorage);
    };
  }, []);

  const discovery = useModuleDiscovery(session);
  const value = useMemo(
    () => ({ ...discovery, authenticated: !!session.token, session }),
    [discovery, session]
  );

  return (
    <ModuleDiscoveryCtx.Provider value={value}>
      {children}
    </ModuleDiscoveryCtx.Provider>
  );
}

export function useModuleDiscoveryContext() {
  const value = useContext(ModuleDiscoveryCtx);
  if (!value) {
    throw new Error("useModuleDiscoveryContext requires ModuleDiscoveryProvider");
  }
  return value;
}
