"use client";

/**
 * Feeds "What I've been doing".
 *
 * Like the attention hook, this fetches nothing. The durable run records are
 * already on the page -- the orchestration hook reads them, and they carry
 * `state`, `updated_at` and `terminal_reason`, which is everything a historical
 * record needs. Verification comes from events already fetched for the
 * contextual run; every other row reports UNAVAILABLE rather than guessing.
 *
 * Having no event listener at all, this surface also cannot repeat the Phase 6
 * name-keyed defect: nothing here keys on an event name. The run list is
 * invalidated once, by the orchestration hook, on the events that can actually
 * change lifecycle -- `run.state`, `run.completed`, `run.timeout` among them --
 * and history simply recomputes when those records change.
 */

import { useMemo } from "react";
import { buildCommandHistory } from "./command-history.js";

export function useCommandHistory({
  runs = [],
  conversationId = "",
  contextRunId = "",
  contextEvents = null,
  includeTestStrategies = false,
} = {}) {
  const eventsByRunId = useMemo(
    () => (contextRunId && contextEvents ? { [contextRunId]: contextEvents } : {}),
    [contextRunId, contextEvents]
  );

  return useMemo(
    () => buildCommandHistory({
      runs,
      conversationId,
      eventsByRunId,
      includeTestStrategies,
    }),
    [runs, conversationId, eventsByRunId, includeTestStrategies]
  );
}
