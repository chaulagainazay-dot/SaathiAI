"""Daily paper portfolio reconciliation — fail closed on mismatch."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from saathi.platform.tg.paper_activation.models import D, PaperPortfolio, RiskHaltReason
from saathi.platform.tg.portfolio import ReconciliationVerdict


def reconcile_portfolio(
    portfolio: PaperPortfolio,
    *,
    orders: list[Any] | None = None,
    journal_count: int | None = None,
) -> dict[str, Any]:
    findings: list[dict[str, str]] = []
    warnings: list[str] = []

    # Cash consistency: cash >= 0
    if portfolio.cash < 0:
        findings.append({"code": "NEGATIVE_CASH", "detail": str(portfolio.cash)})

    # Position consistency: no negative longs
    for sym, pos in portfolio.positions.items():
        if pos.quantity < 0:
            findings.append({"code": "NEGATIVE_POSITION", "detail": f"{sym}:{pos.quantity}"})
        # lot sum vs quantity
        lot_sum = sum((l.quantity for l in pos.lots), Decimal("0"))
        if pos.lots and abs(lot_sum - pos.quantity) > Decimal("0.0001"):
            findings.append({
                "code": "LOT_QTY_MISMATCH",
                "detail": f"{sym}: lots={lot_sum} pos={pos.quantity}",
            })

    # Equity reconstruction
    eq = portfolio.compute_equity()
    pos_val = sum(
        (p.quantity * portfolio.marks.get(s, p.avg_price) for s, p in portfolio.positions.items()),
        Decimal("0"),
    )
    recon_eq = portfolio.cash + pos_val
    if abs(eq - recon_eq) > Decimal("0.02"):
        findings.append({
            "code": "EQUITY_MISMATCH",
            "detail": f"equity={eq} reconstructed={recon_eq}",
        })

    # Ledger vs realized (soft)
    ledger_fees = sum((D(t.get("fee", 0)) for t in portfolio.trade_ledger), Decimal("0"))
    if portfolio.trade_ledger and abs(ledger_fees - portfolio.fees_paid) > Decimal("0.05"):
        warnings.append(f"fee_ledger_drift fees_paid={portfolio.fees_paid} ledger={ledger_fees}")

    # Order consistency
    if orders is not None:
        for o in orders:
            st = getattr(o, "status", None)
            stv = st.value if hasattr(st, "value") else str(st or "")
            fq = D(getattr(o, "filled_qty", 0))
            q = D(getattr(o, "quantity", 0))
            if stv == "FILLED" and fq + Decimal("0.0000001") < q:
                findings.append({"code": "ORDER_FILL_MISMATCH", "detail": getattr(o, "id", "")})
            if stv == "FILLED" and not getattr(o, "fills", None):
                findings.append({"code": "FILLED_WITHOUT_FILLS_RECORDS", "detail": getattr(o, "id", "")})

    if journal_count is not None and portfolio.trade_ledger and journal_count < 0:
        findings.append({"code": "JOURNAL_INVALID", "detail": str(journal_count)})

    if findings:
        verdict = ReconciliationVerdict.UNRECONCILED_BLOCKED
    elif warnings:
        verdict = ReconciliationVerdict.RECONCILED_WITH_WARNINGS
    else:
        verdict = ReconciliationVerdict.RECONCILED

    return {
        "verdict": verdict.value,
        "findings": findings,
        "warnings": warnings,
        "equity": str(eq),
        "cash": str(portfolio.cash),
        "positions_value": str(pos_val),
        "trade_count": len(portfolio.trade_ledger),
        "fail_closed": verdict == ReconciliationVerdict.UNRECONCILED_BLOCKED,
        "blocks_new_orders": verdict == ReconciliationVerdict.UNRECONCILED_BLOCKED,
        "paper_only": True,
        "funds_label": "SIMULATED",
        "disclaimer": "Paper reconciliation only — no live broker positions.",
    }


def apply_reconciliation_halt(
    portfolio: PaperPortfolio,
    result: dict[str, Any],
) -> PaperPortfolio | None:
    if result.get("fail_closed"):
        from saathi.platform.tg.paper_activation.models import PortfolioStatus
        portfolio.status = PortfolioStatus.HALTED
        portfolio.halt_reason = RiskHaltReason.UNRECONCILED
        portfolio.halt_detail = str(result.get("findings"))
        portfolio.audit("reconciliation_halt", findings=result.get("findings"))
        return portfolio
    return None
