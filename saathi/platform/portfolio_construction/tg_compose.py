"""Compose construction proposal with risk + Trading Guardian (no execution)."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.fund_ledger.money import D
from saathi.platform.portfolio_construction.models import ProposalStatus
from saathi.platform.portfolio_risk_engine.models import RiskResult, TradeProposal
from saathi.platform.portfolio_risk_engine.tg_compose import compose_guardian_with_risk


def compose_proposal_with_tg(
    *,
    proposal: dict,
    guardian: Any,
    risk_engine: Any,
    account: Any,
    fund_id: str,
    ledger_state: dict | None = None,
    recon: dict | None = None,
    intent_factory: Any = None,
) -> dict:
    """Attach TG evaluation for each material trade in proposal.

    Returns package for governance; never submits orders.
    """
    trades = [t for t in proposal.get("trades") or [] if t.get("action") in ("BUY", "SELL")]
    tg_results = []
    any_deny = False
    for t in trades:
        # Build minimal OrderIntent-like object if factory provided; else skip full TG
        if intent_factory is None:
            # risk-only path already in proposal
            tg_results.append({"symbol": t["symbol"], "skipped": True, "reason": "no_intent_factory"})
            continue
        intent = intent_factory(t)
        ref_price = D(t["reference_price"])
        from saathi.platform.trading_models import DataQuality, MarketState

        out = compose_guardian_with_risk(
            guardian,
            risk_engine,
            intent,
            account=account,
            ref_price=ref_price,
            price_quality=DataQuality.VALID,
            market_state=MarketState.OPEN,
            fund_id=fund_id,
            ledger_state=ledger_state,
            recon=recon,
        )
        tg_results.append({"symbol": t["symbol"], "tg": out})
        if not out.get("allowed"):
            any_deny = True

    return {
        "proposal_id": proposal.get("proposal_id"),
        "proposal_status": proposal.get("status"),
        "tg_results": tg_results,
        "governance_allowed": (not any_deny)
        and proposal.get("status") == ProposalStatus.READY_FOR_APPROVAL.value,
        "authorizes_execution": False,
        "mode": "PAPER",
    }
