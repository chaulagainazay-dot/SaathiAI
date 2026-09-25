"""M317 Incident response workflow."""
from __future__ import annotations

import time
import uuid
from typing import Any

from saathi.platform.tg.connectivity_governance.models import AUTHORITY_VALUES, IncidentState

INCIDENT_TYPES = (
    "credential_leak",
    "unexpected_provider_call",
    "unauthorized_endpoint",
    "scope_violation",
    "account_mismatch",
    "approval_mismatch",
    "expired_approval_use",
    "unauthorized_order_path",
    "provider_compromise",
    "network_destination_mismatch",
    "evidence_tampering",
    "llm_authority_bypass",
    "emergency_kill_switch_failure",
)

WORKFLOW_STEPS = (
    "detect", "classify", "contain", "revoke", "preserve_evidence",
    "assess_impact", "recover", "perform_human_review", "document_lessons", "close",
)


class IncidentResponse:
    def __init__(self):
        self._incidents: dict[str, dict[str, Any]] = {}

    def create(
        self,
        *,
        incident_type: str,
        actor: str,
        summary: str,
        severity: str = "HIGH",
    ) -> dict[str, Any]:
        if incident_type not in INCIDENT_TYPES:
            return {"ok": False, "error": "INVALID_TYPE", "incident_type": incident_type}
        iid = f"inc_{uuid.uuid4().hex[:12]}"
        rec = {
            "incident_id": iid,
            "incident_type": incident_type,
            "summary": summary,
            "severity": severity,
            "state": IncidentState.DETECTED.value,
            "actor": actor,
            "workflow": list(WORKFLOW_STEPS),
            "completed_steps": ["detect"],
            "created_at": time.time(),
            "updated_at": time.time(),
            "evidence": [],
            "human_review_required": True,
            "auto_closed": False,
        }
        self._incidents[iid] = rec
        return {"ok": True, "incident": rec, **AUTHORITY_VALUES}

    def advance(self, incident_id: str, *, step: str, actor: str, notes: str = "") -> dict[str, Any]:
        rec = self._incidents.get(incident_id)
        if not rec:
            return {"ok": False, "error": "NOT_FOUND"}
        step_to_state = {
            "classify": IncidentState.TRIAGED.value,
            "contain": IncidentState.CONTAINED.value,
            "revoke": IncidentState.REVOKED.value,
            "preserve_evidence": IncidentState.CONTAINED.value,
            "assess_impact": IncidentState.CONTAINED.value,
            "recover": IncidentState.RECOVERY_PENDING.value,
            "perform_human_review": IncidentState.RECOVERY_PENDING.value,
            "document_lessons": IncidentState.RECOVERY_PENDING.value,
            "close": IncidentState.CLOSED_WITH_LIMITATIONS.value,
        }
        if step == "close" and actor.lower() in ("llm", "ai", "agent", "model"):
            return {"ok": False, "error": "LLM_CANNOT_CLOSE", "message": "Human must close incidents"}
        if step == "close" and rec.get("severity") == "CRITICAL" and "perform_human_review" not in rec["completed_steps"]:
            return {"ok": False, "error": "HUMAN_REVIEW_REQUIRED", "message": "Critical incidents require human review"}
        if step not in WORKFLOW_STEPS:
            return {"ok": False, "error": "INVALID_STEP"}
        if step not in rec["completed_steps"]:
            rec["completed_steps"].append(step)
        if step in step_to_state:
            rec["state"] = step_to_state[step]
        rec["updated_at"] = time.time()
        rec["evidence"].append({"step": step, "actor": actor, "notes": notes, "at": time.time()})
        return {"ok": True, "incident": rec, **AUTHORITY_VALUES}

    def get(self, incident_id: str) -> dict[str, Any]:
        rec = self._incidents.get(incident_id)
        if not rec:
            return {"ok": False, "error": "NOT_FOUND"}
        return {"ok": True, "incident": rec, **AUTHORITY_VALUES}

    def list_incidents(self) -> dict[str, Any]:
        return {
            "ok": True,
            "count": len(self._incidents),
            "incidents": list(self._incidents.values()),
            "types": list(INCIDENT_TYPES),
            "workflow": list(WORKFLOW_STEPS),
            "states": [s.value for s in IncidentState],
            **AUTHORITY_VALUES,
        }

    def export(self) -> dict[str, Any]:
        return {
            "schema": "M317_REVOCATION_AND_INCIDENT_RESPONSE",
            "incidents": self.list_incidents(),
            **AUTHORITY_VALUES,
        }
