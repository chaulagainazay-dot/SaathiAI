"""Security and boundary refusals for paper simulation."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from saathi.platform.tg.paper_simulation.models import AUTHORITY_VALUES, LLM_BOUNDARY

FORBIDDEN_ENV = frozenset({
    "BINANCE_API_KEY", "ALPACA_API_KEY", "APCA_API_KEY_ID", "BROKER_API_KEY",
    "OAUTH_CLIENT_SECRET", "TRADING_PASSWORD",
})


class PaperSimSecurity:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def refuse_broker(self, target: str = "") -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "BROKER_CONNECTIVITY_REFUSED",
            "message": "Paper simulation uses a virtual exchange only — no broker connectivity",
            "target": target, **AUTHORITY_VALUES,
        }

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "CREDENTIAL_PROVISIONING_REFUSED",
            "message": "API keys and credentials are not accepted",
            "value_received": bool(value), **AUTHORITY_VALUES,
        }

    def refuse_real_order(self) -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "REAL_ORDER_ROUTING_REFUSED",
            "message": "Real order routing is not authorized; use virtual exchange paper orders only",
            **AUTHORITY_VALUES,
        }

    def refuse_canary(self) -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "CANARY_ACTIVATION_REFUSED",
            "message": "Provider canary activation is not authorized",
            **AUTHORITY_VALUES,
        }

    def refuse_live(self) -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "LIVE_TRADING_REFUSED",
            "message": "Live trading is not authorized",
            **AUTHORITY_VALUES,
        }

    def full_scan(self) -> dict[str, Any]:
        env_hits = [k for k in FORBIDDEN_ENV if os.environ.get(k)]
        llm_bad = [
            k for k, v in LLM_BOUNDARY.items()
            if v is True and k.startswith("may_") and k not in (
                "may_explain_fills", "may_summarise_portfolio",
                "may_propose_paper_orders", "may_explain_risk_breaches",
            )
        ]
        return {
            "ok": len(env_hits) == 0 and len(llm_bad) == 0,
            "credential_env_hits": env_hits,
            "llm_boundary_violations": llm_bad,
            "llm_boundary": dict(LLM_BOUNDARY),
            **AUTHORITY_VALUES,
        }

    def threat_model(self) -> dict[str, Any]:
        threats = [
            "real_order_routing", "broker_credential_injection", "kill_switch_bypass",
            "margin_policy_bypass", "fill_tampering", "cash_ledger_mutation",
            "session_spoofing", "llm_risk_override", "false_live_claims",
        ]
        return {
            "ok": True,
            "threats": [
                {
                    "threat": t,
                    "preventive_control": "virtual_exchange_only_authority_locks_kill_switch",
                    "detective_control": "audit_fill_audit_security_scan",
                    "residual_risk": "low_single_host_sqlite",
                }
                for t in threats
            ],
            "count": len(threats),
            **AUTHORITY_VALUES,
        }
