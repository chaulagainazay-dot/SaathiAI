"""T-NEXT-1 — Canonical paper fund ledger (deterministic books & records).

Agents may research/propose. Deterministic code owns cash, lots, P&L, NAV.

This package is the **single canonical writer** for paper fund accounting state.
Trading Guardian answers "is action allowed?"; ExecutionGateway owns tool routing.
Neither may be bypassed by this ledger for order submission.

Environment: PAPER only. No live brokers, leverage, or shorts.
"""
from __future__ import annotations

from saathi.platform.fund_ledger.money import Money, MoneyError, q_money, q_price, q_qty
from saathi.platform.fund_ledger.models import (
    EventType,
    Fund,
    LedgerEvent,
    Mark,
    PortfolioState,
    PositionLot,
    Security,
    ValuationSnapshot,
)
from saathi.platform.fund_ledger.service import PortfolioLedgerService
from saathi.platform.fund_ledger.reducer import reduce_events
from saathi.platform.fund_ledger.reconcile import reconcile_fills

__all__ = [
    "Money",
    "MoneyError",
    "q_money",
    "q_price",
    "q_qty",
    "EventType",
    "Fund",
    "LedgerEvent",
    "Mark",
    "PortfolioState",
    "PositionLot",
    "Security",
    "ValuationSnapshot",
    "PortfolioLedgerService",
    "reduce_events",
    "reconcile_fills",
]

AUTHORITY = "CANONICAL_PAPER_FUND_LEDGER"
ENGINE_VERSION = "fund-ledger/1.0.0"
ACCOUNTING_METHOD = "FIFO"
ENVIRONMENT = "PAPER"
