export const TERMINAL_RUNTIME_STATES = new Set([
  "COMPLETED",
  "FAILED",
  "CANCELLED",
  "TIMED_OUT",
]);

export function runtimeTone(state) {
  if (state === "COMPLETED" || state === "ACTIVE") return "ok";
  if (state === "FAILED" || state === "REVOKED") return "error";
  if (state === "PAUSED" || state === "RECOVERING" || state === "SUSPENDED") return "warn";
  return "neutral";
}

export function canCancelExecution(execution) {
  return Boolean(execution) && !TERMINAL_RUNTIME_STATES.has(execution.state);
}

export function requiresDestructiveConfirmation(action) {
  return ["REVOKE_BINDING", "RESOLVE_FAILED", "RESOLVE_CANCELLED", "CONFIRM_TIMEOUT"].includes(
    action,
  );
}

export function safeAuthorityOptions(role) {
  if (role === "admin" || role === "system") {
    return ["READ_ONLY", "LOCAL_MUTATION", "EXTERNAL_MUTATION", "SECURITY_SENSITIVE"];
  }
  if (role === "owner") return ["READ_ONLY", "LOCAL_MUTATION", "EXTERNAL_MUTATION"];
  if (role === "operator") return ["READ_ONLY", "LOCAL_MUTATION"];
  return ["READ_ONLY"];
}

// —— M54 private-alpha operational readiness ——

export const EVIDENCE_EXPORT_KINDS = [
  "execution_summary",
  "lifecycle_timeline",
  "attention",
  "reconciliation_history",
  "binding_metadata",
  "approval_references",
  "audit_events",
  "certification_manifest",
];

// Bounded, presentation-only descriptor for every operator-visible surface
// state. Authority is never derived here — the server owns role and tenancy.
const UI_STATE_LABELS = {
  loading: { label: "Loading", tone: "neutral" },
  empty: { label: "Nothing yet", tone: "neutral" },
  denied: { label: "Not permitted", tone: "error" },
  SUSPENDED: { label: "Suspended", tone: "warn" },
  REVOKED: { label: "Revoked", tone: "error" },
  WAITING_APPROVAL: { label: "Waiting approval", tone: "warn" },
  PAUSED: { label: "Paused", tone: "warn" },
  RECOVERING: { label: "Manual review", tone: "warn" },
  UNCERTAIN: { label: "Uncertain dispatch", tone: "warn" },
  FAILED: { label: "Failed", tone: "error" },
  CANCELLED: { label: "Cancelled", tone: "neutral" },
  TIMED_OUT: { label: "Timed out", tone: "error" },
  COMPLETED: { label: "Completed", tone: "ok" },
  ACTIVE: { label: "Active", tone: "ok" },
};

export function uiStateDescriptor(key) {
  return UI_STATE_LABELS[key] || { label: String(key || "Unknown"), tone: "neutral" };
}

const ATTENTION_SEVERITY = {
  DISPATCH_OUTCOME_UNCERTAIN: "critical",
  MANUAL_REVIEW_REQUIRED: "critical",
  BINDING_REVOKED: "critical",
  CONTEXT_INVALIDATED: "critical",
  APPROVAL_EXPIRED: "warn",
  APPROVAL_REJECTED: "warn",
  BINDING_SUSPENDED: "warn",
  IDEMPOTENCY_CONFLICT: "warn",
  TIMEOUT_PENDING: "warn",
  CANCELLATION_PENDING: "warn",
  APPROVAL_REQUIRED: "info",
  PAUSED_AFTER_RESTART: "info",
};

export function attentionSeverity(reason) {
  return ATTENTION_SEVERITY[reason] || "info";
}

// Retention administration (dry-run preview) is owner/admin only.
export function canPreviewRetention(role) {
  return role === "owner" || role === "admin" || role === "system";
}

// Evidence export needs runtime-read, which every known platform role has.
export function canExportEvidence(role) {
  return ["viewer", "operator", "owner", "admin", "system"].includes(role);
}

// Production is never authorized in private alpha; the UI must not imply it.
export function isProductionAuthorized(diagnostics) {
  return Boolean(diagnostics?.environment?.production_authorized) === true
    ? false // fail-closed: even a truthy field is not honored client-side
    : false;
}

export function safetyBadges(diagnostics) {
  const safety = diagnostics?.safety || {};
  return [
    { key: "connector", label: `Connectors: ${safety.connector_mutations || "DRY_RUN_ONLY"}` },
    { key: "financial", label: `Financial: ${safety.financial_execution || "DISABLED"}` },
    { key: "trading", label: `Trading: ${safety.trading_execution || "DISABLED"}` },
    { key: "guardian", label: `Guardian: ${safety.trading_guardian || "UNENGAGED_ADVISORY_ONLY"}` },
  ];
}
