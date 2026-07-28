"use client";
// M59 — shared platform API client + data hook for the spatial workspaces.
//
// One authenticated fetch path (X-Platform-Token, same contract as the M58
// /platform page) and one loader that all four workspaces + the shell consume,
// so mission/agent/approval/attention screens bind to the SAME server truth.
// Cold-start hardening (M57/M58) is retained: a sequential /me warms the cold
// compile + CORS window, then the rest fan out so one straggler can't wipe the
// authenticated surface.
import { useCallback, useEffect, useState } from "react";
import { API_BASE } from "./api.js";

export const TOKEN_KEY = "saathi_platform_token";
export const PLATFORM_CONTEXT_EVENT = "saathi:platform-context";

export function getToken() {
  if (typeof window === "undefined") return "";
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setToken(t) {
  if (typeof window === "undefined") return;
  try {
    if (t) localStorage.setItem(TOKEN_KEY, t);
    else localStorage.removeItem(TOKEN_KEY);
    window.dispatchEvent(
      new CustomEvent(PLATFORM_CONTEXT_EVENT, {
        detail: { token: t || "", orgId: "", workspaceId: "" },
      })
    );
  } catch {
    /* ignore */
  }
}

/** Notify shell consumers after a server-authorized org/workspace selection. */
export function notifyPlatformContextChanged({ orgId = "", workspaceId = "" } = {}) {
  if (typeof window === "undefined") return;
  window.dispatchEvent(
    new CustomEvent(PLATFORM_CONTEXT_EVENT, {
      detail: { token: getToken(), orgId, workspaceId },
    })
  );
}

export async function plat(path, { method = "GET", body, token, signal } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers["X-Platform-Token"] = token;
  const res = await fetch(`${API_BASE}/api/v1/platform${path}`, {
    method,
    headers,
    body: body ? JSON.stringify(body) : undefined,
    credentials: "include",
    signal,
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = data?.detail?.message || data?.detail?.code || data?.error || res.statusText;
    const err = new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
    err.status = res.status;
    throw err;
  }
  return data;
}

const isTransient = (e) => /Failed to fetch|NetworkError|load failed|ECONNREFUSED/i.test(String(e?.message || e));

/* Retry transient failures with bounded backoff; surface hard errors once. */
async function getWithRetry(path, tok, onError, attempts = 7) {
  for (let i = 0; i < attempts; i += 1) {
    try {
      return await plat(path, { token: tok });
    } catch (e) {
      if (i === attempts - 1 || !isTransient(e)) {
        if (!isTransient(e)) onError?.(e);
        return null;
      }
      await new Promise((r) => setTimeout(r, Math.min(2500, 500 * (i + 1))));
    }
  }
  return null;
}

const EMPTY = {
  health: null,
  me: null,
  missions: [],
  approvals: [],
  bindings: [],
  executions: [],
  attention: [],
  metrics: null,
  diagnostics: null,
};

/* Load the whole authenticated workspace surface once, shared by all routes. */
export function usePlatformData() {
  const [token, setTokenState] = useState("");
  const [data, setData] = useState(EMPTY);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    setTokenState(getToken());
  }, []);

  const refresh = useCallback(async (tok) => {
    const t = tok ?? getToken();
    if (!t) {
      setData(EMPTY);
      setReady(true);
      return;
    }
    setLoading(true);
    setError(null);
    const onErr = (e) => setError((prev) => prev || String(e?.message || e));
    const get = (p) => getWithRetry(p, t, onErr);
    const m = await get("/me");
    const [missions, approvals, health, bindings, executions, attention, metrics, diagnostics] = await Promise.all([
      get("/missions"),
      get("/approvals?status=pending"),
      get("/health"),
      get("/agent-bindings"),
      get("/runtime/executions?limit=100"),
      get("/runtime/attention"),
      get("/runtime/metrics"),
      get("/runtime/diagnostics"),
    ]);
    setData({
      health: health || null,
      me: m || null,
      missions: missions?.missions || [],
      approvals: approvals?.approvals || [],
      bindings: bindings?.bindings || [],
      executions: executions?.executions || [],
      attention: attention?.attention || [],
      metrics: metrics?.metrics || null,
      diagnostics: diagnostics?.diagnostics || null,
    });
    setLoading(false);
    setReady(true);
  }, []);

  useEffect(() => {
    if (token) refresh(token);
    else setReady(true);
  }, [token, refresh]);

  const persist = useCallback((t) => {
    setToken(t);
    setTokenState(t);
  }, []);

  return { token, persist, loading, error, ready, ...data, refresh };
}
