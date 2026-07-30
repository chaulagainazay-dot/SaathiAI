"""Security and boundary refusals for portfolio risk intelligence."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from saathi.platform.tg.portfolio_risk.models import AUTHORITY_VALUES, LLM_BOUNDARY

FORBIDDEN_ENV = frozenset({
    "BINANCE_API_KEY", "ALPACA_API_KEY", "APCA_API_KEY_ID", "BROKER_API_KEY",
    "OAUTH_CLIENT_SECRET", "TRADING_PASSWORD",
})


class PortfolioRiskSecurity:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def refuse_broker(self, target: str = "") -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "BROKER_CONNECTIVITY_REFUSED",
                "message": "Portfolio risk intelligence does not connect to brokers",
                "target": target, **AUTHORITY_VALUES}

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "CREDENTIAL_PROVISIONING_REFUSED",
                "message": "Credentials not accepted", "value_received": bool(value), **AUTHORITY_VALUES}

    def refuse_order(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "ORDER_EXECUTION_REFUSED",
                "message": "Order execution not authorized from risk intelligence", **AUTHORITY_VALUES}

    def refuse_canary(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "CANARY_ACTIVATION_REFUSED",
                "message": "Provider canary not authorized", **AUTHORITY_VALUES}

    def refuse_live(self) -> dict[str, Any]:
        return {"ok": False, "refused": True, "code": "LIVE_TRADING_REFUSED",
                "message": "Live trading not authorized", **AUTHORITY_VALUES}

    def full_scan(self) -> dict[str, Any]:
        env_hits = [k for k in FORBIDDEN_ENV if os.environ.get(k)]
        llm_bad = [k for k, v in LLM_BOUNDARY.items() if v is True and k.startswith("may_") and k not in (
            "may_explain_risk", "may_summarise_attribution", "may_propose_rebalance_research",
            "may_draft_committee_notes",
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
            "limit_bypass", "hidden_leverage_in_optimiser", "attribution_tampering",
            "scenario_cherry_picking", "committee_override_by_llm", "false_regulatory_claims",
            "broker_credential_injection", "order_execution_activation",
        ]
        return {
            "ok": True,
            "threats": [{"threat": t, "preventive_control": "authority_locks_fail_closed_limits",
                         "detective_control": "audit_security_scan", "residual_risk": "low"} for t in threats],
            "count": len(threats),
            **AUTHORITY_VALUES,
        }
