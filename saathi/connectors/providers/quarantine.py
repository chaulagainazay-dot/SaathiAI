"""M32 — Provider-adapter quarantine (distinct from connector deprecation & credential quarantine).

Quarantine blocks new provider calls, preserves safe metadata, never deletes
credentials, never auto-revokes unrelated account links, emits safe evidence, and
requires explicit recovery.
"""
from __future__ import annotations

import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# Reasons a provider adapter may be quarantined
QUARANTINE_REASONS = frozenset({
    "repeated_malformed_responses",
    "redaction_failure",
    "secret_exposure",
    "impossible_response_state",
    "adapter_contract_violation",
    "repeated_authentication_anomalies",
    "provider_identity_mismatch",
    "request_signing_mismatch",
    "operator_action",
    "critical_incident",
})


@dataclass
class QuarantineRecord:
    provider_id: str
    quarantined: bool = False
    reason: str = ""
    safe_metadata: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ProviderQuarantineStore:
    """In-process quarantine ledger. Explicit recovery required."""

    def __init__(self, *, clock: Optional[Any] = None) -> None:
        import time as _t
        self.clock = clock or _t.time
        self._lock = threading.RLock()
        self._records: dict[str, QuarantineRecord] = {}

    def _rec(self, provider_id: str) -> QuarantineRecord:
        rec = self._records.get(provider_id)
        if rec is None:
            rec = QuarantineRecord(provider_id=provider_id)
            self._records[provider_id] = rec
        return rec

    def is_quarantined(self, provider_id: str) -> bool:
        with self._lock:
            return self._rec(provider_id).quarantined

    def get(self, provider_id: str) -> QuarantineRecord:
        with self._lock:
            return self._rec(provider_id)

    def quarantine(self, provider_id: str, *, reason: str, safe_metadata: Optional[dict[str, Any]] = None) -> QuarantineRecord:
        safe_reason = reason if reason in QUARANTINE_REASONS else "critical_incident"
        with self._lock:
            rec = self._rec(provider_id)
            rec.quarantined = True
            rec.reason = safe_reason
            # only keep non-sensitive metadata keys
            md = {k: v for k, v in (safe_metadata or {}).items()
                  if not any(x in str(k).lower() for x in ("token", "secret", "cookie", "authorization", "password", "key"))}
            rec.safe_metadata = md
            rec.history.append({"event": "quarantined", "reason": safe_reason, "ts": float(self.clock())})
            rec.history = rec.history[-50:]
            self._records[provider_id] = rec
            return rec

    def recover(self, provider_id: str, *, reason: str = "operator_recovery") -> QuarantineRecord:
        """Explicit recovery only — never automatic."""
        with self._lock:
            rec = self._rec(provider_id)
            rec.quarantined = False
            rec.reason = ""
            rec.history.append({"event": "recovered", "reason": reason[:120], "ts": float(self.clock())})
            self._records[provider_id] = rec
            return rec
