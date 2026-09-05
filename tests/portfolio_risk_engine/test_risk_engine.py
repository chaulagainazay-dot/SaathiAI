"""T-NEXT-2 deterministic risk engine tests (zero LLM)."""
from __future__ import annotations

import time
import unittest
from decimal import Decimal

from saathi.platform.fund_ledger.service import PortfolioLedgerService
from saathi.platform.fund_ledger.store import FundLedgerStore
from saathi.platform.portfolio_risk_engine.budget import RiskBudget, PAPER_BUDGET_V1
from saathi.platform.portfolio_risk_engine.engine import PortfolioRiskEngine
from saathi.platform.portfolio_risk_engine.history import NavHistoryStore
from saathi.platform.portfolio_risk_engine.models import (
    REASON_DAILY_LOSS_LIMIT_EXCEEDED,
    REASON_GROSS_EXPOSURE_LIMIT,
    REASON_LEDGER_UNRECONCILED,
    REASON_MAX_DRAWDOWN_EXCEEDED,
    REASON_MAX_POSITION_WEIGHT_EXCEEDED,
    REASON_MIN_CASH_BUFFER_BREACH,
    REASON_STALE_MARKET_DATA,
    RiskResult,
    RiskState,
    TradeProposal,
)
from saathi.platform.portfolio_risk_engine.sizing import size_stop_risk
from saathi.platform.portfolio_risk_engine.tg_compose import compose_guardian_with_risk
from saathi.platform.trading_guardian import TradingGuardian, RiskLimits
from saathi.platform.trading_models import (
    Account,
    DataQuality,
    Environment,
    MarketState,
    OrderIntent,
    OrderSide,
    OrderType,
    OrderState,
    D,
)


def _ledger_with_cash(cash="100000"):
    svc = PortfolioLedgerService(FundLedgerStore(":memory:"))
    svc.create_fund(fund_id="fund_r", opening_cash=cash)
    return svc


class RiskEngineTests(unittest.TestCase):
    def setUp(self):
        self.ledger = _ledger_with_cash()
        self.hist = NavHistoryStore()
        self.engine = PortfolioRiskEngine(
            budget=PAPER_BUDGET_V1,
            history=self.hist,
            get_ledger_state=lambda fid: self.ledger.get_state(fid),
            get_recon_status=lambda fid: {"ok": True, "portfolio_status": "HEALTHY"},
        )

    def test_healthy_cash_only(self):
        d = self.engine.evaluate_current_state("fund_r")
        self.assertEqual(d.result, RiskResult.ALLOW)
        self.assertEqual(d.risk_state, RiskState.HEALTHY)
        self.assertEqual(d.metrics["nav"], "100000.00")

    def test_max_position_breach_on_trade(self):
        # 15% max → 20k of 100k ok for 15k? 20% of NAV is breach
        prop = TradeProposal(symbol="AAA", side="BUY", quantity=Decimal("200"), price=Decimal("100"))
        # notional 20000 = 20% > 15%
        d = self.engine.evaluate_proposed_trade("fund_r", prop)
        self.assertEqual(d.result, RiskResult.BLOCK)
        self.assertIn(REASON_MAX_POSITION_WEIGHT_EXCEEDED, d.reason_codes)

    def test_cash_buffer_breach(self):
        # buy almost all cash leaving < 5%
        prop = TradeProposal(symbol="AAA", side="BUY", quantity=Decimal("960"), price=Decimal("100"))
        # 96000 notional → cash 4000 = 4% < 5%
        d = self.engine.evaluate_proposed_trade("fund_r", prop)
        self.assertEqual(d.result, RiskResult.BLOCK)
        self.assertTrue(
            REASON_MIN_CASH_BUFFER_BREACH in d.reason_codes
            or REASON_MAX_POSITION_WEIGHT_EXCEEDED in d.reason_codes
            or REASON_GROSS_EXPOSURE_LIMIT in d.reason_codes
        )

    def test_gross_exposure_limit(self):
        # budget max gross 1.0 — buy 100% still ok at 95% with cash buffer hard
        budget = RiskBudget(max_gross_exposure=Decimal("0.50"), max_position_weight=Decimal("0.50"), min_cash_buffer=Decimal("0"))
        eng = PortfolioRiskEngine(
            budget=budget,
            history=NavHistoryStore(),
            get_ledger_state=lambda fid: self.ledger.get_state(fid),
            get_recon_status=lambda fid: {"ok": True, "portfolio_status": "HEALTHY"},
        )
        prop = TradeProposal(symbol="AAA", side="BUY", quantity=Decimal("600"), price=Decimal("100"))
        d = eng.evaluate_proposed_trade("fund_r", prop)
        self.assertEqual(d.result, RiskResult.BLOCK)
        self.assertIn(REASON_GROSS_EXPOSURE_LIMIT, d.reason_codes)

    def test_drawdown_breach(self):
        # seed history peak then lower NAV via loss mark
        self.ledger.register_security(security_id="sec_AAA_PAPER", symbol="AAA")
        self.ledger.record_fill(
            "fund_r", side="BUY", security_id="sec_AAA_PAPER", symbol="AAA",
            quantity="100", price="100", fee="0", fill_ref="b1",
        )
        self.ledger.record_mark("fund_r", security_id="sec_AAA_PAPER", price="100", symbol="AAA")
        t0 = time.time() - 1000
        self.hist.record_nav("fund_r", "100000", ts=t0)
        # mark down 20% on position: NAV drops
        self.ledger.record_mark("fund_r", security_id="sec_AAA_PAPER", price="20", symbol="AAA", ts=t0 + 10)
        # force history peak high and current low
        self.hist.record_nav("fund_r", "100000", ts=t0 + 5)
        state = self.ledger.get_state("fund_r")
        self.hist.record_nav("fund_r", state["nav"], ts=t0 + 20)
        budget = RiskBudget(max_drawdown=Decimal("0.05"), max_position_weight=Decimal("0.50"), min_cash_buffer=Decimal("0"))
        eng = PortfolioRiskEngine(
            budget=budget,
            history=self.hist,
            get_ledger_state=lambda fid: self.ledger.get_state(fid),
            get_recon_status=lambda fid: {"ok": True, "portfolio_status": "HEALTHY"},
        )
        d = eng.evaluate_current_state("fund_r", now=t0 + 30, record_history=False)
        self.assertEqual(d.result, RiskResult.BLOCK)
        self.assertIn(REASON_MAX_DRAWDOWN_EXCEEDED, d.reason_codes)

    def test_daily_loss_breach(self):
        t0 = time.time()
        day = t0 - (t0 % 86400)  # rough; engine uses UTC day start
        self.hist.record_nav("fund_r", "100000", ts=day + 1)
        self.hist.record_nav("fund_r", "90000", ts=day + 100)
        # override state nav
        state = self.ledger.get_state("fund_r")
        state = {**state, "nav": "90000.00", "cash": "90000.00"}
        budget = RiskBudget(max_daily_loss=Decimal("0.05"), min_cash_buffer=Decimal("0"))
        eng = PortfolioRiskEngine(
            budget=budget,
            history=self.hist,
            get_ledger_state=lambda fid: state,
            get_recon_status=lambda fid: {"ok": True, "portfolio_status": "HEALTHY"},
        )
        d = eng.evaluate_current_state("fund_r", ledger_state=state, now=day + 200, record_history=False)
        self.assertEqual(d.result, RiskResult.BLOCK)
        self.assertIn(REASON_DAILY_LOSS_LIMIT_EXCEEDED, d.reason_codes)

    def test_ledger_unreconciled_blocks(self):
        eng = PortfolioRiskEngine(
            get_ledger_state=lambda fid: self.ledger.get_state(fid),
            get_recon_status=lambda fid: {"ok": False, "portfolio_status": "RECONCILIATION_REQUIRED"},
        )
        d = eng.evaluate_current_state("fund_r")
        self.assertEqual(d.result, RiskResult.BLOCK)
        self.assertEqual(d.risk_state, RiskState.RECONCILIATION_REQUIRED)
        self.assertIn(REASON_LEDGER_UNRECONCILED, d.reason_codes)

    def test_stale_price_blocks(self):
        self.ledger.register_security(security_id="sec_AAA_PAPER", symbol="AAA")
        self.ledger.record_fill(
            "fund_r", side="BUY", security_id="sec_AAA_PAPER", symbol="AAA",
            quantity="10", price="100", fee="0", fill_ref="b1",
        )
        self.ledger.record_mark(
            "fund_r", security_id="sec_AAA_PAPER", price="100", symbol="AAA",
            max_age_seconds=10, ts=1_000_000.0,
        )
        d = self.engine.evaluate_current_state("fund_r", now=1_000_000.0 + 100)
        self.assertEqual(d.result, RiskResult.BLOCK)
        self.assertIn(REASON_STALE_MARKET_DATA, d.reason_codes)

    def test_missing_nav(self):
        eng = PortfolioRiskEngine(get_ledger_state=lambda fid: (_ for _ in ()).throw(RuntimeError("x")))
        d = eng.evaluate_current_state("missing")
        self.assertEqual(d.result, RiskResult.DATA_INSUFFICIENT)

    def test_stop_sizing(self):
        r = size_stop_risk(
            nav=Decimal("100000"),
            entry_price=Decimal("100"),
            stop_price=Decimal("95"),
            budget=PAPER_BUDGET_V1,
        )
        self.assertTrue(r["ok"])
        # risk capital 1% = 1000; risk/share 5 → qty 200, then capped by max_trade_notional 10k → qty 100
        self.assertEqual(r["quantity"], "100.000000")

    def test_invalid_stop(self):
        r = size_stop_risk(
            nav=Decimal("100000"),
            entry_price=Decimal("100"),
            stop_price=Decimal("105"),
            budget=PAPER_BUDGET_V1,
        )
        self.assertFalse(r["ok"])

    def test_stress_scenarios(self):
        self.ledger.register_security(security_id="sec_AAA_PAPER", symbol="AAA")
        self.ledger.record_fill(
            "fund_r", side="BUY", security_id="sec_AAA_PAPER", symbol="AAA",
            quantity="100", price="100", fee="0", fill_ref="b1",
        )
        self.ledger.record_mark("fund_r", security_id="sec_AAA_PAPER", price="100", symbol="AAA")
        results = self.engine.run_stress("fund_r")
        self.assertGreaterEqual(len(results), 4)
        m5 = next(r for r in results if r["scenario"]["scenario_id"] == "mkt_m5")
        self.assertLess(Decimal(m5["projected_nav"]), Decimal("100000"))

    def test_reason_codes_and_budget_version(self):
        d = self.engine.evaluate_current_state("fund_r")
        self.assertEqual(d.budget_version, PAPER_BUDGET_V1.version)
        snap = self.engine.get_risk_snapshot("fund_r")
        self.assertIn("risk_budget_bars", snap)
        self.assertEqual(snap["mode"] if "mode" in snap else "PAPER", snap.get("mode", "PAPER"))

    def test_command_contract(self):
        c = self.engine.command_risk_contract("fund_r")
        self.assertEqual(c["label"], "PAPER RISK")
        self.assertEqual(c["live_execution"], "UNAVAILABLE")
        self.assertIn("risk_status", c)

    def test_duplicate_evaluation_stable_metrics(self):
        a = self.engine.evaluate_current_state("fund_r", record_history=False)
        b = self.engine.evaluate_current_state("fund_r", record_history=False)
        self.assertEqual(a.metrics["nav"], b.metrics["nav"])
        self.assertEqual(a.result, b.result)

    def test_tg_composition_blocks_on_risk(self):
        g = TradingGuardian(limits=RiskLimits(max_order_notional=Decimal("1000000")))
        intent = OrderIntent(
            intent_id="i1",
            org_id="o",
            workspace_id="w",
            account_id="a",
            environment=Environment.PAPER,
            symbol="AAA",
            side=OrderSide.BUY,
            order_type=OrderType.MARKET,
            quantity=Decimal("500"),
            state=OrderState.DRAFT,
        )
        acct = Account(account_id="a", environment=Environment.PAPER, cash=Decimal("100000"), currency="USD")
        # large buy should risk-block
        out = compose_guardian_with_risk(
            g,
            self.engine,
            intent,
            account=acct,
            ref_price=Decimal("100"),
            price_quality=DataQuality.VALID,
            market_state=MarketState.OPEN,
            fund_id="fund_r",
        )
        self.assertFalse(out["allowed"])
        self.assertIn("portfolio_risk_engine", [c["check"] for c in out["checks"]])
        self.assertFalse(out.get("authorizes_execution", True))

    def test_no_ledger_mutation_methods(self):
        self.assertFalse(hasattr(self.engine, "record_fill"))
        self.assertFalse(hasattr(self.engine, "set_nav"))


if __name__ == "__main__":
    unittest.main()
