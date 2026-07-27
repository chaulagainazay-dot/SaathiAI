"""M62.4 — simulation-level Guardian review (veto only, NEVER approval).

Reuses the independent M62.1 ``TradingGuardian`` to sanity-check a strategy's
peak intended exposure inside the BACKTEST domain. This is emphatically NOT trade
approval: it constructs a SIMULATION-environment synthetic intent and asks the
Guardian whether such an exposure would be structurally acceptable. It never calls
ExecutionGateway, never consumes an approval, never touches a real/paper account.

A Guardian pass here means "the simulated exposure is within risk limits", not
"you may trade".
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.trading_models import (
    Environment, OrderIntent, OrderSide, OrderType, OrderState, Account, MarketState, DataQuality, D,
)
from saathi.platform.trading_guardian import TradingGuardian, RiskLimits, GuardianDecision


def simulate_guardian_review(
    *,
    instrument: str,
    intended_quantity: Decimal,
    reference_price: Decimal,
    starting_cash: Decimal,
    limits: RiskLimits | None = None,
) -> dict[str, Any]:
    """Run the fail-closed Guardian against a synthetic SIMULATION intent. Returns a
    public decision dict tagged as simulation-only."""
    guardian = TradingGuardian(limits=limits)
    account = Account(account_id="backtest-sim", environment=Environment.SIMULATION, cash=D(starting_cash))
    intent = OrderIntent(
        intent_id="sim", org_id="sim", workspace_id="sim", account_id="backtest-sim",
        environment=Environment.SIMULATION, symbol=instrument, side=OrderSide.BUY,
        order_type=OrderType.MARKET, quantity=D(intended_quantity),
        idempotency_key="sim-key", approval_id="sim-approval", state=OrderState.DRAFT,
    )
    decision: GuardianDecision = guardian.evaluate(
        intent, account=account, ref_price=D(reference_price),
        price_quality=DataQuality.VALID, market_state=MarketState.OPEN,
    )
    pub = decision.to_public()
    pub["context"] = "SIMULATION_ONLY"
    pub["is_trade_approval"] = False
    return pub
