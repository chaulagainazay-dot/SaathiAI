/**
 * "Who I've got working" — the agent orchestration read model.
 *
 * MOTION REFLECTS TRUTH. MOTION NEVER CREATES TRUTH.
 *
 * The centre tells you what Saathi is doing FOR you. This tells you what Saathi
 * is orchestrating AROUND you. They are related truths, not the same one, so
 * background work is visible here while never touching the central state.
 *
 * Pure derivation. It observes runs; it cannot approve, cancel, grant authority
 * or create run state. No clock is read: every timestamp comes from the backend.
 *
 * Built on the Phase 5 contracts (conversation_id correlation, missionLiveness,
 * run-event folding). It introduces no new correlation system and no event bus.
 */

import { missionLiveness } from "./command-core-state.js";

/** Mirrors saathi/agent_runtime/models.py::_TERMINAL exactly. */
export const RUN_TERMINAL_STATES = Object.freeze([
  "completed", "cancelled", "failed", "timed_out", "rolled_back", "partially_completed",
]);

/** Backend RunState vocabulary, used verbatim — no frontend-only lifecycle. */
export const RUN_STATE_LABEL = Object.freeze({
  created: "Queued",
  planning: "Planning",
  awaiting_approval: "Waiting for approval",
  approved: "Approved",
  queued: "Queued",
  running: "Working",
  delegated: "Delegated",
  verifying: "Verifying",
  reviewing: "Reviewing",
  completed: "Completed",
  paused: "Paused",
  cancelled: "Cancelled",
  timed_out: "Timed out",
  blocked: "Blocked",
  failed: "Failed",
  rolled_back: "Rolled back",
  partially_completed: "Partly completed",
});

export const CONTEXT_CLASS = Object.freeze({
  IN_CONTEXT: "IN_CONTEXT",
  BACKGROUND: "BACKGROUND",
  UNASSOCIATED: "UNASSOCIATED",
});

/**
 * Deterministic role → display name. Only roles the runtime actually uses
 * (see saathi/agent_runtime/strategies.py). An unknown role is shown as-is
 * rather than renamed, so the panel can never invent an agent.
 */
export const AGENT_DISPLAY_NAME = Object.freeze({
  planner: "Planner",
  builder: "Builder",
  reviewer: "Reviewer",
  researcher: "Research",
  architect: "Architect",
  writer: "Writer",
  ceo: "Business",
});

export function agentDisplayName(role) {
  const key = String(role || "").trim().toLowerCase();
  if (!key) return "Agent";
  return AGENT_DISPLAY_NAME[key] || String(role).trim();
}

const str = (v) => (v == null ? "" : String(v));
const num = (v) => (Number.isFinite(Number(v)) ? Number(v) : null);

export function isTerminalRunState(state) {
  return RUN_TERMINAL_STATES.includes(str(state).toLowerCase());
}

/** Lifecycle straight from the backend state; nothing is inferred. */
export function runLifecycle(run) {
  const state = str(run?.state || run?.status).toLowerCase();
  return {
    state: state || "unknown",
    label: RUN_STATE_LABEL[state] || "Unknown",
    terminal: isTerminalRunState(state),
    active: Boolean(state) && !isTerminalRunState(state),
  };
}

/**
 * Classify a run against the active conversation.
 *
 * A run with no conversation_id is UNASSOCIATED, never guessed into context.
 */
export function classifyRun(run, conversationId) {
  const rc = str(run?.conversation_id ?? run?.conversationId);
  if (!rc) return CONTEXT_CLASS.UNASSOCIATED;
  if (conversationId && rc === str(conversationId)) return CONTEXT_CLASS.IN_CONTEXT;
  return CONTEXT_CLASS.BACKGROUND;
}

/** Facts this panel needs from a run's own event rows. Never cross-run. */
export function factsFromEvents(events, runId) {
  const rows = Array.isArray(events) ? events : [];
  const mine = rows.filter((e) => {
    const rid = str(e?.run_id ?? e?.payload?.run_id);
    return rid === "" || rid === str(runId);
  });
  const ordered = [...mine].sort((a, b) => (num(a?.created_at) ?? 0) - (num(b?.created_at) ?? 0));

  let agentRole = "";
  let verification = "UNAVAILABLE";
  let failureReason = "";
  let startedAt = null;

  for (const e of ordered) {
    const name = str(e?.name).replace(/^agentrun\./, "");
    const payload = e?.payload && typeof e.payload === "object" ? e.payload : {};
    if (name === "agent.started") {
      agentRole = str(payload.agent) || agentRole;
      if (startedAt === null) startedAt = num(e?.created_at);
    } else if (name === "verification.passed") {
      verification = "PASSED";
    } else if (name === "verification.failed") {
      verification = "FAILED";
    } else if (name === "task.failed") {
      failureReason = str(payload.error || payload.reason) || failureReason;
    }
  }
  return { agentRole, verification, failureReason, startedAt };
}

/**
 * One row per run.
 *
 * Liveness stays exactly as certified: PROGRESS only when the server reported
 * it, HEARTBEAT when only aliveness is known, UNKNOWN otherwise. Absence is
 * never rendered as 0%, and nothing is inferred from elapsed time, event count,
 * task count or animation.
 */
export function buildWorkItem(run, { conversationId = "", events = [] } = {}) {
  const runId = str(run?.id ?? run?.run_id);
  const lifecycle = runLifecycle(run);
  const facts = factsFromEvents(events, runId);
  const liveness = missionLiveness(run);

  return {
    runId,
    missionId: str(run?.mission_id ?? run?.missionId) || null,
    conversationId: str(run?.conversation_id ?? run?.conversationId) || null,
    contextClass: classifyRun(run, conversationId),
    agent: agentDisplayName(facts.agentRole),
    agentRole: facts.agentRole || null,
    strategy: str(run?.strategy) || null,
    objective: str(run?.objective).slice(0, 140) || null,
    lifecycle,
    startedAt: facts.startedAt ?? num(run?.created_at),
    completedAt: lifecycle.terminal ? num(run?.updated_at ?? run?.finished_at) : null,
    liveness,
    verification: facts.verification,
    failureReason: facts.failureReason || null,
    // Populated only by real signals; see WHAT_NEEDS_YOU_SOURCES.
    needsYou: lifecycle.state === "awaiting_approval"
      ? "approval"
      : lifecycle.state === "failed"
        ? "failure"
        : lifecycle.state === "blocked"
          ? "blocked"
          : null,
    provenance: "REAL",
  };
}

/**
 * The panel's whole read model.
 *
 * `eventsByRunId` is optional: rows render from run records alone when a run's
 * events have not been fetched, rather than inventing detail.
 */
export function buildAgentOrchestration({
  runs = [],
  eventsByRunId = {},
  conversationId = "",
} = {}) {
  const list = Array.isArray(runs) ? runs : [];
  const items = list
    .map((run) => buildWorkItem(run, {
      conversationId,
      events: eventsByRunId[str(run?.id ?? run?.run_id)] || [],
    }))
    .filter((item) => item.runId);

  const byRecency = (a, b) => (b.startedAt ?? 0) - (a.startedAt ?? 0);
  const inContext = items.filter((i) => i.contextClass === CONTEXT_CLASS.IN_CONTEXT).sort(byRecency);
  const background = items.filter((i) => i.contextClass === CONTEXT_CLASS.BACKGROUND).sort(byRecency);
  const unassociated = items.filter((i) => i.contextClass === CONTEXT_CLASS.UNASSOCIATED).sort(byRecency);

  const activeCount = items.filter((i) => i.lifecycle.active).length;
  return {
    inContext,
    background,
    unassociated,
    counts: {
      total: items.length,
      active: activeCount,
      inContextActive: inContext.filter((i) => i.lifecycle.active).length,
      backgroundActive: background.filter((i) => i.lifecycle.active).length,
    },
    // Nothing here is an action. The panel observes; it never authorises.
    readOnly: true,
  };
}

/**
 * Phase 7 contract, documented now so the panel does not paint us into a
 * corner. These are the ONLY real signals that should ever flow into
 * "What needs you"; each already exists as backend truth.
 */
export const WHAT_NEEDS_YOU_SOURCES = Object.freeze([
  { key: "approval", source: "run.state = awaiting_approval", authority: "AUTHORITATIVE" },
  { key: "failure", source: "run.state = failed / task.failed", authority: "TRUSTED_RUNTIME" },
  { key: "blocked", source: "run.state = blocked", authority: "AUTHORITATIVE" },
  { key: "degraded", source: "infrastructure health", authority: "ADVISORY" },
]);
