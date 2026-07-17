"""M28 — Deterministic connector side-effect classification.

Caller-supplied classes never override registered policy.
Undeclared operations fail closed. Financial/trading/account changes blocked.
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional


class SideEffectClass(str, Enum):
    READ_ONLY = "READ_ONLY"
    LOCAL_MUTATION = "LOCAL_MUTATION"
    EXTERNAL_MUTATION = "EXTERNAL_MUTATION"
    COMMUNICATION = "COMMUNICATION"
    ACCOUNT_CHANGE = "ACCOUNT_CHANGE"
    FINANCIAL = "FINANCIAL"
    PRIVILEGED = "PRIVILEGED"
    PROHIBITED = "PROHIBITED"


# Operations that always fail closed
PROHIBITED_OPERATIONS = frozenset({
    "trade", "trade.execute", "place_order", "order.place", "withdrawal",
    "transfer_funds", "leverage", "margin", "futures", "spot_trade",
    "binance", "broker.execute",
})

FINANCIAL_OPERATIONS = frozenset({
    "charge", "payments.charge", "payout", "payouts", "transfer",
    "subscriptions", "invoices", "refund", "capture_payment",
})

ACCOUNT_CHANGE_OPERATIONS = frozenset({
    "rotate_credentials", "create_account", "delete_account",
    "change_password", "oauth_connect", "credential_write",
    "revoke_token", "grant_admin",
})

# Read-only / health style ops (no approval by default under policy)
READ_ONLY_OPERATIONS = frozenset({
    "health", "validate", "status", "inventory", "policy_check",
    "get", "list", "search", "read", "discover", "metrics", "report",
    "channels", "repos", "issues", "commits", "download",
    "git_rev_parse", "git_status_short", "python_version", "echo_safe",
})

LOCAL_MUTATION_OPERATIONS = frozenset({
    "draft", "archive", "organize", "append", "update", "create",
    "echo", "noop", "local-echo",
})

COMMUNICATION_OPERATIONS = frozenset({
    "send", "reply", "post", "comment", "invite", "email.send",
    "email.reply", "social.post", "messaging.send", "notify",
})

EXTERNAL_MUTATION_OPERATIONS = frozenset({
    "put", "patch", "delete", "write", "mutate", "upload", "schedule",
    "deploy", "http_request", "navigate", "create_event",
    "pull_requests", "publish",
})


@dataclass(frozen=True)
class SideEffectDecision:
    side_effect_class: SideEffectClass
    allowed: bool
    requires_approval: bool
    reason: str = ""
    blocked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "side_effect_class": self.side_effect_class.value,
            "allowed": self.allowed,
            "requires_approval": self.requires_approval,
            "reason": self.reason,
            "blocked": self.blocked,
        }


def _norm_op(operation: str) -> str:
    return (operation or "").strip().lower()


def classify_operation(
    operation: str,
    *,
    method: str = "GET",
    capability: str = "",
    registered_class: Optional[SideEffectClass] = None,
) -> SideEffectClass:
    """Map operation (+ optional method) to a side-effect class.

    ``registered_class`` from the connector registry wins over heuristics
    but cannot be weaker than PROHIBITED/FINANCIAL/ACCOUNT_CHANGE when
    the operation name clearly matches those sets.
    """
    op = _norm_op(operation)
    cap = _norm_op(capability)
    combined = {op, cap, op.split(".")[-1] if op else "", cap.split(".")[-1] if cap else ""}
    method_u = (method or "GET").upper()

    if any(x in PROHIBITED_OPERATIONS for x in combined) or any(
        p in op or p in cap for p in ("trade", "withdrawal", "binance", "leverage")
    ):
        return SideEffectClass.PROHIBITED
    if any(x in FINANCIAL_OPERATIONS for x in combined) or "payment" in op or "payment" in cap:
        return SideEffectClass.FINANCIAL
    if any(x in ACCOUNT_CHANGE_OPERATIONS for x in combined):
        return SideEffectClass.ACCOUNT_CHANGE

    # Hard security floors — registry cannot weaken these
    if registered_class in (
        SideEffectClass.PROHIBITED,
        SideEffectClass.FINANCIAL,
        SideEffectClass.ACCOUNT_CHANGE,
    ):
        return registered_class

    if registered_class is not None:
        # Registry may tighten (e.g. mark get as PRIVILEGED) but we re-check floors above
        return registered_class

    if any(x in COMMUNICATION_OPERATIONS for x in combined):
        return SideEffectClass.COMMUNICATION
    # Local mutations before method-based external classification
    if any(x in LOCAL_MUTATION_OPERATIONS for x in combined):
        return SideEffectClass.LOCAL_MUTATION
    # http_request inherits method class
    if op == "http_request" or "http_request" in combined:
        if method_u in ("POST", "PUT", "PATCH", "DELETE"):
            return SideEffectClass.EXTERNAL_MUTATION
        return SideEffectClass.READ_ONLY
    if any(x in EXTERNAL_MUTATION_OPERATIONS for x in combined):
        if op in READ_ONLY_OPERATIONS and method_u == "GET":
            return SideEffectClass.READ_ONLY
        return SideEffectClass.EXTERNAL_MUTATION
    if method_u in ("POST", "PUT", "PATCH", "DELETE"):
        if op in READ_ONLY_OPERATIONS:
            return SideEffectClass.READ_ONLY
        return SideEffectClass.EXTERNAL_MUTATION
    if any(x in READ_ONLY_OPERATIONS for x in combined) or method_u == "GET":
        return SideEffectClass.READ_ONLY
    # Undeclared → fail closed (PRIVILEGED blocked unless explicit policy)
    return SideEffectClass.PRIVILEGED


def evaluate_side_effect(
    side_effect_class: SideEffectClass,
    *,
    has_approval: bool = False,
    privileged_authorized: bool = False,
) -> SideEffectDecision:
    """Policy for a resolved side-effect class."""
    if side_effect_class is SideEffectClass.PROHIBITED:
        return SideEffectDecision(
            side_effect_class, False, True, "side_effect:PROHIBITED", blocked=True,
        )
    if side_effect_class is SideEffectClass.FINANCIAL:
        return SideEffectDecision(
            side_effect_class, False, True, "side_effect:FINANCIAL_blocked", blocked=True,
        )
    if side_effect_class is SideEffectClass.ACCOUNT_CHANGE:
        return SideEffectDecision(
            side_effect_class, False, True, "side_effect:ACCOUNT_CHANGE_blocked", blocked=True,
        )
    if side_effect_class is SideEffectClass.PRIVILEGED:
        if not privileged_authorized:
            return SideEffectDecision(
                side_effect_class, False, True, "side_effect:PRIVILEGED_blocked", blocked=True,
            )
        if not has_approval:
            return SideEffectDecision(
                side_effect_class, False, True, "side_effect:PRIVILEGED_approval_required",
            )
        return SideEffectDecision(side_effect_class, True, True, "ok")

    if side_effect_class is SideEffectClass.READ_ONLY:
        return SideEffectDecision(side_effect_class, True, False, "ok")

    if side_effect_class is SideEffectClass.LOCAL_MUTATION:
        # Local mutation follows policy; approval preferred but not mandatory by default
        return SideEffectDecision(side_effect_class, True, False, "ok")

    if side_effect_class in (
        SideEffectClass.EXTERNAL_MUTATION,
        SideEffectClass.COMMUNICATION,
    ):
        if not has_approval:
            return SideEffectDecision(
                side_effect_class, False, True,
                f"side_effect:{side_effect_class.value}_approval_required",
            )
        return SideEffectDecision(side_effect_class, True, True, "ok")

    return SideEffectDecision(
        SideEffectClass.PROHIBITED, False, True, "side_effect:unknown", blocked=True,
    )


def capability_to_side_effect(capability: str) -> SideEffectClass:
    """Map catalog capability strings like email.send → class."""
    cap = _norm_op(capability)
    if not cap:
        return SideEffectClass.PRIVILEGED
    # Full capability and verb
    verb = cap.split(".", 1)[-1]
    return classify_operation(cap, capability=cap, method="POST" if verb in (
        "send", "post", "charge", "upload", "create", "delete", "reply",
    ) else "GET")
