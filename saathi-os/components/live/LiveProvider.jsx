"use client";
import { createContext, useContext, useReducer, useEffect, useRef, useCallback } from "react";
import { API_BASE } from "@/lib/api";

const LiveCtx = createContext(null);
const ACTIVE_MS = 2600;         // how long a department "glows" after an event
const DEDUPE_MS = 1400;         // coalesce identical rapid events
const MAX_NOTIFS = 6;

function reducer(state, action) {
  switch (action.type) {
    case "connect": return { ...state, connected: true };
    case "disconnect": return { ...state, connected: false };
    case "prune": return { ...state, nonce: state.nonce + 1 };
    case "dismiss":
      return { ...state, notifications: state.notifications.filter((n) => n.id !== action.id) };
    case "event": {
      const ev = action.ev, now = Date.now();
      const active = { ...state.active, [ev.dept]: now + ACTIVE_MS };
      let notifications = state.notifications;
      // UI State Engine: coalesce identical rapid events, cap the feed
      const top = notifications[0];
      if (ev.title && !(top && top.name === ev.name && now - top.at < DEDUPE_MS)) {
        notifications = [{ id: `${ev.name}-${now}-${Math.random().toString(36).slice(2, 6)}`,
          at: now, ...ev }, ...notifications].slice(0, MAX_NOTIFS);
      }
      const bump = /^(trade|revenue|investment)\./.test(ev.name) ? state.bump + 1 : state.bump;
      return { ...state, active, notifications, bump, last: ev };
    }
    default: return state;
  }
}

export function LiveProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, {
    connected: false, active: {}, notifications: [], bump: 0, nonce: 0, last: null,
  });
  const esRef = useRef(null);

  useEffect(() => {
    let es;
    try {
      es = new EventSource(`${API_BASE}/api/events/stream?demo=1`);
      esRef.current = es;
      es.onopen = () => dispatch({ type: "connect" });
      es.onerror = () => dispatch({ type: "disconnect" });   // EventSource auto-reconnects
      es.onmessage = (m) => {
        try {
          const ev = JSON.parse(m.data);
          if (ev.name === "stream.connected") { dispatch({ type: "connect" }); return; }
          if (ev.name === "heartbeat") return;
          dispatch({ type: "event", ev });
        } catch {}
      };
    } catch {}
    const prune = setInterval(() => dispatch({ type: "prune" }), 700);
    return () => { clearInterval(prune); es?.close(); };
  }, []);

  const isActive = useCallback((dept) => (state.active[dept] || 0) > Date.now(), [state.active, state.nonce]);
  const dismiss = useCallback((id) => dispatch({ type: "dismiss", id }), []);

  return (
    <LiveCtx.Provider value={{ ...state, isActive, dismiss }}>{children}</LiveCtx.Provider>
  );
}

export function useLive() {
  return useContext(LiveCtx) || { connected: false, notifications: [], bump: 0,
    isActive: () => false, dismiss: () => {} };
}
