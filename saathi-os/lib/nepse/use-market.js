"use client";
// Shared client access to the market aggregates route.
//
// Both the page and the site-wide ticker read these numbers, and they must never
// disagree: one hook, one route, one cached computation. The hook returns an
// explicit `available` rather than zeros, so a caller that cannot render honestly
// is forced to render nothing.

import { useEffect, useState } from "react";

export function useMarketAggregates() {
  const [state, setState] = useState({ loading: true, data: null, error: "" });
  useEffect(() => {
    const ac = new AbortController();
    fetch("/api/nepse/market", { signal: ac.signal, cache: "no-store" })
      .then((r) => r.json())
      .then((d) => setState(d?.available
        ? { loading: false, data: d, error: "" }
        : { loading: false, data: null, error: d?.reason || "UNAVAILABLE" }))
      .catch(() => setState({ loading: false, data: null, error: "UNREACHABLE" }));
    return () => ac.abort();
  }, []);
  return state;
}
