"use client";

/**
 * "Authority Centre" — the read-only view of who decided what.
 *
 * Distinct from `command-authority.js`, which composes the trading authority
 * strip; this reads run-level authority truth from the agent runtime.
 *
 * Two types only, and they are not interchangeable:
 *
 *   APPROVAL_REQUIRED  a decision is waiting for the owner
 *   BLOCKED            the system has stopped the work
 *
 * DEGRADED and FAILED are deliberately absent. A capability problem is not an
 * authority refusal and a runtime failure is not a decision; attention owns
 * both, and copying them here would make this a second "What needs you".
 *
 * Nothing in this module grants, clears, resolves or implies authority. It
 * reports what the approval store and the run state already assert, and where
 * they disagree it prefers the more restrictive reading.
 */

import { CONTEXT_CLASS, classifyRun } from "./agent-orchestration.js";

export const AUTHORITY_TYPE = Object.freeze({
  APPROVAL_REQUIRED: "APPROVAL_REQUIRED",
  BLOCKED: "BLOCKED",
});

/** Which system asserted the decision. Never inferred from wording. */
export const AUTHORITY_PROVENANCE = Object.freeze({
  APPROVAL_STORE: "AUTHORITATIVE_APPROVAL_STORE",
  RUN_STATE: "AUTHORITATIVE_RUN_STATE",
});

export const AUTHORITY_TITLE = Object.freeze({
  [AUTHORITY_TYPE.APPROVAL_REQUIRED]: "Approval required",
  [AUTHORITY_TYPE.BLOCKED]: "Blocked",
});

/** What the owner is told each provenance means, in the system's own voice. */
export const PROVENANCE_LABEL = Object.freeze({
  [AUTHORITY_PROVENANCE.APPROVAL_STORE]: "Approval store",
  [AUTHORITY_PROVENANCE.RUN_STATE]: "Run authority state",
});

/**
 * Deterministic precedence.
 *
 * BLOCKED outranks APPROVAL_REQUIRED for the same reason it does in attention:
 * a block is a refusal the owner cannot satisfy by deciding. Listing an approval
 * above a block would invite the reading that approving clears it.
 */
export const AUTHORITY_PRECEDENCE = Object.freeze({
  [AUTHORITY_TYPE.BLOCKED]: 0,
  [AUTHORITY_TYPE.APPROVAL_REQUIRED]: 1,
});

function str(v) {
  return v == null ? "" : String(v);
}

function num(v) {
  if (v == null || v === "") return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/**
 * One authority item from one API item.
 *
 * Returns null for anything that is not one of the two real authority types, so
 * an unrecognised state can never be rendered as an authority decision.
 */
export function buildAuthorityItem(apiItem, { conversationId = "" } = {}) {
  const type = AUTHORITY_TYPE[str(apiItem?.type).toUpperCase()];
  if (!type) return null;

  const runId = str(apiItem?.run_id);
  if (!runId) return null;

  const approvals = Array.isArray(apiItem?.approvals) ? apiItem.approvals : [];
  const provenance = str(apiItem?.provenance);

  return {
    id: str(apiItem?.id) || `${type}:${runId}`,
    type,
    title: AUTHORITY_TITLE[type],
    source: "agent-runtime.authority",
    // Trusted only when the API named a provenance we recognise.
    provenance: Object.values(AUTHORITY_PROVENANCE).includes(provenance)
      ? provenance
      : AUTHORITY_PROVENANCE.RUN_STATE,
    runId,
    missionId: str(apiItem?.mission_id) || null,
    conversationId: str(apiItem?.conversation_id) || null,
    contextClass: classifyRun({ conversation_id: apiItem?.conversation_id }, conversationId),
    subject: str(apiItem?.objective),
    // Deterministic system wording, supplied by the backend contract.
    reason: str(apiItem?.reason) || null,
    detailCode: str(apiItem?.detail_code) || null,
    state: str(apiItem?.state),
    createdAt: num(apiItem?.created_at),
    updatedAt: num(apiItem?.updated_at),
    resolutionState: "UNRESOLVED",
    // Identifiers only -- never a token, a credential or agent reasoning.
    approvalIds: approvals.map((a) => str(a?.approval_id)).filter(Boolean),
    approvalCount: approvals.length,
    /**
     * Whether a decision exists for the owner to make. It is NOT permission:
     * the approval route performs its own authorisation, and this surface
     * renders no control either way.
     */
    canUserAct: type === AUTHORITY_TYPE.APPROVAL_REQUIRED && approvals.length > 0,
    // Phase 10 is observation. The surface grants nothing.
    allowedActions: [],
    readOnly: true,
  };
}

/** Precedence first, then the backend's own recency; never a model ranking. */
function byPrecedenceThenRecency(a, b) {
  const p = AUTHORITY_PRECEDENCE[a.type] - AUTHORITY_PRECEDENCE[b.type];
  if (p !== 0) return p;
  const d = (b.updatedAt ?? b.createdAt ?? 0) - (a.updatedAt ?? a.createdAt ?? 0);
  if (d !== 0) return d;
  return a.runId < b.runId ? 1 : a.runId > b.runId ? -1 : 0;
}

export function buildAuthorityCentre({ items = [], conversationId = "" } = {}) {
  const list = Array.isArray(items) ? items : [];

  const built = list
    .map((i) => buildAuthorityItem(i, { conversationId }))
    .filter(Boolean);

  // Collapse on the real identifier, so a replayed `approval.requested` or a
  // repeated `run.state` cannot produce two rows for one decision.
  const seen = new Set();
  const deduped = [];
  for (const item of built) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    deduped.push(item);
  }

  deduped.sort(byPrecedenceThenRecency);

  return {
    items: deduped,
    counts: {
      total: deduped.length,
      approvals: deduped.filter((i) => i.type === AUTHORITY_TYPE.APPROVAL_REQUIRED).length,
      blocked: deduped.filter((i) => i.type === AUTHORITY_TYPE.BLOCKED).length,
    },
    /**
     * Execution readiness is deliberately absent.
     *
     * Nothing available here establishes it: an approval being granted is not
     * ExecutionGateway permission, authentication is not authority, and a clear
     * authority list only means nothing is *currently* held. Reporting
     * readiness without a trusted contract would be the one claim this surface
     * must never make, so it makes none.
     */
    executionReadiness: null,
    readOnly: true,
  };
}

/** Only events that can change an authority decision. */
export const AUTHORITY_INVALIDATING_EVENTS = Object.freeze([
  "run.state", "approval.requested", "approval.resolved", "run.completed",
]);

const RUN_EVENT_PREFIX = "agentrun.";

export function shouldRefreshAuthority(eventName) {
  const name = String(eventName || "");
  if (!name.startsWith(RUN_EVENT_PREFIX)) return false;
  return AUTHORITY_INVALIDATING_EVENTS.includes(name.slice(RUN_EVENT_PREFIX.length));
}
