/**
 * CENTRAL COMMAND CORE — which run is the centre responsible for?
 *
 * MOTION REFLECTS TRUTH. MOTION NEVER CREATES TRUTH.
 *
 * The centre follows the user's ACTIVE interaction. Background work running
 * elsewhere in SaathiOS must never hijack it: an agent someone else started, or
 * a scheduled run, belongs to the agent/activity surfaces until it is
 * explicitly brought into context.
 *
 * Correlation uses the identifier SaathiOS already has — `conversation_id` on
 * an agent run (see saathi/agent_runtime/api.py; components/chat/ChatWorkspace
 * resolves its own run the same way). No new ID system is introduced.
 *
 * This module is observational. It selects nothing to execute, grants no
 * authority, and never mutates a run.
 */

/** How a contextual run was chosen. Carried into the snapshot for provenance. */
export const RUN_CONTEXT_SOURCE = Object.freeze({
  EXPLICIT: "EXPLICIT",           // a run id pinned to this interaction
  SUBMITTED: "SUBMITTED",         // returned by the command just submitted here
  CONVERSATION: "CONVERSATION",   // an existing run already on this conversation
  NONE: "NONE",
});

const str = (v) => (v == null ? "" : String(v));

/** A run still doing work, per the agent runtime's own vocabulary. */
export function isRunActive(run) {
  const state = str(run?.state || run?.status).toLowerCase();
  return ["queued", "planning", "running", "executing", "waiting", "paused"].includes(state);
}

/**
 * Resolve the run the Command Core represents.
 *
 * Priority, highest first:
 *   1. an explicit run id pinned to this conversation
 *   2. the run returned by the command just submitted from this surface
 *   3. the newest run already correlated to this conversation
 *   4. nothing
 *
 * There is deliberately NO fallback to a globally active run. A run belonging
 * to another conversation is not this centre's business, even when it is the
 * only thing running.
 *
 * @param {object} [input]
 * @param {string} [input.conversationId] identity of the central interaction
 * @param {string} [input.explicitRunId]
 * @param {string} [input.submittedRunId]
 * @param {Array<object>} [input.conversationRuns] runs the server returned for THIS conversation
 * @returns {{runId: string, conversationId: string, source: string, startedAt: number|null, status: string}|null}
 */
export function selectContextualRun(input = {}) {
  const conversationId = str(input.conversationId);
  const runs = Array.isArray(input.conversationRuns) ? input.conversationRuns : [];

  // Only runs the server itself correlated to this conversation are eligible.
  // A run carrying a different conversation_id is refused even if handed in.
  const eligible = runs.filter((r) => {
    const rc = str(r?.conversation_id ?? r?.conversationId);
    return rc !== "" && conversationId !== "" && rc === conversationId;
  });

  const build = (run, source) => ({
    runId: str(run?.id ?? run?.run_id),
    conversationId,
    source,
    startedAt: Number.isFinite(Number(run?.created_at)) ? Number(run.created_at) : null,
    status: str(run?.state || run?.status),
  });

  const explicit = str(input.explicitRunId);
  if (explicit) {
    const match = eligible.find((r) => str(r?.id ?? r?.run_id) === explicit);
    // An explicit id that the server does not correlate to this conversation is
    // not honoured: pinning must not become a way to adopt someone else's run.
    if (match) return build(match, RUN_CONTEXT_SOURCE.EXPLICIT);
  }

  const submitted = str(input.submittedRunId);
  if (submitted) {
    const match = eligible.find((r) => str(r?.id ?? r?.run_id) === submitted);
    if (match) return build(match, RUN_CONTEXT_SOURCE.SUBMITTED);
    // The submission is this surface's own act, so it stands even before the
    // list catches up — but only ever as this conversation's run.
    if (conversationId) {
      return { runId: submitted, conversationId, source: RUN_CONTEXT_SOURCE.SUBMITTED, startedAt: null, status: "" };
    }
  }

  if (eligible.length > 0) {
    // Newest first by the server's own timestamp; ties keep server order.
    const newest = [...eligible].sort((a, b) => {
      const av = Number(a?.created_at); const bv = Number(b?.created_at);
      if (!Number.isFinite(av) && !Number.isFinite(bv)) return 0;
      if (!Number.isFinite(av)) return 1;
      if (!Number.isFinite(bv)) return -1;
      return bv - av;
    })[0];
    return build(newest, RUN_CONTEXT_SOURCE.CONVERSATION);
  }

  return null;
}

/**
 * Keep only events belonging to the contextual run.
 *
 * The adapter already isolates by run id; this is the earlier gate, so events
 * from an unrelated run never even reach the snapshot.
 */
export function eventsForContext(events, context) {
  const runId = str(context?.runId);
  if (!runId) return [];
  const rows = Array.isArray(events) ? events : [];
  return rows.filter((e) => {
    const rid = str(e?.run_id ?? e?.payload?.run_id);
    return rid === "" || rid === runId;
  });
}
