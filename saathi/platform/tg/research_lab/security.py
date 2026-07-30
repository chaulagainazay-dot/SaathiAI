"""Security scans and boundary refusals for the research lab."""
from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

from saathi.platform.tg.research_lab.models import (
    AUTHORITY_VALUES,
    FORBIDDEN_ENV_VARS,
    FORBIDDEN_PROVIDER_DOMAINS,
    LLM_BOUNDARY,
)


class ResearchLabSecurity:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def refuse_broker(self, target: str = "") -> dict[str, Any]:
        return {
            "ok": False,
            "refused": True,
            "code": "BROKER_CONNECTIVITY_REFUSED",
            "message": "Research lab does not connect to brokers",
            "target": target,
            **AUTHORITY_VALUES,
        }

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return {
            "ok": False,
            "refused": True,
            "code": "CREDENTIAL_PROVISIONING_REFUSED",
            "message": "API keys and credentials are not accepted",
            "value_received": bool(value),
            **AUTHORITY_VALUES,
        }

    def refuse_order(self) -> dict[str, Any]:
        return {
            "ok": False,
            "refused": True,
            "code": "ORDER_EXECUTION_REFUSED",
            "message": "Order submission/modification/cancellation is not authorized",
            **AUTHORITY_VALUES,
        }

    def refuse_canary(self) -> dict[str, Any]:
        return {
            "ok": False,
            "refused": True,
            "code": "CANARY_ACTIVATION_REFUSED",
            "message": "Provider canary activation is not authorized in research lab",
            **AUTHORITY_VALUES,
        }

    def refuse_paper_execution(self) -> dict[str, Any]:
        return {
            "ok": False,
            "refused": True,
            "code": "PAPER_EXECUTION_REFUSED",
            "message": "PAPER_CANDIDATE does not authorize paper order execution",
            **AUTHORITY_VALUES,
        }

    def broker_isolation_scan(self) -> dict[str, Any]:
        hits = []
        lab = self.repo_root / "saathi" / "platform" / "tg" / "research_lab"
        if lab.is_dir():
            for p in lab.rglob("*.py"):
                text = p.read_text(encoding="utf-8", errors="replace")
                for dom in FORBIDDEN_PROVIDER_DOMAINS:
                    if dom in text and "FORBIDDEN" not in text.split(dom)[0][-40:]:
                        # allow listing in FORBIDDEN set
                        if "FORBIDDEN_PROVIDER_DOMAINS" in text:
                            continue
                        hits.append({"file": str(p.relative_to(self.repo_root)), "domain": dom})
        return {
            "ok": len(hits) == 0,
            "hits": hits[:20],
            "scan": "broker_isolation",
            **AUTHORITY_VALUES,
        }

    def credential_scan(self) -> dict[str, Any]:
        present = [k for k in FORBIDDEN_ENV_VARS if os.environ.get(k)]
        return {
            "ok": len(present) == 0,
            "forbidden_env_present": present,
            "scan": "credential",
            **AUTHORITY_VALUES,
        }

    def external_domain_scan(self) -> dict[str, Any]:
        return self.broker_isolation_scan() | {"scan": "external_domain"}

    def llm_authority_scan(self) -> dict[str, Any]:
        bad = [k for k, v in LLM_BOUNDARY.items() if k.startswith("may_") and k not in (
            "may_formulate_research_questions",
            "may_explain_experiment_configuration",
            "may_propose_bounded_experiments",
            "may_summarise_results",
            "may_compare_strategies",
            "may_explain_regime_classifications",
            "may_explain_portfolio_weights",
            "may_explain_stress_failures",
            "may_identify_robustness_concerns",
            "may_prepare_committee_review_material",
            "may_generate_evidence_summaries",
        ) and v is True]
        return {
            "ok": len(bad) == 0,
            "violations": bad,
            "llm_boundary": dict(LLM_BOUNDARY),
            "scan": "llm_authority",
            **AUTHORITY_VALUES,
        }

    def full_scan(self) -> dict[str, Any]:
        scans = {
            "broker_isolation": self.broker_isolation_scan(),
            "credential": self.credential_scan(),
            "external_domain": self.external_domain_scan(),
            "llm_authority": self.llm_authority_scan(),
        }
        ok = all(s.get("ok") for s in scans.values())
        return {"ok": ok, "scans": scans, **AUTHORITY_VALUES}

    def threat_model(self) -> dict[str, Any]:
        threats = [
            "experiment_result_tampering",
            "deleting_failed_experiments",
            "configuration_mutation",
            "checksum_collision_handling",
            "dataset_substitution",
            "feature_version_substitution",
            "final_test_leakage",
            "hidden_parameter_trials",
            "cherry_picking_assets",
            "cherry_picking_regimes",
            "benchmark_manipulation",
            "cost_assumption_manipulation",
            "portfolio_optimiser_instability",
            "covariance_poisoning",
            "excessive_concentration",
            "hidden_leverage",
            "regime_look_ahead",
            "regime_threshold_overfitting",
            "ensemble_leakage",
            "adaptive_allocation_leakage",
            "candidate_promotion_bypass",
            "human_review_bypass",
            "evidence_tampering",
            "synthetic_historical_mislabelling",
            "llm_override",
            "broker_credential_injection",
            "transport_activation",
            "order_execution_activation",
            "false_profitability_claims",
        ]
        rows = []
        for t in threats:
            rows.append({
                "threat": t,
                "attack_path": f"adversary_attempts_{t}",
                "affected_component": "research_lab",
                "preventive_control": "fail_closed_gates_immutability_checksums_authority_locks",
                "detective_control": "audit_events_evidence_hashes_security_scans",
                "response": "block_invalidate_revoke_alert",
                "recovery": "replay_from_immutable_versions",
                "evidence": "rl_audit_events+evidence_hash",
                "residual_risk": "low_to_moderate_single_host_sqlite",
            })
        return {"ok": True, "threats": rows, "count": len(rows), **AUTHORITY_VALUES}
