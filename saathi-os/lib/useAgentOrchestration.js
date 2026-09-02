"use client";

/**
 * Feeds "Who I've got working".
 *
 * One shared read: the agent-runtime run list, plus the contextual run's events
 * that useRunInContext already holds. Background rows render from run records
 * alone rather than opening a fetch per row, so the request count stays bounded
 * no matter how many runs are active.
 *
 * Phase 5F measured 67 run requests across five runs because every run event
 * re-read the list. Here the list is invalidated only by events that can change
 * list membership or lifecycle — not by every task/memory/review event.
 *
 * No new event bus, no per-row subscription, no polling, no timers.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE, afetch } from "./api";
import { useLive } from "@/components/live/LiveProvider";
import { buildAgentOrchestration } from "./agent-orchestration";

const RUN_EVENT_PREFIX = "agentrun.";

/** Only these can change which runs exist or what state they are in. */
export const LIST_INVALIDATING_EVENTS = Object.freeze([
  "run.created", "run.state", "run.completed", "run.paused", "run.timeout",
  "agent.started", "task.failed",
]);

export function shouldInvalidateList(eventName) {
  const name = String(eventName || "");
  if (!name.startsWith(RUN_EVENT_PREFIX)) return false;
  return LIST_INVALIDATING_EVENTS.includes(name.slice(RUN_EVENT_PREFIX.length));
}

export function useAgentOrchestration({ conversationId = "", contextRunId = "", contextEvents = [], limit = 20 } = {}) {
  const live = useLive();
  const [runs, setRuns] = useState([]);
  const abortRef = useRef(null);

  const loadRuns = useCallback(async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const r = await afetch(`${API_BASE}/api/v1/agents/runs?limit=${encodeURIComponent(limit)}`,
        { cache: "no-store", signal: ctrl.signal });
      const j = await r.json();
      setRuns(Array.isArray(j?.runs) ? j.runs : []);
    } catch {
      /* keep the last known truth rather than blanking the panel */
    }
  }, [limit]);

  useEffect(() => { loadRuns(); }, [loadRuns]);
  useEffect(() => () => abortRef.current?.abort(), []);

  // Key on the event object, not its name. Consecutive events legitimately
  // share a name -- a run emits `run.state` for queued->running and again for
  // running->completed -- and keying on the string meant the second one never
  // re-ran this effect, so rows stayed pinned to a finished run's last seen
  // state. The name guard still decides whether a request is made, so the
  // bounded-request property is unchanged: non-invalidating events return here
  // before any fetch. Certified in Phase 6B.
  const lastEvent = live?.last || null;
  useEffect(() => {
    if (!shouldInvalidateList(lastEvent?.name)) return;
    loadRuns();
  }, [lastEvent, loadRuns]);

  return useMemo(() => ({
    ...buildAgentOrchestration({
      runs,
      conversationId,
      // Only the contextual run's events are on hand; background rows render from
      // their run records, which is honest and keeps requests bounded.
      eventsByRunId: contextRunId ? { [contextRunId]: contextEvents } : {},
    }),
    // Phase 7 integration point, additive only: "What needs you" derives from the
    // same run records rather than fetching the list a second time. Exposing the
    // rows this hook already holds is what keeps the attention surface free.
    runs,
  }), [runs, conversationId, contextRunId, contextEvents]);
}
