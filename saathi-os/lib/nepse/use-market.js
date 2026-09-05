"use client";
// Shared client access to the market aggregates route.
//
// Both the page and the site-wide ticker read these numbers, and they must never
// disagree: one hook, one route, one cached computation. The hook returns an
// explicit `available` rather than zeros, so a caller that cannot render honestly
// is forced to render nothing.

import { useEffect, useState } from "react";

function useJsonRoute(url) {
  const [state, setState] = useState({ loading: true, data: null, error: "" });
  useEffect(() => {
    const ac = new AbortController();
    fetch(url, { signal: ac.signal, cache: "no-store" })
      .then((r) => r.json())
      .then((d) => setState(d?.available
        ? { loading: false, data: d, error: "" }
        : { loading: false, data: null, error: d?.reason || "UNAVAILABLE" }))
      .catch(() => setState({ loading: false, data: null, error: "UNREACHABLE" }));
    return () => ac.abort();
  }, [url]);
  return state;
}

/** Breadth, movers and per-company activity, from the per-company archive. */
export function useMarketAggregates() {
  return useJsonRoute("/api/nepse/market");
}

/**
 * The PUBLISHED index and sub-indices. A separate source from the aggregates
 * above, and deliberately a separate fetch: when one is unavailable the other
 * must still render, and neither may stand in for the other.
 */
export function useIndices() {
  return useJsonRoute("/api/nepse/indices");
}

/**
 * Real per-broker trade activity for the last completed session. Pass a symbol to
 * scope it to one instrument.
 */
export function useFloorsheet(symbol = null) {
  return useJsonRoute(symbol ? `/api/nepse/floorsheet?symbol=${encodeURIComponent(symbol)}` : "/api/nepse/floorsheet");
}
