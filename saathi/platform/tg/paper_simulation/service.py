"""M288–M295 Institutional Paper Trading Simulation service facade.

VIRTUAL EXCHANGE ONLY. NO BROKER. NO API KEYS. NO LIVE TRADING.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.platform.tg.paper_simulation.calendar import TradingCalendar
from saathi.platform.tg.paper_simulation.corporate_actions import CorporateActionEngine
from saathi.platform.tg.paper_simulation.errors import PaperSimError
from saathi.platform.tg.paper_simulation.exchange import VirtualExchange
from saathi.platform.tg.paper_simulation.journal import TradeJournal
from saathi.platform.tg.paper_simulation.ledger import PortfolioLedger
from saathi.platform.tg.paper_simulation.matching import MatchingEngine
from saathi.platform.tg.paper_simulation.models import (
    AUTHORITY_VALUES,
    ENGINE_VERSION,
    LLM_BOUNDARY,
    MAX_STATE,
    PS_POSTURE,
    SCHEMA_VERSION,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.paper_simulation.risk import RiskMonitor
from saathi.platform.tg.paper_simulation.security import PaperSimSecurity
from saathi.platform.tg.paper_simulation.storage import PaperSimStore


class PaperSimulationService:
    def __init__(self, db_path: str | Path | None = None, repo_root: Path | None = None):
        self.store = PaperSimStore(db_path)
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        self.exchange = VirtualExchange(self.store)
        self.ledger = PortfolioLedger(self.store)
        self.risk = RiskMonitor(self.store, self.ledger)
        self.matching = MatchingEngine(self.store, self.exchange, self.ledger, self.risk)
        self.calendar = TradingCalendar()
        self.corp_actions = CorporateActionEngine(self.store, self.ledger)
        self.journal = TradeJournal(self.store)
        self.security = PaperSimSecurity(self.repo_root)

    def posture(self) -> dict[str, Any]:
        return {
            **PS_POSTURE,
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M288-M295",
            "terminal_verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "llm_boundary": dict(LLM_BOUNDARY),
            **AUTHORITY_VALUES,
        }

    def terminal_verdict(self) -> dict[str, Any]:
        return {
            "verdict": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "statements": list(TERMINAL_STATEMENTS),
            "capabilities": {
                "virtual_exchange": True,
                "matching_engine": True,
                "order_book": True,
                "market_orders": True,
                "limit_orders": True,
                "stop_orders": True,
                "partial_fills": True,
                "slippage_engine": True,
                "liquidity_model": True,
                "latency_simulation": True,
                "exchange_sessions": True,
                "portfolio_ledger": True,
                "position_manager": True,
                "cash_ledger": True,
                "margin_research_only": True,
                "corporate_action_replay": True,
                "dividend_handling": True,
                "trading_calendar": True,
                "trade_journal": True,
                "fill_audit": True,
                "risk_monitor": True,
                "kill_switch": True,
                "paper_portfolio_dashboard": True,
            },
            "limitations": [
                "Not a real exchange or broker",
                "Simulated fills only",
                "No real market data dependency required",
                "Margin is research-only",
            ],
            **AUTHORITY_VALUES,
        }

    # Portfolio
    def create_portfolio(self, name: str = "Paper Core", **kw: Any) -> dict[str, Any]:
        return self.ledger.create_portfolio(name, **kw)

    def get_portfolio(self, portfolio_id: str) -> dict[str, Any]:
        return self.ledger.get_portfolio(portfolio_id)

    def list_portfolios(self) -> dict[str, Any]:
        return self.ledger.list_portfolios()

    def cash_ledger(self, portfolio_id: str) -> dict[str, Any]:
        return self.ledger.cash_history(portfolio_id)

    # Orders
    def submit_order(self, portfolio_id: str, symbol: str, side: str, order_type: str, quantity: float, **kw: Any) -> dict[str, Any]:
        return self.matching.submit_order(portfolio_id, symbol, side, order_type, quantity, **kw)

    def cancel_order(self, order_id: str, **kw: Any) -> dict[str, Any]:
        return self.matching.cancel_order(order_id, **kw)

    def list_orders(self, portfolio_id: str, status: str | None = None) -> dict[str, Any]:
        return self.matching.list_orders(portfolio_id, status)

    def list_fills(self, portfolio_id: str) -> dict[str, Any]:
        return self.matching.list_fills(portfolio_id)

    def process_symbol(self, symbol: str) -> dict[str, Any]:
        return self.matching.process_tick(symbol)

    # Exchange
    def exchange_status(self) -> dict[str, Any]:
        return self.exchange.status()

    def order_book(self, symbol: str) -> dict[str, Any]:
        return self.exchange.order_book(symbol)

    def publish_tick(self, symbol: str, bid: float, ask: float, last: float, **kw: Any) -> dict[str, Any]:
        tick = self.exchange.publish_tick(symbol, bid, ask, last, **kw)
        self.matching.process_tick(symbol)
        # mark portfolio positions
        for pf in self.list_portfolios().get("portfolios") or []:
            self.ledger.mark_positions(pf["portfolio_id"], {symbol.upper(): last})
        return tick

    def set_session(self, symbol: str, state: str) -> dict[str, Any]:
        return self.exchange.set_session(symbol, state)

    # Risk
    def activate_kill_switch(self, reason: str, **kw: Any) -> dict[str, Any]:
        return self.risk.activate_kill_switch(reason, **kw)

    def deactivate_kill_switch(self, kill_switch_id: str, **kw: Any) -> dict[str, Any]:
        return self.risk.deactivate_kill_switch(kill_switch_id, **kw)

    def kill_switch_status(self) -> dict[str, Any]:
        return self.risk.kill_switch_status()

    def risk_events(self, portfolio_id: str) -> dict[str, Any]:
        return self.risk.risk_events(portfolio_id)

    # Calendar / CA / journal
    def trading_calendar(self, symbol: str | None = None) -> dict[str, Any]:
        if symbol:
            return self.calendar.for_symbol(symbol)
        return self.calendar.overview()

    def register_corporate_action(self, **kw: Any) -> dict[str, Any]:
        return self.corp_actions.register(**kw)

    def apply_corporate_action(self, ca_id: str, portfolio_id: str) -> dict[str, Any]:
        return self.corp_actions.apply(ca_id, portfolio_id)

    def list_corporate_actions(self, symbol: str | None = None) -> dict[str, Any]:
        return self.corp_actions.list(symbol)

    def write_journal(self, title: str, body: str, **kw: Any) -> dict[str, Any]:
        return self.journal.write(title, body, **kw)

    def list_journal(self) -> dict[str, Any]:
        return self.journal.list()

    # Bootstrap / dashboard
    def bootstrap_demo_pipeline(self) -> dict[str, Any]:
        pf = self.create_portfolio("M288 Demo Portfolio", initial_cash=100_000.0)
        pid = pf["portfolio_id"]
        self.write_journal("Demo open", f"Portfolio {pid} created", kind="session", refs={"portfolio_id": pid})

        # Market buy SPY
        mkt = self.submit_order(pid, "SPY", "BUY", "MARKET", 10)
        market_fill = bool((mkt.get("match") or {}).get("filled"))

        # Limit buy AAPL below market (resting)
        tick = self.exchange.latest_tick("AAPL")
        limit_px = float(tick["bid"]) - 5.0 if tick else 180.0
        lim = self.submit_order(pid, "AAPL", "BUY", "LIMIT", 5, limit_price=limit_px, tif="GTC")

        # Publish better tick to fill limit
        self.publish_tick("AAPL", limit_px - 0.05, limit_px, limit_px, volume=2_000_000)

        # Stop sell on SPY
        spy = self.exchange.latest_tick("SPY")
        stop_px = float(spy["last"]) - 50 if spy else 400.0
        self.submit_order(pid, "SPY", "SELL", "STOP", 2, stop_price=stop_px)

        book = self.order_book("SPY")
        fills = self.list_fills(pid)
        cash = self.cash_ledger(pid)
        overview = self.get_portfolio(pid)

        # Dividend demo
        ca = self.register_corporate_action(
            symbol="SPY", action_type="DIVIDEND", ex_date="2026-07-01", amount=0.5,
        )
        self.apply_corporate_action(ca["ca_id"], pid)

        # Kill switch activate then deactivate for demo evidence
        ks = self.activate_kill_switch("demo halt", scope="PORTFOLIO", scope_ref=pid, actor="operator")
        ks_active = self.kill_switch_status().get("active") is True
        self.deactivate_kill_switch(ks["kill_switch_id"], actor="operator")

        return {
            "ok": True,
            "portfolio_id": pid,
            "market_fill": market_fill,
            "market_order_id": (mkt.get("order") or {}).get("order_id"),
            "limit_order_id": (lim.get("order") or {}).get("order_id"),
            "order_book": book,
            "fill_count": fills.get("count"),
            "cash_entries": cash.get("count"),
            "portfolio": overview,
            "kill_switch_active": ks_active,
            "corporate_action_id": ca["ca_id"],
            **AUTHORITY_VALUES,
        }

    def dashboard(self) -> dict[str, Any]:
        pfs = self.list_portfolios()
        first = (pfs.get("portfolios") or [None])[0]
        overview = self.get_portfolio(first["portfolio_id"]) if first else None
        return {
            "title": "Institutional Paper Trading Simulation Control Center",
            "verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "statements": list(TERMINAL_STATEMENTS),
            "exchange": self.exchange_status(),
            "portfolios": pfs,
            "portfolio_overview": overview,
            "kill_switch": self.kill_switch_status(),
            "calendar": self.trading_calendar(),
            "labels": {
                "PAPER_SIMULATION_ONLY": True,
                "VIRTUAL_EXCHANGE_ONLY": True,
                "NO_BROKER_CONNECTIVITY": True,
                "NO_REAL_ORDER_ROUTING": True,
                "NO_LIVE_TRADING": True,
            },
            **AUTHORITY_VALUES,
        }

    def evidence_bundle(self) -> dict[str, Any]:
        return {
            "exchange": self.exchange_status(),
            "portfolios": self.list_portfolios(),
            "security": self.security_scan(),
            "threat_model": self.threat_model(),
            **AUTHORITY_VALUES,
        }

    def refuse_broker(self, target: str = "") -> dict[str, Any]:
        return self.security.refuse_broker(target)

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return self.security.refuse_credentials(value)

    def refuse_real_order(self) -> dict[str, Any]:
        return self.security.refuse_real_order()

    def refuse_canary(self) -> dict[str, Any]:
        return self.security.refuse_canary()

    def refuse_live(self) -> dict[str, Any]:
        return self.security.refuse_live()

    def security_scan(self) -> dict[str, Any]:
        return self.security.full_scan()

    def threat_model(self) -> dict[str, Any]:
        return self.security.threat_model()

    def certify(self) -> dict[str, Any]:
        from saathi.platform.tg.paper_simulation.certification import certify_paper_simulation
        return certify_paper_simulation(self)


_default: PaperSimulationService | None = None


def default_paper_simulation() -> PaperSimulationService:
    global _default
    if _default is None:
        _default = PaperSimulationService()
    return _default


def reset_paper_simulation_for_tests(db_path: str | Path | None = None) -> PaperSimulationService:
    global _default
    if _default is not None:
        try:
            _default.store.close()
        except Exception:
            pass
    _default = PaperSimulationService(db_path=db_path)
    return _default
