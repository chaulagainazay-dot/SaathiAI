"""M246 — Human authorization / owner review package.

owner_signoff_generated_by_automation = false always.
Decision options: REJECT | REQUEST_CHANGES | APPROVE_PLANNING_PACKAGE_ONLY
No option authorizes connectivity.
"""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.provider_canary_planning.models import (
    AUTHORITY_VALUES,
    FALLBACK_PROVIDER,
    MAX_PLANNING_STATE,
    OwnerDecisionOption,
    PREFERRED_PROVIDER,
    TERMINAL_STATEMENTS,
)
from saathi.platform.tg.provider_canary_planning.store import PlanningStore, _uid, evidence_hash

DECISION_OPTIONS = [
    OwnerDecisionOption.REJECT.value,
    OwnerDecisionOption.REQUEST_CHANGES.value,
    OwnerDecisionOption.APPROVE_PLANNING_PACKAGE_ONLY.value,
]


class OwnerReviewPackage:
    def __init__(self, store: PlanningStore, deps: dict[str, Any]):
        """deps: ranking, capabilities, eligibility, canary, credentials, gates callables/objects."""
        self.store = store
        self.deps = deps

    def build(self) -> dict[str, Any]:
        ranking = self.deps["ranking"].ranking()
        preferred = self.deps["ranking"].preferred()
        fallback = self.deps["ranking"].fallback()
        caps = self.deps["capabilities"].map()
        scopes = self.deps["capabilities"].scopes()
        elig = self.deps["eligibility"].review()
        terms = self.deps["eligibility"].terms()
        canary = self.deps["canary"].design()
        cred = self.deps["credentials"].runbook()
        gates = self.deps["gates"].gates()
        sources = self.deps["sources"].list_sources()

        package = {
            "executive_summary": (
                "M240–M247 produces a provider-specific, evidence-backed read-only canary "
                "planning package for human owner review. Preferred provider is a recommendation only. "
                "No connectivity, credentials, or canary activation is authorized."
            ),
            "milestone_boundary": "M240-M247",
            "max_planning_state": MAX_PLANNING_STATE,
            "preferred_provider": PREFERRED_PROVIDER,
            "fallback_provider": FALLBACK_PROVIDER,
            "preferred_is_recommendation_only": True,
            "ranking_evidence": ranking,
            "provider_specific_capability_map": caps,
            "eligibility_findings": elig,
            "unresolved_eligibility_questions": elig.get("unresolved", []),
            "terms_review": terms,
            "legal_review_items": elig.get("legal_review_items", []),
            "minimum_required_scopes": scopes.get("proposed_read_only_scopes", []),
            "forbidden_scopes": scopes.get("forbidden_scopes", []),
            "network_allow_list": canary.get("network_allowlist_proposal", []),
            "endpoint_allow_list": canary.get("endpoint_allowlist_proposal", []),
            "canary_architecture": canary,
            "credential_ceremony": {
                "status": cred.get("status"),
                "executed": False,
                "steps_count": len(cred.get("ceremony", {}).get("steps", [])),
            },
            "data_retention_plan": canary.get("budgets", {}).get("data_retention_limit"),
            "audit_plan": canary.get("audit_flow"),
            "monitoring_plan": gates.get("monitoring_plan"),
            "reconciliation_plan": gates.get("reconciliation_plan"),
            "incident_plan": cred.get("compromise"),
            "kill_switch_plan": canary.get("kill_switch_flow"),
            "revocation_plan": cred.get("revocation"),
            "rollback_plan": canary.get("rollback"),
            "acceptance_criteria": gates.get("success_criteria"),
            "abort_criteria": gates.get("abort_triggers"),
            "residual_risks": [
                "Owner eligibility unconfirmed",
                "Terms review incomplete",
                "Provider documentation may drift after retrieval_date",
                "Non-expiring keys residual risk on some providers",
                "Market-data redistribution legal risk",
            ],
            "limitations": [
                "Planning only — no runtime provider adapter",
                "No credentials requested or stored",
                "Eligibility not certified",
                "Legal approval not generated",
                "Single-host SQLite planning store",
            ],
            "explicit_non_authorizations": list(TERMINAL_STATEMENTS),
            "authority_values": dict(AUTHORITY_VALUES),
            "sources_inventory_count": sources.get("count", 0),
            "owner_decision_form": {
                "options": DECISION_OPTIONS,
                "preselected": None,
                "signed_by_automation": False,
                "note": (
                    "APPROVE_PLANNING_PACKAGE_ONLY does not authorize connectivity, "
                    "credentials, or canary activation."
                ),
                "connectivity_authorization_option_present": False,
            },
            "owner_signoff_generated_by_automation": False,
            "owner_decision": "",  # never pre-filled
        }

        eh = evidence_hash(package)
        self.store.execute(
            """INSERT INTO pcp_owner_packages(
                id, preferred_provider, fallback_provider, package_json, owner_decision,
                owner_signoff_generated_by_automation, decision_options_json, evidence_hash, created_at
            ) VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                _uid("own"), PREFERRED_PROVIDER, FALLBACK_PROVIDER,
                json.dumps(package), "", 0, json.dumps(DECISION_OPTIONS),
                eh, time.time(),
            ),
        )
        self.store.audit("owner_package.built", detail={"evidence_hash": eh})
        package["evidence_hash"] = eh
        package["REAL_CONNECTIVITY_AUTHORIZED"] = False
        return package

    def attempt_auto_signoff(self, decision: str = "APPROVE_PLANNING_PACKAGE_ONLY") -> dict[str, Any]:
        self.store.audit(
            "owner_signoff.automation_refused",
            detail={"attempted_decision": decision},
        )
        return {
            "ok": False,
            "code": "OWNER_SIGNOFF_AUTOMATION_FORBIDDEN",
            "message": "Automation must not pre-select or sign an owner decision.",
            "owner_signoff_generated_by_automation": False,
            "decision_options": DECISION_OPTIONS,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }

    def record_planning_review_status(self, status: str, notes: str = "", actor: str = "system") -> dict[str, Any]:
        """Planning-only review status — not owner sign-off."""
        allowed = {
            "PLANNING_PACKAGE_READY",
            "AWAITING_OWNER_REVIEW",
            "CHANGES_REQUESTED_NOTED",
            "PACKAGE_REJECTED_NOTED",
            "PACKAGE_APPROVED_PLANNING_ONLY_NOTED",
        }
        if status not in allowed:
            return {
                "ok": False,
                "code": "INVALID_PLANNING_REVIEW_STATUS",
                "allowed": sorted(allowed),
                "REAL_CONNECTIVITY_AUTHORIZED": False,
            }
        # Note statuses do not grant connectivity
        self.store.execute(
            """INSERT INTO pcp_review_status(id, status, notes, actor, created_at)
               VALUES(?,?,?,?,?)""",
            (_uid("rev"), status, notes, actor, time.time()),
        )
        self.store.audit("planning_review_status", actor=actor, detail={"status": status, "notes": notes})
        return {
            "ok": True,
            "status": status,
            "grants_connectivity": False,
            "owner_signoff_generated_by_automation": False,
            "REAL_CONNECTIVITY_AUTHORIZED": False,
        }
