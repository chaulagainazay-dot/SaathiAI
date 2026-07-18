"""M32 — Deterministic, bounded retry decisions.

A retry is permitted ONLY when every gate holds: the operation is idempotent, the
error category is retryable, retry budget remains, the total deadline still has
room, the credential is eligible, approval is still valid, the provider is not
quarantined, connector rollout permits it, and the request fingerprint is
unchanged. Any failure denies the retry. Non-idempotent writes never auto-retry.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from saathi.connectors.providers.models import RETRYABLE_CATEGORIES, RetryCategory


@dataclass
class RetryDecision:
    should_retry: bool
    reason: str
    delay_seconds: float = 0.0
    attempt: int = 0


@dataclass
class RetryGates:
    idempotent: bool = False
    credential_eligible: bool = True
    approval_valid: bool = True
    provider_quarantined: bool = False
    rollout_permits: bool = True
    fingerprint_unchanged: bool = True


def deterministic_backoff(
    attempt: int, *, base: float = 0.01, factor: float = 2.0, cap: float = 5.0,
) -> float:
    """Pure deterministic backoff (no jitter → stable tests)."""
    if attempt <= 0:
        return 0.0
    return min(cap, base * (factor ** (attempt - 1)))


def decide_retry(
    *,
    category: RetryCategory,
    attempt: int,
    max_retries: int,
    remaining_deadline: float,
    gates: RetryGates,
    retry_after: Optional[float] = None,
    max_retry_after: float = 10.0,
    backoff_base: float = 0.01,
    backoff_factor: float = 2.0,
) -> RetryDecision:
    """Return a deterministic retry decision. attempt is the number already made."""
    # Hard denials first (fail closed) — order matters for clear reasons
    if category == RetryCategory.CANCELLED:
        return RetryDecision(False, "cancelled", attempt=attempt)
    if category == RetryCategory.POLICY_BLOCKED:
        return RetryDecision(False, "policy_blocked", attempt=attempt)
    if not gates.idempotent:
        return RetryDecision(False, "non_idempotent", attempt=attempt)
    if not gates.fingerprint_unchanged:
        return RetryDecision(False, "request_changed", attempt=attempt)
    if not gates.credential_eligible:
        return RetryDecision(False, "credential_ineligible", attempt=attempt)
    if not gates.approval_valid:
        return RetryDecision(False, "approval_invalid", attempt=attempt)
    if gates.provider_quarantined:
        return RetryDecision(False, "provider_quarantined", attempt=attempt)
    if not gates.rollout_permits:
        return RetryDecision(False, "rollout_blocked", attempt=attempt)
    if category in (RetryCategory.NO_RETRY, RetryCategory.PERMANENT_FAILURE, RetryCategory.REAUTH_REQUIRED):
        return RetryDecision(False, f"non_retryable:{category.value}", attempt=attempt)
    if category not in RETRYABLE_CATEGORIES:
        return RetryDecision(False, f"non_retryable:{category.value}", attempt=attempt)
    if attempt > max_retries:
        return RetryDecision(False, "retry_budget_exhausted", attempt=attempt)

    # compute delay
    if category in (RetryCategory.RATE_LIMITED, RetryCategory.RETRY_AFTER) and retry_after is not None:
        if retry_after > max_retry_after:
            return RetryDecision(False, "retry_after_exceeds_cap", attempt=attempt)
        delay = float(retry_after)
    else:
        delay = deterministic_backoff(attempt + 1, base=backoff_base, factor=backoff_factor)

    if delay > remaining_deadline:
        return RetryDecision(False, "retry_exceeds_deadline", attempt=attempt)

    return RetryDecision(True, "retry_permitted", delay_seconds=delay, attempt=attempt)
