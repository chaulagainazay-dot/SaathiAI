"""Compose PortfolioRiskEngine decision into Trading Guardian evaluation.

Does NOT replace TG. Risk BLOCK forces deny; TG retains other checks.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.portfolio_risk_engine.engine import PortfolioRiskEngine
from saathi.platform.portfolio_risk_engine.models import RiskResult, TradeProposal
from saathi.platform.fund_ledger.money import D


def compose_guardian_with_risk(
    guardian: Any,
    risk_engine: PortfolioRiskEngine,
    intent: Any,
    *,
    account: Any,
    ref_price: Decimal,
    price_quality: Any,
    market_state: Any,
    marks: dict | None = None,
    fund_id: str,
    ledger_state: dict | None = None,
    recon: dict | None = None,
) -> dict:
    """Run TG evaluate + risk evaluate_proposed_trade; combine fail-closed.

    Returns public dict: allowed, reasons, checks, risk_decision, portfolio_input_source.
    """
    tg_decision = guardian.evaluate(
        intent,
        account=account,
        ref_price=ref_price,
        price_quality=price_quality,
        market_state=market_state,
        marks=marks,
    )
    pub = tg_decision.to_public() if hasattr(tg_decision, "to_public") else dict(tg_decision)

    side = intent.side.value if hasattr(intent.side, "value") else str(intent.side)
    prop = TradeProposal(
        symbol=intent.symbol,
        side=side,
        quantity=D(intent.quantity),
        price=D(ref_price),
    )
    risk = risk_engine.evaluate_proposed_trade(
        fund_id, prop, ledger_state=ledger_state, recon=recon
    )
    risk_pub = risk.to_public()
    pub["risk_decision"] = risk_pub
    pub["risk_result"] = risk.result.value
    pub["risk_state"] = risk.risk_state.value
    pub["risk_reason_codes"] = list(risk.reason_codes)

    if risk.result in (RiskResult.BLOCK, RiskResult.DATA_INSUFFICIENT):
        pub["allowed"] = False
        for code in risk.reason_codes:
            detail = f"risk_engine:{code}"
            if detail not in pub.get("reasons", []):
                pub.setdefault("reasons", []).append(detail)
        pub.setdefault("checks", []).append(
            {
                "check": "portfolio_risk_engine",
                "ok": False,
                "detail": ",".join(risk.reason_codes) or risk.result.value,
            }
        )
    else:
        pub.setdefault("checks", []).append(
            {
                "check": "portfolio_risk_engine",
                "ok": True,
                "detail": risk.result.value,
            }
        )
        # WARN does not deny by itself
    pub["authorizes_execution"] = False
    pub["mode"] = "PAPER"
    return pub
