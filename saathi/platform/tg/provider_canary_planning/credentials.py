"""M244 — Credential ceremony and revocation runbooks.

Status: CREDENTIAL_CEREMONY_DOCUMENTED_NOT_EXECUTED
Do not create, request, accept, or store raw credentials.
LLM must never receive raw secret values.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.provider_canary_planning.models import (
    CREDENTIAL_CEREMONY_STATUS,
    PREFERRED_PROVIDER,
)
from saathi.platform.tg.provider_canary_planning.store import PlanningStore, _uid, evidence_hash

CEREMONY_STEPS = [
    {"n": 1, "step": "who_may_create", "detail": "Only the human account owner (or designated operator under owner authority) at the provider console."},
    {"n": 2, "step": "where_created", "detail": "Provider's official web console over HTTPS on a trusted device; never via SaathiOS LLM chat."},
    {"n": 3, "step": "confirm_provider_identity", "detail": "Verify TLS cert, official domain (e.g. app.alpaca.markets), and account identity before key creation."},
    {"n": 4, "step": "select_required_scopes", "detail": "Select only proposed read-only scopes: account_read, orders_read, activities_read (or provider-equivalent view-only)."},
    {"n": 5, "step": "reject_write_permissions", "detail": "Explicitly leave trading/order write permissions disabled. Abort if UI forces mixed scopes."},
    {"n": 6, "step": "reject_withdrawal_permissions", "detail": "Ensure withdrawal/transfer permissions are off. Abort if not independently selectable."},
    {"n": 7, "step": "configure_ip_restrictions", "detail": "Bind key to canary egress IP allow-list only."},
    {"n": 8, "step": "configure_expiry", "detail": "Set shortest practical expiry (or calendar rotation if provider lacks expiry)."},
    {"n": 9, "step": "enter_without_llm", "detail": "Use direct terminal secret prompt, OS keychain, or secret-manager operator workflow — never paste into LLM chat."},
    {"n": 10, "step": "reference_only_visible", "detail": "SaathiOS stores only a credential reference ID + metadata (provider, scopes claimed, expiry, IP policy). Raw secret stays in OS secret store."},
    {"n": 11, "step": "test_credential", "detail": "Future controlled probe of allow-listed GET only after separate activation authority (NOT in M240–M247)."},
    {"n": 12, "step": "permission_introspection", "detail": "If provider supports key permission introspection, verify observed scopes match proposal exactly."},
    {"n": 13, "step": "excessive_scope_abort", "detail": "Any write/withdraw/transfer scope → immediate abort and revocation."},
    {"n": 14, "step": "rotation", "detail": "Create new key, enter via non-LLM path, switch ref, revoke old key at provider, verify old key fails."},
    {"n": 15, "step": "suspension", "detail": "Mark local ref SUSPENDED; stop collector; leave provider key intact until revoke decision."},
    {"n": 16, "step": "revocation", "detail": "Owner deletes/disables key at provider console; mark local ref REVOKED."},
    {"n": 17, "step": "external_verification", "detail": "Confirm provider UI shows key deleted/disabled; optional fail probe returns auth error."},
    {"n": 18, "step": "remove_local_references", "detail": "Delete secret from OS keychain/secret manager; retain only audit metadata and hashes."},
    {"n": 19, "step": "preserve_incident_evidence", "detail": "Keep immutable audit of ceremony, rotation, revoke events."},
    {"n": 20, "step": "destruction_attestation", "detail": "Operator signs destruction checklist (human, not automation)."},
]

ACCEPTABLE_SECRET_ENTRY = [
    "direct_terminal_secret_prompt",
    "os_keychain_entry",
    "secret_manager_operator_workflow",
    "masked_provider_specific_setup_utility",
]

ROTATION_RUNBOOK = {
    "trigger": ["scheduled_expiry", "suspected_exposure", "scope_change", "personnel_change"],
    "steps": [
        "Create new key with identical minimal scopes and IP allow-list",
        "Enter new secret via non-LLM path",
        "Register new reference metadata",
        "Disable use of old reference",
        "Revoke old key at provider",
        "Verify old key authentication fails",
        "Audit both keys' lifecycle events",
    ],
    "executed": False,
}

REVOCATION_RUNBOOK = {
    "triggers": ["owner_request", "security_abort", "compromise", "canary_end", "eligibility_concern"],
    "steps": [
        "Stop canary collector (if ever running)",
        "Mark local ref REVOKED",
        "Owner deletes key in provider console",
        "Verify provider UI state",
        "Remove secret from local secret store",
        "Retain audit evidence",
        "Complete destruction checklist",
    ],
    "executed": False,
}

COMPROMISE_RUNBOOK = {
    "steps": [
        "Assume key is hostile",
        "Immediate kill switch",
        "Revoke at provider",
        "Rotate any related secrets",
        "Scan logs for secret leakage",
        "Preserve forensic evidence",
        "Owner and security notification",
        "No automated re-entry after security abort",
    ],
    "executed": False,
}

DESTRUCTION_CHECKLIST = [
    "Provider key disabled or deleted",
    "Local secret material removed from keychain/secret manager",
    "Local credential reference marked DESTROYED",
    "No secret present in logs, evidence, or chat transcripts",
    "Audit events retained",
    "Operator attestation recorded by human",
]

OPERATOR_ACK_TEMPLATE = """
OPERATOR ACKNOWLEDGEMENT — CREDENTIAL CEREMONY (PLANNING TEMPLATE ONLY)
I understand that:
1. No credential is created or accepted during M240–M247.
2. Raw secrets must never be pasted into an LLM.
3. Only reference metadata may enter SaathiOS.
4. Write, withdrawal, and transfer permissions are forbidden.
5. Revocation and destruction require human attestation.
Operator name: _______________
Date: _______________
Signature: _______________
"""


class CredentialCeremony:
    def __init__(self, store: PlanningStore):
        self.store = store

    def ensure_seeded(self) -> None:
        row = self.store.fetchone("SELECT COUNT(*) AS c FROM pcp_credential_runbooks")
        if row and int(row["c"]) > 0:
            return
        payload = {
            "status": CREDENTIAL_CEREMONY_STATUS,
            "steps": CEREMONY_STEPS,
            "acceptable_secret_entry": ACCEPTABLE_SECRET_ENTRY,
            "rotation": ROTATION_RUNBOOK,
            "revocation": REVOCATION_RUNBOOK,
            "compromise": COMPROMISE_RUNBOOK,
            "destruction_checklist": DESTRUCTION_CHECKLIST,
            "operator_acknowledgement_template": OPERATOR_ACK_TEMPLATE.strip(),
            "llm_must_never_receive_raw_value": True,
            "executed": False,
        }
        self.store.execute(
            """INSERT INTO pcp_credential_runbooks(
                id, provider, status, ceremony_json, rotation_json, revocation_json,
                compromise_json, destruction_json, acknowledgement_template, evidence_hash, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?)""",
            (
                _uid("cred"), PREFERRED_PROVIDER, CREDENTIAL_CEREMONY_STATUS,
                json.dumps(payload),
                json.dumps(ROTATION_RUNBOOK),
                json.dumps(REVOCATION_RUNBOOK),
                json.dumps(COMPROMISE_RUNBOOK),
                json.dumps(DESTRUCTION_CHECKLIST),
                OPERATOR_ACK_TEMPLATE.strip(),
                evidence_hash(payload),
                time.time(),
            ),
        )
        self.store.audit("credential_ceremony.documented", subject=PREFERRED_PROVIDER)

    def runbook(self) -> dict[str, Any]:
        self.ensure_seeded()
        row = self.store.fetchone("SELECT * FROM pcp_credential_runbooks ORDER BY created_at DESC LIMIT 1")
        assert row is not None
        ceremony = json.loads(row["ceremony_json"] or "{}")
        return {
            "provider": row["provider"],
            "status": row["status"],
            "executed": False,
            "ceremony": ceremony,
            "rotation": json.loads(row["rotation_json"] or "{}"),
            "revocation": json.loads(row["revocation_json"] or "{}"),
            "compromise": json.loads(row["compromise_json"] or "{}"),
            "destruction_checklist": json.loads(row["destruction_json"] or "[]"),
            "operator_acknowledgement_template": row["acknowledgement_template"],
            "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
            "evidence_hash": row["evidence_hash"],
        }

    def refuse_raw_secret(self, value: str | None = None) -> dict[str, Any]:
        self.store.audit("credential.raw_secret_rejected", detail={"had_value": bool(value)})
        return {
            "ok": False,
            "code": "RAW_CREDENTIAL_REJECTED",
            "message": "Raw API credentials are rejected. Ceremony is documented but not executed.",
            "CREDENTIAL_PROVISIONING_AUTHORIZED": False,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def refuse_oauth(self) -> dict[str, Any]:
        self.store.audit("credential.oauth_rejected")
        return {
            "ok": False,
            "code": "OAUTH_INITIATION_FORBIDDEN",
            "message": "OAuth initiation is forbidden in M240–M247.",
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
