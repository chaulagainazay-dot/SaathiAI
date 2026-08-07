"""T-NEXT-1 scenario corpus S1–S10 + invariants (zero LLM)."""
from __future__ import annotations

import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from saathi.platform.fund_ledger.money import Money, MoneyError, D, q_money
from saathi.platform.fund_ledger.reducer import LedgerError, reduce_events, state_hash
from saathi.platform.fund_ledger.service import PortfolioLedgerService
from saathi.platform.fund_ledger.store import FundLedgerStore
from saathi.platform.fund_ledger.paper_bridge import post_paper_fill_to_ledger


class MoneyTests(unittest.TestCase):
    def test_no_float(self):
        with self.assertRaises(MoneyError):
            D(0.1)  # type: ignore[arg-type]

    def test_currency_mix_rejected(self):
        with self.assertRaises(MoneyError):
            Money("1", "USD") + Money("1", "NPR")


class ScenarioCorpus(unittest.TestCase):
    def setUp(self):
        self.svc = PortfolioLedgerService(FundLedgerStore(":memory:"))
        self.fund = self.svc.create_fund(fund_id="fund_test", opening_cash="100000")
        self.sec = self.svc.register_security(security_id="sec_AAA", symbol="AAA")

    def test_s1_cash_only(self):
        s = self.svc.get_state("fund_test")
        self.assertEqual(s["cash"], "100000.00")
        self.assertEqual(s["nav"], "100000.00")
        self.assertEqual(s["positions"], [])
        self.assertTrue(s["invariants_ok"])

    def test_s2_single_profitable_long(self):
        self.svc.record_fill(
            "fund_test",
            side="BUY",
            security_id="sec_AAA",
            symbol="AAA",
            quantity="10",
            price="100",
            fee="1",
            fill_ref="f1",
        )
        self.svc.record_mark("fund_test", security_id="sec_AAA", price="110", symbol="AAA")
        self.svc.record_fill(
            "fund_test",
            side="SELL",
            security_id="sec_AAA",
            symbol="AAA",
            quantity="10",
            price="110",
            fee="1",
            fill_ref="f2",
        )
        s = self.svc.get_state("fund_test")
        self.assertEqual(s["positions"], [])
        # buy cost with fee: 1000+1; sell proceeds 1100-1=1099; realized ~ (110 - 100.1)*10
        self.assertGreater(D(s["realized_pnl"]), Decimal("0"))
        self.assertTrue(s["invariants_ok"])

    def test_s3_single_losing_long(self):
        self.svc.record_fill(
            "fund_test",
            side="BUY",
            security_id="sec_AAA",
            symbol="AAA",
            quantity="10",
            price="100",
            fee="0",
            fill_ref="f1",
        )
        self.svc.record_fill(
            "fund_test",
            side="SELL",
            security_id="sec_AAA",
            symbol="AAA",
            quantity="10",
            price="90",
            fee="0",
            fill_ref="f2",
        )
        s = self.svc.get_state("fund_test")
        self.assertEqual(D(s["realized_pnl"]), Decimal("-100.00"))
        self.assertEqual(s["cash"], "99900.00")

    def test_s4_multiple_lots_fifo(self):
        self.svc.record_fill(
            "fund_test", side="BUY", security_id="sec_AAA", symbol="AAA",
            quantity="10", price="100", fee="0", fill_ref="b1",
        )
        self.svc.record_fill(
            "fund_test", side="BUY", security_id="sec_AAA", symbol="AAA",
            quantity="10", price="120", fee="0", fill_ref="b2",
        )
        # sell 10 should close first lot @100 → realized 10*(130-100)=300 if sell 130
        self.svc.record_fill(
            "fund_test", side="SELL", security_id="sec_AAA", symbol="AAA",
            quantity="10", price="130", fee="0", fill_ref="s1",
        )
        s = self.svc.get_state("fund_test")
        self.assertEqual(D(s["realized_pnl"]), Decimal("300.00"))
        lots = self.svc.get_lots("fund_test")
        self.assertEqual(len(lots), 1)
        self.assertEqual(lots[0]["cost_price"], "120.000000")

    def test_s5_partial_close(self):
        self.svc.record_fill(
            "fund_test", side="BUY", security_id="sec_AAA", symbol="AAA",
            quantity="10", price="100", fee="0", fill_ref="b1",
        )
        self.svc.record_fill(
            "fund_test", side="SELL", security_id="sec_AAA", symbol="AAA",
            quantity="4", price="110", fee="0", fill_ref="s1",
        )
        s = self.svc.get_state("fund_test")
        self.assertEqual(s["positions"][0]["quantity"], "6.000000")
        self.assertEqual(D(s["realized_pnl"]), Decimal("40.00"))
        lots = self.svc.get_lots("fund_test")
        self.assertEqual(lots[0]["quantity_open"], "6.000000")

    def test_s6_fees(self):
        self.svc.record_fee("fund_test", amount="25", reason="platform_fee")
        s = self.svc.get_state("fund_test")
        self.assertEqual(s["cash"], "99975.00")
        self.assertEqual(s["total_fees"], "25.00")

    def test_s7_duplicate_fill_idempotent(self):
        r1 = self.svc.record_fill(
            "fund_test", side="BUY", security_id="sec_AAA", symbol="AAA",
            quantity="5", price="50", fee="0", fill_ref="dup1",
        )
        r2 = self.svc.record_fill(
            "fund_test", side="BUY", security_id="sec_AAA", symbol="AAA",
            quantity="5", price="50", fee="0", fill_ref="dup1",
        )
        self.assertEqual(r2["status"], "duplicate")
        s = self.svc.get_state("fund_test")
        self.assertEqual(s["positions"][0]["quantity"], "5.000000")
        # cash only one buy
        self.assertEqual(s["cash"], "99750.00")

    def test_s8_reconciliation_mismatch(self):
        self.svc.record_fill(
            "fund_test", side="BUY", security_id="sec_AAA", symbol="AAA",
            quantity="1", price="10", fee="0", fill_ref="only_ledger",
        )
        report = self.svc.reconcile(
            "fund_test",
            oms_fills=[{"fill_id": "missing_from_ledger", "quantity": "1", "price": "10"}],
        )
        self.assertFalse(report["ok"])
        codes = {i["code"] for i in report["issues"]}
        self.assertIn("MISSING_FILL", codes)

    def test_s9_stale_market_price(self):
        self.svc.record_fill(
            "fund_test", side="BUY", security_id="sec_AAA", symbol="AAA",
            quantity="1", price="100", fee="0", fill_ref="b1",
        )
        old = 1_000_000.0
        self.svc.record_mark(
            "fund_test",
            security_id="sec_AAA",
            price="200",
            max_age_seconds=10,
            ts=old,
            symbol="AAA",
        )
        s = self.svc.get_state("fund_test", now=old + 100)
        self.assertTrue(s["positions"][0]["mark_stale"])
        # still uses mark price but flags stale
        self.assertEqual(s["positions"][0]["market_value"], "200.00")

    def test_s10_restart_replay(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "ledger.db"
            svc1 = PortfolioLedgerService(FundLedgerStore(path))
            svc1.create_fund(fund_id="fund_r", opening_cash="1000")
            svc1.register_security(security_id="sec_X", symbol="X")
            svc1.record_fill(
                "fund_r", side="BUY", security_id="sec_X", symbol="X",
                quantity="2", price="100", fee="0", fill_ref="r1",
            )
            svc1.record_mark("fund_r", security_id="sec_X", price="105", symbol="X")
            s1 = svc1.get_state("fund_r")
            h1 = state_hash(
                reduce_events(svc1.store.list_events("fund_r"), fund_id="fund_r")
            )
            # destroy service, reopen
            svc2 = PortfolioLedgerService(FundLedgerStore(path))
            s2 = svc2.replay("fund_r")
            h2 = state_hash(
                reduce_events(svc2.store.list_events("fund_r"), fund_id="fund_r")
            )
            self.assertEqual(s1, s2)
            self.assertEqual(h1, h2)

    def test_short_rejected(self):
        with self.assertRaises(LedgerError):
            self.svc.record_fill(
                "fund_test", side="SELL", security_id="sec_AAA", symbol="AAA",
                quantity="1", price="10", fee="0", fill_ref="short1",
            )

    def test_negative_cash_rejected(self):
        with self.assertRaises(LedgerError):
            self.svc.record_fill(
                "fund_test", side="BUY", security_id="sec_AAA", symbol="AAA",
                quantity="10000", price="100", fee="0", fill_ref="big",
            )

    def test_nav_exposure(self):
        self.svc.record_fill(
            "fund_test", side="BUY", security_id="sec_AAA", symbol="AAA",
            quantity="10", price="100", fee="0", fill_ref="b1",
        )
        self.svc.record_mark("fund_test", security_id="sec_AAA", price="100", symbol="AAA")
        nav = self.svc.get_nav("fund_test")
        exp = self.svc.get_exposure("fund_test")
        self.assertEqual(nav["nav"], "100000.00")
        self.assertEqual(exp["gross"], "1000.00")
        self.assertEqual(exp["short"], "0.00")
        self.assertFalse(exp["leverage_enabled"])

    def test_no_set_position_api(self):
        self.assertFalse(hasattr(self.svc, "set_position"))
        self.assertFalse(hasattr(self.svc, "set_nav"))
        self.assertFalse(hasattr(self.svc, "set_pnl"))

    def test_paper_bridge_idempotent(self):
        post_paper_fill_to_ledger(
            self.svc, "fund_test", fill_id="pf1", side="BUY", symbol="BBB",
            quantity="3", price="20", fee="0",
        )
        post_paper_fill_to_ledger(
            self.svc, "fund_test", fill_id="pf1", side="BUY", symbol="BBB",
            quantity="3", price="20", fee="0",
        )
        s = self.svc.get_state("fund_test")
        pos = [p for p in s["positions"] if p["symbol"] == "BBB"][0]
        self.assertEqual(pos["quantity"], "3.000000")

    def test_command_center_summary(self):
        cc = self.svc.command_center_summary("fund_test")
        self.assertEqual(cc["mode"], "PAPER")
        self.assertEqual(cc["live_execution"], "UNAVAILABLE")
        self.assertEqual(cc["source"], "canonical_fund_ledger")
        self.assertEqual(cc["paper_nav"], "100000.00")

    def test_correction_reverses_fee(self):
        r = self.svc.record_fee("fund_test", amount="10", reason="err_fee")
        eid = r["event"]["event_id"]
        self.svc.reverse_event("fund_test", target_event_id=eid, reason="fix fee")
        s = self.svc.get_state("fund_test")
        self.assertEqual(s["cash"], "100000.00")


if __name__ == "__main__":
    unittest.main()
