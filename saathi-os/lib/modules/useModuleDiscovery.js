"use client";
/**
 * M64 — authenticated module discovery hook.
 *
 * Drives the shell bootstrap state machine from the authoritative backend
 * discovery endpoint. Handles: no token → AUTH_REQUIRED, fetch → READY/DEGRADED,
 * classified failure → SESSION_EXPIRED / PERMISSION_RESTRICTED / OFFLINE / ERROR,
 * bounded retry, logout + tenant/workspace switch invalidation (no cross-tenant
 * stale state), and request cancellation on unmount / context change.
 *
 * The backend is authoritative. The local mirror is only a loading skeleton
 * exposed as `fallback` and clearly marked stale/non-operational.
 */
import { useEffect, useReducer, useRef, useCallback } from "react";
import { getToken } from "../platform-client.js";
import { fetchModuleDiscovery, classifyError } from "./client.js";
import { bootReducer, initialBootState, BOOT } from "./bootstrap.js";
import { buildDefaultRegistry } from "./registry.js";

const MAX_RETRIES = 3;

/** Non-operational skeleton derived from the static mirror (loading only). */
function fallbackSkeleton() {
  const reg = buildDefaultRegistry();
  return reg.dashboardCards().map((c) => ({
    id: c.moduleId,
    name: c.title,
    icon: c.icon,
    routes: reg.get(c.moduleId)?.routes || [],
    state: "unknown",
    actionable: false,
    stale: true,
  }));
}

/**
 * @param {{ token?: string, orgId?: string, workspaceId?: string, platFn?: Function }} ctx
 *   Changing orgId/workspaceId invalidates module state (CONTEXT_SWITCH).
 */
export function useModuleDiscovery(ctx = {}) {
  const { token, orgId = "", workspaceId = "", platFn } = ctx;
  const [state, dispatch] = useReducer(bootReducer, undefined, initialBootState);
  const abortRef = useRef(null);
  const retryRef = useRef(0);
  const retryTimerRef = useRef(null);
  const generationRef = useRef(0);
  // context key: any change invalidates prior (possibly cross-tenant) state
  const ctxKey = `${orgId}::${workspaceId}`;
  const prevCtxKey = useRef(ctxKey);

  const load = useCallback(async (generation = generationRef.current) => {
    if (generation !== generationRef.current) return;
    const tok = token !== undefined ? token : getToken();
    if (!tok) {
      dispatch({ type: "NO_TOKEN" });
      return;
    }
    dispatch({ type: "HAVE_TOKEN" });
    dispatch({ type: "CONTEXT_READY" });
    if (abortRef.current) abortRef.current.abort();
    const ac = typeof AbortController !== "undefined" ? new AbortController() : null;
    abortRef.current = ac;
    try {
      const disc = await fetchModuleDiscovery({ token: tok, platFn, signal: ac?.signal });
      if (generation !== generationRef.current) return;
      dispatch({ type: "MODULES_OK", payload: disc });
      retryRef.current = 0;
    } catch (e) {
      if (generation !== generationRef.current) return;
      const category = classifyError(e);
      if (category === "network" && retryRef.current < MAX_RETRIES) {
        retryRef.current += 1;
        dispatch({ type: "RETRY" });
        // bounded backoff; single scheduled retry, never an infinite poll
        retryTimerRef.current = setTimeout(
          () => load(generation),
          400 * retryRef.current
        );
        return;
      }
      dispatch({ type: "MODULES_ERR", category });
    }
  }, [token, platFn]);

  // initial + context-switch load
  useEffect(() => {
    generationRef.current += 1;
    const generation = generationRef.current;
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    if (prevCtxKey.current !== ctxKey) {
      prevCtxKey.current = ctxKey;
      dispatch({ type: "CONTEXT_SWITCH" }); // clear stale cross-tenant state first
    }
    load(generation);
    return () => {
      generationRef.current += 1;
      if (abortRef.current) abortRef.current.abort();
      if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    };
  }, [ctxKey, load]);

  const logout = useCallback(() => {
    generationRef.current += 1;
    if (abortRef.current) abortRef.current.abort();
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    dispatch({ type: "LOGOUT" });
  }, []);

  const retry = useCallback(() => {
    generationRef.current += 1;
    const generation = generationRef.current;
    retryRef.current = 0;
    if (retryTimerRef.current) clearTimeout(retryTimerRef.current);
    load(generation);
  }, [load]);

  return {
    phase: state.phase,
    modules: state.modules,
    cards: state.cards,
    navigation: state.navigation,
    contractVersion: state.contractVersion,
    errorCategory: state.errorCategory,
    isReady: state.phase === BOOT.READY || state.phase === BOOT.DEGRADED,
    fallback: fallbackSkeleton(),
    retry,
    logout,
  };
}
