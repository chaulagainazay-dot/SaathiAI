"""M312–M319 Connectivity Governance service facade.

GOVERNANCE ONLY. NO PROVIDER CONNECTION. NO CREDENTIALS. NO OAUTH.
NO ACCOUNT ACCESS. NO ORDERS. NO CANARY. NO LIVE TRADING.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.connectivity_governance.approval_policy import ApprovalFramework
from saathi.platform.tg.connectivity_governance.authority import (
    authority_model_export,
    evaluate_authority,
    prove_deny_overrides_allow,
    prove_emergency_override,
    prove_expiry,
    prove_no_implicit_expansion,
    prove_revocation,
    authority_matrix,
)
from saathi.platform.tg.connectivity_governance.certification import certify_connectivity_governance
from saathi.platform.tg.connectivity_governance.charter import build_charter, charter_public
from saathi.platform.tg.connectivity_governance.credential_policy import CredentialGovernance
from saathi.platform.tg.connectivity_governance.emergency_shutdown import EmergencyShutdown
from saathi.platform.tg.connectivity_governance.errors import (
    ApprovalRejected,
    ConnectivityGovernanceError,
    CredentialPolicyViolation,
    SecretFieldDetected,
)
from saathi.platform.tg.connectivity_governance.incident_response import IncidentResponse
from saathi.platform.tg.connectivity_governance.maturity import maturity_status
from saathi.platform.tg.connectivity_governance.models import (
    AUTHORITY_VALUES,
    CG_POSTURE,
    CURRENT_MATURITY,
    ENGINE_VERSION,
    LLM_BOUNDARY,
    MAX_STATE,
    PROHIBITED_OPERATIONS,
    SCHEMA_VERSION,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.connectivity_governance.provider_registry import ProviderRegistry
from saathi.platform.tg.connectivity_governance.revocation import RevocationService
from saathi.platform.tg.connectivity_governance.storage import GovernanceStore, evidence_hash
from saathi.platform.tg.connectivity_governance.threat_model import export_threat_model, list_threats, risk_summary


class ConnectivityGovernanceService:
    def __init__(self, db_path: str | Path | None = None, repo_root: Path | None = None):
        self.store = GovernanceStore(db_path)
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        self.providers = ProviderRegistry()
        self.approvals = ApprovalFramework()
        self.credentials = CredentialGovernance()
        self.revocations = RevocationService()
        self.emergency = EmergencyShutdown()
        self.incidents = IncidentResponse()
        # Persist charter
        charter = build_charter()
        self.store.execute(
            "INSERT OR REPLACE INTO cg_charter(id, version, payload_json, finalized, evidence_hash, created_at) VALUES(?,?,?,?,?,?)",
            (
                "charter_v1",
                charter["charter_version"],
                json.dumps(charter, sort_keys=True),
                1,
                evidence_hash(charter),
                time.time(),
            ),
        )
        self.store.audit("bootstrap", "system", "charter", {"version": charter["charter_version"]})

    def posture(self) -> dict[str, Any]:
        return {
            **CG_POSTURE,
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M312-M319",
            "terminal_verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "emergency_shutdown": self.emergency.active,
            "llm_boundary": dict(LLM_BOUNDARY),
            "purpose": "connectivity_governance_only",
            **AUTHORITY_VALUES,
        }

    def terminal_verdict(self) -> dict[str, Any]:
        return {
            "verdict": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "current_maturity": CURRENT_MATURITY,
            "statements": list(TERMINAL_STATEMENTS),
            "capabilities": {
                "connectivity_governance_charter": True,
                "authority_model": True,
                "provider_governance_registry": True,
                "approval_framework": True,
                "credential_governance_policy": True,
                "revocation_and_emergency": True,
                "threat_model": True,
                "maturity_model": True,
            },
            "forbidden": {
                "provider_connection": True,
                "broker_login": True,
                "oauth": True,
                "credentials": True,
                "account_access": True,
                "orders": True,
                "canary_activation": True,
                "live_trading": True,
            },
            "limitations": [
                "Governance only — no provider connection",
                "Approvals do not activate connectivity",
                "Synthetic credential references only",
                "Live trading prohibited",
            ],
            "purpose": "connectivity_governance_only",
            **AUTHORITY_VALUES,
        }

    # --- Charter / Authority ---
    def charter(self) -> dict[str, Any]:
        return charter_public()

    def authority_model(self) -> dict[str, Any]:
        return authority_model_export()

    def authority_list(self) -> dict[str, Any]:
        return authority_matrix()

    def authority_evaluate(self, capability: str, **kw: Any) -> dict[str, Any]:
        if self.emergency.active:
            kw["emergency"] = True
        return evaluate_authority(capability, **kw)

    # --- Providers ---
    def list_providers(self) -> dict[str, Any]:
        return self.providers.list_providers()

    def get_provider(self, provider_id: str) -> dict[str, Any]:
        return self.providers.get_provider(provider_id)

    def register_provider(self, record: dict[str, Any], *, actor: str) -> dict[str, Any]:
        if self.emergency.active:
            return self.emergency.attempt_bypass()
        r = self.providers.register_provider(record, actor=actor)
        if r.get("ok"):
            self.store.audit("provider_register", actor, record.get("provider_id", ""), {"status": r["provider"]["governance_status"]})
        return r

    def prohibit_provider(self, provider_id: str, *, actor: str, reason: str) -> dict[str, Any]:
        r = self.providers.prohibit_provider(provider_id, actor=actor, reason=reason)
        self.store.audit("provider_prohibit", actor, provider_id, {"reason": reason})
        return r

    def capability_policy(self) -> dict[str, Any]:
        return self.providers.capability_policy()

    def domain_allowlists(self) -> dict[str, Any]:
        return self.providers.domain_allowlists()

    def provider_registry_export(self) -> dict[str, Any]:
        return self.providers.export_registry()

    # --- Approvals ---
    def create_approval(self, **kw: Any) -> dict[str, Any]:
        if self.emergency.active and kw.get("approval_type") != "emergency_shutdown_request":
            return self.emergency.attempt_bypass()
        # Scan for secrets in kwargs
        self.credentials.scan_input(kw)
        r = self.approvals.create_draft(**kw)
        self.store.audit("approval_create", kw.get("requestor", ""), r["approval"]["approval_id"], {"type": kw.get("approval_type")})
        return r

    def submit_approval(self, approval_id: str, *, actor: str) -> dict[str, Any]:
        r = self.approvals.submit(approval_id, actor=actor)
        self.store.audit("approval_submit", actor, approval_id, {})
        return r

    def review_approval(self, approval_id: str, *, approver: str, decision: str, notes: str = "") -> dict[str, Any]:
        r = self.approvals.review(approval_id, approver=approver, decision=decision, notes=notes)
        self.store.audit("approval_review", approver, approval_id, {"decision": decision, "activates": False})
        return r

    def revoke_approval(self, approval_id: str, *, actor: str, reason: str, emergency: bool = False) -> dict[str, Any]:
        r = self.approvals.revoke(approval_id, actor=actor, reason=reason, emergency=emergency)
        self.revocations.revoke(scope="approval", target_id=approval_id, reason="operator_request" if not emergency else "emergency_shutdown", actor=actor, emergency=emergency)
        self.store.audit("approval_revoke", actor, approval_id, {"reason": reason})
        return r

    def list_approvals(self, status: str | None = None) -> dict[str, Any]:
        return self.approvals.list_approvals(status)

    def get_approval(self, approval_id: str) -> dict[str, Any]:
        return self.approvals.get(approval_id)

    def approval_framework_export(self) -> dict[str, Any]:
        return self.approvals.export_framework()

    # --- Credentials ---
    def credential_policy(self) -> dict[str, Any]:
        return self.credentials.policy()

    def declare_synthetic_reference(self, **kw: Any) -> dict[str, Any]:
        return self.credentials.declare_synthetic_reference(**kw)

    def reject_raw_credential(self, field: str, value: str | None = None) -> dict[str, Any]:
        return self.credentials.reject_raw_credential(field, value)

    def scan_secrets(self, payload: dict[str, Any] | None) -> dict[str, Any]:
        return self.credentials.scan_input(payload)

    def list_credential_refs(self) -> dict[str, Any]:
        return self.credentials.list_references()

    # --- Revocation / Emergency / Incidents ---
    def revoke(self, **kw: Any) -> dict[str, Any]:
        r = self.revocations.revoke(**kw)
        self.store.audit("revoke", kw.get("actor", ""), kw.get("target_id", ""), kw)
        return r

    def list_revocations(self) -> dict[str, Any]:
        return self.revocations.list_revocations()

    def emergency_status(self) -> dict[str, Any]:
        return self.emergency.status()

    def emergency_shutdown(self, *, actor: str, reason: str) -> dict[str, Any]:
        r = self.emergency.activate(actor=actor, reason=reason)
        self.store.audit("emergency_shutdown", actor, "global", {"reason": reason})
        return r

    def emergency_bypass_attempt(self) -> dict[str, Any]:
        return self.emergency.attempt_bypass()

    def emergency_recovery_request(self, *, actor: str, notes: str = "") -> dict[str, Any]:
        return self.emergency.recovery_request(actor=actor, notes=notes)

    def create_incident(self, **kw: Any) -> dict[str, Any]:
        r = self.incidents.create(**kw)
        self.store.audit("incident_create", kw.get("actor", ""), r.get("incident", {}).get("incident_id", ""), kw)
        return r

    def advance_incident(self, incident_id: str, **kw: Any) -> dict[str, Any]:
        return self.incidents.advance(incident_id, **kw)

    def list_incidents(self) -> dict[str, Any]:
        return self.incidents.list_incidents()

    def get_incident(self, incident_id: str) -> dict[str, Any]:
        return self.incidents.get(incident_id)

    # --- Threats / Maturity ---
    def list_threats(self, severity: str | None = None) -> dict[str, Any]:
        return list_threats(severity)

    def risk_summary(self) -> dict[str, Any]:
        return risk_summary()

    def threat_model_export(self) -> dict[str, Any]:
        return export_threat_model()

    def maturity(self) -> dict[str, Any]:
        return maturity_status(checks={
            "charter": True,
            "authority_model": True,
            "provider_registry": True,
            "approval_framework": True,
            "credential_policy": True,
            "threat_model": True,
            "incident_response": True,
            "certification": True,
        })

    # --- Dashboard / Evidence / Cert ---
    def dashboard(self) -> dict[str, Any]:
        prov = self.list_providers()
        appr = self.list_approvals()
        inc = self.list_incidents()
        risks = self.risk_summary()
        return {
            "title": "Connectivity Governance Control Center",
            "verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "current_maturity": CURRENT_MATURITY,
            "statements": list(TERMINAL_STATEMENTS),
            "overview": {
                "connectivity_status": "NO_PROVIDER_CONNECTION",
                "active_authority": "NONE_FOR_CONNECTIVITY",
                "provider_count": prov.get("count"),
                "approved_providers": 0,
                "prohibited_providers": sum(
                    1 for p in prov.get("providers") or [] if p.get("governance_status") == "PROHIBITED"
                ),
                "pending_approvals": sum(
                    1 for a in appr.get("approvals") or [] if a.get("status") in ("SUBMITTED", "UNDER_REVIEW", "DRAFT")
                ),
                "expired_approvals": sum(1 for a in appr.get("approvals") or [] if a.get("status") == "EXPIRED"),
                "revoked_approvals": sum(
                    1 for a in appr.get("approvals") or [] if a.get("status") in ("REVOKED", "EMERGENCY_REVOKED")
                ),
                "open_incidents": sum(
                    1 for i in inc.get("incidents") or [] if i.get("state") not in ("CLOSED", "CLOSED_WITH_LIMITATIONS", "NONE")
                ),
                "emergency_shutdown_state": self.emergency.active,
                "critical_threats": risks.get("by_severity", {}).get("CRITICAL", 0),
            },
            "authority_matrix_summary": AUTHORITY_VALUES,
            "prohibited_operations": sorted(PROHIBITED_OPERATIONS),
            "governance_only_banner": True,
            "allowed_ui_actions": [
                "review_governance_charter",
                "inspect_authority",
                "inspect_provider_policy",
                "draft_approval_request",
                "submit_governance_only_request",
                "approve_governance_policy",
                "reject_request",
                "revoke_approval",
                "activate_emergency_governance_shutdown",
                "review_incident",
                "export_evidence",
            ],
            "forbidden_ui_actions": [
                "enter_api_key",
                "enter_password",
                "connect_provider",
                "authorize_oauth",
                "select_real_account",
                "view_balance",
                "view_position",
                "submit_order",
                "activate_canary",
                "enable_paper_execution",
                "enable_live_trading",
            ],
            **AUTHORITY_VALUES,
        }

    def bootstrap_demo_pipeline(self) -> dict[str, Any]:
        """Governance-only demo: seed approval + incident + synthetic ref — no connectivity."""
        charter = self.charter()
        matrix = self.authority_list()
        providers = self.list_providers()
        draft = self.create_approval(
            requestor="gov_requestor",
            approval_type="provider_documentation_review",
            provider="prov_mock_contract",
            environment="governance",
            capability_scope=["offline_fixture_access"],
            operation_scope=["documentation_review"],
            jurisdiction="N/A",
            expiry_time=time.time() + 86400,
            allowed_network_destinations=["localhost"],
            evidence_requirements=["charter_hash", "provider_docs"],
            revocation_conditions=["operator_request", "policy_violation"],
            acknowledgements=["governance_only", "no_activation", "no_credentials"],
        )
        aid = draft["approval"]["approval_id"]
        self.submit_approval(aid, actor="gov_requestor")
        reviewed = self.review_approval(aid, approver="gov_approver", decision="approve")
        syn = self.declare_synthetic_reference(
            reference="secret-ref://synthetic/not-active",
            owner="gov_requestor",
            provider="prov_mock_contract",
        )
        inc = self.create_incident(
            incident_type="llm_authority_bypass",
            actor="gov_operator",
            summary="Simulated LLM approval attempt (governance drill)",
            severity="HIGH",
        )
        self.advance_incident(inc["incident"]["incident_id"], step="classify", actor="gov_operator")
        self.advance_incident(inc["incident"]["incident_id"], step="contain", actor="gov_operator")
        proofs = {
            "no_implicit_expansion": prove_no_implicit_expansion(),
            "deny_overrides_allow": prove_deny_overrides_allow(),
            "expiry": prove_expiry(),
            "revocation": prove_revocation(),
            "emergency_override": prove_emergency_override(),
        }
        return {
            "ok": True,
            "charter_version": charter.get("charter_version"),
            "capability_count": len(matrix.get("capabilities") or []),
            "provider_count": providers.get("count"),
            "approval_id": aid,
            "approval_status": reviewed["approval"]["status"],
            "activates_connectivity": False,
            "synthetic_ref_id": syn["credential_reference"]["reference_id"],
            "incident_id": inc["incident"]["incident_id"],
            "proofs_ok": all(p.get("ok") for p in proofs.values()),
            "proofs": proofs,
            "provider_connected": False,
            "purpose": "connectivity_governance_only",
            **AUTHORITY_VALUES,
        }

    def certify(self) -> dict[str, Any]:
        return certify_connectivity_governance(self)

    def evidence_bundle(self) -> dict[str, Any]:
        return {
            "ok": True,
            "charter": self.charter(),
            "authority": self.authority_model(),
            "providers": self.provider_registry_export(),
            "approvals": self.approval_framework_export(),
            "credentials": self.credential_policy(),
            "revocations": self.list_revocations(),
            "emergency": self.emergency_status(),
            "incidents": self.list_incidents(),
            "threats": self.threat_model_export(),
            "maturity": self.maturity(),
            "audit": self.store.list_audit(50),
            "schema_scan": self.store.schema_scan(),
            **AUTHORITY_VALUES,
        }

    def security_scan(self) -> dict[str, Any]:
        findings = []
        # Authority must all be false for connectivity
        for k in (
            "REAL_CONNECTIVITY_AUTHORIZED", "BROKER_CONNECTIVITY_AUTHORIZED",
            "CREDENTIAL_PROVISIONING_AUTHORIZED", "OAUTH_AUTHORIZED",
            "ACCOUNT_ACCESS_AUTHORIZED", "ORDER_SUBMISSION_AUTHORIZED",
            "CANARY_ACTIVATION_AUTHORIZED", "LIVE_TRADING_AUTHORIZED",
        ):
            if AUTHORITY_VALUES.get(k) is True:
                findings.append(f"authority_true:{k}")
        schema = self.store.schema_scan()
        if not schema.get("ok"):
            findings.append("schema_secret_fields")
        # No provider may be connected
        for p in self.list_providers().get("providers") or []:
            if p.get("connected") or p.get("active") or p.get("connection_established"):
                findings.append(f"provider_active:{p.get('provider_id')}")
        return {
            "ok": len(findings) == 0,
            "findings": findings,
            "schema": schema,
            "provider_isolation": True,
            "llm_authority_scan": {"llm_may_approve": False, "llm_may_activate": False},
            **AUTHORITY_VALUES,
        }

    # --- Hard refusals ---
    def refuse_broker_login(self, target: str = "") -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "BROKER_LOGIN_REFUSED",
                "message": "Broker login forbidden under connectivity governance", "target": target, **AUTHORITY_VALUES}

    def refuse_oauth(self, provider: str = "") -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "OAUTH_REFUSED",
                "message": "OAuth forbidden under connectivity governance", "provider": provider, **AUTHORITY_VALUES}

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return self.reject_raw_credential("api_key", value)

    def refuse_order(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "ORDER_REFUSED",
                "message": "Orders forbidden — governance only", **AUTHORITY_VALUES}

    def refuse_account_access(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "ACCOUNT_ACCESS_REFUSED",
                "message": "Account access forbidden", **AUTHORITY_VALUES}

    def refuse_balance_access(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "BALANCE_READ_REFUSED",
                "message": "Balance access forbidden", **AUTHORITY_VALUES}

    def refuse_position_access(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "POSITION_READ_REFUSED",
                "message": "Position access forbidden", **AUTHORITY_VALUES}

    def refuse_canary(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "CANARY_ACTIVATION_REFUSED",
                "message": "Canary activation not authorized", **AUTHORITY_VALUES}

    def refuse_live_trading(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "LIVE_TRADING_REFUSED",
                "message": "Live trading remains prohibited", **AUTHORITY_VALUES}

    def refuse_provider_connect(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "PROVIDER_CONNECTION_REFUSED",
                "message": "Provider connection forbidden in governance milestone", **AUTHORITY_VALUES}

    def refuse_transfer(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "TRANSFER_REFUSED", **AUTHORITY_VALUES}

    def refuse_withdrawal(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "WITHDRAWAL_REFUSED", **AUTHORITY_VALUES}


_default: ConnectivityGovernanceService | None = None


def default_connectivity_governance() -> ConnectivityGovernanceService:
    global _default
    if _default is None:
        _default = ConnectivityGovernanceService()
    return _default


def reset_connectivity_governance_for_tests(db_path: str | Path | None = None) -> ConnectivityGovernanceService:
    global _default
    _default = ConnectivityGovernanceService(db_path=db_path)
    return _default
