"""Paper reconciliation: OMS fills vs ledger fills (no silent repair)."""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any, Iterable

from saathi.platform.fund_ledger.money import D, q_money, q_qty
from saathi.platform.fund_ledger.models import EventType, LedgerEvent, PortfolioState


@dataclass
class ReconIssue:
    code: str
    detail: str
    severity: str = "ERROR"  # ERROR | WARN

    def to_public(self) -> dict:
        return {"code": self.code, "detail": self.detail, "severity": self.severity}


@dataclass
class ReconReport:
    fund_id: str
    ok: bool
    issues: list[ReconIssue] = field(default_factory=list)
    oms_fill_count: int = 0
    ledger_fill_count: int = 0
    cash_ledger: str = "0"
    cash_expected: str | None = None

    def to_public(self) -> dict:
        return {
            "fund_id": self.fund_id,
            "ok": self.ok,
            "issues": [i.to_public() for i in self.issues],
            "oms_fill_count": self.oms_fill_count,
            "ledger_fill_count": self.ledger_fill_count,
            "cash_ledger": self.cash_ledger,
            "cash_expected": self.cash_expected,
            "mode": "PAPER",
        }


def reconcile_fills(
    *,
    fund_id: str,
    ledger_events: Iterable[LedgerEvent],
    oms_fills: Iterable[dict[str, Any]],
    state: PortfolioState | None = None,
    expected_cash: Decimal | None = None,
) -> ReconReport:
    """Compare OMS-provided fills to ledger BUY/SELL fill events.

    oms_fills items: {fill_id, security_id|symbol, side, quantity, price, fee?}
    """
    events = list(ledger_events)
    ledger_fills = [
        e
        for e in events
        if e.event_type in (EventType.BUY_FILL, EventType.SELL_FILL)
        or (isinstance(e.event_type, str) and e.event_type in ("BUY_FILL", "SELL_FILL"))
    ]
    oms = list(oms_fills)
    issues: list[ReconIssue] = []

    ledger_by_ref: dict[str, LedgerEvent] = {}
    for e in ledger_fills:
        key = e.fill_ref or e.event_id
        if key in ledger_by_ref:
            issues.append(ReconIssue("DUPLICATE_LEDGER_FILL", f"fill_ref={key}"))
        ledger_by_ref[key] = e

    oms_ids = set()
    for f in oms:
        fid = str(f.get("fill_id") or f.get("id") or "")
        if not fid:
            issues.append(ReconIssue("OMS_FILL_MISSING_ID", str(f)))
            continue
        if fid in oms_ids:
            issues.append(ReconIssue("DUPLICATE_OMS_FILL", fid))
        oms_ids.add(fid)
        if fid not in ledger_by_ref:
            issues.append(ReconIssue("MISSING_FILL", f"OMS fill {fid} not in ledger"))
        else:
            le = ledger_by_ref[fid]
            if q_qty(f.get("quantity")) != q_qty(le.quantity):
                issues.append(
                    ReconIssue(
                        "QUANTITY_MISMATCH",
                        f"{fid} oms={f.get('quantity')} ledger={le.quantity}",
                    )
                )
            if D(f.get("price")) != D(le.price):
                # price compare at price scale
                if abs(D(f.get("price")) - D(le.price)) > D("0.000001"):
                    issues.append(
                        ReconIssue(
                            "PRICE_MISMATCH",
                            f"{fid} oms={f.get('price')} ledger={le.price}",
                        )
                    )

    for ref, le in ledger_by_ref.items():
        if ref not in oms_ids and oms:
            # only flag if OMS list was provided non-empty
            issues.append(ReconIssue("EXTRA_LEDGER_FILL", f"ledger fill {ref} not in OMS set"))

    cash_ledger = state.cash if state else None
    if expected_cash is not None and cash_ledger is not None:
        if q_money(cash_ledger) != q_money(expected_cash):
            issues.append(
                ReconIssue(
                    "CASH_MISMATCH",
                    f"ledger={cash_ledger} expected={expected_cash}",
                )
            )

    if state and state.invariants:
        for inv in state.invariants:
            issues.append(ReconIssue("INVARIANT", inv))

    return ReconReport(
        fund_id=fund_id,
        ok=len([i for i in issues if i.severity == "ERROR"]) == 0,
        issues=issues,
        oms_fill_count=len(oms),
        ledger_fill_count=len(ledger_fills),
        cash_ledger=str(q_money(cash_ledger)) if cash_ledger is not None else "0",
        cash_expected=str(q_money(expected_cash)) if expected_cash is not None else None,
    )
