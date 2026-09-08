"use client";
// Screener/detail indicator consumer. The browser only RENDERS typed results —
// it never computes an indicator (NEPSE-HIST-2 Phase 10).
import { useEffect, useState } from "react";

export function useNepseIndicators() {
  const [state, setState] = useState({ indicators: {}, loading: true, covered: 0, adjustment: null });
  useEffect(() => {
    const ac = new AbortController();
    fetch("/api/nepse/indicators", { signal: ac.signal, cache: "no-store" })
      .then((r) => r.json())
      .then((d) => setState({
        indicators: d?.indicators || {},
        covered: d?.covered || 0,
        adjustment: d?.adjustment || null,
        loading: false,
      }))
      .catch(() => setState((s) => ({ ...s, loading: false })));
    return () => ac.abort();
  }, []);
  return state;
}

/** Day change from live LTP against the archive-derived previous close. */
export function liveDayChange(livePrice, entry, isLive = true) {
  const se = entry?.session;
  // A day change is only meaningful when the PRICE is from today's session. Pairing
  // a snapshot price with a real previous close produces a confident, wrong
  // percentage — the exact failure this guard exists to prevent.
  if (!isLive) return { available: false, changePct: null, change: null, reason: "PRICE_NOT_LIVE" };
  // Market shut: the "live" price IS the last close, so an intraday change is 0 by
  // construction. Show the last completed session instead of a hollow 0.00%.
  if (se && se.previousCloseDate && livePrice === se.previousClose && se.lastSessionChangePct !== null
      && se.lastSessionChangePct !== undefined) {
    return {
      available: true,
      change: se.lastSessionChange,
      changePct: se.lastSessionChangePct,
      against: se.lastSessionChangeFrom,
      basis: "LAST_SESSION",
      marketClosed: true,
    };
  }
  if (typeof livePrice !== "number" || !se || se.previousClose === null || se.previousClose === undefined) {
    return { available: false, changePct: null, change: null, reason: "NO_PREVIOUS_CLOSE" };
  }
  const prev = se.previousClose;
  if (!prev) return { available: false, changePct: null, change: null };
  const change = livePrice - prev;
  return {
    available: true,
    change: +change.toFixed(4),
    changePct: +((change / prev) * 100).toFixed(2),
    against: se.previousCloseDate,
    basis: se.previousCloseBasis,
  };
}

/** A typed result renders as a value or an em dash — never a fabricated number. */
export function show(res, format = (v) => String(v)) {
  if (!res || res.value === null || res.value === undefined || res.status !== "VALID") return "—";
  return format(res.value);
}
