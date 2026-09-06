"""Derive attribution inputs from canonical SHADOW-TRADING-1 records.

A BRIDGE, not a second source of truth. It reads the durable shadow session and
turns its fills and counterfactuals into the typed records attribution_v2
consumes. It writes nothing, holds no execution authority, and invents no number:
where the session cannot support a field, the field is absent rather than zero.

Kept separate from attribution_v2 so that module stays pure and testable without
a database, and so there is exactly one place that knows the session's shape.
"""
from __future__ import annotations

from decimal import Decimal

from saathi.platform.tg.attribution_v2 import (
    AttributionRecord,
    CounterfactualRecord,
)
from saathi.platform.trading_models import D


def _is_sell(side) -> bool:
    return str(side).upper() == "SELL"


def records_from_session(
    store,
    session_id: str,
    *,
    strategy_id: str | None = None,
    venue: str = "BINANCE",
    asset_class: str = "CRYPTO",
    mark_prices: dict | None = None,
) -> list[AttributionRecord]:
    """One attribution record per instrument in a shadow session.

    Gross P&L is realized plus, where a mark is supplied, unrealized. A holding
    with no mark contributes its realized part only and the caller can see from
    the portfolio that a position remains — silently marking it at cost would
    report a flat position that was never flat.
    """
    session = store.get_session(session_id)
    if session is None:
        raise ValueError(f"unknown shadow session: {session_id}")

    state = store.derive_portfolio(session_id)
    fills = store.fills(session_id)
    marks = {k: D(v) for k, v in (mark_prices or {}).items()}

    # The session records a strategy for the whole run. A session that mixed
    # strategies could not attribute a fill to one of them from these records, so
    # that is reported as ambiguous rather than guessed.
    session_strategy = strategy_id or session.get("strategy_version") or "UNKNOWN"
    ambiguous = strategy_id is None and not session.get("strategy_version")

    per_symbol: dict[str, dict] = {}
    for f in fills:
        sym = f["symbol"]
        b = per_symbol.setdefault(sym, {
            "fee": Decimal("0"), "spread": Decimal("0"), "slippage": Decimal("0"),
            "notional": Decimal("0"), "cash_flow": Decimal("0"), "quantity": Decimal("0"),
        })
        qty = D(f["quantity"])
        px = D(f["fill_price"])
        b["fee"] += D(f.get("fee") or 0)
        b["spread"] += D(f.get("spread_cost") or 0)
        b["slippage"] += D(f.get("slippage_cost") or 0)
        b["notional"] += qty * px
        # Cash OUT on a buy, cash IN on a sell — gross of costs, which are
        # accumulated separately so gross and net never double-count them.
        value = qty * px
        b["cash_flow"] += value if _is_sell(f["side"]) else -value
        b["quantity"] += -qty if _is_sell(f["side"]) else qty

    out: list[AttributionRecord] = []
    for sym, b in sorted(per_symbol.items()):
        held = state.positions.get(sym, Decimal("0"))
        gross = b["cash_flow"]
        if held != 0:
            mark = marks.get(sym)
            if mark is None:
                # No mark: the open position's unrealized part is simply not
                # claimed. Reporting it as zero would assert the position is flat.
                pass
            else:
                gross = gross + held * mark
        cost = b["fee"] + b["spread"] + b["slippage"]
        out.append(AttributionRecord(
            strategy_id=session_strategy, symbol=sym, venue=venue, asset_class=asset_class,
            gross_pnl=gross, cost=cost,
            fee=b["fee"], spread_cost=b["spread"], slippage_cost=b["slippage"],
            notional=b["notional"], strategy_ambiguous=ambiguous,
        ))
    return out


def counterfactuals_from_session(
    store, session_id: str, *, strategy_id: str | None = None,
) -> list[CounterfactualRecord]:
    """Blocked proposals and their observed forward path, as estimates."""
    session = store.get_session(session_id)
    if session is None:
        raise ValueError(f"unknown shadow session: {session_id}")
    strategy = strategy_id or session.get("strategy_version") or "UNKNOWN"

    out: list[CounterfactualRecord] = []
    for cf in store.counterfactuals(session_id):
        forward = cf.get("forward_price")
        out.append(CounterfactualRecord(
            strategy_id=strategy,
            symbol=cf["symbol"],
            blocked_by=cf.get("blocked_by") or "UNKNOWN",
            reference_price=D(cf["reference_price"]),
            quantity=D(cf["quantity"]),
            forward_price=None if forward is None else D(forward),
            reason_codes=tuple(cf.get("reason_codes") or ()),
        ))
    return out
