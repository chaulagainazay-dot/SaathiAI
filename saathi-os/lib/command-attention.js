"use client";

/**
 * "What needs you" — the attention read model.
 *
 * One rule decides membership: if the owner does not currently need to know,
 * decide, acknowledge, repair or intervene, it is not here. This surface is not
 * a notification feed, not an activity history and not an approval console.
 *
 * Everything below is derived from backend truth that already exists:
 *   APPROVAL_REQUIRED  run.state = awaiting_approval        AUTHORITATIVE
 *   BLOCKED            run.state = blocked                  AUTHORITATIVE
 *   FAILED             run.state = failed                   TRUSTED_RUNTIME
 *   DEGRADED           the certified Command Core snapshot  ADVISORY
 *
 * No new source was invented to make the panel richer, and no row derives its
 * own authority: authority is a property of the type, fixed here.
 *
 * Resolution is backend truth, never a frontend event. An item stops being
 * produced the moment the run leaves the state that justified it, or the
 * degraded condition clears. Nothing here resolves because a row was clicked,
 * an animation ended, time passed, or another item arrived.
 */

import { CONTEXT_CLASS, classifyRun } from "./agent-orchestration.js";
import { degradedText } from "./command-core-status.js";

export const ATTENTION_TYPE = Object.freeze({
  APPROVAL_REQUIRED: "APPROVAL_REQUIRED",
  BLOCKED: "BLOCKED",
  FAILED: "FAILED",
  DEGRADED: "DEGRADED",
});

/** How much a type is allowed to assert. Fixed per type; never per row. */
export const AUTHORITY_CLASS = Object.freeze({
  AUTHORITATIVE: "AUTHORITATIVE",
  TRUSTED_RUNTIME: "TRUSTED_RUNTIME",
  ADVISORY: "ADVISORY",
});

export const TYPE_AUTHORITY = Object.freeze({
  [ATTENTION_TYPE.BLOCKED]: AUTHORITY_CLASS.AUTHORITATIVE,
  [ATTENTION_TYPE.APPROVAL_REQUIRED]: AUTHORITY_CLASS.AUTHORITATIVE,
  [ATTENTION_TYPE.FAILED]: AUTHORITY_CLASS.TRUSTED_RUNTIME,
  [ATTENTION_TYPE.DEGRADED]: AUTHORITY_CLASS.ADVISORY,
});

/**
 * Deterministic precedence. Not a score, not a model judgement.
 *
 * BLOCKED outranks APPROVAL_REQUIRED because a block is a refusal the owner
 * cannot satisfy by deciding: an approval is waiting *for* the owner and can
 * still proceed, while a block has already stopped the work. Ranking approval
 * first would invite the reading that approving clears the block.
 */
export const TYPE_PRECEDENCE = Object.freeze({
  [ATTENTION_TYPE.BLOCKED]: 0,
  [ATTENTION_TYPE.APPROVAL_REQUIRED]: 1,
  [ATTENTION_TYPE.FAILED]: 2,
  [ATTENTION_TYPE.DEGRADED]: 3,
});

/** Only these run states are unresolved attention. Terminal success is not. */
export const RUN_STATE_ATTENTION = Object.freeze({
  awaiting_approval: ATTENTION_TYPE.APPROVAL_REQUIRED,
  blocked: ATTENTION_TYPE.BLOCKED,
  failed: ATTENTION_TYPE.FAILED,
});

export const ATTENTION_TITLE = Object.freeze({
  [ATTENTION_TYPE.APPROVAL_REQUIRED]: "Approval required",
  [ATTENTION_TYPE.BLOCKED]: "Blocked",
  [ATTENTION_TYPE.FAILED]: "Failed",
  [ATTENTION_TYPE.DEGRADED]: "Reduced capability",
});

/**
 * Presentation retention for FAILED only.
 *
 * A failed run is terminal, and the backend carries no "acknowledged" flag, so
 * nothing will ever mark it resolved. Retaining every failure forever would
 * turn this surface into the history panel it must not become. The cap is a
 * count over backend-ordered timestamps -- deterministic, and with no clock, so
 * it can never resolve anything by elapsed time. It limits what is *shown*; it
 * never touches lifecycle truth, and the overflow is disclosed, never silent.
 */
export const FAILED_RETENTION_LIMIT = 3;

function str(v) {
  return v == null ? "" : String(v);
}

function num(v) {
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

/** The attention type a run's own state justifies, or null. */
export function attentionTypeForRun(run) {
  return RUN_STATE_ATTENTION[str(run?.state).toLowerCase()] || null;
}

/**
 * One attention item from one run record.
 *
 * `detail` is optional and is only ever read for a reason string the backend
 * already produced. A reason is never generated: absence stays absence.
 */
export function buildRunAttentionItem(run, { conversationId = "", detail = null } = {}) {
  const type = attentionTypeForRun(run);
  if (!type) return null;

  const runId = str(run?.id ?? run?.run_id);
  if (!runId) return null;

  // Only a reason the backend wrote. No model text, no inference, no filler.
  const backendReason =
    str(detail?.terminal_reason) ||
    str(detail?.reason) ||
    str(run?.terminal_reason) ||
    "";

  return {
    // Stable across renders and derived from real identifiers, so repeated
    // events for the same run collapse onto the same row.
    id: `${type}:${runId}`,
    type,
    source: "agent-runtime.run.state",
    authorityClass: TYPE_AUTHORITY[type],
    title: ATTENTION_TITLE[type],
    // The objective is the run's own text, not a description we composed.
    subject: str(run?.objective),
    reason: backendReason || null,
    runId,
    missionId: str(run?.mission_id) || null,
    conversationId: str(run?.conversation_id) || null,
    contextClass: classifyRun(run, conversationId),
    createdAt: num(run?.created_at),
    resolutionState: "UNRESOLVED",
    provenance: "REAL",
    // The panel observes. It grants nothing.
    allowedActions: [],
    readOnly: true,
  };
}

/**
 * The single degraded item.
 *
 * Deliberately one item, never one per subsystem: the owner needs to know that
 * capability is reduced, not to read an inventory. The condition itself is the
 * certified Command Core signal (`command-core-adapter`), which already counts
 * only subsystem-level degradation -- models, gateway, voice -- and not each
 * unavailable optional provider. Reusing it means this panel and the centre can
 * never disagree about whether the system is degraded.
 */
export function buildDegradedAttentionItem(snapshot) {
  if (!snapshot || snapshot.degraded !== true) return null;

  return {
    id: `${ATTENTION_TYPE.DEGRADED}:system`,
    type: ATTENTION_TYPE.DEGRADED,
    source: "command-core.snapshot.degraded",
    authorityClass: AUTHORITY_CLASS.ADVISORY,
    title: ATTENTION_TITLE[ATTENTION_TYPE.DEGRADED],
    // Deterministic wording already certified in Phase 5.
    subject: degradedText(snapshot),
    reason: null,
    runId: null,
    missionId: null,
    conversationId: null,
    // System-wide: it belongs to no conversation and must not claim one.
    contextClass: CONTEXT_CLASS.UNASSOCIATED,
    createdAt: null,
    resolutionState: "UNRESOLVED",
    provenance: "REAL",
    allowedActions: [],
    readOnly: true,
  };
}

/** Precedence first, then the backend's own recency. Never a model ranking. */
function byPrecedenceThenRecency(a, b) {
  const p = TYPE_PRECEDENCE[a.type] - TYPE_PRECEDENCE[b.type];
  if (p !== 0) return p;
  return (b.createdAt ?? 0) - (a.createdAt ?? 0);
}

/**
 * The whole surface.
 *
 * Takes the run list Phase 6 already holds and the Command Core snapshot Phase 5
 * already owns, so this adds no request, no subscription and no second bus.
 */
export function buildAttention({
  runs = [],
  conversationId = "",
  snapshot = null,
  detailsByRunId = {},
} = {}) {
  const list = Array.isArray(runs) ? runs : [];

  const fromRuns = list
    .map((run) => buildRunAttentionItem(run, {
      conversationId,
      detail: detailsByRunId[str(run?.id ?? run?.run_id)] || null,
    }))
    .filter(Boolean);

  // Collapse by real identifier, never by display text. One run in one state is
  // one item however many task.failed or repeated run.state events produced it.
  const seen = new Set();
  const deduped = [];
  for (const item of fromRuns) {
    if (seen.has(item.id)) continue;
    seen.add(item.id);
    deduped.push(item);
  }

  // Presentation retention, applied to FAILED only and disclosed below.
  const failed = deduped
    .filter((i) => i.type === ATTENTION_TYPE.FAILED)
    .sort((a, b) => (b.createdAt ?? 0) - (a.createdAt ?? 0));
  const retainedFailed = failed.slice(0, FAILED_RETENTION_LIMIT);
  const withheldFailed = Math.max(0, failed.length - retainedFailed.length);
  const retainedFailedIds = new Set(retainedFailed.map((i) => i.id));

  const items = deduped
    .filter((i) => i.type !== ATTENTION_TYPE.FAILED || retainedFailedIds.has(i.id));

  const degradedItem = buildDegradedAttentionItem(snapshot);
  if (degradedItem) items.push(degradedItem);

  items.sort(byPrecedenceThenRecency);

  return {
    items,
    counts: {
      total: items.length,
      byType: Object.values(ATTENTION_TYPE).reduce((acc, t) => {
        acc[t] = items.filter((i) => i.type === t).length;
        return acc;
      }, {}),
    },
    // Never a silent cap: the panel says so when older failures are not listed.
    withheldFailed,
    // Nothing on this surface carries authority.
    readOnly: true,
  };
}
