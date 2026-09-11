"""T-NEXT-4 scenario corpus H1–H18 (deterministic performance history)."""
from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from saathi.platform.fund_ledger.service import PortfolioLedgerService
from saathi.platform.fund_ledger.store import FundLedgerStore
from saathi.platform.portfolio_performance.engine import PortfolioPerformanceEngine
from saathi.platform.portfolio_performance.store import PerformanceStore


class PerformanceTests(unittest.TestCase):
    def setUp(self):
        self.ledger = PortfolioLedgerService(FundLedgerStore(":memory:"))
        self.ledger.create_fund(fund_id="fund_perf", opening_cash="100000")
        self.ledger.register_security(security_id="sec_AAA_PAPER", symbol="AAA")
        self.ledger.register_security(security_id="sec_BBB_PAPER", symbol="BBB")
        self.ledger.register_security(security_id="sec_CCC_PAPER", symbol="CCC")
        self.ledger.register_security(security_id="sec_DDD_PAPER", symbol="DDD")
        self.ledger.register_security(security_id="sec_EEE_PAPER", symbol="EEE")
        self.ledger.register_security(security_id="sec_A1_PAPER", symbol="A1")
        self.ledger.register_security(security_id="sec_A2_PAPER", symbol="A2")
        self.store = PerformanceStore(":memory:")
        self.eng = PortfolioPerformanceEngine(
            store=self.store,
            get_ledger_state=lambda f: self.ledger.get_state(f),
            get_recon=lambda f: {"ok": True, "portfolio_status": "HEALTHY"},
            get_events=lambda f: self.ledger.list_events(f),
        )

    def test_h1_cash_only_flat_nav(self):
        st = self.ledger.get_state("fund_perf")
        self.eng.record_observation_from_state("fund_perf", {**st, "state_hash": "h1a"}, ts=1000)
        self.eng.record_observation_from_state("fund_perf", {**st, "state_hash": "h1b"}, ts=2000)
        snap = self.eng.get_performance_snapshot("fund_perf")
        self.assertEqual(snap["performance"]["nav"], "100000.00")
        summary = self.eng.get_period_summary("fund_perf")
        self.assertEqual(summary["status"], "OK")
        self.assertEqual(Decimal(summary["return"]["return_pct"]), Decimal("0"))

    def test_h2_single_profitable_position(self):
        self.ledger.record_fill(
            "fund_perf", side="BUY", security_id="sec_AAA_PAPER", symbol="AAA",
            quantity="10", price="100", fee="0", fill_ref="f1",
        )
        self.ledger.record_mark("fund_perf", security_id="sec_AAA_PAPER", price="110", symbol="AAA")
        st0 = {"nav": "100000", "cash": "100000", "realized_pnl": "0", "unrealized_pnl": "0",
               "positions_value": "0", "total_fees": "0", "positions": [], "event_count": 0, "state_hash": "h2s"}
        self.eng.record_observation_from_state("fund_perf", st0, ts=1000)
        st1 = self.ledger.get_state("fund_perf")
        self.eng.record_observation_from_state("fund_perf", {**st1, "state_hash": "h2e"}, ts=2000)
        c = self.eng.get_position_contribution("fund_perf")
        self.assertEqual(c["kind"], "POSITION_CONTRIBUTION")
        self.assertTrue(c.get("rows"))

    def test_h3_single_losing_position(self):
        self.ledger.record_fill(
            "fund_perf", side="BUY", security_id="sec_BBB_PAPER", symbol="BBB",
            quantity="10", price="100", fee="0", fill_ref="f2",
        )
        self.ledger.record_mark("fund_perf", security_id="sec_BBB_PAPER", price="90", symbol="BBB")
        st = self.ledger.get_state("fund_perf")
        self.assertLess(Decimal(st["unrealized_pnl"]), 0)
        self.eng.record_observation_from_state("fund_perf", {**st, "state_hash": "h3"}, ts=2000)
        pnl = self.eng.get_pnl_history("fund_perf")
        self.assertGreaterEqual(pnl["n"], 1)

    def test_h4_realized_unrealized_split(self):
        self.ledger.record_fill(
            "fund_perf", side="BUY", security_id="sec_CCC_PAPER", symbol="CCC",
            quantity="10", price="50", fee="0", fill_ref="f3",
        )
        self.ledger.record_mark("fund_perf", security_id="sec_CCC_PAPER", price="60", symbol="CCC")
        self.ledger.record_fill(
            "fund_perf", side="SELL", security_id="sec_CCC_PAPER", symbol="CCC",
            quantity="5", price="60", fee="0", fill_ref="f4",
        )
        st = self.ledger.get_state("fund_perf")
        self.assertGreater(Decimal(st["realized_pnl"]), 0)
        self.eng.record_observation_from_state("fund_perf", {**st, "state_hash": "h4"}, ts=2000)
        snap = self.eng.get_performance_snapshot("fund_perf")
        self.assertIsNotNone(snap["performance"]["realized_pnl"])
        self.assertIsNotNone(snap["performance"]["unrealized_pnl"])

    def test_h5_fees(self):
        self.ledger.record_fill(
            "fund_perf", side="BUY", security_id="sec_DDD_PAPER", symbol="DDD",
            quantity="1", price="100", fee="5", fill_ref="f5",
        )
        st = self.ledger.get_state("fund_perf")
        self.assertGreaterEqual(Decimal(st.get("total_fees") or 0), Decimal("5"))
        self.eng.record_observation_from_state("fund_perf", {**st, "state_hash": "h5"}, ts=1000)

    def test_h6_external_deposit_not_return(self):
        st0 = self.ledger.get_state("fund_perf")
        self.eng.record_observation_from_state(
            "fund_perf", {**st0, "state_hash": "h6a"}, ts=1000, external_flow="0"
        )
        self.ledger.record_deposit("fund_perf", amount="10000", actor="test")
        st1 = self.ledger.get_state("fund_perf")
        self.eng.record_observation_from_state(
            "fund_perf", {**st1, "state_hash": "h6b"}, ts=2000, external_flow="10000"
        )
        ret = self.eng.get_period_summary("fund_perf")
        self.assertEqual(ret["status"], "OK")
        self.assertEqual(ret["return"]["methodology"], "TWR")
        r = Decimal(ret["return"]["return_pct"])
        self.assertLess(abs(r), Decimal("0.001"))

    def test_h7_partial_close(self):
        self.ledger.record_fill(
            "fund_perf", side="BUY", security_id="sec_EEE_PAPER", symbol="EEE",
            quantity="10", price="20", fee="0", fill_ref="f7a",
        )
        self.ledger.record_fill(
            "fund_perf", side="SELL", security_id="sec_EEE_PAPER", symbol="EEE",
            quantity="4", price="25", fee="0", fill_ref="f7b",
        )
        st = self.ledger.get_state("fund_perf")
        pos = [p for p in st["positions"] if p.get("symbol") == "EEE"]
        self.assertTrue(pos)
        self.assertEqual(Decimal(pos[0]["quantity"]), Decimal("6"))
        self.eng.record_observation_from_state("fund_perf", {**st, "state_hash": "h7"}, ts=2000)

    def test_h8_multiple_contributors(self):
        for sym, px, mark in [("A1", "10", "12"), ("A2", "20", "18")]:
            self.ledger.record_fill(
                "fund_perf", side="BUY", security_id=f"sec_{sym}_PAPER", symbol=sym,
                quantity="10", price=px, fee="0", fill_ref=f"f8{sym}",
            )
            self.ledger.record_mark("fund_perf", security_id=f"sec_{sym}_PAPER", price=mark, symbol=sym)
        st0 = {"nav": "100000", "cash": "100000", "realized_pnl": "0", "unrealized_pnl": "0",
               "positions_value": "0", "total_fees": "0", "positions": [], "event_count": 0, "state_hash": "h8s"}
        self.eng.record_observation_from_state("fund_perf", st0, ts=1000)
        st1 = self.ledger.get_state("fund_perf")
        self.eng.record_observation_from_state("fund_perf", {**st1, "state_hash": "h8e"}, ts=2000)
        c = self.eng.get_position_contribution("fund_perf")
        self.assertGreaterEqual(len(c.get("rows") or []), 2)
        self.assertEqual(c["kind"], "POSITION_CONTRIBUTION")

    def test_h9_drawdown_recovery(self):
        for i, nav in enumerate(["100", "120", "90", "110"]):
            self.eng.record_observation_from_state(
                "fund_perf",
                {"nav": nav, "cash": nav, "realized_pnl": "0", "unrealized_pnl": "0",
                 "positions_value": "0", "total_fees": "0", "positions": [],
                 "event_count": i, "state_hash": f"h9{i}"},
                ts=1000 + i * 100,
            )
        dd = self.eng.get_drawdown_history("fund_perf")
        self.assertEqual(dd["status"], "OK")
        self.assertGreater(Decimal(dd["summary"]["max_drawdown"]), 0)
        for pt in dd["series"]:
            self.assertGreaterEqual(Decimal(pt["value"]), 0)

    def test_h10_stale_mark(self):
        st = self.ledger.get_state("fund_perf")
        st = {**st, "state_hash": "h10", "mark_stale": True, "positions": [
            {"security_id": "sec_X", "symbol": "X", "market_value": "0", "mark_stale": True}
        ]}
        r = self.eng.record_observation_from_state("fund_perf", st, ts=5000)
        self.assertEqual(r["observation"]["valuation_status"], "INCOMPLETE_VALUATION")
        self.assertEqual(r["observation"]["freshness"], "STALE")

    def test_h11_reconciliation_required(self):
        eng = PortfolioPerformanceEngine(
            store=PerformanceStore(":memory:"),
            get_ledger_state=lambda f: self.ledger.get_state(f),
            get_recon=lambda f: {"ok": False, "portfolio_status": "RECONCILIATION_REQUIRED"},
        )
        st = self.ledger.get_state("fund_perf")
        eng.record_observation_from_state("fund_perf", {**st, "state_hash": "h11a"}, ts=1)
        eng.record_observation_from_state("fund_perf", {**st, "state_hash": "h11b", "nav": "100001"}, ts=2)
        snap = eng.get_performance_snapshot("fund_perf")
        self.assertEqual(snap["performance"]["trust"], "RECONCILIATION_REQUIRED")
        self.assertEqual(snap["performance"]["reconciliation"], "RECONCILIATION_REQUIRED")

    def test_h12_restart_replay(self):
        with tempfile.TemporaryDirectory() as td:
            path = str(Path(td) / "perf.db")
            s1 = PerformanceStore(path)
            e1 = PortfolioPerformanceEngine(store=s1)
            for i, nav in enumerate(["100000", "101000", "102000"]):
                e1.record_observation_from_state(
                    "fund_r",
                    {"nav": nav, "cash": nav, "realized_pnl": "0", "unrealized_pnl": str(i * 1000),
                     "positions_value": "0", "total_fees": "0", "positions": [],
                     "event_count": i, "state_hash": f"rp{i}"},
                    ts=1000 + i,
                )
            hist1 = e1.get_nav_history("fund_r")
            s2 = PerformanceStore(path)
            e2 = PortfolioPerformanceEngine(store=s2)
            hist2 = e2.get_nav_history("fund_r")
            self.assertEqual(hist1["series"], hist2["series"])
            ret1 = e1.get_period_summary("fund_r")
            ret2 = e2.get_period_summary("fund_r")
            self.assertEqual(ret1["return"]["return_pct"], ret2["return"]["return_pct"])

    def test_h13_duplicate_snapshot(self):
        st = {"nav": "100000", "cash": "100000", "realized_pnl": "0", "unrealized_pnl": "0",
              "positions_value": "0", "total_fees": "0", "positions": [], "event_count": 1, "state_hash": "dup1"}
        a = self.eng.record_observation_from_state("fund_perf", st, ts=10)
        b = self.eng.record_observation_from_state("fund_perf", st, ts=11)
        self.assertTrue(a.get("inserted"))
        self.assertTrue(b.get("duplicate") or not b.get("inserted"))
        self.assertEqual(self.store.count("fund_perf"), 1)

    def test_h14_correction_rebuild(self):
        self.eng.record_observation_from_state(
            "fund_perf",
            {"nav": "100000", "cash": "100000", "realized_pnl": "0", "unrealized_pnl": "0",
             "positions_value": "0", "total_fees": "0", "positions": [], "event_count": 1, "state_hash": "c1"},
            ts=1,
        )
        self.eng.record_observation_from_state(
            "fund_perf",
            {"nav": "99000", "cash": "99000", "realized_pnl": "-1000", "unrealized_pnl": "0",
             "positions_value": "0", "total_fees": "0", "positions": [], "event_count": 2, "state_hash": "c2"},
            ts=2,
        )
        self.eng.record_observation_from_state(
            "fund_perf",
            {"nav": "99500", "cash": "99500", "realized_pnl": "-500", "unrealized_pnl": "0",
             "positions_value": "0", "total_fees": "0", "positions": [], "event_count": 3, "state_hash": "c3"},
            ts=3,
        )
        hist = self.eng.get_nav_history("fund_perf")
        self.assertEqual(hist["series"][-1]["value"], "99500.00")

    def test_h15_benchmark_unavailable(self):
        st = self.ledger.get_state("fund_perf")
        self.eng.record_observation_from_state("fund_perf", {**st, "state_hash": "bm1"}, ts=1)
        self.eng.record_observation_from_state("fund_perf", {**st, "state_hash": "bm2", "nav": "100001"}, ts=2)
        snap = self.eng.get_performance_snapshot("fund_perf")
        self.assertEqual(snap["performance"]["benchmark_status"], "BENCHMARK_UNAVAILABLE")
        self.assertIsNone(snap["performance"]["excess_return"])
        self.assertEqual(snap["performance"]["alpha_beta_status"], "DEFER")

    def test_h16_qualified_benchmark_boundary(self):
        snap = self.eng.get_performance_snapshot("fund_perf")
        self.assertEqual(snap["performance"]["benchmark_status"], "BENCHMARK_UNAVAILABLE")

    def test_h17_insufficient_volatility_sample(self):
        for i in range(5):
            self.eng.record_observation_from_state(
                "fund_perf",
                {"nav": str(100000 + i * 10), "cash": "100000", "realized_pnl": "0", "unrealized_pnl": str(i * 10),
                 "positions_value": "0", "total_fees": "0", "positions": [], "event_count": i, "state_hash": f"v{i}"},
                ts=1000 + i,
            )
        snap = self.eng.get_performance_snapshot("fund_perf")
        self.assertEqual(snap["performance"]["volatility_status"], "DATA_INSUFFICIENT")
        self.assertEqual(snap["performance"]["sharpe_status"], "DATA_INSUFFICIENT")

    def test_h18_decision_history_association(self):
        self.eng.link_decision("fund_perf", "proposal", ref_id="pprop_1", note="READY_FOR_APPROVAL")
        st = self.ledger.get_state("fund_perf")
        self.eng.record_observation_from_state("fund_perf", {**st, "state_hash": "d1"}, ts=5000)
        hist = self.eng.get_decision_history("fund_perf")
        self.assertTrue(hist["events"])
        self.assertFalse(hist["causal_claim"])
        self.assertIn("ASSOCIATED_WITH", hist["wording"])

    def test_command_contract_no_execution(self):
        st = self.ledger.get_state("fund_perf")
        self.eng.record_observation_from_state("fund_perf", {**st, "state_hash": "cc1"}, ts=1)
        self.eng.record_observation_from_state("fund_perf", {**st, "state_hash": "cc2", "nav": "100100"}, ts=2)
        c = self.eng.command_performance_contract("fund_perf")
        self.assertEqual(c["paper_performance"]["mode"], "PAPER")
        self.assertEqual(c["paper_performance"]["live_execution"], "UNAVAILABLE")
        self.assertEqual(c["paper_performance"]["source"], "portfolio_performance_engine")

    def test_authority_no_ledger_mutation(self):
        before = self.ledger.get_state("fund_perf")
        self.eng.record_observation_from_state("fund_perf", {**before, "state_hash": "auth1"}, ts=1)
        after = self.ledger.get_state("fund_perf")
        self.assertEqual(before["event_count"], after["event_count"])
        self.assertEqual(before["nav"], after["nav"])


if __name__ == "__main__":
    unittest.main()
