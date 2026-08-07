/**
 * UI-NEXT-3.1 — Pure helpers for Production Hybrid Command motion.
 * No runtime animation library. State-truth only; no financial authority.
 */

import { VOICE_SESSION_STATES } from "./design-lab/contracts.js";

/** Proposal lifecycle labels (presentation only — never implies execution). */
export const PROPOSAL_LIFECYCLE_STATES = Object.freeze([
  "DRAFT",
  "READY_FOR_RISK",
  "RISK_BLOCKED",
  "DATA_INSUFFICIENT",
  "READY_FOR_APPROVAL",
  "APPROVED",
  "REJECTED",
  "EXPIRED",
  "SUPERSEDED",
  "STALE_PROPOSAL",
]);

/** Risk presentation statuses (pass-through; not computed here). */
export const RISK_MOTION_STATES = Object.freeze([
  "HEALTHY",
  "WARNING",
  "BREACHED",
  "DATA_INSUFFICIENT",
  "RECONCILIATION_REQUIRED",
  "UNAVAILABLE",
]);

/** Agent / mission bounded indicators. */
export const AGENT_MOTION_STATES = Object.freeze([
  "ACTIVE",
  "WAITING",
  "BLOCKED",
  "COMPLETE",
  "FAILED",
  "VETOED",
  "APPROVAL_REQUIRED",
  "IDLE",
]);

/**
 * Voice presentation metadata for Saathi Core.
 * @param {string} state
 */
export function voicePresentation(state) {
  const s = VOICE_SESSION_STATES.includes(state) ? state : "READY";
  const map = {
    IDLE: { tone: "muted", loop: false, label: "Idle", reduced: "static" },
    READY: { tone: "info", loop: false, label: "Ready", reduced: "static" },
    LISTENING: { tone: "info", loop: true, label: "Listening", reduced: "static badge" },
    TRANSCRIBING: { tone: "info", loop: true, label: "Transcribing", reduced: "static badge" },
    THINKING: { tone: "think", loop: true, label: "Thinking", reduced: "text only" },
    SPEAKING: { tone: "ok", loop: true, label: "Speaking", reduced: "static" },
    INTERRUPTING: { tone: "warn", loop: false, label: "Interrupting", reduced: "static" },
    DEGRADED: { tone: "warn", loop: false, label: "Degraded", reduced: "badge" },
    ERROR: { tone: "crit", loop: false, label: "Error", reduced: "badge" },
    CLOSED: { tone: "muted", loop: false, label: "Closed", reduced: "static" },
  };
  return { state: s, ...map[s] };
}

/**
 * Risk visual tone from backend risk_status (no recomputation).
 * @param {string|null|undefined} status
 */
export function riskMotionTone(status) {
  const s = String(status || "UNAVAILABLE").toUpperCase();
  if (s === "HEALTHY") return "ok";
  if (s === "WARNING") return "warn";
  if (s === "BREACHED" || s === "RECONCILIATION_REQUIRED") return "crit";
  if (s === "DATA_INSUFFICIENT") return "warn";
  return "muted";
}

/**
 * Proposal visual tone — never "executed"/green success for money movement.
 * APPROVED stays warn/info attention (not execution).
 * @param {string|null|undefined} status
 */
export function proposalMotionTone(status) {
  const s = String(status || "DRAFT").toUpperCase();
  if (s === "RISK_BLOCKED" || s === "REJECTED") return "crit";
  if (
    s === "READY_FOR_APPROVAL" ||
    s === "APPROVED" ||
    s === "DATA_INSUFFICIENT" ||
    s === "STALE_PROPOSAL" ||
    s === "EXPIRED" ||
    s === "SUPERSEDED"
  ) {
    return "warn";
  }
  if (s === "READY_FOR_RISK") return "info";
  return "info";
}

/**
 * Whether motion loops are allowed for a voice state under reduced motion.
 * @param {string} state
 * @param {boolean} reducedMotion
 */
export function allowVoiceLoop(state, reducedMotion) {
  if (reducedMotion) return false;
  const p = voicePresentation(state);
  return !!p.loop;
}

/**
 * Related evidence filter — only real link fields; never fabricate.
 * @param {Array<object>} events
 * @param {{ kind?: string, id?: string|null, relatedIds?: string[] }} sel
 */
export function relatedEvidenceEvents(events, sel) {
  const list = Array.isArray(events) ? events : [];
  if (!sel?.id && !(sel?.relatedIds || []).length) return [];
  const ids = new Set([sel.id, ...(sel.relatedIds || [])].filter(Boolean).map(String));
  const kind = sel.kind ? String(sel.kind).toLowerCase() : "";
  return list.filter((ev) => {
    const evIds = [
      ev.id,
      ev.proposal_id,
      ev.agent_id,
      ev.mission_id,
      ev.symbol,
      ...(ev.related_ids || []),
    ]
      .filter(Boolean)
      .map(String);
    if (evIds.some((x) => ids.has(x))) return true;
    if (kind && String(ev.type || "").toLowerCase().includes(kind)) return true;
    return false;
  });
}

/**
 * Technology decision constants for certification docs / tests.
 */
export const MOTION_TECH = Object.freeze({
  primary: "CSS_SUFFICIENT",
  gsap: "GSAP_RUNTIME_DEFERRED",
  lottie: "LOTTIE_RUNTIME_DEFERRED",
  three: "THREE_JS_DEFERRED",
  webAnimations: "NOT_REQUIRED",
});

export { VOICE_SESSION_STATES };
