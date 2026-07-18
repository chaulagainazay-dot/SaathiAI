"""M32 — Idempotency: bind provider execution to a canonical request fingerprint.

Secret material is never part of a fingerprint or record. Reuse is scoped to the
same provider + connector + account + operation + material request. A changed
material request, a different provider/connector/account, or an expired record
all fail closed. Duplicate provider responses never duplicate logical state.
"""
from __future__ import annotations

import hashlib
import json
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Optional

# Keys never allowed to influence a fingerprint (secret / volatile material)
_EXCLUDED_FINGERPRINT_KEYS = frozenset({
    "authorization", "token", "access_token", "refresh_token", "api_key",
    "secret", "password", "cookie", "bearer", "credential", "nonce", "timestamp",
    "request_id", "correlation_id",
})


def _clean_for_fingerprint(obj: Any, depth: int = 0) -> Any:
    if depth > 8:
        return "***"
    if isinstance(obj, dict):
        return {
            str(k): _clean_for_fingerprint(v, depth + 1)
            for k, v in sorted(obj.items(), key=lambda kv: str(kv[0]))
            if str(k).lower() not in _EXCLUDED_FINGERPRINT_KEYS
        }
    if isinstance(obj, list):
        return [_clean_for_fingerprint(x, depth + 1) for x in obj]
    return obj


def compute_request_fingerprint(
    *,
    connector_id: str,
    provider_id: str,
    operation: str,
    normalized_payload: dict[str, Any],
    account_link_id: str = "",
) -> str:
    """Deterministic SHA-256 over the material request (no secrets, no timestamps)."""
    material = {
        "schema": "m32.request_fingerprint.v1",
        "connector_id": connector_id,
        "provider_id": provider_id,
        "operation": operation,
        "account_link_id": account_link_id,
        "payload": _clean_for_fingerprint(normalized_payload or {}),
    }
    blob = json.dumps(material, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


@dataclass
class IdempotencyRecord:
    idempotency_key: str
    connector_id: str
    provider_id: str
    operation: str
    request_fingerprint: str
    approval_fingerprint: str = ""
    account_link_id: str = ""
    credential_ref_id: str = ""
    created_at: float = 0.0
    expires_at: float = 0.0
    status: str = "in_progress"   # in_progress|completed|failed
    provider_request_id_safe: str = ""
    result_reference: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # defense-in-depth: never emit secret-shaped keys even if mis-set
        for bad in ("credential_ref_id",):
            if d.get(bad):
                d[bad] = "ref"  # keep only a boolean-ish marker
        return d


class IdempotencyConflict(Exception):
    pass


class IdempotencyStore:
    """In-process idempotency ledger. Scoped composite key prevents cross reuse."""

    def __init__(self, *, clock: Optional[Any] = None, ttl_seconds: float = 300.0):
        import time as _t
        self.clock = clock or _t.time
        self.ttl_seconds = float(ttl_seconds)
        self._lock = threading.RLock()
        self._records: dict[str, IdempotencyRecord] = {}

    @staticmethod
    def _composite(connector_id: str, provider_id: str, account_link_id: str, key: str) -> str:
        return f"{connector_id}|{provider_id}|{account_link_id}|{key}"

    def reserve(
        self,
        *,
        idempotency_key: str,
        connector_id: str,
        provider_id: str,
        operation: str,
        request_fingerprint: str,
        account_link_id: str = "",
        approval_fingerprint: str = "",
    ) -> tuple[str, IdempotencyRecord]:
        """Return (state, record) where state ∈ {new, replay, conflict}.

        - new: no live record for this scoped key.
        - replay: same scoped key AND same fingerprint (safe to reuse result).
        - conflict: same scoped key but a different material fingerprint.
        Expired records are treated as new (fail safe → fresh operation).
        """
        with self._lock:
            now = float(self.clock())
            ck = self._composite(connector_id, provider_id, account_link_id, idempotency_key)
            rec = self._records.get(ck)
            if rec is not None and rec.expires_at and rec.expires_at <= now:
                # expired → drop, behave as new
                self._records.pop(ck, None)
                rec = None
            if rec is None:
                new_rec = IdempotencyRecord(
                    idempotency_key=idempotency_key,
                    connector_id=connector_id,
                    provider_id=provider_id,
                    operation=operation,
                    request_fingerprint=request_fingerprint,
                    approval_fingerprint=approval_fingerprint,
                    account_link_id=account_link_id,
                    created_at=now,
                    expires_at=now + self.ttl_seconds,
                    status="in_progress",
                )
                self._records[ck] = new_rec
                return ("new", new_rec)
            if rec.request_fingerprint != request_fingerprint:
                return ("conflict", rec)
            return ("replay", rec)

    def complete(
        self,
        *,
        idempotency_key: str,
        connector_id: str,
        provider_id: str,
        account_link_id: str = "",
        status: str = "completed",
        provider_request_id_safe: str = "",
        result_reference: str = "",
    ) -> IdempotencyRecord:
        with self._lock:
            ck = self._composite(connector_id, provider_id, account_link_id, idempotency_key)
            rec = self._records.get(ck)
            if rec is None:
                raise KeyError("idempotency_record_missing")
            rec.status = status
            rec.provider_request_id_safe = provider_request_id_safe
            rec.result_reference = result_reference
            self._records[ck] = rec
            return rec

    def get(
        self, *, idempotency_key: str, connector_id: str, provider_id: str, account_link_id: str = "",
    ) -> Optional[IdempotencyRecord]:
        with self._lock:
            return self._records.get(
                self._composite(connector_id, provider_id, account_link_id, idempotency_key)
            )
