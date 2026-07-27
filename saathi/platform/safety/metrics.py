"""M62.7 — deterministic safety-metric collection.

Every metric is a pure function of persisted paper state (immutable fills, orders,
intents, positions, cash) + a named timezone + an evaluation timestamp + optional
explicit marks. No wall-clock is read for the value itself (the caller passes the
evaluation ``now``), no RNG, no unsorted query dependence. Financial math is Decimal.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.paper_trading.store import PaperStore
from saathi.platform.paper_trading.models import q2, q6
from saathi.platform.trading_models import D, OrderSide
from saathi.platform.safety.models import trading_day


class MetricsCollector:
    """Reads the PaperStore and computes deterministic per-account safety metrics."""

    def __init__(self, paper_store: PaperStore):
        self.paper = paper_store

    # ── deterministic fill replay (same ordering as reconciliation) ─────────────────
    def _replay(self, org_id: str, account_id: str) -> dict[str, Any]:
        acct = self.paper.get_account(org_id, account_id)
        orders = self.paper.list_orders(org_id, account_id=account_id, limit=500)
        sym_by_order = {o.id: o.symbol for o in orders}
        fills: list[dict] = []
        for o in orders:
            for f in self.paper.list_fills(org_id, o.id):
                fills.append(f)
        fills.sort(key=lambda f: (f.get("created_at", 0.0), f["paper_order_id"], f.get("seq", 0)))

        pos: dict[str, dict] = {}
        realized_by_ts: list[tuple[float, Decimal]] = []
        realized_total = Decimal("0")
        for f in fills:
            sym = sym_by_order.get(f["paper_order_id"])
            qty = D(f["quantity"]); price = D(f["price"]); gross = D(f["gross_amount"])
            p = pos.setdefault(sym, {"qty": Decimal("0"), "avg_cost": Decimal("0")})
            if f["side"] == OrderSide.BUY.value:
                new_qty = p["qty"] + qty
                p["avg_cost"] = q6((p["avg_cost"] * p["qty"] + gross) / new_qty) if new_qty > 0 else Decimal("0")
                p["qty"] = new_qty
            else:
                r = q2((price - p["avg_cost"]) * qty)
                realized_total = q2(realized_total + r)
                realized_by_ts.append((float(f.get("event_ts", 0.0)), r))
                p["qty"] = p["qty"] - qty
                if p["qty"] == 0:
                    p["avg_cost"] = Decimal("0")
        return {"account": acct, "positions": pos, "realized_by_ts": realized_by_ts,
                "realized_total": realized_total, "fill_count": len(fills)}

    def _positions_value(self, pos: dict[str, dict], marks: dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        for sym, p in pos.items():
            if p["qty"] == 0:
                continue
            mark = D(marks.get(sym, p["avg_cost"]))
            total = q2(total + q2(p["qty"] * mark))
        return total

    # ── public metric surface ────────────────────────────────────────────────────
    def account_metrics(self, org_id: str, account_id: str, *, now: float, tz_name: str = "UTC",
                        marks: dict[str, Decimal] | None = None) -> dict[str, Any]:
        marks = {k: D(v) for k, v in (marks or {}).items()}
        rp = self._replay(org_id, account_id)
        acct = rp["account"]
        cash = D(acct.current_cash)
        positions_value = self._positions_value(rp["positions"], marks)
        equity = q2(cash + positions_value)

        # daily realized (deterministic trading-day window)
        day = trading_day(now, tz_name=tz_name)
        daily_realized = Decimal("0")
        for ts, r in rp["realized_by_ts"]:
            if day["start"] <= ts < day["end"]:
                daily_realized = q2(daily_realized + r)

        # unrealized (mark vs avg_cost); 0 when no marks supplied
        unrealized = Decimal("0")
        for sym, p in rp["positions"].items():
            if p["qty"] == 0 or sym not in marks:
                continue
            unrealized = q2(unrealized + q2((marks[sym] - p["avg_cost"]) * p["qty"]))

        # gross exposure (long-only) + concentration
        gross = Decimal("0")
        max_symbol_notional = Decimal("0")
        top_symbol = ""
        for sym, p in rp["positions"].items():
            if p["qty"] == 0:
                continue
            mark = D(marks.get(sym, p["avg_cost"]))
            notional = q2(p["qty"] * mark)
            gross = q2(gross + notional)
            if notional > max_symbol_notional:
                max_symbol_notional = notional; top_symbol = sym
        concentration_pct = (q2(max_symbol_notional / equity * Decimal("100")) if equity > 0
                             else Decimal("0"))

        orders = self.paper.list_orders(org_id, account_id=account_id, limit=500)
        open_orders = sum(1 for o in orders if not o.is_terminal)

        return {
            "account_id": account_id, "day": day, "cash": cash, "positions_value": positions_value,
            "equity": equity, "daily_realized_pnl": daily_realized, "realized_pnl_total": rp["realized_total"],
            "unrealized_pnl": unrealized, "daily_total_pnl": q2(daily_realized + unrealized),
            "gross_exposure": gross, "concentration_pct": concentration_pct, "top_symbol": top_symbol,
            "top_symbol_notional": max_symbol_notional, "open_order_count": open_orders,
            "fill_count": rp["fill_count"], "status": acct.status.value, "reserved_cash": D(acct.reserved_cash),
            "available_cash": D(acct.available_cash),
        }

    def rejection_rate(self, org_id: str, account_id: str, *, now: float, window_seconds: int) -> dict[str, Any]:
        """Rejected intents / total intents within a bounded window. Guardian vetoes and
        broker validation rejects both land as REJECTED intents."""
        since = now - window_seconds if window_seconds > 0 else 0.0
        intents = self.paper.list_intents(org_id, account_id=account_id, limit=1000)
        total = 0; rejected = 0
        for it in intents:
            if it.get("created_at", 0.0) < since:
                continue
            total += 1
            if str(it.get("state", "")).upper() == "REJECTED":
                rejected += 1
        rate = (q6(Decimal(rejected) / Decimal(total)) if total > 0 else Decimal("0"))
        return {"numerator": Decimal(rejected), "denominator": Decimal(total), "rate": rate}
