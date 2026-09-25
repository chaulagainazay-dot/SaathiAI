"""M316 Credential Governance Policy — no real credentials."""
from __future__ import annotations

import re
import time
from typing import Any

from saathi.platform.tg.connectivity_governance.errors import CredentialPolicyViolation, SecretFieldDetected
from saathi.platform.tg.connectivity_governance.models import (
    ALLOWED_SYNTHETIC_REF,
    AUTHORITY_VALUES,
    FORBIDDEN_SECRET_FIELDS,
    MAX_CREDENTIAL_STATE,
    SYNTHETIC_REF_PREFIX,
    CredentialState,
)

PERMITTED_REFERENCE_BACKENDS = (
    "os_keychain_reference",
    "hardware_backed_secret_reference",
    "environment_secret_reference",
    "managed_secret_store_reference",
    "short_lived_token_reference",
    "disposable_canary_credential_reference",
)

RAW_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|api[_-]?secret|secret[_-]?key)\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{8,}"),
    re.compile(r"(?i)(password|passphrase)\s*[:=]\s*\S+"),
    re.compile(r"(?i)(bearer)\s+[A-Za-z0-9_\-\.]{10,}"),
    re.compile(r"(?i)(-----BEGIN (RSA |EC |OPENSSH )?PRIVATE KEY-----)"),
    re.compile(r"(?i)(sk_live_|sk_test_|AKIA[0-9A-Z]{16})"),
]


def is_forbidden_field(name: str) -> bool:
    n = name.lower().strip()
    return n in FORBIDDEN_SECRET_FIELDS or any(f in n for f in ("password", "secret", "private_key", "api_key"))


def scan_payload_for_secrets(payload: dict[str, Any] | None) -> dict[str, Any]:
    findings = []
    if not payload:
        return {"ok": True, "findings": [], "raw_credentials_forbidden": True}

    def walk(obj, path=""):
        if isinstance(obj, dict):
            for k, v in obj.items():
                p = f"{path}.{k}" if path else k
                if is_forbidden_field(str(k)):
                    findings.append({"path": p, "kind": "forbidden_field", "field": k})
                walk(v, p)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                walk(v, f"{path}[{i}]")
        elif isinstance(obj, str):
            for pat in RAW_SECRET_PATTERNS:
                if pat.search(obj):
                    findings.append({"path": path, "kind": "raw_secret_pattern"})
                    break
            # reject non-synthetic secret-looking long tokens in credential contexts
            if "secret" in path.lower() or "token" in path.lower() or "key" in path.lower():
                if obj and not obj.startswith(SYNTHETIC_REF_PREFIX) and len(obj) > 12:
                    if not obj.startswith("secret-ref://"):
                        findings.append({"path": path, "kind": "non_synthetic_secret_like"})

    walk(payload)
    return {
        "ok": len(findings) == 0,
        "findings": findings,
        "raw_credentials_forbidden": True,
    }


def validate_synthetic_reference(ref: str) -> dict[str, Any]:
    if not ref:
        raise CredentialPolicyViolation("EMPTY_REFERENCE", "Reference required")
    if not ref.startswith(SYNTHETIC_REF_PREFIX):
        raise CredentialPolicyViolation(
            "REAL_REFERENCE_FORBIDDEN",
            "Only synthetic references allowed in M312-M319",
            ref_prefix_required=SYNTHETIC_REF_PREFIX,
        )
    # Label after prefix must not look like a raw key paste
    label = ref[len(SYNTHETIC_REF_PREFIX):]
    if not label or len(label) > 128:
        raise CredentialPolicyViolation("INVALID_SYNTHETIC_LABEL", "Synthetic reference label invalid")
    if any(c in label for c in (" ", "=", "\n", "\t")):
        raise CredentialPolicyViolation("INVALID_SYNTHETIC_LABEL", "Synthetic reference must be a simple label")
    # Reject if raw secret patterns appear (e.g. embedded key material)
    for pat in RAW_SECRET_PATTERNS:
        if pat.search(ref):
            raise CredentialPolicyViolation("RAW_SECRET_IN_REFERENCE", "Raw secret pattern in reference")
    return {
        "ok": True,
        "reference": ref,
        "state": CredentialState.REFERENCE_DECLARED.value,
        "max_state": MAX_CREDENTIAL_STATE,
        "active": False,
        "validated": False,
        **AUTHORITY_VALUES,
    }


class CredentialGovernance:
    def __init__(self):
        self._refs: dict[str, dict[str, Any]] = {}

    def policy(self) -> dict[str, Any]:
        return {
            "ok": True,
            "schema": "M316_CREDENTIAL_GOVERNANCE_POLICY",
            "raw_credentials_forbidden": True,
            "permitted_reference_backends": list(PERMITTED_REFERENCE_BACKENDS),
            "secret_reference_format": f"{SYNTHETIC_REF_PREFIX}<label>",
            "allowed_synthetic_example": ALLOWED_SYNTHETIC_REF,
            "forbidden_storage": [
                "raw_api_keys", "raw_secrets", "passwords", "oauth_refresh_tokens",
                "private_keys", "recovery_codes", "session_cookies", "bearer_tokens",
            ],
            "forbidden_fields": sorted(FORBIDDEN_SECRET_FIELDS),
            "states": [s.value for s in CredentialState],
            "max_state_this_milestone": MAX_CREDENTIAL_STATE,
            "lifecycle": {
                "creation": "synthetic_reference_declaration_only",
                "validation": "forbidden",
                "use": "forbidden",
                "expiry": "required_when_created_in_future",
                "rotation": "future_only",
                "revocation": "supported_as_policy",
                "destruction": "supported_as_policy",
            },
            "ownership": "human_operator",
            "environment_binding": True,
            "provider_binding": True,
            "account_binding": True,
            "capability_binding": True,
            "evidence_rules": {"no_raw_secrets_in_evidence": True},
            "leak_handling": "incident_and_revoke",
            "scanners": [
                "raw_secret_pattern_scan",
                "credential_like_field_scan",
                "evidence_leak_scan",
                "logs_leak_scan",
                "database_schema_scan",
                "frontend_field_scan",
                "api_input_scan",
                "cli_argument_scan",
            ],
            **AUTHORITY_VALUES,
        }

    def declare_synthetic_reference(
        self,
        *,
        reference: str,
        owner: str,
        provider: str,
        environment: str = "governance",
        account_ref: str = "none",
        capability_binding: list[str] | None = None,
    ) -> dict[str, Any]:
        if owner.lower() in ("llm", "ai", "agent", "model"):
            raise CredentialPolicyViolation("HUMAN_OWNER_REQUIRED", "Human owner required")
        validate_synthetic_reference(reference)
        # Cap at REFERENCE_DECLARED
        rid = f"cref_{int(time.time() * 1000)}"
        rec = {
            "reference_id": rid,
            "reference": reference,
            "state": CredentialState.REFERENCE_DECLARED.value,
            "owner": owner,
            "provider": provider,
            "environment": environment,
            "account_ref": account_ref,
            "capability_binding": list(capability_binding or []),
            "active": False,
            "validated": False,
            "created_at": time.time(),
        }
        self._refs[rid] = rec
        return {"ok": True, "credential_reference": rec, "max_state": MAX_CREDENTIAL_STATE, **AUTHORITY_VALUES}

    def reject_raw_credential(self, field: str, value: str | None = None) -> dict[str, Any]:
        return {
            "ok": False,
            "refused": True,
            "code": "RAW_CREDENTIAL_FORBIDDEN",
            "field": field,
            "value_received": bool(value),
            "stored": False,
            "validated": False,
            "message": "Raw credentials are forbidden",
            **AUTHORITY_VALUES,
        }

    def scan_input(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        result = scan_payload_for_secrets(payload)
        if not result["ok"]:
            raise SecretFieldDetected("SECRET_FIELD_DETECTED", "Secret-like field or raw secret detected", findings=result["findings"])
        return result

    def list_references(self) -> dict[str, Any]:
        return {
            "ok": True,
            "count": len(self._refs),
            "references": list(self._refs.values()),
            "any_active": False,
            "any_validated": False,
            **AUTHORITY_VALUES,
        }
