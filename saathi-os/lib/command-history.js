"use client";

/**
 * "What I've been doing" — the history read model.
 *
 * The third surface of the triad, and the only one that looks backwards:
 *
 *   Who I've got working   active work            (Phase 6)
 *   What needs you         unresolved attention   (Phase 7)
 *   What I've been doing   terminal truth         here
 *
 * It is built from durable run records -- the backend's own `orchestration_run`
 * rows, carrying `state`, `updated_at` and `terminal_reason` -- never from rows
 * the other two surfaces dropped. Those surfaces apply presentation retention;
 * reading their leftovers would make history a function of what was recently on
 * screen instead of what actually happened.
 *
 * It is not an event log. A run that emitted nineteen lifecycle events is one
 * historical record, because that is what the owner did: one piece of work that
 * ended one way.
 *
 * Three truths are kept apart, because conflating them is how a history surface
 * starts lying: a run *ending* is not a run *succeeding*, succeeding is not
 * being *verified*, and being verified is not having *executed* anything.
 */

import { CONTEXT_CLASS, classifyRun } from "./agent-orchestration.js";

/** Terminal states, mirroring `agent_runtime/models.py::_TERMINAL` exactly. */
export const TERMINAL_STATES = Object.freeze([
  "completed", "cancelled", "failed", "timed_out", "rolled_back", "partially_completed",
]);

/**
 * Owner-facing wording. Each maps one backend state and nothing else:
 * `partially_completed` is never "Completed", and no state is ever "Verified".
 */
export const TERMINAL_LABEL = Object.freeze({
  completed: "Completed",
  failed: "Failed",
  cancelled: "Cancelled",
  timed_out: "Timed out",
  rolled_back: "Rolled back",
  partially_completed: "Partially completed",
});

/** Verification is its own axis, never derived from how a run ended. */
export const VERIFICATION = Object.freeze({
  PASSED: "PASSED",
  FAILED: "FAILED",
  UNAVAILABLE: "UNAVAILABLE",
});

export const VERIFICATION_LABEL = Object.freeze({
  [VERIFICATION.PASSED]: "Verified",
  [VERIFICATION.FAILED]: "Verification failed",
  // Absence says nothing at all -- it must never read as a quiet success.
  [VERIFICATION.UNAVAILABLE]: null,
});

/**
 * Certification strategies. Their runs are real runtime records, but they exist
 * to exercise the system, not to do the owner's work, so they are excluded from
 * history by default. Mirrors the doubly-gated fixtures in
 * `agent_runtime/test_hold.py` and `agent_runtime/test_fail.py`.
 */
export const TEST_STRATEGIES = Object.freeze(["test_hold", "test_fail"]);

/** How many historical records the surface shows before disclosing the rest. */
export const HISTORY_LIMIT = 10;

function str(v) {
  return v == null ? "" : String(v);
}

function num(v) {
  // `Number(null)` and `Number("")` are 0, which is finite -- so a missing
  // timestamp would sort as the epoch instead of falling back to the run's
  // start. Absent stays absent.
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

export function isTerminal(state) {
  return TERMINAL_STATES.includes(str(state).toLowerCase());
}

export function isTestStrategy(strategy) {
  return TEST_STRATEGIES.includes(str(strategy).toLowerCase());
}

/**
 * Verification for one run, from that run's own events.
 *
 * Only a real `verification.passed` / `verification.failed` counts. A completed
 * run with no verification event is UNAVAILABLE, not passed -- inferring
 * otherwise is exactly the manufactured success this surface must not produce.
 * A single failure outweighs any number of passes.
 */
export function verificationFromEvents(events) {
  const list = Array.isArray(events) ? events : [];
  let sawPass = false;
  for (const ev of list) {
    const name = str(ev?.name).toLowerCase().replace(/^agentrun\./, "");
    if (name === "verification.failed") return VERIFICATION.FAILED;
    if (name === "verification.passed") sawPass = true;
  }
  return sawPass ? VERIFICATION.PASSED : VERIFICATION.UNAVAILABLE;
}

/** One historical record from one durable run row. */
export function buildHistoryItem(run, { conversationId = "", events = null } = {}) {
  const state = str(run?.state).toLowerCase();
  if (!isTerminal(state)) return null;

  const runId = str(run?.id ?? run?.run_id);
  if (!runId) return null;

  const strategy = str(run?.strategy);

  return {
    // Derived from the run's own identifier, so replayed events, a repeated
    // `run.state` and a duplicated SSE delivery all collapse onto one record.
    id: `HISTORY:${runId}`,
    type: "RUN",
    runId,
    missionId: str(run?.mission_id) || null,
    conversationId: str(run?.conversation_id) || null,
    contextClass: classifyRun(run, conversationId),
    // The run's own text, not a summary we wrote.
    subject: str(run?.objective),
    strategy,
    terminalState: state,
    terminalLabel: TERMINAL_LABEL[state] || state,
    startedAt: num(run?.created_at),
    // Stamped by the backend on the transition that ended the run.
    endedAt: num(run?.updated_at),
    verificationState: events ? verificationFromEvents(events) : VERIFICATION.UNAVAILABLE,
    // Only the reason the backend itself wrote. Absence stays absence.
    failureReason: str(run?.terminal_reason) || null,
    // A record of a certification fixture, not of the owner's work.
    isTestStrategy: isTestStrategy(strategy),
    provenance: "REAL",
    source: "agent-runtime.orchestration_run",
    // History observes. It never offers to re-run, retry or restore anything.
    allowedActions: [],
    readOnly: true,
  };
}

/**
 * Most recently ended first.
 *
 * `updated_at` is wall-clock and the fabric gives only a partial order, so two
 * records that ended in the same instant have no guaranteed order between them;
 * the run id breaks that tie so the list is at least stable across renders
 * rather than appearing to shuffle.
 */
function byMostRecentlyEnded(a, b) {
  const d = (b.endedAt ?? b.startedAt ?? 0) - (a.endedAt ?? a.startedAt ?? 0);
  if (d !== 0) return d;
  return a.runId < b.runId ? 1 : a.runId > b.runId ? -1 : 0;
}

/**
 * The whole surface.
 *
 * Takes the durable run list the page already holds and, optionally, events for
 * runs whose events were already fetched -- so this adds no request, no
 * subscription and no per-row fetch.
 */
export function buildCommandHistory({
  runs = [],
  conversationId = "",
  eventsByRunId = {},
  includeTestStrategies = false,
  limit = HISTORY_LIMIT,
} = {}) {
  const list = Array.isArray(runs) ? runs : [];

  const all = list
    .map((run) => buildHistoryItem(run, {
      conversationId,
      events: eventsByRunId[str(run?.id ?? run?.run_id)] || null,
    }))
    .filter(Boolean);

  // Collapse on the real identifier, never on display text: two different runs
  // may legitimately share an objective.
  const seen = new Set();
  const deduped = [];
  for (const item of all) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    deduped.push(item);
  }

  // Certification runs are real, but they are not the owner's work.
  const eligible = includeTestStrategies
    ? deduped
    : deduped.filter((i) => !i.isTestStrategy);
  const testStrategyRecords = deduped.length - eligible.length;

  eligible.sort(byMostRecentlyEnded);

  const items = eligible.slice(0, Math.max(0, limit));
  const withheld = Math.max(0, eligible.length - items.length);

  return {
    items,
    counts: {
      shown: items.length,
      total: eligible.length,
      byTerminalState: TERMINAL_STATES.reduce((acc, s) => {
        acc[s] = eligible.filter((i) => i.terminalState === s).length;
        return acc;
      }, {}),
    },
    // Never a silent cap.
    withheld,
    // Reported so certification can state how much of the record is fixtures.
    testStrategyRecords,
    // Nothing here is an action.
    readOnly: true,
  };
}

/**
 * The handoff between the three surfaces, written down so it cannot drift.
 *
 * A run is active, then terminal: orchestration hands it to history. A failure
 * is unresolved attention *and* a historical fact, so it legitimately appears on
 * both surfaces -- but answering different questions, in different words, and
 * never with the same emphasis: attention says a thing needs the owner, history
 * says a thing happened.
 */
export const TRIAD_HANDOFF = Object.freeze([
  { surface: "WHO_IVE_GOT_WORKING", holds: "non-terminal runs", question: "what is running now" },
  { surface: "WHAT_NEEDS_YOU", holds: "unresolved attention", question: "what needs a decision" },
  { surface: "WHAT_IVE_BEEN_DOING", holds: "terminal runs", question: "what actually happened" },
]);
