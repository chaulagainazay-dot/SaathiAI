"""M32 — Provider health & readiness (distinct from connector health / account readiness).

Provider health is a SEPARATE signal. A healthy provider does not imply
authorized execution; a linked account does not imply provider health; a
certified connector does not imply provider compatibility. Readiness composes
all layers but never collapses them.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field, replace
from typing import Any, Optional

from saathi.connectors.providers.models import (
    HEALTHY_STATES,
    ProviderErrorCode,
    ProviderHealthState,
)

# How many consecutive malformed responses trigger quarantine consideration
MALFORMED_QUARANTINE_THRESHOLD = 3
DEGRADE_TIMEOUT_THRESHOLD = 1


@dataclass
class ProviderHealthRecord:
    provider_id: str
    state: str = ProviderHealthState.UNKNOWN.value
    consecutive_timeouts: int = 0
    consecutive_malformed: int = 0
    consecutive_auth_failures: int = 0
    last_reason: str = ""
    total_calls: int = 0
    total_failures: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderHealthTracker:
    """In-process provider health signal. Deterministic transitions on observations."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._records: dict[str, ProviderHealthRecord] = {}

    def _rec(self, provider_id: str) -> ProviderHealthRecord:
        rec = self._records.get(provider_id)
        if rec is None:
            rec = ProviderHealthRecord(provider_id=provider_id)
            self._records[provider_id] = rec
        return rec

    def get(self, provider_id: str) -> ProviderHealthRecord:
        with self._lock:
            return self._rec(provider_id)

    def peek(self, provider_id: str) -> Optional[ProviderHealthRecord]:
        """Read a provider's record WITHOUT creating one. Returns None if unseen.

        `get` defaults a missing provider into existence, which is correct for an
        observation path — the first call is about to record something. It is wrong
        for a health READ: asking "how is provider X?" must never be what causes
        provider X to exist, or a monitoring pass would grow the registry with
        every provider it merely asked about.

        Returns a copy, so a reader cannot mutate tracked state by holding the
        record it was given.
        """
        with self._lock:
            rec = self._records.get(provider_id)
            return None if rec is None else replace(rec)

    def peek_all(self) -> dict[str, ProviderHealthRecord]:
        """Every KNOWN provider record, copied. Creates nothing."""
        with self._lock:
            return {k: replace(v) for k, v in self._records.items()}

    def known_provider_ids(self) -> tuple[str, ...]:
        with self._lock:
            return tuple(sorted(self._records))

    def observe_success(self, provider_id: str) -> ProviderHealthState:
        with self._lock:
            rec = self._rec(provider_id)
            rec.total_calls += 1
            rec.consecutive_timeouts = 0
            rec.consecutive_malformed = 0
            rec.consecutive_auth_failures = 0
            rec.state = ProviderHealthState.HEALTHY.value
            rec.last_reason = "success"
            return ProviderHealthState(rec.state)

    def observe_error(self, provider_id: str, code: ProviderErrorCode) -> ProviderHealthState:
        with self._lock:
            rec = self._rec(provider_id)
            rec.total_calls += 1
            rec.total_failures += 1
            state = ProviderHealthState.DEGRADED

            if code == ProviderErrorCode.TIMEOUT:
                rec.consecutive_timeouts += 1
                state = ProviderHealthState.DEGRADED
            elif code == ProviderErrorCode.RATE_LIMITED:
                state = ProviderHealthState.RATE_LIMITED
            elif code in (ProviderErrorCode.AUTHENTICATION_FAILED, ProviderErrorCode.AUTHORIZATION_FAILED, ProviderErrorCode.SCOPE_INSUFFICIENT):
                rec.consecutive_auth_failures += 1
                state = ProviderHealthState.AUTH_BLOCKED
            elif code in (ProviderErrorCode.PROVIDER_UNAVAILABLE, ProviderErrorCode.CONNECTION_FAILED):
                state = ProviderHealthState.UNAVAILABLE
            elif code == ProviderErrorCode.MALFORMED_RESPONSE:
                rec.consecutive_malformed += 1
                if rec.consecutive_malformed >= MALFORMED_QUARANTINE_THRESHOLD:
                    state = ProviderHealthState.QUARANTINED
                else:
                    state = ProviderHealthState.DEGRADED

            rec.state = state.value
            rec.last_reason = code.value
            return state

    def force_state(self, provider_id: str, state: ProviderHealthState, *, reason: str = "") -> None:
        with self._lock:
            rec = self._rec(provider_id)
            rec.state = state.value
            rec.last_reason = reason or state.value

    def should_quarantine(self, provider_id: str) -> bool:
        with self._lock:
            rec = self._rec(provider_id)
            return rec.consecutive_malformed >= MALFORMED_QUARANTINE_THRESHOLD


@dataclass
class ReadinessDecision:
    ready: bool
    provider_id: str
    reason: str = "ok"
    layers: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def compute_readiness(
    *,
    provider_id: str,
    config_enabled: bool,
    connector_certified: bool,
    provider_verified: bool,
    provider_health: ProviderHealthState,
    account_ready: bool = True,
    credential_ready: bool = True,
    scope_sufficient: bool = True,
    operation_supported: bool = True,
    approval_valid: bool = True,
    rollout_permits_production: bool = False,
) -> ReadinessDecision:
    """Compose all readiness layers. Any single failure denies. Layers stay distinct."""
    layers = {
        "config_enabled": config_enabled,
        "connector_certified": connector_certified,
        "provider_verified": provider_verified,
        "provider_health": provider_health.value,
        "account_ready": account_ready,
        "credential_ready": credential_ready,
        "scope_sufficient": scope_sufficient,
        "operation_supported": operation_supported,
        "approval_valid": approval_valid,
        "rollout_permits_production": rollout_permits_production,
    }
    if not config_enabled:
        return ReadinessDecision(False, provider_id, "provider_disabled", layers)
    if not connector_certified:
        return ReadinessDecision(False, provider_id, "connector_not_certified", layers)
    if not provider_verified:
        return ReadinessDecision(False, provider_id, "provider_not_verified", layers)
    if provider_health not in HEALTHY_STATES:
        return ReadinessDecision(False, provider_id, f"provider_health:{provider_health.value}", layers)
    if not operation_supported:
        return ReadinessDecision(False, provider_id, "operation_unsupported", layers)
    if not account_ready:
        return ReadinessDecision(False, provider_id, "account_not_ready", layers)
    if not credential_ready:
        return ReadinessDecision(False, provider_id, "credential_not_ready", layers)
    if not scope_sufficient:
        return ReadinessDecision(False, provider_id, "scope_insufficient", layers)
    if not approval_valid:
        return ReadinessDecision(False, provider_id, "approval_invalid", layers)
    # All governance layers pass; still shadow/simulation only (rollout OFF).
    return ReadinessDecision(True, provider_id, "ready_shadow_only", layers)
