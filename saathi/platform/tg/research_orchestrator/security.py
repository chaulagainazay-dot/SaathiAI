"""Security scans and boundary refusals for research orchestrator."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from saathi.platform.tg.research_orchestrator.models import AUTHORITY_VALUES, LLM_BOUNDARY


FORBIDDEN_ENV = frozenset({
    "BINANCE_API_KEY", "ALPACA_API_KEY", "APCA_API_KEY_ID", "BROKER_API_KEY",
    "OAUTH_CLIENT_SECRET", "TRADING_PASSWORD",
})


class OrchestratorSecurity:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def refuse_broker(self, target: str = "") -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "BROKER_CONNECTIVITY_REFUSED",
                "message": "Orchestrator does not connect to brokers", "target": target, **AUTHORITY_VALUES}

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "CREDENTIAL_PROVISIONING_REFUSED",
                "message": "Credentials not accepted", "value_received": bool(value), **AUTHORITY_VALUES}

    def refuse_order(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "ORDER_EXECUTION_REFUSED",
                "message": "Order execution not authorized", **AUTHORITY_VALUES}

    def refuse_canary(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "CANARY_ACTIVATION_REFUSED",
                "message": "Provider canary not authorized", **AUTHORITY_VALUES}

    def refuse_paper_execution(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "PAPER_EXECUTION_REFUSED",
                "message": "Orchestrator does not activate paper order execution", **AUTHORITY_VALUES}

    def full_scan(self) -> dict[str, Any]:
        env_hits = [k for k in FORBIDDEN_ENV if os.environ.get(k)]
        llm_bad = [k for k, v in LLM_BOUNDARY.items() if v is True and k.startswith("may_") and k not in (
            "may_propose_experiments", "may_summarise_queue", "may_explain_failures",
            "may_draft_hypotheses", "may_prepare_journal_entries",
        )]
        return {
            "ok": len(env_hits) == 0 and len(llm_bad) == 0,
            "credential_env_hits": env_hits,
            "llm_boundary_violations": llm_bad,
            "llm_boundary": dict(LLM_BOUNDARY),
            **AUTHORITY_VALUES,
        }

    def threat_model(self) -> dict[str, Any]:
        threats = [
            "queue_tampering", "priority_injection", "hidden_jobs", "budget_bypass",
            "worker_spoofing", "result_mutation", "retry_amplification", "dependency_cycle",
            "template_poisoning", "session_replay_forgery", "llm_gate_override",
            "broker_credential_injection", "order_execution_activation",
        ]
        rows = [{
            "threat": t,
            "preventive_control": "fail_closed_gates_checksums_immutable_jobs",
            "detective_control": "audit_timeline_security_scan",
            "response": "cancel_invalidate_alert",
            "residual_risk": "low_single_host_sqlite",
        } for t in threats]
        return {"ok": True, "threats": rows, "count": len(rows), **AUTHORITY_VALUES}
