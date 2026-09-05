"use client";
// NEPSE live quotes — client side.
//
// Calls our own server route (never the vendor directly, so no credential ever
// reaches the browser) and merges live prices over the snapshot. The returned
// `source` drives the banner: the UI must always state whether what you are
// looking at is live or snapshot.

import { useCallback, useEffect, useState } from "react";
import { STOCKS } from "./data.js";
import { mergeLiveQuotes, FEED_SOURCE_LABEL } from "./feed-policy.js";

const REFRESH_MS = 30_000;

export function useNepseQuotes({ auto = true } = {}) {
  const [state, setState] = useState({
    stocks: STOCKS,
    source: "snapshot",
    reason: "",
    asOf: null,
    loading: true,
  });

  const load = useCallback(async (signal) => {
    try {
      const res = await fetch("/api/nepse/quotes", { signal, cache: "no-store" });
      const data = await res.json();
      if (data?.source === "live" && Array.isArray(data.quotes) && data.quotes.length) {
        setState({
          stocks: mergeLiveQuotes(STOCKS, data.quotes),
          source: "live",
          reason: "",
          asOf: data.asOf,
          loading: false,
        });
        return;
      }
      // Anything that is not a usable live payload stays on the snapshot, and
      // says which of the honest non-live states it is in.
      setState({
        stocks: STOCKS,
        source: data?.source === "unconfigured" || data?.source === "blocked" ? data.source : "error",
        reason: data?.reason || "",
        asOf: data?.asOf || null,
        loading: false,
      });
    } catch {
      setState((s) => ({ ...s, stocks: STOCKS, source: "error", reason: "unreachable", loading: false }));
    }
  }, []);

  useEffect(() => {
    const ac = new AbortController();
    load(ac.signal);
    if (!auto) return () => ac.abort();
    const t = setInterval(() => load(ac.signal), REFRESH_MS);
    return () => { ac.abort(); clearInterval(t); };
  }, [load, auto]);

  return { ...state, isLive: state.source === "live", reload: () => load(), FEED_SOURCE_LABEL };
}

export { FEED_SOURCE_LABEL };
