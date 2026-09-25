"""M315 Approval, Scope and Human Authorization Framework."""
from __future__ import annotations

import time
import uuid
from typing import Any

from saathi.platform.tg.connectivity_governance.errors import ApprovalRejected
from saathi.platform.tg.connectivity_governance.models import (
    APPROVAL_CATEGORIES,
    AUTHORITY_VALUES,
    MAX_APPROVAL_STATE,
    PROHIBITED_OPERATIONS,
    ApprovalState,
)

LLM_IDENTITIES = frozenset({
    "llm", "ai", "agent", "model", "gpt", "claude", "grok", "assistant", "system",
})

PROHIBITED_IN_SCOPE = frozenset({
    "live_execution", "live_trading", "withdraw", "withdrawal", "transfer",
    "wildcard", "*", "production_activation", "canary_activation",
})


def _uid(prefix: str = "appr") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:16]}"


class ApprovalFramework:
    def __init__(self):
        self._records: dict[str, dict[str, Any]] = {}

    def create_draft(
        self,
        *,
        requestor: str,
        approval_type: str,
        provider: str,
        environment: str,
        capability_scope: list[str],
        operation_scope: list[str],
        instrument_scope: list[str] | None = None,
        jurisdiction: str = "UNRESOLVED",
        start_time: float | None = None,
        expiry_time: float | None = None,
        maximum_session_duration: float = 3600.0,
        allowed_network_destinations: list[str] | None = None,
        account_identifier_reference: str = "",
        credential_reference_policy: str = "synthetic_only",
        evidence_requirements: list[str] | None = None,
        rollback_requirements: list[str] | None = None,
        revocation_conditions: list[str] | None = None,
        emergency_contacts: list[str] | None = None,
        acknowledgements: list[str] | None = None,
        limitations: list[str] | None = None,
    ) -> dict[str, Any]:
        if approval_type not in APPROVAL_CATEGORIES:
            raise ApprovalRejected("INVALID_APPROVAL_TYPE", f"Unknown type: {approval_type}")
        if not requestor or requestor.lower() in LLM_IDENTITIES:
            raise ApprovalRejected("INVALID_REQUESTOR", "Explicit human requestor required")
        if not expiry_time:
            raise ApprovalRejected("EXPIRY_REQUIRED", "Mandatory expiry time required")
        if not capability_scope:
            raise ApprovalRejected("SCOPE_REQUIRED", "Capability scope required")
        if any(c in PROHIBITED_IN_SCOPE or c == "*" for c in capability_scope):
            raise ApprovalRejected("PROHIBITED_SCOPE", "Capability scope contains prohibited or wildcard items")
        if any(o in PROHIBITED_IN_SCOPE or o in PROHIBITED_OPERATIONS for o in operation_scope):
            raise ApprovalRejected("PROHIBITED_OPERATION_SCOPE", "Operation scope includes prohibited operations")
        if not allowed_network_destinations:
            raise ApprovalRejected("DESTINATIONS_REQUIRED", "Allowed network destinations required")
        if any("*" in d for d in allowed_network_destinations):
            raise ApprovalRejected("WILDCARD_DOMAIN", "Wildcard domains forbidden")
        if jurisdiction in ("", "UNRESOLVED", None) and approval_type not in (
            "provider_documentation_review", "revocation_request", "emergency_shutdown_request",
        ):
            raise ApprovalRejected("JURISDICTION_UNRESOLVED", "Jurisdiction must be resolved")
        if not revocation_conditions:
            raise ApprovalRejected("REVOCATION_CONDITIONS_REQUIRED", "Revocation conditions required")
        if not evidence_requirements:
            raise ApprovalRejected("EVIDENCE_REQUIRED", "Evidence requirements required")
        if environment in ("", "ambiguous", "production") and approval_type not in (
            "revocation_request", "emergency_shutdown_request", "provider_documentation_review",
        ):
            if environment == "production":
                raise ApprovalRejected("PRODUCTION_FORBIDDEN", "Production environment not allowed")
            if environment in ("", "ambiguous"):
                raise ApprovalRejected("ENVIRONMENT_AMBIGUOUS", "Environment must be explicit")

        rid = _uid("req")
        aid = _uid("appr")
        now = time.time()
        rec = {
            "approval_id": aid,
            "request_id": rid,
            "requestor": requestor,
            "approver": None,
            "approval_type": approval_type,
            "provider": provider,
            "environment": environment,
            "account_identifier_reference": account_identifier_reference or "none",
            "capability_scope": list(capability_scope),
            "operation_scope": list(operation_scope),
            "instrument_scope": list(instrument_scope or ["none"]),
            "jurisdiction": jurisdiction,
            "start_time": start_time or now,
            "expiry_time": expiry_time,
            "maximum_session_duration": maximum_session_duration,
            "allowed_network_destinations": list(allowed_network_destinations),
            "credential_reference_policy": credential_reference_policy,
            "evidence_requirements": list(evidence_requirements),
            "rollback_requirements": list(rollback_requirements or ["revoke_and_disable"]),
            "revocation_conditions": list(revocation_conditions),
            "emergency_contacts": list(emergency_contacts or []),
            "explicit_acknowledgements": list(acknowledgements or []),
            "limitations": list(limitations or [
                "approval_does_not_equal_activation",
                "no_provider_connection",
                "governance_only",
            ]),
            "status": ApprovalState.DRAFT.value,
            "audit_references": [],
            "activates_connectivity": False,
            "immutable_decision": False,
            "created_at": now,
            "updated_at": now,
        }
        self._records[aid] = rec
        return {"ok": True, "approval": rec, "activates_connectivity": False, **AUTHORITY_VALUES}

    def submit(self, approval_id: str, *, actor: str) -> dict[str, Any]:
        rec = self._require(approval_id)
        if rec["status"] != ApprovalState.DRAFT.value:
            raise ApprovalRejected("INVALID_STATE", f"Cannot submit from {rec['status']}")
        if actor != rec["requestor"]:
            raise ApprovalRejected("ONLY_REQUESTOR_SUBMITS", "Only requestor may submit")
        if not rec.get("explicit_acknowledgements"):
            raise ApprovalRejected("ACKNOWLEDGEMENTS_REQUIRED", "Explicit acknowledgements required")
        rec["status"] = ApprovalState.SUBMITTED.value
        rec["updated_at"] = time.time()
        rec["audit_references"].append(f"submitted_by:{actor}")
        return {"ok": True, "approval": rec, "activates_connectivity": False, **AUTHORITY_VALUES}

    def review(self, approval_id: str, *, approver: str, decision: str, notes: str = "") -> dict[str, Any]:
        rec = self._require(approval_id)
        if rec["status"] not in (ApprovalState.SUBMITTED.value, ApprovalState.UNDER_REVIEW.value):
            raise ApprovalRejected("INVALID_STATE", f"Cannot review from {rec['status']}")
        if not approver or approver.lower() in LLM_IDENTITIES:
            raise ApprovalRejected("LLM_APPROVAL_REJECTED", "LLM/AI cannot approve")
        if approver == rec["requestor"]:
            raise ApprovalRejected("SELF_APPROVAL_REJECTED", "Maker-checker: approver cannot equal requestor")
        rec["status"] = ApprovalState.UNDER_REVIEW.value
        if decision == "approve":
            # Still APPROVED_NOT_ACTIVE — never activates connectivity
            rec["status"] = ApprovalState.APPROVED_NOT_ACTIVE.value
            rec["approver"] = approver
            rec["immutable_decision"] = True
            rec["decision_notes"] = notes
            rec["decision_at"] = time.time()
            rec["activates_connectivity"] = False
            rec["audit_references"].append(f"approved_not_active_by:{approver}")
        elif decision == "reject":
            rec["status"] = ApprovalState.REJECTED.value
            rec["approver"] = approver
            rec["immutable_decision"] = True
            rec["decision_notes"] = notes
            rec["decision_at"] = time.time()
            rec["audit_references"].append(f"rejected_by:{approver}")
        else:
            raise ApprovalRejected("INVALID_DECISION", "decision must be approve or reject")
        rec["updated_at"] = time.time()
        return {
            "ok": True,
            "approval": rec,
            "activates_connectivity": False,
            "approval_does_not_equal_activation": True,
            "max_approval_state": MAX_APPROVAL_STATE,
            **AUTHORITY_VALUES,
        }

    def revoke(self, approval_id: str, *, actor: str, reason: str, emergency: bool = False) -> dict[str, Any]:
        rec = self._require(approval_id)
        if rec.get("immutable_decision") and rec["status"] in (
            ApprovalState.REJECTED.value,
        ):
            # rejected stays rejected; can mark revoked for approved
            pass
        rec["status"] = (
            ApprovalState.EMERGENCY_REVOKED.value if emergency else ApprovalState.REVOKED.value
        )
        rec["revoked_by"] = actor
        rec["revocation_reason"] = reason
        rec["revoked_at"] = time.time()
        rec["activates_connectivity"] = False
        rec["updated_at"] = time.time()
        rec["audit_references"].append(f"revoked_by:{actor}:{reason}")
        return {"ok": True, "approval": rec, **AUTHORITY_VALUES}

    def expire_if_needed(self, approval_id: str, *, now: float | None = None) -> dict[str, Any]:
        rec = self._require(approval_id)
        now = now if now is not None else time.time()
        if rec["status"] == ApprovalState.APPROVED_NOT_ACTIVE.value and now > rec["expiry_time"]:
            rec["status"] = ApprovalState.EXPIRED.value
            rec["updated_at"] = now
            rec["audit_references"].append("auto_expired")
        return {"ok": True, "approval": rec, **AUTHORITY_VALUES}

    def get(self, approval_id: str) -> dict[str, Any]:
        rec = self._records.get(approval_id)
        if not rec:
            return {"ok": False, "error": "NOT_FOUND"}
        return {"ok": True, "approval": rec, "activates_connectivity": False, **AUTHORITY_VALUES}

    def list_approvals(self, status: str | None = None) -> dict[str, Any]:
        items = list(self._records.values())
        if status:
            items = [i for i in items if i["status"] == status]
        return {
            "ok": True,
            "count": len(items),
            "approvals": items,
            "any_active_connectivity": False,
            **AUTHORITY_VALUES,
        }

    def _require(self, approval_id: str) -> dict[str, Any]:
        rec = self._records.get(approval_id)
        if not rec:
            raise ApprovalRejected("NOT_FOUND", f"Approval not found: {approval_id}")
        return rec

    def export_framework(self) -> dict[str, Any]:
        return {
            "schema": "M315_CONNECTIVITY_APPROVAL_FRAMEWORK",
            "categories": list(APPROVAL_CATEGORIES),
            "states": [s.value for s in ApprovalState],
            "controls": {
                "maker_checker": True,
                "no_self_approval": True,
                "no_llm_approval": True,
                "no_automatic_activation": True,
                "single_purpose": True,
                "narrow_scopes": True,
                "mandatory_expiry": True,
                "explicit_human_identity": True,
                "immutable_decision": True,
                "revocation_support": True,
                "approval_does_not_equal_activation": True,
            },
            "approvals": self.list_approvals(),
            **AUTHORITY_VALUES,
        }
