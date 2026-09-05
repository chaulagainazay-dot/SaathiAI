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

/** A typed result renders as a value or an em dash — never a fabricated number. */
export function show(res, format = (v) => String(v)) {
  if (!res || res.value === null || res.value === undefined || res.status !== "VALID") return "—";
  return format(res.value);
}
