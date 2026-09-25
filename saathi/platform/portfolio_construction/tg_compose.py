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
    price_quality: Any = None,
    market_state: Any = None,
    marks: dict | None = None,
) -> dict:
    """Attach TG evaluation for each material trade in proposal.

    Returns package for governance; never submits orders.
    """
    trades = [t for t in proposal.get("trades") or [] if t.get("action") in ("BUY", "SELL")]
    tg_results = []
    any_deny = False
    for t in trades:
        # Guardian review is mandatory for a positive governance result.  A
        # missing adapter is not evidence of safety and must fail closed.
        if intent_factory is None:
            tg_results.append({"symbol": t["symbol"], "skipped": True, "reason": "no_intent_factory"})
            any_deny = True
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
            price_quality=price_quality if price_quality is not None else DataQuality.VALID,
            market_state=market_state if market_state is not None else MarketState.OPEN,
            marks=marks,
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
        "governance_allowed": bool(trades)
        and (not any_deny)
        and proposal.get("status") == ProposalStatus.READY_FOR_APPROVAL.value,
        "authorizes_execution": False,
        "risk_approved": False,
        "execution_reachable": False,
        "mode": "PAPER",
    }


def compose_candidate_with_tg(
    *,
    engine: Any,
    request: Any,
    candidate: Any,
    guardian: Any,
    risk_engine: Any,
    account: Any,
    fund_id: str,
    ledger_state: dict | None = None,
    recon: dict | None = None,
    intent_factory: Any = None,
    price_quality: Any = None,
    market_state: Any = None,
    marks: dict | None = None,
) -> dict:
    """Dry-run a V2 candidate through canonical risk and Guardian gates.

    This adapter is intentionally terminal: it exposes no gateway, OMS, broker,
    approval creation, cash reservation, or ledger mutation operation.
    """
    candidate_risk = risk_engine.evaluate_candidate_portfolio(
        candidate,
        portfolio_snapshot=request.portfolio_snapshot,
    )
    candidate_risk_public = candidate_risk.to_public()
    if candidate_risk.result in (RiskResult.BLOCK, RiskResult.DATA_INSUFFICIENT):
        return {
            "candidate_portfolio_id": candidate.candidate_portfolio_id,
            "candidate_status": candidate.status.value,
            "candidate_risk": candidate_risk_public,
            "governance_allowed": False,
            "reason": "CANDIDATE_PORTFOLIO_RISK_BLOCKED",
            "tg_results": [],
            "authorizes_execution": False,
            "risk_approved": False,
            "execution_reachable": False,
            "mode": "PAPER",
        }
    handoff = engine.build_risk_handoff(request, candidate)
    if not handoff:
        return {
            "candidate_portfolio_id": candidate.candidate_portfolio_id,
            "candidate_status": candidate.status.value,
            "candidate_risk": candidate_risk_public,
            "governance_allowed": False,
            "reason": "NO_MATERIAL_CANDIDATE_CHANGE",
            "tg_results": [],
            "authorizes_execution": False,
            "risk_approved": False,
            "execution_reachable": False,
            "mode": "PAPER",
        }
    proposal = {
        "proposal_id": candidate.candidate_portfolio_id,
        "status": ProposalStatus.READY_FOR_APPROVAL.value,
        "trades": [
            {
                "security_id": trade.security_id,
                "symbol": trade.symbol,
                "action": trade.side,
                "reference_price": str(trade.price),
                "estimated_quantity": str(trade.quantity),
            }
            for trade in handoff
        ],
    }
    result = compose_proposal_with_tg(
        proposal=proposal,
        guardian=guardian,
        risk_engine=risk_engine,
        account=account,
        fund_id=fund_id,
        ledger_state=ledger_state,
        recon=recon,
        intent_factory=intent_factory,
        price_quality=price_quality,
        market_state=market_state,
        marks=marks,
    )
    result["candidate_portfolio_id"] = candidate.candidate_portfolio_id
    result["candidate_status"] = candidate.status.value
    result["candidate_risk"] = candidate_risk_public
    result["risk_approved"] = False
    result["execution_reachable"] = False
    return result
