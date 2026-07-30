"""M226 — Simulated Credential Lifecycle.

Credential references only. Never stores keys/secrets/tokens.
Invariant: credential_usable_for_real_connection = false
"""
from __future__ import annotations

import hashlib
import json
import time
from typing import Any

from saathi.platform.tg.broker_readiness.models import (
    CREDENTIAL_LIFECYCLE_ORDER,
    CredentialLifecycleState,
    FORBIDDEN_SCOPES,
    TERMINAL_LIFECYCLE,
)
from saathi.platform.tg.broker_readiness.secrets import (
    SecretRejectionError,
    reject_secrets_in_payload,
)
from saathi.platform.tg.broker_readiness.store import ReadinessStore, _uid, evidence_hash


class CredentialLifecycleError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


# Allowed forward transitions (plus some skip paths for drills).
_TRANSITIONS: dict[CredentialLifecycleState, set[CredentialLifecycleState]] = {
    CredentialLifecycleState.PROPOSED: {
        CredentialLifecycleState.CLASSIFIED,
        CredentialLifecycleState.REVOKED,
        CredentialLifecycleState.DESTROYED,
    },
    CredentialLifecycleState.CLASSIFIED: {
        CredentialLifecycleState.SCOPE_REVIEWED,
        CredentialLifecycleState.REVOKED,
        CredentialLifecycleState.DESTROYED,
    },
    CredentialLifecycleState.SCOPE_REVIEWED: {
        CredentialLifecycleState.SECURITY_REVIEWED,
        CredentialLifecycleState.REVOKED,
    },
    CredentialLifecycleState.SECURITY_REVIEWED: {
        CredentialLifecycleState.OWNER_REVIEWED,
        CredentialLifecycleState.REVOKED,
        CredentialLifecycleState.SUSPENDED,
    },
    CredentialLifecycleState.OWNER_REVIEWED: {
        CredentialLifecycleState.APPROVED_FOR_SIMULATION,
        CredentialLifecycleState.REVOKED,
        CredentialLifecycleState.SUSPENDED,
    },
    CredentialLifecycleState.APPROVED_FOR_SIMULATION: {
        CredentialLifecycleState.ACTIVATED_IN_SIMULATION,
        CredentialLifecycleState.REVOKED,
        CredentialLifecycleState.SUSPENDED,
        CredentialLifecycleState.EXPIRED,
    },
    CredentialLifecycleState.ACTIVATED_IN_SIMULATION: {
        CredentialLifecycleState.EXPIRING,
        CredentialLifecycleState.EXPIRED,
        CredentialLifecycleState.ROTATION_REQUIRED,
        CredentialLifecycleState.SUSPENDED,
        CredentialLifecycleState.REVOKED,
    },
    CredentialLifecycleState.EXPIRING: {
        CredentialLifecycleState.EXPIRED,
        CredentialLifecycleState.ROTATION_REQUIRED,
        CredentialLifecycleState.REVOKED,
        CredentialLifecycleState.SUSPENDED,
    },
    CredentialLifecycleState.EXPIRED: {
        CredentialLifecycleState.ROTATION_REQUIRED,
        CredentialLifecycleState.DESTROYED,
        CredentialLifecycleState.ARCHIVED,
        CredentialLifecycleState.REVOKED,
    },
    CredentialLifecycleState.ROTATION_REQUIRED: {
        CredentialLifecycleState.ROTATED_IN_SIMULATION,
        CredentialLifecycleState.REVOKED,
        CredentialLifecycleState.DESTROYED,
    },
    CredentialLifecycleState.ROTATED_IN_SIMULATION: {
        CredentialLifecycleState.ACTIVATED_IN_SIMULATION,
        CredentialLifecycleState.APPROVED_FOR_SIMULATION,
        CredentialLifecycleState.REVOKED,
        CredentialLifecycleState.ARCHIVED,
    },
    CredentialLifecycleState.SUSPENDED: {
        CredentialLifecycleState.REVOKED,
        CredentialLifecycleState.DESTROYED,
        CredentialLifecycleState.ARCHIVED,
        # No automatic restoration to activated
    },
    CredentialLifecycleState.REVOKED: {
        CredentialLifecycleState.DESTROYED,
        CredentialLifecycleState.ARCHIVED,
    },
    CredentialLifecycleState.DESTROYED: {
        CredentialLifecycleState.ARCHIVED,
    },
    CredentialLifecycleState.ARCHIVED: set(),
}


class SimulatedCredentialLifecycle:
    def __init__(self, store: ReadinessStore):
        self.store = store

    def propose(
        self,
        provider_id: str,
        *,
        credential_type: str = "SIMULATED_METADATA",
        declared_scopes: list[str] | None = None,
        environment: str = "SIMULATION",
        expires_at: float | None = None,
        rotation_deadline: float | None = None,
        actor: str = "system",
        metadata: dict | None = None,
    ) -> dict[str, Any]:
        metadata = metadata or {}
        try:
            reject_secrets_in_payload(metadata)
            reject_secrets_in_payload({"scopes": declared_scopes or []})
            reject_secrets_in_payload({"provider_id": provider_id, "type": credential_type})
        except SecretRejectionError as e:
            raise CredentialLifecycleError(e.code, e.message) from e

        scopes = list(declared_scopes or [
            "ACCOUNT_METADATA_READ", "BALANCE_READ", "POSITION_READ", "PORTFOLIO_READ",
        ])
        # Reject write scopes at propose
        for s in scopes:
            su = s.upper().replace(":", "_").replace("-", "_")
            if su in FORBIDDEN_SCOPES:
                raise CredentialLifecycleError(
                    "WRITE_SCOPE_REJECTED",
                    f"Cannot propose credential with write scope {s}. No silent downgrade.",
                )

        now = time.time()
        cid = _uid("cref")
        fp_src = {
            "provider_id": provider_id,
            "scopes": scopes,
            "environment": environment,
            "credential_type": credential_type,
            "ts": now,
        }
        fingerprint = evidence_hash(fp_src)
        self.store.execute(
            """INSERT INTO br_credential_refs(
                id, provider_id, credential_type, lifecycle_state, declared_scopes_json,
                environment, fingerprint, owner_approval_json, security_approval_json,
                activated_at, expires_at, rotation_deadline, revoked_at,
                secret_material_present, credential_usable_for_real_connection,
                audit_refs_json, detail_json, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cid, provider_id, credential_type,
                CredentialLifecycleState.PROPOSED.value,
                json.dumps(scopes), environment, fingerprint,
                json.dumps({}), json.dumps({}),
                None, expires_at or (now + 86400 * 30),
                rotation_deadline or (now + 86400 * 25),
                None,
                0, 0,  # never secrets, never usable for real connection
                json.dumps([]),
                json.dumps({"metadata": metadata, "label": f"sim-ref-{provider_id}"}),
                now, now,
            ),
        )
        self._event(cid, "", CredentialLifecycleState.PROPOSED.value, actor, "proposed")
        self.store.audit("credential.proposed", actor=actor, subject=cid, detail={
            "provider_id": provider_id, "usable_for_real": False,
        })
        return self.get(cid)

    def get(self, credential_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM br_credential_refs WHERE id=?", (credential_id,))
        if not row:
            raise CredentialLifecycleError("CREDENTIAL_NOT_FOUND", credential_id)
        return self._public(row)

    def list(self, provider_id: str = "") -> list[dict[str, Any]]:
        if provider_id:
            rows = self.store.fetchall(
                "SELECT * FROM br_credential_refs WHERE provider_id=? ORDER BY created_at DESC",
                (provider_id,),
            )
        else:
            rows = self.store.fetchall(
                "SELECT * FROM br_credential_refs ORDER BY created_at DESC"
            )
        return [self._public(r) for r in rows]

    def _public(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "reference_id": row["id"],
            "provider_id": row["provider_id"],
            "credential_type": row["credential_type"],
            "lifecycle_state": row["lifecycle_state"],
            "declared_scopes": json.loads(row["declared_scopes_json"] or "[]"),
            "environment": row["environment"],
            "fingerprint": row["fingerprint"],
            "owner_approval": json.loads(row["owner_approval_json"] or "{}"),
            "security_approval": json.loads(row["security_approval_json"] or "{}"),
            "created_at": row["created_at"],
            "activated_at": row["activated_at"],
            "expires_at": row["expires_at"],
            "rotation_deadline": row["rotation_deadline"],
            "revocation_timestamp": row["revoked_at"],
            "secret_material_present": False,
            "credential_usable_for_real_connection": False,
            "audit_refs": json.loads(row["audit_refs_json"] or "[]"),
            "detail": json.loads(row["detail_json"] or "{}"),
            "updated_at": row["updated_at"],
            "simulation_only": True,
            "contains": {
                "key": False, "secret": False, "token": False, "password": False,
                "cookie": False, "recovery_code": False, "private_certificate": False,
                "seed_phrase": False, "raw_authorization_header": False,
            },
        }

    def transition(
        self,
        credential_id: str,
        to_state: str,
        *,
        actor: str = "system",
        reason: str = "",
        owner_approval: dict | None = None,
        security_approval: dict | None = None,
        force: bool = False,
    ) -> dict[str, Any]:
        ref = self.get(credential_id)
        current = CredentialLifecycleState(ref["lifecycle_state"])
        try:
            target = CredentialLifecycleState(to_state)
        except ValueError:
            # accept with hyphen/underscore variants
            target = CredentialLifecycleState(to_state.replace("_", "-"))

        # Never restore revoked/destroyed to activated automatically
        if current in (CredentialLifecycleState.REVOKED, CredentialLifecycleState.DESTROYED):
            if target in (
                CredentialLifecycleState.ACTIVATED_IN_SIMULATION,
                CredentialLifecycleState.APPROVED_FOR_SIMULATION,
            ):
                raise CredentialLifecycleError(
                    "RESTORATION_AFTER_REVOCATION_FORBIDDEN",
                    "Cannot restore revoked/destroyed credentials to active simulation.",
                )

        allowed = _TRANSITIONS.get(current, set())
        if target not in allowed and not force:
            raise CredentialLifecycleError(
                "INVALID_LIFECYCLE_TRANSITION",
                f"Cannot transition {current.value} → {target.value}",
            )

        if owner_approval:
            reject_secrets_in_payload(owner_approval)
        if security_approval:
            reject_secrets_in_payload(security_approval)

        now = time.time()
        activated = ref["activated_at"]
        revoked = ref["revocation_timestamp"]
        if target == CredentialLifecycleState.ACTIVATED_IN_SIMULATION:
            activated = now
        if target == CredentialLifecycleState.REVOKED:
            revoked = now

        oa = owner_approval if owner_approval is not None else ref["owner_approval"]
        sa = security_approval if security_approval is not None else ref["security_approval"]

        self.store.execute(
            """UPDATE br_credential_refs SET lifecycle_state=?, owner_approval_json=?,
               security_approval_json=?, activated_at=?, revoked_at=?,
               secret_material_present=0, credential_usable_for_real_connection=0,
               updated_at=? WHERE id=?""",
            (
                target.value, json.dumps(oa), json.dumps(sa),
                activated, revoked, now, credential_id,
            ),
        )
        self._event(credential_id, current.value, target.value, actor, reason)
        self.store.audit("credential.lifecycle", actor=actor, subject=credential_id, detail={
            "from": current.value, "to": target.value, "reason": reason,
        })
        out = self.get(credential_id)
        assert out["credential_usable_for_real_connection"] is False
        assert out["secret_material_present"] is False
        return out

    def advance_happy_path(self, credential_id: str, *, actor: str = "system") -> dict[str, Any]:
        """Drive proposed → activated-in-simulation through reviews."""
        path = [
            CredentialLifecycleState.CLASSIFIED,
            CredentialLifecycleState.SCOPE_REVIEWED,
            CredentialLifecycleState.SECURITY_REVIEWED,
            CredentialLifecycleState.OWNER_REVIEWED,
            CredentialLifecycleState.APPROVED_FOR_SIMULATION,
            CredentialLifecycleState.ACTIVATED_IN_SIMULATION,
        ]
        ref = self.get(credential_id)
        for state in path:
            if CredentialLifecycleState(ref["lifecycle_state"]) == state:
                continue
            kwargs: dict[str, Any] = {"actor": actor, "reason": f"advance to {state.value}"}
            if state == CredentialLifecycleState.SECURITY_REVIEWED:
                kwargs["security_approval"] = {"decision": "approve", "actor": actor, "sim": True}
            if state == CredentialLifecycleState.OWNER_REVIEWED:
                kwargs["owner_approval"] = {"decision": "approve", "actor": actor, "sim": True, "signoff_claimed": False}
            ref = self.transition(credential_id, state.value, **kwargs)
        return ref

    def _event(self, cid: str, from_state: str, to_state: str, actor: str, reason: str) -> None:
        self.store.execute(
            """INSERT INTO br_lifecycle_events(
                id, credential_id, from_state, to_state, actor, reason, detail_json, created_at
            ) VALUES(?,?,?,?,?,?,?,?)""",
            (_uid("lev"), cid, from_state, to_state, actor, reason, json.dumps({}), time.time()),
        )

    def lifecycle_events(self, credential_id: str = "") -> list[dict[str, Any]]:
        if credential_id:
            rows = self.store.fetchall(
                "SELECT * FROM br_lifecycle_events WHERE credential_id=? ORDER BY created_at",
                (credential_id,),
            )
        else:
            rows = self.store.fetchall(
                "SELECT * FROM br_lifecycle_events ORDER BY created_at DESC LIMIT 100"
            )
        for r in rows:
            r["detail"] = json.loads(r.pop("detail_json") or "{}")
        return rows

    def attempt_use_for_real(self, credential_id: str) -> dict[str, Any]:
        ref = self.get(credential_id)
        self.store.audit("credential.real_use_refused", subject=credential_id, detail={
            "lifecycle": ref["lifecycle_state"],
        })
        return {
            "ok": False,
            "error": "CREDENTIAL_UNUSABLE_FOR_REAL_CONNECTION",
            "credential_usable_for_real_connection": False,
            "message": "Simulated credential references cannot authenticate any real broker.",
            "simulation_only": True,
        }


__all__ = ["SimulatedCredentialLifecycle", "CredentialLifecycleError"]
