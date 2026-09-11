"""Derive risk metrics from canonical ledger state (no re-accounting)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.fund_ledger.money import D, q_money


def portfolio_metrics(state: dict[str, Any], *, now: float | None = None) -> dict[str, Any]:
    """Compute concentration / exposure views from ledger public state."""
    nav = D(state.get("nav") or state.get("paper_nav") or "0")
    cash = D(state.get("cash") or "0")
    positions = list(state.get("positions") or [])
    exposure = state.get("exposure") or {}
    gross = D(exposure.get("gross") or state.get("positions_value") or "0")
    net = D(exposure.get("net") or gross)
    cash_pct = (cash / nav) if nav > 0 else Decimal("0")
    gross_pct = (gross / nav) if nav > 0 else Decimal("0")
    net_pct = (net / nav) if nav > 0 else Decimal("0")

    weights = []
    stale_marks = 0
    for p in positions:
        w = D(p.get("weight") or "0")
        if w == 0 and nav > 0:
            w = D(p.get("market_value") or "0") / nav
        weights.append(
            {
                "symbol": p.get("symbol"),
                "security_id": p.get("security_id"),
                "weight": q_money(w),
                "market_value": D(p.get("market_value") or "0"),
                "quantity": D(p.get("quantity") or "0"),
                "mark_stale": bool(p.get("mark_stale")),
            }
        )
        if p.get("mark_stale"):
            stale_marks += 1
    weights.sort(key=lambda x: x["weight"], reverse=True)
    largest = weights[0]["weight"] if weights else Decimal("0")
    top3 = sum((w["weight"] for w in weights[:3]), Decimal("0"))
    top5 = sum((w["weight"] for w in weights[:5]), Decimal("0"))

    return {
        "nav": q_money(nav),
        "cash": q_money(cash),
        "cash_pct": q_money(cash_pct),
        "gross_exposure": q_money(gross),
        "net_exposure": q_money(net),
        "gross_exposure_pct": q_money(gross_pct),
        "net_exposure_pct": q_money(net_pct),
        "positions_value": q_money(D(state.get("positions_value") or "0")),
        "position_count": len([p for p in positions if D(p.get("quantity") or 0) != 0]),
        "largest_position_pct": q_money(largest),
        "top3_concentration": q_money(top3),
        "top5_concentration": q_money(top5),
        "realized_pnl": q_money(D(state.get("realized_pnl") or "0")),
        "unrealized_pnl": q_money(D(state.get("unrealized_pnl") or "0")),
        "total_pnl": q_money(D(state.get("total_pnl") or "0")),
        "weights": [
            {**w, "weight": str(w["weight"]), "market_value": str(q_money(w["market_value"])),
             "quantity": str(w["quantity"])}
            for w in weights
        ],
        "stale_mark_count": stale_marks,
        "invariants_ok": bool(state.get("invariants_ok", True)),
        "mode": "PAPER",
    }


def project_trade(
    state: dict[str, Any],
    *,
    side: str,
    symbol: str,
    quantity: Decimal,
    price: Decimal,
    fee: Decimal = Decimal("0"),
) -> dict[str, Any]:
    """Hypothetical portfolio after trade — does not mutate ledger."""
    side_u = side.upper()
    qty = D(quantity)
    px = D(price)
    fee_d = D(fee)
    notional = q_money(qty * px)
    cash = D(state.get("cash") or "0")
    positions = {p.get("symbol"): dict(p) for p in (state.get("positions") or [])}
    cur = positions.get(symbol) or {
        "symbol": symbol,
        "security_id": f"sec_{symbol.upper()}_PAPER",
        "quantity": "0",
        "market_value": "0",
        "avg_cost": str(px),
        "unrealized_pnl": "0",
        "realized_pnl": "0",
        "weight": "0",
        "mark_stale": False,
    }
    cur_qty = D(cur.get("quantity") or "0")
    if side_u == "BUY":
        new_cash = cash - notional - fee_d
        new_qty = cur_qty + qty
    elif side_u == "SELL":
        new_cash = cash + notional - fee_d
        new_qty = cur_qty - qty
        if new_qty < 0:
            return {"ok": False, "error": "SHORTS_DISABLED", "projected_qty": str(new_qty)}
    else:
        return {"ok": False, "error": "INVALID_SIDE"}

    if new_qty == 0:
        positions.pop(symbol, None)
    else:
        mv = q_money(new_qty * px)
        cur["quantity"] = str(new_qty)
        cur["market_value"] = str(mv)
        positions[symbol] = cur

    positions_value = sum((D(p.get("market_value") or 0) for p in positions.values()), Decimal("0"))
    nav = q_money(new_cash + positions_value)
    # rebuild weights
    pos_list = []
    for p in positions.values():
        mv = D(p.get("market_value") or 0)
        w = (mv / nav) if nav > 0 else Decimal("0")
        p = {**p, "weight": str(q_money(w))}
        pos_list.append(p)
    projected_state = {
        **state,
        "cash": str(q_money(new_cash)),
        "positions_value": str(q_money(positions_value)),
        "nav": str(nav),
        "paper_nav": str(nav),
        "positions": pos_list,
        "exposure": {
            "gross": str(q_money(positions_value)),
            "net": str(q_money(positions_value)),
            "long": str(q_money(positions_value)),
            "short": "0.00",
            "cash_weight": str(q_money(new_cash / nav) if nav > 0 else Decimal("0")),
        },
        "total_pnl": state.get("total_pnl"),
        "realized_pnl": state.get("realized_pnl"),
        "unrealized_pnl": state.get("unrealized_pnl"),
        "invariants_ok": True,
    }
    return {
        "ok": True,
        "trade_notional": str(notional),
        "projected_cash": str(q_money(new_cash)),
        "projected_nav": str(nav),
        "projected_metrics": portfolio_metrics(projected_state),
        "projected_state": projected_state,
    }
