"use client";

/**
 * Feeds the Authority Centre.
 *
 * One bounded read of `/api/v1/agents/authority`, which returns runs held by an
 * authority decision together with their pending approvals, batched. No per-row
 * approval lookup, no polling, no timer.
 *
 * Invalidation is keyed on the event *object*, never its name: a run emits
 * `run.state` repeatedly and an approval can be requested and resolved in the
 * same session, and Phase 6 proved that keying on the string silently drops
 * every event after the first.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE, afetch } from "./api";
import { useLive } from "@/components/live/LiveProvider";
import {
  buildAuthorityCentre, shouldRefreshAuthority, AUTHORITY_INVALIDATING_EVENTS,
} from "./command-authority-centre.js";

export { shouldRefreshAuthority, AUTHORITY_INVALIDATING_EVENTS };

export function useCommandAuthorityCentre({ conversationId = "", limit = 20 } = {}) {
  const live = useLive();
  const [items, setItems] = useState([]);
  const abortRef = useRef(null);

  const load = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const r = await afetch(`${API_BASE}/api/v1/agents/authority?limit=${encodeURIComponent(limit)}`,
        { cache: "no-store", signal: ctrl.signal });
      const j = await r.json();
      setItems(Array.isArray(j?.items) ? j.items : []);
    } catch {
      /* keep the last known truth rather than implying authority cleared */
    }
  }, [limit]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => () => abortRef.current?.abort(), []);

  const lastEvent = live?.last || null;
  useEffect(() => {
    if (!shouldRefreshAuthority(lastEvent?.name)) return;
    load();
  }, [lastEvent, load]);

  return useMemo(
    () => buildAuthorityCentre({ items, conversationId }),
    [items, conversationId]
  );
}
