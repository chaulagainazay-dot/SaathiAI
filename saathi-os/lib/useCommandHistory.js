"use client";

/**
 * Feeds "What I've been doing".
 *
 * Phase 9: history now comes from `/api/v1/agents/history`, a read that filters
 * to terminal runs and excludes certification fixtures *inside the query*, and
 * returns a batched verification summary for every row.
 *
 * The surface previously derived history from the generic run list, which asked
 * a different question -- "the newest runs of any kind" -- so a burst of
 * short-lived runs could push real history out of the window entirely, and
 * verification was only ever known for the one run whose events happened to be
 * loaded. Both were measured limitations, and both are answered by the contract
 * rather than by more requests from here.
 *
 * One bounded request, no per-row fetch, no polling, no timer. Invalidation is
 * event-driven and keyed on the event *object*, never its name: a run emits
 * `run.state` repeatedly, and Phase 6 proved that keying on the string drops
 * every event after the first.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE, afetch } from "./api";
import { useLive } from "@/components/live/LiveProvider";
import {
  buildCommandHistory, normalizeHistoryApiItem, HISTORY_LIMIT,
  HISTORY_INVALIDATING_EVENTS, shouldRefreshHistory,
} from "./command-history.js";

export { HISTORY_INVALIDATING_EVENTS, shouldRefreshHistory };

export function useCommandHistory({
  conversationId = "",
  limit = HISTORY_LIMIT,
  includeTestStrategies = false,
} = {}) {
  const live = useLive();
  const [items, setItems] = useState([]);
  const [hasMore, setHasMore] = useState(false);
  const abortRef = useRef(null);

  // One extra row tells the panel there is older history without a second read.
  const fetchLimit = limit + 1;

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const qs = new URLSearchParams({ limit: String(fetchLimit) });
      if (includeTestStrategies) qs.set("include_test_strategies", "true");
      const r = await afetch(`${API_BASE}/api/v1/agents/history?${qs}`,
        { cache: "no-store", signal: ctrl.signal });
      const j = await r.json();
      setItems(Array.isArray(j?.items) ? j.items : []);
      setHasMore(Boolean(j?.has_more));
    } catch {
      /* keep the last known truth rather than blanking the panel */
    }
  }, [fetchLimit, includeTestStrategies]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => () => abortRef.current?.abort(), []);

  const lastEvent = live?.last || null;
  useEffect(() => {
    if (!shouldRefreshHistory(lastEvent?.name)) return;
    load();
  }, [lastEvent, load]);

  const runs = useMemo(
    () => items.map(normalizeHistoryApiItem).filter(Boolean),
    [items]
  );

  return useMemo(() => {
    const model = buildCommandHistory({ runs, conversationId, limit });
    return {
      ...model,
      // `hasMore` says older history exists; it does not say how much, and the
      // panel must not invent a number. It discloses that more exists instead.
      hasMore: hasMore || model.withheld > 0,
    };
  }, [runs, conversationId, limit, hasMore]);
}
