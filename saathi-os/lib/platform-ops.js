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
