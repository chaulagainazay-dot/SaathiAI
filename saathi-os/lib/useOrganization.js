"use client";

// AI Company data hook. Event-driven first: the canonical SSE stream
// (LiveProvider → /api/events/stream) announces org.* and agentrun.* events and
// we refetch the snapshot (debounced). A slow fallback poll runs only while the
// tab is visible; it speeds up only during a mission when live events are down.

import { useCallback, useEffect, useRef, useState } from "react";
import { API_BASE, afetch } from "./api.js";
import { useLive } from "@/components/live/LiveProvider";
import { isRelevantEvent, refreshInterval } from "./organization.js";

const BASE = `${API_BASE}/api/v1/organization`;

async function getJson(url, opts) {
  const r = await afetch(url, opts);
  let body = null;
  try { body = await r.json(); } catch { body = null; }
  if (!r.ok) {
    const err = new Error(body?.message || body?.error || `Request failed (${r.status})`);
    err.status = r.status;
    err.code = body?.error;
    throw err;
  }
  return body;
}

export const orgApi = {
  company: () => getJson(`${BASE}/company`),
  systemStatus: () => getJson(`${BASE}/system-status`),
  role: (id) => getJson(`${BASE}/roles/${encodeURIComponent(id)}`),
  office: (id) => getJson(`${BASE}/offices/${encodeURIComponent(id)}`),
  mission: (id) => getJson(`${BASE}/missions/${encodeURIComponent(id)}`),
  missions: () => getJson(`${BASE}/missions?limit=10`),
  templates: () => getJson(`${BASE}/templates`),
  evidence: (id) => getJson(`${BASE}/evidence/${encodeURIComponent(id)}`),
  startMission: (body) => getJson(`${BASE}/missions`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
  }),
};

function useVisible() {
  const [visible, setVisible] = useState(true);
  useEffect(() => {
    const on = () => setVisible(document.visibilityState !== "hidden");
    on();
    document.addEventListener("visibilitychange", on);
    return () => document.removeEventListener("visibilitychange", on);
  }, []);
  return visible;
}

export function useOrganization() {
  const [snap, setSnap] = useState(null);
  const [error, setError] = useState(null);
  const [loading, setLoading] = useState(true);
  const [systems, setSystems] = useState(null);
  const [lastEventAt, setLastEventAt] = useState(null);
  const live = useLive();
  const visible = useVisible();
  const inflight = useRef(false);
  const pending = useRef(false);
  const timer = useRef(null);

  const refresh = useCallback(async () => {
    if (inflight.current) { pending.current = true; return; }
    inflight.current = true;
    try {
      const d = await orgApi.company();
      setSnap(d);
      setError(null);
    } catch (e) {
      setError(e);
    } finally {
      inflight.current = false;
      setLoading(false);
      if (pending.current) { pending.current = false; refresh(); }
    }
  }, []);

  const refreshSystems = useCallback(async () => {
    try { setSystems(await orgApi.systemStatus()); } catch (e) { setSystems({ error: String(e.message || e) }); }
  }, []);

  useEffect(() => { refresh(); refreshSystems(); }, [refresh, refreshSystems]);

  // event-driven refresh (debounced)
  useEffect(() => {
    const name = live.last?.name;
    if (!isRelevantEvent(name)) return;
    setLastEventAt(Date.now());
    clearTimeout(timer.current);
    timer.current = setTimeout(refresh, 250);
  }, [live.last, refresh]);
  useEffect(() => () => clearTimeout(timer.current), []);

  // fallback poll
  const missionActive = (snap?.active_missions || []).length > 0;
  useEffect(() => {
    const ms = refreshInterval({ missionActive, liveConnected: !!live.connected, visible });
    if (!ms) return undefined;
    const id = setInterval(refresh, ms);
    return () => clearInterval(id);
  }, [missionActive, live.connected, visible, refresh]);

  useEffect(() => {
    if (!visible) return undefined;
    const id = setInterval(refreshSystems, 60000);
    return () => clearInterval(id);
  }, [visible, refreshSystems]);

  return { snap, error, loading, systems, refresh, refreshSystems,
    liveConnected: !!live.connected, lastEventAt, missionActive };
}
