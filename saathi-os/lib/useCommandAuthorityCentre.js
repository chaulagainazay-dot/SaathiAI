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
  mutationErrorFor,
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

  /**
   * Ask the server to resolve one approval.
   *
   * A request, never a grant. Nothing about the item changes here: no row is
   * removed, no status is rewritten, and the model is not touched on success.
   * The surface learns the outcome the same way it learns everything else --
   * by re-reading authority truth. On failure the item stays exactly as it was,
   * because a request that did not succeed decided nothing.
   *
   * Binds to the approval's own id and the run that owns it; the server checks
   * that pairing again and refuses if it does not hold.
   */
  const resolveApproval = useCallback(async ({ runId, approvalId, approved }) => {
    if (!runId || !approvalId) {
      return { ok: false, error: mutationErrorFor(404) };
    }
    try {
      const r = await afetch(
        `${API_BASE}/api/v1/agents/runs/${encodeURIComponent(runId)}/approve`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ approval_id: approvalId, approved: Boolean(approved) }),
        });

      if (!r.ok) {
        // Re-read regardless: a 404 or a conflict usually means the decision was
        // already made elsewhere, and the panel should show that rather than a
        // row the server no longer recognises.
        await load();
        return { ok: false, status: r.status, error: mutationErrorFor(r.status) };
      }

      const body = await r.json().catch(() => ({}));
      // Authority becomes visible only once the read model reflects the server.
      await load();
      return { ok: true, status: body?.status || null };
    } catch {
      return { ok: false, status: null, error: mutationErrorFor(null) };
    }
  }, [load]);

  const model = useMemo(
    () => buildAuthorityCentre({ items, conversationId }),
    [items, conversationId]
  );

  return useMemo(() => ({ ...model, resolveApproval }), [model, resolveApproval]);
}
