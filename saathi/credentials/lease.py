"""M31 — Secret access leases (temporary, bound, single-use by default)."""
from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from typing import Any, Callable, Optional

from saathi.credentials.models import LeaseStatus, SecretLease

DEFAULT_LEASE_TTL_SEC = 30.0
MAX_LEASE_TTL_SEC = 120.0


def request_fingerprint(
    *,
    connector_id: str,
    operation: str,
    request_id: str,
    payload: Optional[dict] = None,
    resource_target: str = "",
) -> str:
    body = json.dumps(
        {
            "c": connector_id,
            "o": operation,
            "r": request_id,
            "t": resource_target,
            "p": payload or {},
        },
        sort_keys=True,
        default=str,
        separators=(",", ":"),
    )
    return hashlib.sha256(body.encode()).hexdigest()


class LeaseStore:
    def __init__(self, *, clock: Optional[Callable[[], float]] = None) -> None:
        self.clock = clock or time.time
        self._leases: dict[str, SecretLease] = {}
        self._lock = threading.RLock()

    def issue(
        self,
        *,
        credential_ref_id: str,
        request_id: str,
        connector_id: str,
        operation: str,
        actor: str,
        purpose: str = "execution_injection",
        ttl_seconds: float = DEFAULT_LEASE_TTL_SEC,
        single_use: bool = True,
        request_fingerprint: str = "",
        allowed_fields: tuple[str, ...] = (),
    ) -> SecretLease:
        # Caller cannot select unrestricted duration
        ttl = min(max(1.0, float(ttl_seconds)), MAX_LEASE_TTL_SEC)
        now = float(self.clock())
        lease = SecretLease(
            lease_id="lease_" + uuid.uuid4().hex[:16],
            credential_ref_id=credential_ref_id,
            request_id=request_id,
            connector_id=connector_id,
            operation=operation,
            actor=actor,
            purpose=purpose,
            issued_at=now,
            expires_at=now + ttl,
            single_use=single_use,
            status=LeaseStatus.ISSUED.value,
            request_fingerprint=request_fingerprint,
            allowed_fields=tuple(allowed_fields),
        )
        with self._lock:
            self._leases[lease.lease_id] = lease
        return lease

    def get(self, lease_id: str) -> Optional[SecretLease]:
        with self._lock:
            return self._leases.get(lease_id)

    def list_safe(self) -> list[dict[str, Any]]:
        with self._lock:
            return [l.to_safe_dict() for l in self._leases.values()]

    def validate_and_consume(
        self,
        lease_id: str,
        *,
        credential_ref_id: str,
        request_id: str,
        connector_id: str,
        operation: str,
        request_fingerprint: str = "",
    ) -> SecretLease:
        with self._lock:
            lease = self._leases.get(lease_id)
            if lease is None:
                raise LeaseError("lease_not_found")
            now = float(self.clock())
            if lease.status == LeaseStatus.REVOKED.value:
                raise LeaseError("lease_revoked")
            if lease.status == LeaseStatus.CONSUMED.value:
                raise LeaseError("lease_replay")
            if lease.status == LeaseStatus.EXPIRED.value or now > lease.expires_at:
                lease.status = LeaseStatus.EXPIRED.value
                raise LeaseError("lease_expired")
            if lease.credential_ref_id != credential_ref_id:
                raise LeaseError("lease_credential_mismatch")
            if lease.request_id != request_id:
                raise LeaseError("lease_request_mismatch")
            if lease.connector_id != connector_id:
                raise LeaseError("lease_connector_mismatch")
            if lease.operation != operation:
                raise LeaseError("lease_operation_mismatch")
            if lease.request_fingerprint and request_fingerprint:
                if lease.request_fingerprint != request_fingerprint:
                    raise LeaseError("lease_request_mutated")
            if lease.single_use:
                lease.status = LeaseStatus.CONSUMED.value
            return lease

    def revoke(self, lease_id: str) -> None:
        with self._lock:
            lease = self._leases.get(lease_id)
            if lease:
                lease.status = LeaseStatus.REVOKED.value

    def revoke_for_credential(self, credential_ref_id: str) -> int:
        n = 0
        with self._lock:
            for lease in self._leases.values():
                if lease.credential_ref_id == credential_ref_id and lease.status == LeaseStatus.ISSUED.value:
                    lease.status = LeaseStatus.REVOKED.value
                    n += 1
        return n


class LeaseError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code
