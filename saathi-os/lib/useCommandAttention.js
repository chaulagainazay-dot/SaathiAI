"use client";

/**
 * Feeds "What needs you".
 *
 * This hook deliberately fetches nothing. Every input already exists on the
 * page: the run list Phase 6's orchestration hook holds, and the Command Core
 * snapshot Phase 5 owns. So the attention surface costs zero extra requests,
 * zero extra SSE connections, no per-row polling and no timers -- the Phase 6
 * request-efficiency gain is preserved exactly.
 *
 * There is no invalidation effect here at all, which is also why the Phase 6
 * name-keyed defect cannot recur on this surface: nothing subscribes to event
 * names. Attention recomputes when its inputs change, and its inputs change
 * when the backend truth behind them changes.
 */

import { useMemo } from "react";
import { buildAttention } from "./command-attention.js";

export function useCommandAttention({
  runs = [],
  conversationId = "",
  snapshot = null,
  detailsByRunId = null,
} = {}) {
  return useMemo(
    () => buildAttention({
      runs,
      conversationId,
      snapshot,
      detailsByRunId: detailsByRunId || {},
    }),
    [runs, conversationId, snapshot, detailsByRunId]
  );
}
