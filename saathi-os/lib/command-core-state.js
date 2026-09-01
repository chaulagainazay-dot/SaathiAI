/**
 * CENTRAL COMMAND CORE — canonical runtime state contract.
 *
 * MOTION REFLECTS TRUTH. MOTION NEVER CREATES TRUTH.
 *
 * Pure derivation only. This module holds NO authority: it never grants
 * execution, never clears a Guardian block, and never synthesises progress.
 * Every value it returns is derived from state the backend already asserted,
 * or is an explicit sentinel meaning "not reported".
 *
 * Companion to lib/command-motion.js (presentation) and lib/command-authority.js
 * (authority strip composition). This module is the single state source those
 * surfaces read, so components do not each invent their own booleans.
 */

/** The twelve Command Core states. Ordered loosely by lifecycle, not priority. */
export const COMMAND_CORE_STATES = Object.freeze([
  "IDLE",
  "LISTENING",
  "UNDERSTANDING",
  "THINKING",
  "SPEAKING",
  "DELEGATING",
  "SUPERVISING",
  "WAITING_APPROVAL",
  "EXECUTING",
  "VERIFYING",
  "BLOCKED",
  "DEGRADED",
]);

/** Motion primitive per state. One grammar, not twelve unrelated animations. */
export const MOTION_PRIMITIVE = Object.freeze({
  IDLE: "breathing",
  LISTENING: "energy-expansion",
  UNDERSTANDING: "inward-settle",
  THINKING: "restrained-orbital",
  SPEAKING: "speech-envelope",
  DELEGATING: "outward-handoff",
  SUPERVISING: "breathing-with-mission-marker",
  WAITING_APPROVAL: "held",
  EXECUTING: "directional-transfer",
  VERIFYING: "return-confirmation",
  BLOCKED: "locked-boundary",
  DEGRADED: "irregular-restrained",
});

/** Semantic timing classes. Authority never waits for cinema. */
export const TIMING_CLASS = Object.freeze({
  INSTANT: Object.freeze({ name: "INSTANT", minMs: 0, maxMs: 120 }),
  FAST: Object.freeze({ name: "FAST", minMs: 120, maxMs: 220 }),
  NORMAL: Object.freeze({ name: "NORMAL", minMs: 220, maxMs: 400 }),
  EXPRESSIVE: Object.freeze({ name: "EXPRESSIVE", minMs: 400, maxMs: 700 }),
  CONTINUOUS: Object.freeze({ name: "CONTINUOUS", minMs: null, maxMs: null }),
});

/** Entry timing per state. Safety states are INSTANT/FAST by contract. */
export const STATE_TIMING = Object.freeze({
  IDLE: "EXPRESSIVE",
  LISTENING: "CONTINUOUS",
  UNDERSTANDING: "NORMAL",
  THINKING: "CONTINUOUS",
  SPEAKING: "CONTINUOUS",
  DELEGATING: "NORMAL",
  SUPERVISING: "NORMAL",
  WAITING_APPROVAL: "INSTANT",
  EXECUTING: "NORMAL",
  VERIFYING: "NORMAL",
  BLOCKED: "INSTANT",
  DEGRADED: "FAST",
});

/** States whose entry must never be delayed for effect. */
export const SAFETY_STATES = Object.freeze(["BLOCKED", "WAITING_APPROVAL"]);

const truthy = (value) => value === true;
const nonEmpty = (value) => Array.isArray(value) && value.length > 0;
const finiteOrNull = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

/**
 * Mission liveness, split so heartbeat can never be read as progress.
 *
 * PROGRESS  — the server reported an actual percentage. Trustworthy.
 * HEARTBEAT — the worker is alive, and that is ALL that is known.
 * UNKNOWN   — nothing was reported. Renders as a sentinel, never as 0%.
 *
 * Elapsed time, animation duration, token streaming and frontend timers are
 * deliberately not accepted as inputs here.
 *
 * @param {{progress_percent?: number, last_heartbeat_at?: number}} [raw]
 * @returns {{kind: "PROGRESS"|"HEARTBEAT"|"UNKNOWN", percent: number|null, lastHeartbeatAt: number|null}}
 */
export function missionLiveness(raw) {
  const source = raw && typeof raw === "object" ? raw : {};
  const percent = finiteOrNull(source.progress_percent);
  const beat = finiteOrNull(source.last_heartbeat_at);
  if (percent !== null) {
    return {
      kind: "PROGRESS",
      percent: Math.max(0, Math.min(100, percent)),
      lastHeartbeatAt: beat,
    };
  }
  if (beat !== null) return { kind: "HEARTBEAT", percent: null, lastHeartbeatAt: beat };
  return { kind: "UNKNOWN", percent: null, lastHeartbeatAt: null };
}

/** True when the backend says at least one mission/agent is still working. */
export function hasLiveDelegatedWork(missions) {
  if (!nonEmpty(missions)) return false;
  return missions.some((m) => {
    const state = String(m?.state || m?.health || "").toUpperCase();
    return state === "ACTIVE" || state === "RUNNING" || state === "WAITING";
  });
}

/**
 * Derive the single Command Core state from runtime truth.
 *
 * Precedence is deliberate: authority outranks everything, because a block or
 * a pending approval must never be visually masked by conversation.
 *
 * @param {object} [input]
 * @returns {{state: string, motion: string, timing: string, degraded: boolean,
 *            supervising: boolean, reason: string}}
 */
export function deriveCommandCoreState(input = {}) {
  const guardian = input.guardian || {};
  const approval = input.approval || {};
  const execution = input.execution || {};
  const assistant = input.assistant || {};
  const voice = input.voice || {};
  const system = input.system || {};
  const delegation = input.delegation || {};
  const missions = Array.isArray(input.missions) ? input.missions : [];

  const degraded = truthy(system.degraded);
  const supervising = hasLiveDelegatedWork(missions);
  const voiceState = String(voice.state || "").toUpperCase();

  const settle = (state, reason) => ({
    state,
    motion: MOTION_PRIMITIVE[state],
    timing: STATE_TIMING[state],
    degraded,
    supervising,
    reason,
  });

  // 1. Authority first, always.
  if (truthy(guardian.blocked)) return settle("BLOCKED", "guardian.blocked");
  if (truthy(approval.pending)) return settle("WAITING_APPROVAL", "approval.requested");

  // 2. Work the backend says is actually in flight.
  if (truthy(execution.verifying)) return settle("VERIFYING", "execution.completed");
  if (truthy(execution.active)) return settle("EXECUTING", "execution.started");

  // 3. Saathi's own turn.
  if (truthy(assistant.speaking) || voiceState === "SPEAKING") {
    return settle("SPEAKING", "assistant.speaking.started");
  }
  if (truthy(delegation.active)) return settle("DELEGATING", "agent.delegated");
  if (truthy(assistant.processing) || voiceState === "THINKING") {
    return settle("THINKING", "assistant.processing.started");
  }
  if (voiceState === "TRANSCRIBING") return settle("UNDERSTANDING", "voice.transcript.final");
  if (voiceState === "LISTENING" || voiceState === "SPEECH_DETECTED") {
    return settle("LISTENING", "voice.energy.changed");
  }

  // 4. Delegated work still running while Saathi itself is quiet.
  //    This must NOT look like IDLE.
  if (supervising) return settle("SUPERVISING", "agent.started");

  // 5. Reduced capability, when nothing more specific is happening.
  if (degraded) return settle("DEGRADED", "system.degraded");

  return settle("IDLE", "idle");
}

/**
 * Guard illegal transitions. The UI cannot talk itself into execution.
 *
 * `grants` carries backend-asserted authority only. A frontend-set flag will
 * not appear here, because callers pass the server payload through unchanged.
 *
 * @returns {{allowed: boolean, reason: string}}
 */
export function assertTransition(from, to, grants = {}) {
  const deny = (reason) => ({ allowed: false, reason });
  const allow = () => ({ allowed: true, reason: "" });

  if (!COMMAND_CORE_STATES.includes(to)) return deny("unknown-target-state");

  if (to === "EXECUTING") {
    if (!truthy(grants.executionGranted)) return deny("execution-requires-backend-grant");
    if (from === "WAITING_APPROVAL" && !truthy(grants.approvalGranted)) {
      return deny("execution-requires-approval");
    }
    if (from === "BLOCKED") {
      const clearedAt = finiteOrNull(grants.guardianClearedAt);
      const blockedAt = finiteOrNull(grants.guardianBlockedAt);
      if (clearedAt === null || blockedAt === null || clearedAt <= blockedAt) {
        return deny("execution-requires-new-guardian-clearance");
      }
    }
    return allow();
  }

  if (to === "VERIFYING" && from !== "EXECUTING") return deny("verification-follows-execution");

  return allow();
}

/** Reduced-motion presentation. Safety state must survive without animation. */
export function reducedMotionPresentation(state) {
  const safe = COMMAND_CORE_STATES.includes(state) ? state : "IDLE";
  return Object.freeze({
    state: safe,
    animate: false,
    // Safety-critical states carry a text/badge affordance so meaning never
    // depends on movement.
    requiresTextAffordance: SAFETY_STATES.includes(safe) || safe === "DEGRADED",
  });
}
