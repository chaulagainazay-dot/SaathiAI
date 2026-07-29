"""Paper portfolio risk controls — fail closed, paper halt only."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.tg.paper_activation.models import (
    D,
    PaperPortfolio,
    RiskHaltReason,
    RiskLimits,
    SimOrder,
)


class RiskController:
    def __init__(self, limits: RiskLimits | None = None):
        self.limits = limits or RiskLimits()

    def pre_trade_check(self, portfolio: PaperPortfolio, order: SimOrder) -> dict[str, Any]:
        if portfolio.status.value != "ACTIVE":
            return {"ok": False, "reason": f"portfolio_{portfolio.status.value.lower()}"}
        if portfolio.halt_reason != RiskHaltReason.NONE:
            return {"ok": False, "reason": f"halted:{portfolio.halt_reason.value}"}

        qty = D(order.quantity)
        if qty <= 0:
            return {"ok": False, "reason": "invalid_quantity"}

        # estimate notional using mark or limit
        mark = portfolio.marks.get(order.symbol)
        ref = mark or order.limit_price or order.stop_price or Decimal("0")
        if ref <= 0:
            ref = Decimal("100")  # conservative placeholder for gate only
        notional = qty * D(ref)

        if notional > self.limits.max_position_notional:
            return {"ok": False, "reason": "max_position_size"}

        open_pos = sum(1 for p in portfolio.positions.values() if p.quantity > 0)
        if order.side.upper() == "BUY" and order.symbol not in portfolio.positions:
            if open_pos >= self.limits.max_concurrent_positions:
                return {"ok": False, "reason": "max_concurrent_positions"}

        eq = portfolio.compute_equity() or Decimal("1")
        # exposure
        gross = sum(
            (p.quantity * portfolio.marks.get(s, p.avg_price) for s, p in portfolio.positions.items()),
            Decimal("0"),
        )
        if order.side.upper() == "BUY":
            projected = gross + notional
            if (projected / eq) * Decimal("100") > self.limits.max_portfolio_exposure_pct:
                return {"ok": False, "reason": "max_portfolio_exposure"}
            # cash long-only — never allow margin execution even if sim label set
            cost = notional * (Decimal("1") + self.limits.fee_bps / Decimal("10000"))
            if cost > portfolio.cash - portfolio.reserved_cash:
                return {"ok": False, "reason": "insufficient_cash"}
        else:
            pos = portfolio.positions.get(order.symbol)
            held = pos.quantity if pos else Decimal("0")
            if qty > held:
                return {"ok": False, "reason": "oversell_long_only"}

        # leverage sim is display only — block if someone tries max_leverage_sim > 1 as executable
        if self.limits.max_leverage_sim > Decimal("1") and self.limits.margin_simulation_enabled:
            # still cash-constrained; no action — document
            pass

        return {"ok": True, "reason": ""}

    def post_trade_check(self, portfolio: PaperPortfolio) -> dict[str, Any]:
        eq = portfolio.compute_equity()
        daily_pnl_pct = Decimal("0")
        weekly_pnl_pct = Decimal("0")
        if portfolio.day_start_equity > 0:
            daily_pnl_pct = ((eq - portfolio.day_start_equity) / portfolio.day_start_equity) * Decimal("100")
        if portfolio.week_start_equity > 0:
            weekly_pnl_pct = ((eq - portfolio.week_start_equity) / portfolio.week_start_equity) * Decimal("100")
        dd = portfolio.drawdown_pct()

        if daily_pnl_pct <= -self.limits.daily_loss_limit_pct:
            return {
                "halt": True,
                "reason": RiskHaltReason.DAILY_LOSS.value,
                "detail": f"daily_pnl_pct={daily_pnl_pct}",
                "circuit_breaker": True,
            }
        if weekly_pnl_pct <= -self.limits.weekly_loss_limit_pct:
            return {
                "halt": True,
                "reason": RiskHaltReason.WEEKLY_LOSS.value,
                "detail": f"weekly_pnl_pct={weekly_pnl_pct}",
                "circuit_breaker": True,
            }
        if dd >= self.limits.max_drawdown_pct:
            return {
                "halt": True,
                "reason": RiskHaltReason.MAX_DRAWDOWN.value,
                "detail": f"drawdown_pct={dd}",
                "circuit_breaker": True,
            }
        return {
            "halt": False,
            "reason": RiskHaltReason.NONE.value,
            "daily_pnl_pct": str(daily_pnl_pct),
            "weekly_pnl_pct": str(weekly_pnl_pct),
            "drawdown_pct": str(dd),
            "circuit_breaker": False,
            "paper_only": True,
        }
