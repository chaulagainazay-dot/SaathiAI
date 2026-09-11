"""Position contribution (not full institutional factor attribution)."""
from __future__ import annotations

from decimal import Decimal

from saathi.platform.fund_ledger.money import D, q_money


def position_contributions(start_obs: dict, end_obs: dict) -> dict:
    """Deterministic contribution by security between two observations.

    contribution ≈ Δunrealized + Δrealized (position-level) when available,
    else Δmarket_value + cash_effect approximation from start/end MV.

    Aggregate must reconcile to portfolio total P&L change within tolerance.
    """
    start_pos = {p.get("security_id") or p.get("symbol"): p for p in (start_obs.get("positions") or [])}
    end_pos = {p.get("security_id") or p.get("symbol"): p for p in (end_obs.get("positions") or [])}
    ids = set(start_pos) | set(end_pos)
    rows = []
    total_contrib = Decimal("0")
    for sid in sorted(ids):
        s = start_pos.get(sid) or {}
        e = end_pos.get(sid) or {}
        s_mv = D(s.get("market_value") or "0")
        e_mv = D(e.get("market_value") or "0")
        s_rp = D(s.get("realized_pnl") or "0")
        e_rp = D(e.get("realized_pnl") or "0")
        s_up = D(s.get("unrealized_pnl") or "0")
        e_up = D(e.get("unrealized_pnl") or "0")
        realized_c = e_rp - s_rp
        unrealized_c = e_up - s_up
        # Prefer P&L decomposition; fallback MV change if no pnl fields
        if s.get("realized_pnl") is None and e.get("realized_pnl") is None:
            # market value change is not pure contribution when trades occur —
            # still report MV delta as best effort with flag
            total_c = e_mv - s_mv
            method = "MARKET_VALUE_DELTA"
        else:
            total_c = realized_c + unrealized_c
            method = "REALIZED_PLUS_UNREALIZED"
        total_contrib += total_c
        rows.append(
            {
                "security_id": sid,
                "symbol": e.get("symbol") or s.get("symbol") or sid,
                "period_starting_value": str(q_money(s_mv)),
                "period_ending_value": str(q_money(e_mv)),
                "realized_contribution": str(q_money(realized_c)),
                "unrealized_contribution": str(q_money(unrealized_c)),
                "fees": "0.00",  # position-level fees deferred unless present
                "total_contribution": str(q_money(total_c)),
                "method": method,
            }
        )
    rows.sort(key=lambda r: D(r["total_contribution"]), reverse=True)
    port_rp = D(end_obs.get("realized_pnl") or "0") - D(start_obs.get("realized_pnl") or "0")
    port_up = D(end_obs.get("unrealized_pnl") or "0") - D(start_obs.get("unrealized_pnl") or "0")
    port_total = port_rp + port_up
    # fees reduce total pnl
    fee_delta = D(end_obs.get("total_fees") or "0") - D(start_obs.get("total_fees") or "0")
    # portfolio total investment P&L change (fees already in realized often)
    return {
        "kind": "POSITION_CONTRIBUTION",  # not full ATTRIBUTION
        "rows": rows,
        "aggregate_contribution": str(q_money(total_contrib)),
        "portfolio_pnl_change": str(q_money(port_total)),
        "fee_delta": str(q_money(fee_delta)),
        "top_contributors": rows[:5],
        "bottom_contributors": list(reversed(rows[-5:])) if rows else [],
    }
