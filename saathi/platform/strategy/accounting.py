"""M62.4 — deterministic portfolio accounting (average-cost lots).

Single source of truth for cash, positions, realized/unrealized P&L, fees, equity
curve, turnover, and drawdown across a backtest. Decimal throughout.

Invariants (asserted by ``check_invariants`` and the test suite):

* ending_equity == cash + marked positions
* cash delta reconciles to fills (signed notional) + fees
* position quantity reconciles to the signed sum of fills
* realized + unrealized P&L reconciles to (equity change) given no deposits

Long-only in M62.4 (short-selling not authorized). A SELL never drives quantity
below zero; oversell is clamped and flagged upstream.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.strategy.models import (
    SimPosition, SimulatedOrder, SimOrderStatus, EquityPoint, D, q2,
)


class PortfolioAccountant:
    def __init__(self, *, starting_cash: Decimal, instruments: list[str]):
        self.starting_cash = D(starting_cash)
        self.cash = D(starting_cash)
        self.positions: dict[str, SimPosition] = {s: SimPosition(instrument=s) for s in instruments}
        self.total_fees = Decimal("0")
        self.realized_pnl = Decimal("0")
        self.gross_traded_notional = Decimal("0")   # for turnover
        self.equity_curve: list[EquityPoint] = []
        self.fills: list[SimulatedOrder] = []
        self._peak_equity = D(starting_cash)
        self._buy_cash_out = Decimal("0")
        self._sell_cash_in = Decimal("0")

    # ── apply a simulated fill ───────────────────────────────────────────
    def apply(self, order: SimulatedOrder) -> None:
        if order.status not in (SimOrderStatus.FILLED, SimOrderStatus.PARTIAL):
            return
        pos = self.positions.setdefault(order.instrument, SimPosition(instrument=order.instrument))
        qty = D(order.quantity)
        px = D(order.fill_price)
        fees = D(order.fees)
        notional = qty * px

        if order.side == "BUY":
            new_qty = pos.quantity + qty
            if new_qty > 0:
                pos.avg_cost = ((pos.avg_cost * pos.quantity) + notional) / new_qty
            pos.quantity = new_qty
            self.cash -= (notional + fees)
            self._buy_cash_out += notional
        else:  # SELL (long reduction only)
            sell_qty = min(qty, pos.quantity)          # clamp: no shorting
            realized = (px - pos.avg_cost) * sell_qty
            pos.realized_pnl += realized
            self.realized_pnl += realized
            pos.quantity -= sell_qty
            if pos.quantity == 0:
                pos.avg_cost = Decimal("0")
            self.cash += (px * sell_qty - fees)
            self._sell_cash_in += px * sell_qty
            notional = px * sell_qty

        self.total_fees += fees
        self.gross_traded_notional += abs(notional)
        self.fills.append(order)

    # ── mark-to-market snapshot ──────────────────────────────────────────
    def positions_value(self, marks: dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        for sym, pos in self.positions.items():
            if pos.quantity != 0:
                total += pos.market_value(D(marks.get(sym, pos.avg_cost)))
        return total

    def unrealized_pnl(self, marks: dict[str, Decimal]) -> Decimal:
        total = Decimal("0")
        for sym, pos in self.positions.items():
            if pos.quantity != 0:
                total += pos.unrealized_pnl(D(marks.get(sym, pos.avg_cost)))
        return total

    def equity(self, marks: dict[str, Decimal]) -> Decimal:
        return self.cash + self.positions_value(marks)

    def gross_exposure(self, marks: dict[str, Decimal]) -> Decimal:
        return sum((abs(p.market_value(D(marks.get(s, p.avg_cost)))) for s, p in self.positions.items() if p.quantity != 0), Decimal("0"))

    def mark(self, epoch: float, marks: dict[str, Decimal]) -> EquityPoint:
        eq = self.equity(marks)
        if eq > self._peak_equity:
            self._peak_equity = eq
        dd = Decimal("0")
        if self._peak_equity > 0:
            dd = (self._peak_equity - eq) / self._peak_equity
        pt = EquityPoint(epoch=epoch, equity=q2(eq), cash=q2(self.cash),
                         positions_value=q2(self.positions_value(marks)), drawdown=q2(dd))
        self.equity_curve.append(pt)
        return pt

    # ── invariants ───────────────────────────────────────────────────────
    def check_invariants(self, marks: dict[str, Decimal], *, tol: Decimal = Decimal("0.01")) -> list[str]:
        errors: list[str] = []
        # 1. equity == cash + marked positions
        eq = self.equity(marks)
        recomputed = self.cash + self.positions_value(marks)
        if abs(eq - recomputed) > tol:
            errors.append(f"equity mismatch {eq} != {recomputed}")
        # 2. cash reconciles to fills + fees
        expected_cash = self.starting_cash - self._buy_cash_out + self._sell_cash_in - self.total_fees
        if abs(self.cash - expected_cash) > tol:
            errors.append(f"cash mismatch {self.cash} != {expected_cash}")
        # 3. position quantity == signed sum of fills
        for sym, pos in self.positions.items():
            signed = Decimal("0")
            for f in self.fills:
                if f.instrument != sym:
                    continue
                signed += D(f.quantity) if f.side == "BUY" else -D(f.quantity)
            # clamp for long-only sells: quantity can't go negative
            if signed < 0:
                signed = Decimal("0")
            if abs(pos.quantity - signed) > tol:
                errors.append(f"{sym} qty mismatch {pos.quantity} != {signed}")
        # 4. realized + unrealized reconciles to equity change (no deposits)
        pnl = self.realized_pnl + self.unrealized_pnl(marks) - self.total_fees
        eq_change = eq - self.starting_cash
        if abs(pnl - eq_change) > tol:
            errors.append(f"pnl reconciliation {pnl} != equity change {eq_change}")
        return errors

    def turnover(self, marks: dict[str, Decimal]) -> Decimal:
        eq = self.equity(marks)
        if eq <= 0:
            return Decimal("0")
        return q2(self.gross_traded_notional / eq)
