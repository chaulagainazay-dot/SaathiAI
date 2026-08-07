"""M240–M247 Provider Canary Planning service facade.

PLANNING ONLY. No real connectivity. No credentials. No canary activation.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.provider_canary_planning.canary import CanaryArchitecture
from saathi.platform.tg.provider_canary_planning.capabilities import CapabilityMap
from saathi.platform.tg.provider_canary_planning.control_center import PlanningControlCenter
from saathi.platform.tg.provider_canary_planning.credentials import CredentialCeremony
from saathi.platform.tg.provider_canary_planning.eligibility import EligibilityReview
from saathi.platform.tg.provider_canary_planning.gates import CanaryGates
from saathi.platform.tg.provider_canary_planning.models import (
    AUTHORITY_VALUES,
    ENGINE_VERSION,
    FALLBACK_PROVIDER,
    LLM_BOUNDARY,
    MAX_PLANNING_STATE,
    PCP_POSTURE,
    PREFERRED_PROVIDER,
    SCHEMA_VERSION,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.provider_canary_planning.owner_package import OwnerReviewPackage
from saathi.platform.tg.provider_canary_planning.ranking import ProviderRanking
from saathi.platform.tg.provider_canary_planning.security import PlanningSecurity
from saathi.platform.tg.provider_canary_planning.sources import SourceInventory
from saathi.platform.tg.provider_canary_planning.store import PlanningStore, _uid, evidence_hash
from saathi.platform.tg.provider_canary_planning.transport import (
    REAL_PROVIDER_TRANSPORT_FORBIDDEN,
    reset_transport_guard,
)


class ProviderCanaryPlanningError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class ProviderCanaryPlanningService:
    def __init__(self, db_path: str | Path | None = None, repo_root: Path | None = None):
        self.store = PlanningStore(db_path)
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        self.transport = reset_transport_guard(self.store)
        self.sources = SourceInventory(self.store)
        self.ranking = ProviderRanking(self.store)
        self.capabilities = CapabilityMap(self.store)
        self.eligibility = EligibilityReview(self.store)
        self.canary = CanaryArchitecture(self.store)
        self.credentials = CredentialCeremony(self.store)
        self.gates = CanaryGates(self.store)
        self.owner = OwnerReviewPackage(self.store, {
            "ranking": self.ranking,
            "capabilities": self.capabilities,
            "eligibility": self.eligibility,
            "canary": self.canary,
            "credentials": self.credentials,
            "gates": self.gates,
            "sources": self.sources,
        })
        self.security = PlanningSecurity(self.store, self.transport, self.repo_root)
        self.control = PlanningControlCenter(self)
        # Seed planning data
        self.bootstrap()

    def bootstrap(self) -> None:
        self.sources.seed_if_empty()
        self.ranking.ensure_seeded()
        self.capabilities.ensure_seeded()
        self.eligibility.ensure_seeded()
        self.canary.ensure_seeded()
        self.credentials.ensure_seeded()
        self.gates.ensure_seeded()

    def posture(self) -> dict[str, Any]:
        return {
            **PCP_POSTURE,
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M240-M247",
            "preferred_provider": PREFERRED_PROVIDER,
            "fallback_provider": FALLBACK_PROVIDER,
            "terminal_verdict_target": TERMINAL_VERDICT,
            "llm_boundary": dict(LLM_BOUNDARY),
            **AUTHORITY_VALUES,
        }

    def terminal_verdict(self) -> dict[str, Any]:
        return {
            "verdict": TERMINAL_VERDICT,
            "max_planning_state": MAX_PLANNING_STATE,
            "paper_only": True,
            "sandbox_only": True,
            "planning_only": True,
            "preferred_provider": PREFERRED_PROVIDER,
            "fallback_provider": FALLBACK_PROVIDER,
            "preferred_is_recommendation_only": True,
            "owner_eligibility_claimed": False,
            "owner_signoff": "NOT_CLAIMED_AUTOMATED_ONLY",
            "owner_signoff_generated_by_automation": False,
            "provider_adapter_implemented": False,
            "canary_activated": False,
            "real_connectivity_authorized": False,
            "credential_provisioning_authorized": False,
            "canary_activation_authorized": False,
            "read_only_production_authorized": False,
            "live_trading_authorized": False,
            "statements": list(TERMINAL_STATEMENTS),
            "limitations": [
                "Owner geographic eligibility unconfirmed",
                "Terms/legal review incomplete",
                "Provider documentation may drift after retrieval date",
                "No runtime provider adapter",
                "Single-host SQLite planning store",
                "Preferred provider is recommendation only",
            ],
            **AUTHORITY_VALUES,
        }

    # M240
    def candidates(self) -> dict[str, Any]:
        return self.ranking.candidates()

    def rankings(self) -> dict[str, Any]:
        return self.ranking.ranking()

    def preferred(self) -> dict[str, Any]:
        return self.ranking.preferred()

    def fallback(self) -> dict[str, Any]:
        return self.ranking.fallback()

    def list_sources(self, provider: str | None = None) -> dict[str, Any]:
        return self.sources.list_sources(provider)

    # M241
    def capabilities_map(self) -> dict[str, Any]:
        return self.capabilities.map()

    def endpoints(self) -> dict[str, Any]:
        m = self.capabilities.map()
        return {
            "provider": m["provider"],
            "endpoints": m["endpoints"],
            "by_auth_category": m["by_auth_category"],
            "provider_adapter_implemented": False,
            **AUTHORITY_VALUES,
        }

    def scopes(self) -> dict[str, Any]:
        return self.capabilities.scopes()

    def validate_scopes(self, scopes: list[str]) -> dict[str, Any]:
        return self.capabilities.reject_mixed_scope(scopes)

    # M242
    def eligibility_review(self) -> dict[str, Any]:
        return self.eligibility.review()

    def terms_review(self) -> dict[str, Any]:
        return self.eligibility.terms()

    # M243
    def canary_design(self) -> dict[str, Any]:
        return self.canary.design()

    def canary_activate_attempt(self) -> dict[str, Any]:
        return self.canary.attempt_activate()

    # M244
    def credential_ceremony(self) -> dict[str, Any]:
        return self.credentials.runbook()

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return self.credentials.refuse_raw_secret(value)

    def refuse_oauth(self) -> dict[str, Any]:
        return self.credentials.refuse_oauth()

    # M245
    def acceptance_gates(self) -> dict[str, Any]:
        g = self.gates.gates()
        return {
            "pre_activation_gates": g["pre_activation_gates"],
            "success_criteria": g["success_criteria"],
            "thresholds": g["thresholds"],
            **AUTHORITY_VALUES,
        }

    def abort_gates(self) -> dict[str, Any]:
        g = self.gates.gates()
        return {
            "abort_triggers": g["abort_triggers"],
            "thresholds": g["thresholds"],
            "automated_recovery_after_security_abort": False,
            **AUTHORITY_VALUES,
        }

    def monitoring_plan(self) -> dict[str, Any]:
        g = self.gates.gates()
        return {**g["monitoring_plan"], **AUTHORITY_VALUES}

    def reconciliation_plan(self) -> dict[str, Any]:
        g = self.gates.gates()
        return {**g["reconciliation_plan"], **AUTHORITY_VALUES}

    # M246
    def owner_package(self) -> dict[str, Any]:
        return self.owner.build()

    def owner_auto_signoff_attempt(self, decision: str = "APPROVE_PLANNING_PACKAGE_ONLY") -> dict[str, Any]:
        return self.owner.attempt_auto_signoff(decision)

    def planning_review_status(self, status: str, notes: str = "", actor: str = "system") -> dict[str, Any]:
        return self.owner.record_planning_review_status(status, notes=notes, actor=actor)

    # M247
    def dashboard(self) -> dict[str, Any]:
        return self.control.overview()

    def network_policy(self) -> dict[str, Any]:
        design = self.canary.design()
        return {
            "runtime_provider_transport": REAL_PROVIDER_TRANSPORT_FORBIDDEN,
            "network_allowlist_proposal": design.get("network_allowlist_proposal", []),
            "endpoint_allowlist_proposal": design.get("endpoint_allowlist_proposal", []),
            "endpoint_denylist_proposal": design.get("endpoint_denylist_proposal", []),
            "documentation_research_separated": True,
            "allowed_runtime": ["localhost", "127.0.0.1", "repository-local files"],
            **AUTHORITY_VALUES,
        }

    def transport_probe(self, url: str) -> dict[str, Any]:
        return self.transport.probe(url)

    def security_scan(self) -> dict[str, Any]:
        return self.security.full_scan()

    def threat_model(self) -> dict[str, Any]:
        return self.security.threat_model()

    def llm_refuse(self, action: str) -> dict[str, Any]:
        forbidden = {
            "certify_owner_eligibility", "legal_approval", "owner_approval",
            "security_approval", "create_credentials", "receive_credentials",
            "store_credentials", "activate_canary", "initiate_oauth",
            "connect_provider", "access_account_data", "approve_scopes",
            "enable_live_trading", "generate_owner_signoff",
        }
        a = (action or "").strip().lower()
        if a in forbidden or a.replace("-", "_") in forbidden:
            self.store.audit("llm.action_refused", detail={"action": a})
            return {
                "ok": False,
                "code": "LLM_ACTION_FORBIDDEN",
                "action": a,
                "message": "LLM authority boundary refuses this action.",
                **AUTHORITY_VALUES,
            }
        return {
            "ok": True,
            "action": a,
            "message": "Advisory/research actions may proceed; no authority granted.",
            **AUTHORITY_VALUES,
        }

    def audit_timeline(self, limit: int = 100) -> dict[str, Any]:
        return {
            "events": self.store.list_audit(limit=limit),
            **AUTHORITY_VALUES,
        }

    def certify(self) -> dict[str, Any]:
        """Certification for planning package readiness — not connectivity."""
        ranking = self.rankings()
        caps = self.capabilities_map()
        elig = self.eligibility_review()
        canary = self.canary_design()
        cred = self.credential_ceremony()
        gates = self.gates.gates()
        sec = self.security_scan()
        owner_block = self.owner_auto_signoff_attempt()
        activate_block = self.canary_activate_attempt()
        adapter = sec.get("runtime_adapter_scan", {})
        hard_ok = (
            ranking.get("preferred_provider") == PREFERRED_PROVIDER
            and ranking.get("fallback_provider") == FALLBACK_PROVIDER
            and caps.get("provider_adapter_implemented") is False
            and elig.get("owner_eligibility_claimed") is False
            and canary.get("state") == "CANARY_DESIGNED_NOT_AUTHORIZED"
            and cred.get("status") == "CREDENTIAL_CEREMONY_DOCUMENTED_NOT_EXECUTED"
            and owner_block.get("ok") is False
            and activate_block.get("ok") is False
            and adapter.get("ok") is True
            and sec.get("credential_scan", {}).get("ok") is True
            and sec.get("network_isolation", {}).get("ok") is True
            and sec.get("llm_boundary_scan", {}).get("ok") is True
        )
        verdict = TERMINAL_VERDICT if hard_ok else "M240_M247_IMPLEMENTED_NOT_VERIFIED"
        result = {
            "verdict": verdict,
            "hard_gates_pass": hard_ok,
            "preferred_provider": PREFERRED_PROVIDER,
            "fallback_provider": FALLBACK_PROVIDER,
            "eligibility_result": elig.get("result"),
            "canary_state": canary.get("state"),
            "credential_status": cred.get("status"),
            "owner_signoff_generated_by_automation": False,
            "security": {
                "credential_scan_ok": sec.get("credential_scan", {}).get("ok"),
                "network_isolation_ok": sec.get("network_isolation", {}).get("ok"),
                "adapter_scan_ok": adapter.get("ok"),
                "llm_boundary_ok": sec.get("llm_boundary_scan", {}).get("ok"),
            },
            "gates_present": {
                "pre_activation": len(gates.get("pre_activation_gates", [])),
                "success": len(gates.get("success_criteria", [])),
                "abort": len(gates.get("abort_triggers", [])),
            },
            "max_planning_state": MAX_PLANNING_STATE,
            "statements": list(TERMINAL_STATEMENTS),
            **AUTHORITY_VALUES,
        }
        eh = evidence_hash(result)
        result["evidence_hash"] = eh
        self.store.execute(
            """INSERT INTO pcp_certifications(id, verdict, result_json, evidence_hash, created_at)
               VALUES(?,?,?,?,?)""",
            (_uid("cert"), verdict, json.dumps(result), eh, time.time()),
        )
        self.store.audit("certify", detail={"verdict": verdict, "hard_ok": hard_ok})
        return result


_default: ProviderCanaryPlanningService | None = None


def default_provider_canary_planning() -> ProviderCanaryPlanningService:
    global _default
    if _default is None:
        _default = ProviderCanaryPlanningService()
    return _default


def reset_provider_canary_planning_for_tests(
    db_path: str | Path | None = None,
    repo_root: Path | None = None,
) -> ProviderCanaryPlanningService:
    global _default
    if _default is not None:
        try:
            _default.store.close()
        except Exception:
            pass
    _default = ProviderCanaryPlanningService(db_path=db_path, repo_root=repo_root)
    return _default
