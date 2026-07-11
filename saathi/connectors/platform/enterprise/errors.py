"""M15.3 provider error taxonomy — stable, safe, redacted normalization."""
from __future__ import annotations

from saathi.security.redteam.config import redact

# stable category -> (retryable, user_action, operator_action)
TAXONOMY = {
    "authentication_required": (False, "Connect the account.", "n/a"),
    "authentication_expired": (False, "Reconnect the account.", "check token refresh"),
    "token_refresh_failed": (False, "Reconnect the account.", "inspect refresh flow"),
    "permission_denied": (False, "Grant the required permission.", "n/a"),
    "missing_scope": (False, "Reconnect with the required scope.", "n/a"),
    "invalid_request": (False, "Fix the request.", "validate input schema"),
    "not_found": (False, "Check the target exists.", "n/a"),
    "conflict": (False, "Resolve the conflict and retry.", "n/a"),
    "rate_limited": (True, "Wait and retry.", "raise limits / backoff"),
    "provider_unavailable": (True, "Retry shortly.", "check provider status"),
    "timeout": (True, "Retry shortly.", "increase timeout / check network"),
    "network_error": (True, "Retry shortly.", "check connectivity"),
    "invalid_response": (False, "Contact support.", "inspect provider payload"),
    "webhook_invalid": (False, "n/a", "verify signature/secret"),
    "side_effect_uncertain": (False, "Reconcile before retrying.", "manual reconciliation"),
    "account_revoked": (False, "Reconnect the account.", "n/a"),
    "circuit_open": (False, "Wait for recovery.", "inspect provider failures"),
    "policy_denied": (False, "Action not permitted.", "review policy"),
    "approval_required": (False, "Approve the exact action.", "n/a"),
    "approval_invalid": (False, "Re-request approval.", "n/a"),
    "internal_error": (False, "Contact support.", "inspect logs"),
}


def normalize(*, category: str, provider_code: str = "", detail: str = "",
              correlation_id: str = "") -> dict:
    retryable, user_action, op_action = TAXONOMY.get(
        category, (False, "Contact support.", "inspect"))
    return {
        "code": category if category in TAXONOMY else "internal_error",
        "retryable": retryable,
        "user_message": user_action,          # safe, non-sensitive
        "user_action": user_action,
        "operator_action": op_action,
        "provider_code": redact(str(provider_code))[:64],
        "correlation_id": correlation_id,
        "detail": redact(str(detail))[:200],  # redacted — never a secret
    }
