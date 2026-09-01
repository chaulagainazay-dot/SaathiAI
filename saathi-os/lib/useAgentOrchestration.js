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

  const lastName = live?.last?.name || "";
  useEffect(() => {
    if (!shouldInvalidateList(lastName)) return;
    loadRuns();
  }, [lastName, loadRuns]);

  return useMemo(() => buildAgentOrchestration({
    runs,
    conversationId,
    // Only the contextual run's events are on hand; background rows render from
    // their run records, which is honest and keeps requests bounded.
    eventsByRunId: contextRunId ? { [contextRunId]: contextEvents } : {},
  }), [runs, conversationId, contextRunId, contextEvents]);
}
