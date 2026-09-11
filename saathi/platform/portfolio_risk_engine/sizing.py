"""Deterministic position sizing (LLM cannot set final size)."""
from __future__ import annotations

from decimal import Decimal

from saathi.platform.fund_ledger.money import D, q_money, q_price, q_qty
from saathi.platform.portfolio_risk_engine.budget import RiskBudget
from saathi.platform.portfolio_risk_engine.models import (
    REASON_INVALID_QUANTITY,
    REASON_INVALID_STOP,
    REASON_MAX_TRADE_NOTIONAL,
)


def size_fixed_fractional(
    *,
    nav: Decimal,
    price: Decimal,
    budget: RiskBudget,
    fraction: Decimal | None = None,
) -> dict:
    """Quantity from min(max_position_weight, fraction) of NAV / price."""
    if price <= 0:
        return {"ok": False, "reason_code": REASON_INVALID_QUANTITY, "detail": "non-positive price"}
    frac = D(fraction) if fraction is not None else D(budget.max_position_weight)
    frac = min(frac, D(budget.max_position_weight), Decimal("1"))
    if frac < 0:
        return {"ok": False, "reason_code": REASON_INVALID_QUANTITY, "detail": "negative fraction"}
    notional = q_money(D(nav) * frac)
    if notional > D(budget.max_trade_notional):
        notional = q_money(budget.max_trade_notional)
    qty = q_qty(notional / D(price))
    return {
        "ok": True,
        "method": "fixed_fractional",
        "quantity": str(qty),
        "notional": str(notional),
        "fraction": str(q_money(frac)),
        "price": str(q_price(price)),
        "authorizes_execution": False,
        "mode": "PAPER",
    }


def size_max_notional(*, price: Decimal, budget: RiskBudget, cash: Decimal) -> dict:
    if price <= 0:
        return {"ok": False, "reason_code": REASON_INVALID_QUANTITY, "detail": "non-positive price"}
    notional = min(D(budget.max_trade_notional), D(cash))
    if notional <= 0:
        return {"ok": False, "reason_code": REASON_INVALID_QUANTITY, "detail": "no cash"}
    qty = q_qty(notional / D(price))
    return {
        "ok": True,
        "method": "max_notional",
        "quantity": str(qty),
        "notional": str(q_money(notional)),
        "authorizes_execution": False,
        "mode": "PAPER",
    }


def size_stop_risk(
    *,
    nav: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
    budget: RiskBudget,
    side: str = "BUY",
) -> dict:
    """Long-only: risk_per_share = entry - stop; qty = (nav * risk_frac) / risk_per_share."""
    side_u = side.upper()
    if side_u != "BUY":
        return {"ok": False, "reason_code": REASON_INVALID_STOP, "detail": "stop sizing long-only"}
    entry = D(entry_price)
    stop = D(stop_price)
    if entry <= 0 or stop <= 0:
        return {"ok": False, "reason_code": REASON_INVALID_STOP, "detail": "non-positive prices"}
    risk_ps = entry - stop
    if risk_ps <= 0:
        return {"ok": False, "reason_code": REASON_INVALID_STOP, "detail": "stop must be below entry for long"}
    risk_capital = q_money(D(nav) * D(budget.max_trade_risk_fraction))
    qty = q_qty(risk_capital / risk_ps)
    notional = q_money(qty * entry)
    if notional > D(budget.max_trade_notional):
        qty = q_qty(D(budget.max_trade_notional) / entry)
        notional = q_money(qty * entry)
    if qty <= 0:
        return {"ok": False, "reason_code": REASON_INVALID_QUANTITY, "detail": "zero quantity"}
    return {
        "ok": True,
        "method": "stop_risk",
        "quantity": str(qty),
        "notional": str(notional),
        "risk_per_share": str(q_price(risk_ps)),
        "risk_capital": str(risk_capital),
        "authorizes_execution": False,
        "mode": "PAPER",
    }
