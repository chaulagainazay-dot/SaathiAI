"use client";

/**
 * Resolve the run the Command Core is currently responsible for, and stream
 * that run's REAL events into the single snapshot owner.
 *
 * Reuses what already exists: the agent-runtime REST surface and the Event
 * Fabric SSE feed the browser is already subscribed to through LiveProvider.
 * No second event bus, no polling loop, no per-component subscription.
 *
 * Observational only: it reads runs, never creates, mutates or authorises one.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { API_BASE, afetch } from "./api";
import { useLive } from "@/components/live/LiveProvider";
import { selectContextualRun, eventsForContext } from "./command-run-context";

const RUN_EVENT_PREFIX = "agentrun.";

export function useRunInContext({ conversationId = "", submittedRunId = "", explicitRunId = "" } = {}) {
  const live = useLive();
  const [conversationRuns, setConversationRuns] = useState([]);
  const [rawEvents, setRawEvents] = useState([]);
  const abortRef = useRef(null);

  // Runs correlated to THIS conversation only — the server does the filtering,
  // exactly as components/chat/ChatWorkspace resolves its own run.
  const loadRuns = useCallback(async () => {
    if (!conversationId) { setConversationRuns([]); return; }
    try {
      const r = await afetch(
        `${API_BASE}/api/v1/agents/runs?conversation_id=${encodeURIComponent(conversationId)}&limit=5`,
        { cache: "no-store" });
      const j = await r.json();
      setConversationRuns(Array.isArray(j?.runs) ? j.runs : []);
    } catch {
      setConversationRuns([]);
    }
  }, [conversationId]);

  const context = useMemo(
    () => selectContextualRun({ conversationId, submittedRunId, explicitRunId, conversationRuns }),
    [conversationId, submittedRunId, explicitRunId, conversationRuns]
  );
  const contextRunId = context?.runId || "";

  const loadEvents = useCallback(async () => {
    if (!contextRunId) { setRawEvents([]); return; }
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    try {
      const r = await afetch(
        `${API_BASE}/api/v1/agents/runs/${encodeURIComponent(contextRunId)}/events?limit=200`,
        { cache: "no-store", signal: ctrl.signal });
      const j = await r.json();
      setRawEvents(Array.isArray(j?.events) ? j.events : []);
    } catch {
      /* keep the last known truth rather than inventing an empty run */
    }
  }, [contextRunId]);

  useEffect(() => { loadRuns(); }, [loadRuns]);
  useEffect(() => { loadEvents(); }, [loadEvents]);
  useEffect(() => () => abortRef.current?.abort(), []);

  // The Event Fabric already mirrors every run event as `agentrun.<name>`.
  // Refresh only when one actually arrives — no timer, no interval.
  const lastName = live?.last?.name || "";
  const lastRunId = live?.last?.payload?.run_id || "";
  useEffect(() => {
    if (!lastName.startsWith(RUN_EVENT_PREFIX)) return;
    if (lastRunId && contextRunId && lastRunId !== contextRunId) return; // another run: not ours
    loadEvents();
    if (!contextRunId) loadRuns();
  }, [lastName, lastRunId, contextRunId, loadEvents, loadRuns]);

  // Second gate: even if the API returned something stray, only this run's
  // events reach the snapshot.
  const runEvents = useMemo(() => eventsForContext(rawEvents, context), [rawEvents, context]);

  return { context, runId: contextRunId, runEvents, conversationRuns };
}
