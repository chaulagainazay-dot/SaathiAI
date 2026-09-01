/**
 * CENTRAL COMMAND CORE — runtime-to-core adapter.
 *
 * MOTION REFLECTS TRUTH. MOTION NEVER CREATES TRUTH.
 *
 * Folds existing SaathiOS runtime truth into ONE Command Core snapshot so the
 * UI never reconstructs the state machine itself. See
 * docs/command-core/EVENT_PROVENANCE.md for the source of every field.
 *
 * Hard rules enforced here:
 * - No frontend clock. This module never reads Date.now(), never starts a
 *   timer, and never treats elapsed time, animation completion or React
 *   lifecycle as system truth. Every timestamp comes from the backend row.
 * - No authority. It grants nothing, clears no Guardian block, and turns no
 *   model output into an approval.
 * - No fabrication. Absent progress stays absent; absent verification is
 *   reported as unavailable, never as success.
 */

import { deriveCommandCoreState, missionLiveness } from "./command-core-state.js";

/** Run-event names as written by saathi/agent_runtime/store.py. */
export const RUN_EVENT = Object.freeze({
  DELEGATED: "delegation.created",
  AGENT_STARTED: "agent.started",
  APPROVAL_REQUESTED: "approval.requested",
  APPROVAL_RESOLVED: "approval.resolved",
  VERIFICATION_PASSED: "verification.passed",
  VERIFICATION_FAILED: "verification.failed",
  TOOL_REQUESTED: "tool.requested",
  TASK_FAILED: "task.failed",
  RUN_STATE: "run.state",
  RUN_COMPLETED: "run.completed",
});

/** Provenance classes, mirroring the map document. */
export const PROVENANCE = Object.freeze({
  AUTHORITATIVE: "AUTHORITATIVE",
  TRUSTED_RUNTIME: "TRUSTED_RUNTIME",
  DERIVED: "DERIVED",
  ADVISORY: "ADVISORY",
  UNAVAILABLE: "UNAVAILABLE",
});

const num = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

/** The fabric mirrors run events as `agentrun.<name>`; accept either form. */
function eventName(raw) {
  const name = String(raw || "");
  return name.startsWith("agentrun.") ? name.slice("agentrun.".length) : name;
}

/** An approval payload is authoritative only when it states an outcome. */
function approvalOutcome(payload) {
  const source = payload && typeof payload === "object" ? payload : {};
  if (source.approved === true || source.outcome === "APPROVED" || source.decision === "APPROVED") {
    return "APPROVED";
  }
  if (source.approved === false || source.outcome === "DENIED" || source.decision === "DENIED") {
    return "DENIED";
  }
  return null;
}

/**
 * Fold a run's event log into current facts.
 *
 * Defends against out-of-order and duplicate delivery: rows are deduped by id
 * and folded in backend timestamp order, so a late-arriving older event cannot
 * overwrite a newer fact. Events for other runs are dropped, so mission A can
 * never move mission B.
 *
 * @param {Array<object>} events rows from GET /runs/{rid}/events or agentrun.* frames
 * @param {{runId?: string}} [options]
 */
export function reduceRunEvents(events, options = {}) {
  const runId = options.runId ? String(options.runId) : null;
  const rows = Array.isArray(events) ? events : [];

  const seen = new Set();
  const ordered = rows
    .filter((row) => {
      if (!row || typeof row !== "object") return false;
      const rowRun = row.run_id ?? row.payload?.run_id;
      if (runId && rowRun != null && String(rowRun) !== runId) return false;
      const id = row.id != null ? String(row.id) : null;
      if (id !== null) {
        if (seen.has(id)) return false;
        seen.add(id);
      }
      return true;
    })
    .map((row, index) => ({ row, index, at: num(row.created_at ?? row.ts) }))
    .sort((a, b) => {
      if (a.at === null && b.at === null) return a.index - b.index;
      if (a.at === null) return -1;
      if (b.at === null) return 1;
      if (a.at === b.at) return a.index - b.index;
      return a.at - b.at;
    });

  const fold = {
    delegatedAt: null,
    agentStartedAt: null,
    runState: null,
    runCompletedAt: null,
    toolRequestedAt: null,
    approvalPending: false,
    approvalId: null,
    approvalRequestedAt: null,
    approvalDecision: null,
    approvalDecidedAt: null,
    verificationState: "UNAVAILABLE",
    verifiedAt: null,
    failedAt: null,
    lastEvent: null,
    lastEventAt: null,
  };

  for (const { row, at } of ordered) {
    const name = eventName(row.name);
    const payload = row.payload && typeof row.payload === "object" ? row.payload : {};
    fold.lastEvent = name;
    fold.lastEventAt = at;

    switch (name) {
      case RUN_EVENT.DELEGATED:
        fold.delegatedAt = at;
        break;
      case RUN_EVENT.AGENT_STARTED:
        fold.agentStartedAt = at;
        break;
      case RUN_EVENT.TOOL_REQUESTED:
        // A request is not a start. Never promoted to EXECUTING.
        fold.toolRequestedAt = at;
        break;
      case RUN_EVENT.APPROVAL_REQUESTED:
        fold.approvalPending = true;
        fold.approvalId = payload.approval_id != null ? String(payload.approval_id) : fold.approvalId;
        fold.approvalRequestedAt = at;
        fold.approvalDecision = null;
        fold.approvalDecidedAt = null;
        break;
      case RUN_EVENT.APPROVAL_RESOLVED: {
        const outcome = approvalOutcome(payload);
        // An unlabelled resolution is not a grant.
        if (outcome) {
          fold.approvalPending = false;
          fold.approvalDecision = outcome;
          fold.approvalDecidedAt = at;
        }
        break;
      }
      case RUN_EVENT.VERIFICATION_PASSED:
        fold.verificationState = "PASSED";
        fold.verifiedAt = at;
        break;
      case RUN_EVENT.VERIFICATION_FAILED:
        fold.verificationState = "FAILED";
        fold.verifiedAt = at;
        break;
      case RUN_EVENT.TASK_FAILED:
        fold.failedAt = at;
        break;
      case RUN_EVENT.RUN_STATE:
        // The agent runtime writes the transition as {from, to}; `state` is the
        // shape this fold originally assumed. Read both so a terminal run is
        // actually recognised.
        if (payload.to != null) fold.runState = String(payload.to);
        else if (payload.state != null) fold.runState = String(payload.state);
        break;
      case RUN_EVENT.RUN_COMPLETED:
        fold.runCompletedAt = at;
        break;
      default:
        break;
    }
  }

  return fold;
}

/**
 * Build the Command Core snapshot the UI renders from.
 *
 * @param {object} [input]
 * @param {object} [input.voiceSession] `useVoiceSession().session`
 * @param {number|null} [input.microphoneEnergy] RMS from the owned capture path
 * @param {Array<object>} [input.runEvents] run event rows
 * @param {string} [input.runId] isolate to one run
 * @param {Array<object>} [input.missions] normalized mission runtime summaries
 * @param {object} [input.guardian] verdict supplied by the trading path only
 * @param {object} [input.execution] execution truth supplied by the trading path only
 * @param {object} [input.system] infra health read model
 * @param {string} [input.previousCoreState]
 */
export function buildCommandCoreSnapshot(input = {}) {
  const session = input.voiceSession || {};
  const voiceState = String(session.state || "").toUpperCase();
  const fold = reduceRunEvents(input.runEvents, { runId: input.runId });
  const missions = Array.isArray(input.missions) ? input.missions : [];
  const guardian = input.guardian || {};
  const execution = input.execution || {};
  const system = input.system || {};

  // Guardian is only ever asserted by the trading path. Absent that input the
  // Command Core cannot and must not produce BLOCKED.
  const guardianBlocked = guardian.blocked === true;
  const guardianBlockedAt = num(guardian.blockedAt);

  // A grant older than the block does not survive the block.
  const approvalGranted =
    fold.approvalDecision === "APPROVED" &&
    !(guardianBlocked && guardianBlockedAt !== null && num(fold.approvalDecidedAt) !== null
      && num(fold.approvalDecidedAt) < guardianBlockedAt);

  const degradedReasons = [];
  if (system?.models?.status === "DEGRADED") degradedReasons.push("models");
  if (system?.gateway?.status === "DEGRADED") degradedReasons.push("gateway");
  if (voiceState === "DEGRADED" || voiceState === "ERROR") degradedReasons.push("voice");
  const degraded = degradedReasons.length > 0;

  // Execution is only what the trading path asserted. Nothing here promotes a
  // tool request into an execution.
  const executionActive = execution.active === true;
  const executionComplete = execution.complete === true;
  const executionState = executionActive
    ? "ACTIVE"
    : executionComplete
      ? "COMPLETE"
      : fold.toolRequestedAt !== null
        ? "REQUESTED"
        : "NONE";

  const verifying = executionComplete && fold.verificationState === "UNAVAILABLE"
    ? false
    : execution.verifying === true;

  // The contextual run counts as live delegated work once an agent has started
  // and the run has not finished. A terminal run stops supervising, so the
  // centre cannot get stuck reporting work that already ended.
  const terminalRun = ["completed", "failed", "cancelled", "expired"]
    .includes(String(fold.runState || "").toLowerCase());
  const runDelegatedWorkActive =
    fold.agentStartedAt !== null && fold.runCompletedAt === null && !terminalRun;

  const derived = deriveCommandCoreState({
    delegatedWorkActive: runDelegatedWorkActive,
    guardian: { blocked: guardianBlocked },
    approval: { pending: fold.approvalPending },
    execution: { active: executionActive, verifying },
    assistant: {
      processing: voiceState === "THINKING",
      speaking: voiceState === "SPEAKING",
    },
    voice: { state: voiceState },
    delegation: { active: fold.delegatedAt !== null && fold.agentStartedAt === null },
    missions,
    system: { degraded },
  });

  // Execution finished but SaathiOS produced no verification signal for it.
  // This is a real, reportable condition — never rendered as success.
  const verificationLabel =
    executionComplete && fold.verificationState === "UNAVAILABLE"
      ? "EXECUTION_COMPLETE_VERIFICATION_UNAVAILABLE"
      : fold.verificationState;

  return {
    coreState: derived.state,
    previousCoreState: input.previousCoreState || null,
    motion: derived.motion,
    timing: derived.timing,
    transitionReason: derived.reason,
    transitionEvent: fold.lastEvent,
    sourceTimestamp: fold.lastEventAt,

    listening: derived.state === "LISTENING",
    microphoneEnergy: num(input.microphoneEnergy),
    transcriptPartial: String(session.transcriptPartial || ""),
    transcriptFinal: String(session.transcriptFinal || ""),
    assistantProcessing: voiceState === "THINKING",
    assistantSpeaking: voiceState === "SPEAKING",

    supervising: derived.supervising,
    activeMissionIds: [
      ...missions
        .filter((m) => ["ACTIVE", "RUNNING", "WAITING"].includes(String(m?.state || "").toUpperCase()))
        .map((m) => String(m.missionId ?? m.mission_id ?? "")),
      ...(runDelegatedWorkActive && input.runId ? [String(input.runId)] : []),
    ].filter((id, i, all) => id && all.indexOf(id) === i),
    missionLiveness: missions.map((m) => missionLiveness(m)),

    approvalPending: fold.approvalPending,
    approvalId: fold.approvalId,
    approvalDecision: fold.approvalDecision,
    approvalGranted,

    guardianBlocked,
    guardianDecisionId: guardian.decisionId != null ? String(guardian.decisionId) : null,

    executionState,
    verificationState: verificationLabel,

    degraded,
    degradedReasons,

    provenance: {
      voice: PROVENANCE.TRUSTED_RUNTIME,
      delegation: PROVENANCE.TRUSTED_RUNTIME,
      agent: PROVENANCE.TRUSTED_RUNTIME,
      agentCompletion: PROVENANCE.DERIVED,
      approval: PROVENANCE.AUTHORITATIVE,
      guardian: guardianBlocked ? PROVENANCE.AUTHORITATIVE : PROVENANCE.UNAVAILABLE,
      execution: executionActive || executionComplete ? PROVENANCE.AUTHORITATIVE : PROVENANCE.UNAVAILABLE,
      verification: fold.verificationState === "UNAVAILABLE" ? PROVENANCE.UNAVAILABLE : PROVENANCE.AUTHORITATIVE,
      degraded: PROVENANCE.ADVISORY,
    },
  };
}
