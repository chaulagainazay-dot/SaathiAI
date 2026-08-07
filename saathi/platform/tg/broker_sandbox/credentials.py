"""M218 — Credential Trust Framework.

Design: credential *references* and metadata only.
Never stores real credentials. Never accepts usable secrets.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.broker_sandbox.models import (
    CredentialRefStatus,
    PROHIBITED_SECRET_KEYS,
)
from saathi.platform.tg.broker_sandbox.store import SandboxStore, _uid


class CredentialTrustError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class CredentialTrustFramework:
    """Metadata-only credential architecture. Secrets are never stored or usable."""

    def __init__(self, store: SandboxStore):
        self.store = store

    def _reject_secrets(self, payload: dict[str, Any] | None) -> None:
        if not payload:
            return
        lowered = {str(k).lower().replace("-", "_"): v for k, v in payload.items()}
        for key in PROHIBITED_SECRET_KEYS:
            if key in lowered and lowered[key] not in (None, "", False, 0, "REDACTED", "PLACEHOLDER"):
                # Any non-empty secret-like value is rejected
                if isinstance(lowered[key], str) and lowered[key].upper() in (
                    "REDACTED", "PLACEHOLDER", "NONE", "N/A", "UNUSABLE",
                ):
                    continue
                raise CredentialTrustError(
                    "SECRET_MATERIAL_REJECTED",
                    f"Refusing to store secret-like field '{key}'. "
                    "Credential framework accepts metadata only.",
                )
        # Nested dicts
        for v in payload.values():
            if isinstance(v, dict):
                self._reject_secrets(v)

    def create_reference(
        self,
        broker_id: str,
        *,
        label: str = "",
        provider_metadata: dict | None = None,
        permission_scopes: list[str] | None = None,
        rotation_metadata: dict | None = None,
        expires_at: float | None = None,
        actor: str = "system",
        extra: dict | None = None,
    ) -> dict[str, Any]:
        # Fail closed on any secret material in metadata or extra
        self._reject_secrets(provider_metadata)
        self._reject_secrets(rotation_metadata)
        self._reject_secrets(extra)

        # Explicit reject if caller tried to pass secret fields at top level
        if extra:
            for k in extra:
                if k.lower().replace("-", "_") in PROHIBITED_SECRET_KEYS:
                    raise CredentialTrustError(
                        "SECRET_MATERIAL_REJECTED",
                        f"Field '{k}' is prohibited. No real credentials accepted.",
                    )

        cid = _uid("cref")
        now = time.time()
        audit = [{
            "at": now,
            "event": "created",
            "actor": actor,
            "note": "metadata-only reference; secret_material_present=0; usable=0",
        }]
        self.store.execute(
            """INSERT INTO bs_credential_refs(
                id, broker_id, provider_metadata_json, permission_scopes_json,
                rotation_metadata_json, expires_at, revoked_at, status,
                secret_material_present, usable, approval_chain_json, audit_trail_json,
                label, created_at, updated_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (
                cid,
                broker_id,
                json.dumps(provider_metadata or {"provider": broker_id, "env": "SANDBOX"}),
                json.dumps(permission_scopes or ["read:metadata", "sandbox:simulate"]),
                json.dumps(rotation_metadata or {"rotation_policy": "N/A_NO_SECRETS", "last_rotated": None}),
                expires_at,
                None,
                CredentialRefStatus.PLACEHOLDER.value,
                0,  # never present
                0,  # never usable
                json.dumps([]),
                json.dumps(audit),
                label or f"ref-{broker_id}",
                now,
                now,
            ),
        )
        self.store.audit(
            "credential.ref_created",
            actor=actor,
            subject=cid,
            detail={"broker_id": broker_id, "usable": False, "secret_material_present": False},
        )
        return self.get_reference(cid)

    def get_reference(self, ref_id: str) -> dict[str, Any]:
        row = self.store.fetchone("SELECT * FROM bs_credential_refs WHERE id=?", (ref_id,))
        if not row:
            raise CredentialTrustError("CREDENTIAL_REF_NOT_FOUND", f"No reference {ref_id}")
        return self._public(row)

    def list_references(self, broker_id: str = "") -> list[dict[str, Any]]:
        if broker_id:
            rows = self.store.fetchall(
                "SELECT * FROM bs_credential_refs WHERE broker_id=? ORDER BY created_at DESC",
                (broker_id,),
            )
        else:
            rows = self.store.fetchall(
                "SELECT * FROM bs_credential_refs ORDER BY created_at DESC"
            )
        return [self._public(r) for r in rows]

    def _public(self, row: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": row["id"],
            "broker_id": row["broker_id"],
            "label": row["label"],
            "provider_metadata": json.loads(row["provider_metadata_json"] or "{}"),
            "permission_scopes": json.loads(row["permission_scopes_json"] or "[]"),
            "rotation_metadata": json.loads(row["rotation_metadata_json"] or "{}"),
            "expires_at": row["expires_at"],
            "revoked_at": row["revoked_at"],
            "status": row["status"],
            "secret_material_present": False,  # hard lock
            "usable": False,  # hard lock — no secret is usable
            "approval_chain": json.loads(row["approval_chain_json"] or "[]"),
            "audit_trail": json.loads(row["audit_trail_json"] or "[]"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
            "paper_only": True,
            "note": "Metadata only. No secret material. Cannot authenticate any broker.",
        }

    def revoke(self, ref_id: str, *, actor: str, reason: str = "") -> dict[str, Any]:
        ref = self.get_reference(ref_id)
        now = time.time()
        trail = ref["audit_trail"] + [{
            "at": now, "event": "revoked", "actor": actor, "reason": reason,
        }]
        self.store.execute(
            """UPDATE bs_credential_refs SET status=?, revoked_at=?, usable=0,
               secret_material_present=0, audit_trail_json=?, updated_at=? WHERE id=?""",
            (CredentialRefStatus.REVOKED.value, now, json.dumps(trail), now, ref_id),
        )
        self.store.audit("credential.revoked", actor=actor, subject=ref_id, detail={"reason": reason})
        return self.get_reference(ref_id)

    def mark_expired(self, ref_id: str, *, actor: str = "system") -> dict[str, Any]:
        ref = self.get_reference(ref_id)
        now = time.time()
        trail = ref["audit_trail"] + [{"at": now, "event": "expired", "actor": actor}]
        self.store.execute(
            """UPDATE bs_credential_refs SET status=?, usable=0, audit_trail_json=?, updated_at=?
               WHERE id=?""",
            (CredentialRefStatus.EXPIRED.value, json.dumps(trail), now, ref_id),
        )
        return self.get_reference(ref_id)

    def append_approval(
        self, ref_id: str, *, stage: str, actor: str, decision: str, reason: str = ""
    ) -> dict[str, Any]:
        """Record approval metadata only. Does not make credentials usable."""
        ref = self.get_reference(ref_id)
        now = time.time()
        chain = ref["approval_chain"] + [{
            "stage": stage, "actor": actor, "decision": decision,
            "reason": reason, "at": now,
        }]
        trail = ref["audit_trail"] + [{
            "at": now, "event": "approval_recorded", "stage": stage,
            "decision": decision, "actor": actor,
        }]
        status = ref["status"]
        if decision.lower() == "approve":
            status = CredentialRefStatus.APPROVED_METADATA.value
        elif decision.lower() == "reject":
            status = CredentialRefStatus.REVOKED.value
        self.store.execute(
            """UPDATE bs_credential_refs SET approval_chain_json=?, audit_trail_json=?,
               status=?, usable=0, secret_material_present=0, updated_at=? WHERE id=?""",
            (json.dumps(chain), json.dumps(trail), status, now, ref_id),
        )
        # Even after approval, usable remains False
        out = self.get_reference(ref_id)
        assert out["usable"] is False
        assert out["secret_material_present"] is False
        return out

    def attempt_use(self, ref_id: str) -> dict[str, Any]:
        """Any attempt to use a credential reference fails closed."""
        ref = self.get_reference(ref_id)
        self.store.audit(
            "credential.use_refused",
            subject=ref_id,
            detail={"reason": "CREDENTIALS_UNUSABLE", "status": ref["status"]},
        )
        return {
            "ok": False,
            "error": "CREDENTIAL_UNUSABLE",
            "ref_id": ref_id,
            "usable": False,
            "secret_material_present": False,
            "message": "Credential references are metadata only and cannot authenticate anything.",
            "paper_only": True,
        }

    def framework_summary(self) -> dict[str, Any]:
        refs = self.list_references()
        return {
            "milestone": "M218",
            "stores_real_credentials": False,
            "accepts_api_keys": False,
            "secrets_usable": False,
            "references_count": len(refs),
            "all_unusable": all(not r["usable"] for r in refs),
            "all_no_secret_material": all(not r["secret_material_present"] for r in refs),
            "supports": [
                "credential references",
                "provider metadata",
                "permission scopes",
                "rotation metadata",
                "expiry",
                "revocation",
                "audit trail",
                "approval chain",
            ],
            "never": [
                "real credentials",
                "real API keys",
                "usable secrets",
                "OAuth tokens",
            ],
            "paper_only": True,
        }


__all__ = ["CredentialTrustFramework", "CredentialTrustError"]
