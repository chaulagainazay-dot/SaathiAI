"""M304–M311 Read-Only Market Observation service facade.

VALIDATION — NOT TRADING. NO BROKER LOGIN. NO OAUTH. NO CREDENTIALS.
NO ORDERS. NO ACCOUNT / PORTFOLIO / BALANCE ACCESS.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.platform.tg.market_observation.models import (
    AUTHORITY_VALUES,
    ENGINE_VERSION,
    LLM_BOUNDARY,
    MAX_STATE,
    MO_POSTURE,
    SCHEMA_VERSION,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.market_observation.observation import ObservationEngine
from saathi.platform.tg.market_observation.security import ObservationSecurity
from saathi.platform.tg.market_observation.storage import ObservationStore


class MarketObservationService:
    def __init__(self, db_path: str | Path | None = None, repo_root: Path | None = None):
        self.store = ObservationStore(db_path)
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        self.engine = ObservationEngine(self.store)
        self.security = ObservationSecurity(self.repo_root)

    def posture(self) -> dict[str, Any]:
        return {
            **MO_POSTURE,
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M304-M311",
            "terminal_verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "llm_boundary": dict(LLM_BOUNDARY),
            "purpose": "validation_not_trading",
            **AUTHORITY_VALUES,
        }

    def terminal_verdict(self) -> dict[str, Any]:
        return {
            "verdict": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "statements": list(TERMINAL_STATEMENTS),
            "capabilities": {
                "read_only_market_snapshots": True,
                "read_only_quotes": True,
                "read_only_historical_refresh": True,
                "read_only_symbol_metadata": True,
                "read_only_exchange_status": True,
                "read_only_corporate_actions": True,
                "read_only_benchmark_updates": True,
            },
            "forbidden": {
                "broker_login": True,
                "oauth": True,
                "trading": True,
                "orders": True,
                "portfolio_access": True,
                "account_balances": True,
                "api_credential_storage": True,
                "order_execution": True,
            },
            "limitations": [
                "Offline fixture observation by default",
                "Not authenticated live market data",
                "Validation only — not trading",
            ],
            "purpose": "validation_not_trading",
            **AUTHORITY_VALUES,
        }

    # Observation APIs
    def list_symbols(self) -> dict[str, Any]:
        return self.engine.list_symbols()

    def get_symbol(self, symbol: str) -> dict[str, Any]:
        return self.engine.get_symbol(symbol)

    def get_quote(self, symbol: str, **kw: Any) -> dict[str, Any]:
        return self.engine.get_quote(symbol, **kw)

    def list_quotes(self, symbols: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        return self.engine.list_quotes(symbols, **kw)

    def market_snapshot(self, **kw: Any) -> dict[str, Any]:
        return self.engine.market_snapshot(**kw)

    def get_snapshot(self, snapshot_id: str) -> dict[str, Any]:
        return self.engine.get_snapshot(snapshot_id)

    def historical_refresh(self, symbol: str, **kw: Any) -> dict[str, Any]:
        return self.engine.historical_refresh(symbol, **kw)

    def get_history(self, symbol: str, **kw: Any) -> dict[str, Any]:
        return self.engine.get_history(symbol, **kw)

    def list_exchange_status(self) -> dict[str, Any]:
        return self.engine.list_exchange_status()

    def get_exchange_status(self, exchange: str) -> dict[str, Any]:
        return self.engine.get_exchange_status(exchange)

    def list_corporate_actions(self, symbol: str | None = None) -> dict[str, Any]:
        return self.engine.list_corporate_actions(symbol)

    def update_benchmarks(self, **kw: Any) -> dict[str, Any]:
        return self.engine.update_benchmarks(**kw)

    def list_benchmarks(self) -> dict[str, Any]:
        return self.engine.list_benchmarks()

    def bootstrap_demo_pipeline(self) -> dict[str, Any]:
        snap = self.market_snapshot(label="m304_demo", seed=42)
        quotes = self.list_quotes(seed=42)
        symbols = self.list_symbols()
        hist = self.historical_refresh("SPY", n=30, seed=42)
        exchanges = self.list_exchange_status()
        ca = self.list_corporate_actions("AAPL")
        bm = self.update_benchmarks(seed=42)
        return {
            "ok": True,
            "snapshot_id": snap.get("snapshot_id"),
            "quote_count": quotes.get("count"),
            "symbol_count": symbols.get("count"),
            "history_bars": hist.get("bar_count"),
            "exchange_count": exchanges.get("count"),
            "corporate_actions_ok": ca.get("ok") is True,
            "benchmark_count": bm.get("count"),
            "authenticated_live": False,
            "source": "OFFLINE_FIXTURE",
            "purpose": "validation_not_trading",
            **AUTHORITY_VALUES,
        }

    def dashboard(self) -> dict[str, Any]:
        pipe = self.bootstrap_demo_pipeline()
        return {
            "title": "Read-Only Market Observation Control Center",
            "verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "statements": list(TERMINAL_STATEMENTS),
            "overview": {
                "symbol_count": pipe.get("symbol_count"),
                "quote_count": pipe.get("quote_count"),
                "snapshot_id": pipe.get("snapshot_id"),
                "exchange_count": pipe.get("exchange_count"),
                "benchmark_count": pipe.get("benchmark_count"),
                "authenticated_live": False,
                "purpose": "validation_not_trading",
            },
            "labels": {
                "READ_ONLY_OBSERVATION": True,
                "VALIDATION_NOT_TRADING": True,
                "NO_BROKER_LOGIN": True,
                "NO_OAUTH": True,
                "NO_CREDENTIAL_STORAGE": True,
                "NO_ORDERS": True,
                "NO_ACCOUNT_ACCESS": True,
                "NO_LIVE_TRADING": True,
            },
            **AUTHORITY_VALUES,
        }

    def evidence_bundle(self) -> dict[str, Any]:
        return {
            "security": self.security_scan(),
            "threat_model": self.threat_model(),
            "symbols": self.list_symbols(),
            **AUTHORITY_VALUES,
        }

    # Refusals
    def refuse_broker_login(self, target: str = "") -> dict[str, Any]:
        return self.security.refuse_broker_login(target)

    def refuse_oauth(self, provider: str = "") -> dict[str, Any]:
        return self.security.refuse_oauth(provider)

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return self.security.refuse_credentials(value)

    def refuse_order(self) -> dict[str, Any]:
        return self.security.refuse_order()

    def refuse_account_access(self) -> dict[str, Any]:
        return self.security.refuse_account_access()

    def refuse_portfolio_access(self) -> dict[str, Any]:
        return self.security.refuse_portfolio_access()

    def refuse_balance_access(self) -> dict[str, Any]:
        return self.security.refuse_balance_access()

    def refuse_canary(self) -> dict[str, Any]:
        return self.security.refuse_canary()

    def refuse_live_trading(self) -> dict[str, Any]:
        return self.security.refuse_live_trading()

    def refuse_authenticated_live_feed(self) -> dict[str, Any]:
        return self.security.refuse_authenticated_live_feed()

    def security_scan(self) -> dict[str, Any]:
        return self.security.full_scan()

    def threat_model(self) -> dict[str, Any]:
        return self.security.threat_model()

    def certify(self) -> dict[str, Any]:
        from saathi.platform.tg.market_observation.certification import certify_market_observation
        return certify_market_observation(self)


_default: MarketObservationService | None = None


def default_market_observation() -> MarketObservationService:
    global _default
    if _default is None:
        _default = MarketObservationService()
    return _default


def reset_market_observation_for_tests(db_path: str | Path | None = None) -> MarketObservationService:
    global _default
    if _default is not None:
        try:
            _default.store.close()
        except Exception:
            pass
    _default = MarketObservationService(db_path=db_path)
    return _default
