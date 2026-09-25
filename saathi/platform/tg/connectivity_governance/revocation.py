"""M317 Revocation framework."""
from __future__ import annotations

import time
import uuid
from typing import Any

from saathi.platform.tg.connectivity_governance.models import AUTHORITY_VALUES

REVOCATION_SCOPES = (
    "provider", "environment", "account", "credential_reference",
    "capability", "approval", "session", "canary", "transport", "execution_authority",
)

REVOCATION_REASONS = (
    "operator_request",
    "approval_expiry",
    "policy_violation",
    "provider_incident",
    "credential_exposure",
    "anomalous_activity",
    "authority_mismatch",
    "account_mismatch",
    "jurisdiction_conflict",
    "audit_failure",
    "evidence_failure",
    "emergency_shutdown",
)


class RevocationService:
    def __init__(self):
        self._records: list[dict[str, Any]] = []

    def revoke(
        self,
        *,
        scope: str,
        target_id: str,
        reason: str,
        actor: str,
        emergency: bool = False,
        detail: str = "",
    ) -> dict[str, Any]:
        if scope not in REVOCATION_SCOPES:
            return {"ok": False, "error": "INVALID_SCOPE", "scope": scope}
        if reason not in REVOCATION_REASONS:
            return {"ok": False, "error": "INVALID_REASON", "reason": reason}
        if not actor:
            return {"ok": False, "error": "ACTOR_REQUIRED"}
        rec = {
            "revocation_id": f"rev_{uuid.uuid4().hex[:12]}",
            "scope": scope,
            "target_id": target_id,
            "reason": reason,
            "actor": actor,
            "emergency": emergency,
            "detail": detail,
            "created_at": time.time(),
            "effective": True,
            "reconnect_allowed": False,
        }
        self._records.append(rec)
        return {"ok": True, "revocation": rec, "reconnect_allowed": False, **AUTHORITY_VALUES}

    def list_revocations(self) -> dict[str, Any]:
        return {
            "ok": True,
            "count": len(self._records),
            "revocations": list(self._records),
            **AUTHORITY_VALUES,
        }
