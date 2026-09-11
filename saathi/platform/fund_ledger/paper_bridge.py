"""Bridge: accepted paper OMS fills → canonical fund ledger (one-way).

Does not bypass Trading Guardian or ExecutionGateway. Call only after a fill is
accepted by the paper OMS. Agents never call this with invented positions.
"""
from __future__ import annotations

from typing import Any

from saathi.platform.fund_ledger.service import PortfolioLedgerService


def post_paper_fill_to_ledger(
    ledger: PortfolioLedgerService,
    fund_id: str,
    *,
    fill_id: str,
    side: str,
    symbol: str,
    quantity: Any,
    price: Any,
    fee: Any = "0",
    order_id: str = "",
    security_id: str | None = None,
    actor: str = "paper_oms",
) -> dict:
    """Map a durable paper fill into ledger.record_fill (idempotent by fill_id)."""
    sid = security_id or f"sec_{symbol.upper()}_PAPER"
    # ensure security exists
    if not ledger.store.get_security(sid):
        ledger.register_security(security_id=sid, symbol=symbol)
    return ledger.record_fill(
        fund_id,
        side=side,
        security_id=sid,
        symbol=symbol,
        quantity=quantity,
        price=price,
        fee=fee,
        fill_ref=fill_id,
        order_ref=order_id,
        actor=actor,
        source="paper_oms_bridge",
        idempotency_key=f"fill:{fill_id}",
    )
