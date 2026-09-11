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
from saathi.platform.fund_ledger.paper_bridge import post_paper_fill_to_ledger
from saathi.platform.fund_ledger.posting import post_accepted_fill, retry_pending_posts, FillPostingStore
from saathi.platform.fund_ledger.view_adapter import LedgerPortfolioViewAdapter
from saathi.platform.fund_ledger.cutover import fund_id_for_account, CUTOVER_POLICY, DEFAULT_MARKER

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
    "post_paper_fill_to_ledger",
    "post_accepted_fill",
    "retry_pending_posts",
    "FillPostingStore",
    "LedgerPortfolioViewAdapter",
    "fund_id_for_account",
    "CUTOVER_POLICY",
    "DEFAULT_MARKER",
]

AUTHORITY = "CANONICAL_PAPER_FUND_LEDGER"
ENGINE_VERSION = "fund-ledger/1.0.0"
ACCOUNTING_METHOD = "FIFO"
ENVIRONMENT = "PAPER"
