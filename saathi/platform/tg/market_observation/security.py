"""Security and hard refusals for read-only market observation."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from saathi.platform.tg.market_observation.models import AUTHORITY_VALUES, LLM_BOUNDARY

FORBIDDEN_ENV = frozenset({
    "BINANCE_API_KEY", "BINANCE_API_SECRET",
    "ALPACA_API_KEY", "ALPACA_API_SECRET", "APCA_API_KEY_ID", "APCA_API_SECRET_KEY",
    "IBKR_USERNAME", "IBKR_PASSWORD",
    "BROKER_API_KEY", "BROKER_API_SECRET", "PROVIDER_API_KEY",
    "OAUTH_CLIENT_SECRET", "OAUTH_CLIENT_ID", "TRADING_PASSWORD",
})


class ObservationSecurity:
    def __init__(self, repo_root: Path):
        self.repo_root = repo_root

    def refuse_broker_login(self, target: str = "") -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "BROKER_LOGIN_REFUSED",
            "message": "Broker login is forbidden in read-only market observation",
            "target": target, **AUTHORITY_VALUES,
        }

    def refuse_oauth(self, provider: str = "") -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "OAUTH_REFUSED",
            "message": "OAuth is forbidden in read-only market observation",
            "provider": provider, **AUTHORITY_VALUES,
        }

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "CREDENTIAL_STORAGE_REFUSED",
            "message": "API keys and credentials must not be accepted or stored",
            "value_received": bool(value), "stored": False, **AUTHORITY_VALUES,
        }

    def refuse_order(self) -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "ORDER_REFUSED",
            "message": "Orders are forbidden — observation is validation only, not trading",
            **AUTHORITY_VALUES,
        }

    def refuse_account_access(self) -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "ACCOUNT_ACCESS_REFUSED",
            "message": "Account access is forbidden in read-only observation",
            **AUTHORITY_VALUES,
        }

    def refuse_portfolio_access(self) -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "PORTFOLIO_ACCESS_REFUSED",
            "message": "Live portfolio access is forbidden — use paper simulation surfaces separately",
            **AUTHORITY_VALUES,
        }

    def refuse_balance_access(self) -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "BALANCE_ACCESS_REFUSED",
            "message": "Account balance access is forbidden",
            **AUTHORITY_VALUES,
        }

    def refuse_canary(self) -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "CANARY_ACTIVATION_REFUSED",
            "message": "Provider canary activation is not authorized",
            **AUTHORITY_VALUES,
        }

    def refuse_live_trading(self) -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "LIVE_TRADING_REFUSED",
            "message": "Live trading is not authorized",
            **AUTHORITY_VALUES,
        }

    def refuse_authenticated_live_feed(self) -> dict[str, Any]:
        return {
            "ok": False, "refused": True, "code": "AUTHENTICATED_LIVE_FEED_REFUSED",
            "message": "Authenticated live market data feeds are out of scope; offline fixtures only",
            **AUTHORITY_VALUES,
        }

    def full_scan(self) -> dict[str, Any]:
        env_hits = [k for k in FORBIDDEN_ENV if os.environ.get(k)]
        llm_bad = [
            k for k, v in LLM_BOUNDARY.items()
            if v is True and k.startswith("may_") and k not in (
                "may_summarise_snapshots", "may_explain_quotes",
                "may_map_symbol_metadata", "may_flag_stale_data",
            )
        ]
        # Ensure store claims no credentials
        return {
            "ok": len(env_hits) == 0 and len(llm_bad) == 0,
            "credential_env_hits": env_hits,
            "llm_boundary_violations": llm_bad,
            "llm_boundary": dict(LLM_BOUNDARY),
            "credential_storage_authorized": False,
            **AUTHORITY_VALUES,
        }

    def threat_model(self) -> dict[str, Any]:
        threats = [
            "broker_login_attempt",
            "oauth_initiation",
            "api_key_storage",
            "order_submission",
            "account_balance_read",
            "portfolio_access",
            "authenticated_live_feed",
            "credential_env_injection",
            "false_live_trading_claim",
            "llm_credential_request",
        ]
        return {
            "ok": True,
            "threats": [
                {
                    "threat": t,
                    "preventive_control": "hard_refusal_endpoints_authority_locks_no_credential_schema",
                    "detective_control": "security_scan_audit_events",
                    "response": "refuse_alert",
                    "residual_risk": "low",
                }
                for t in threats
            ],
            "count": len(threats),
            "purpose": "validation_not_trading",
            **AUTHORITY_VALUES,
        }
