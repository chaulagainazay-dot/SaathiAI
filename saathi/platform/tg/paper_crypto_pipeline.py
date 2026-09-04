"""PAPER-CRYPTO-2 — canonical paper cycle orchestration.

Composes the already-certified authorities in their non-negotiable order and
stops at the first refusal:

    TradingIntentProposal
      -> PortfolioConstructionEngine   (proposes weights)
      -> PortfolioRiskEngine           (hard deterministic limits)
      -> Trading Guardian venue policy (independent safety boundary)
      -> Approval                      (never auto-granted)
      -> [ExecutionGateway]            (canonical; NOT called from here)

This orchestrator holds NO execution authority. Its best possible outcome is
READY_FOR_EXECUTION_GATEWAY: a venue-normalized execution *plan* an authorized
caller may hand to the ExecutionGateway. It never submits an order, never mutates
the ledger, never approves itself, and never upgrades a strategy status. A zero
allocation is a valid, successful outcome — not an error and not a reason to force
investment.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from saathi.platform.portfolio_construction.engine import PortfolioConstructionEngine
from saathi.platform.portfolio_construction.models import CandidatePortfolioStatus
from saathi.platform.portfolio_risk_engine.budget import PAPER_BUDGET_V2
from saathi.platform.portfolio_risk_engine.engine import PortfolioRiskEngine
from saathi.platform.portfolio_risk_engine.models import RiskResult
from saathi.platform.tg.paper_simulation.conventions import normalize_order
from saathi.platform.tg.venue_policy import evaluate_venue, venue_for


class PaperCycleStage(str, Enum):
    CONSTRUCTION = "CONSTRUCTION"
    RISK = "RISK"
    GUARDIAN_VENUE = "GUARDIAN_VENUE"
    APPROVAL = "APPROVAL"
    EXECUTION_PLAN = "EXECUTION_PLAN"


class PaperCycleOutcome(str, Enum):
    NO_ALLOCATION = "NO_ALLOCATION"                        # valid: propose nothing
    BLOCKED_CONSTRUCTION = "BLOCKED_CONSTRUCTION"
    BLOCKED_RISK = "BLOCKED_RISK"
    BLOCKED_GUARDIAN = "BLOCKED_GUARDIAN"
    BLOCKED_CONVENTION = "BLOCKED_CONVENTION"
    APPROVAL_REQUIRED = "APPROVAL_REQUIRED"
    READY_FOR_EXECUTION_GATEWAY = "READY_FOR_EXECUTION_GATEWAY"


@dataclass(frozen=True)
class PlannedOrder:
    instrument_id: str
    symbol: str
    venue: str
    target_weight: Decimal
    target_notional: Decimal
    quantity: Decimal | None
    reasons: tuple[str, ...] = ()


@dataclass
class PaperCycleDecision:
    stage: PaperCycleStage
    outcome: PaperCycleOutcome
    reason_codes: tuple[str, ...] = ()
    candidate_status: str = ""
    risk_result: str = ""
    venue_results: tuple[dict, ...] = ()
    planned_orders: tuple[PlannedOrder, ...] = ()
    # Structural invariant: this orchestrator never authorizes execution.
    authorizes_execution: bool = field(default=False, init=False)

    @property
    def ready(self) -> bool:
        return self.outcome == PaperCycleOutcome.READY_FOR_EXECUTION_GATEWAY

    def to_public(self) -> dict:
        return {
            "stage": self.stage.value,
            "outcome": self.outcome.value,
            "reason_codes": list(self.reason_codes),
            "candidate_status": self.candidate_status,
            "risk_result": self.risk_result,
            "planned_orders": [
                {
                    "instrument_id": o.instrument_id,
                    "symbol": o.symbol,
                    "venue": o.venue,
                    "target_weight": str(o.target_weight),
                    "quantity": None if o.quantity is None else str(o.quantity),
                }
                for o in self.planned_orders
            ],
            "authorizes_execution": False,
            "mode": "PAPER",
        }


class PaperCryptoPipeline:
    """Deterministic paper cycle. Read-only with respect to every authority."""

    def __init__(self, *, construction=None, risk=None) -> None:
        self.construction = construction or PortfolioConstructionEngine()
        self.risk = risk or PortfolioRiskEngine(budget=PAPER_BUDGET_V2)

    def run(
        self,
        request,
        *,
        portfolio_snapshot,
        disabled_venues=(),
        require_session: bool = False,
        session_open: bool | None = None,
        approval_granted: bool = False,
        price_map: dict | None = None,
    ) -> PaperCycleDecision:
        # 1. Construction proposes.
        candidate = self.construction.construct_from_intents(request)
        status = getattr(candidate.status, "value", str(candidate.status))
        if candidate.status == CandidatePortfolioStatus.ZERO_ALLOCATION:
            # A deliberate zero is a valid, successful proposal — never forced investment.
            return PaperCycleDecision(
                PaperCycleStage.CONSTRUCTION, PaperCycleOutcome.NO_ALLOCATION,
                ("ZERO_ALLOCATION",), candidate_status=status,
            )
        if candidate.status not in (
            CandidatePortfolioStatus.CANDIDATE_ALLOCATION,
            CandidatePortfolioStatus.REDUCED_ALLOCATION,
        ):
            # Unknown construction status: fail closed rather than assume it is safe.
            return PaperCycleDecision(
                PaperCycleStage.CONSTRUCTION, PaperCycleOutcome.BLOCKED_CONSTRUCTION,
                (status,), candidate_status=status,
            )

        active = tuple(a for a in candidate.allocations if a.target_weight > 0)
        if not active:
            # Zero allocation is a legitimate result, never forced investment.
            return PaperCycleDecision(
                PaperCycleStage.CONSTRUCTION, PaperCycleOutcome.NO_ALLOCATION,
                ("ZERO_ALLOCATION",), candidate_status=status,
            )

        # 2. Risk enforces hard limits.
        risk_decision = self.risk.evaluate_candidate_portfolio(
            candidate, portfolio_snapshot=portfolio_snapshot
        )
        risk_result = getattr(risk_decision.result, "value", str(risk_decision.result))
        if risk_decision.result != RiskResult.ALLOW:
            return PaperCycleDecision(
                PaperCycleStage.RISK, PaperCycleOutcome.BLOCKED_RISK,
                tuple(risk_decision.reason_codes), candidate_status=status,
                risk_result=risk_result,
            )

        # 3. Guardian venue policy — independent of construction and risk.
        venue_results = []
        for alloc in active:
            res = evaluate_venue(
                alloc.symbol,
                disabled_venues=disabled_venues,
                require_session=require_session,
                session_open=session_open,
            )
            venue_results.append(res)
        blocked = [r for r in venue_results if not r["ok"]]
        if blocked:
            return PaperCycleDecision(
                PaperCycleStage.GUARDIAN_VENUE, PaperCycleOutcome.BLOCKED_GUARDIAN,
                tuple(r["reason"] for r in blocked), candidate_status=status,
                risk_result=risk_result, venue_results=tuple(venue_results),
            )

        # 4. Approval is never self-granted.
        if not approval_granted:
            return PaperCycleDecision(
                PaperCycleStage.APPROVAL, PaperCycleOutcome.APPROVAL_REQUIRED,
                ("APPROVAL_REQUIRED",), candidate_status=status,
                risk_result=risk_result, venue_results=tuple(venue_results),
            )

        # 5. Venue-normalized execution plan (handed onward, never executed here).
        orders: list[PlannedOrder] = []
        rejects: list[str] = []
        for alloc in active:
            qty = None
            reasons: tuple[str, ...] = ()
            price = (price_map or {}).get(alloc.symbol) or (price_map or {}).get(alloc.instrument_id)
            if price:
                raw_qty = alloc.target_notional / Decimal(str(price))
                norm = normalize_order(alloc.symbol, raw_qty)
                reasons = norm.reasons
                if not norm.accepted:
                    rejects.extend(norm.reasons)
                    continue
                qty = norm.quantity
            orders.append(PlannedOrder(
                instrument_id=alloc.instrument_id, symbol=alloc.symbol,
                venue=venue_for(alloc.symbol), target_weight=alloc.target_weight,
                target_notional=alloc.target_notional, quantity=qty, reasons=reasons,
            ))

        if rejects and not orders:
            return PaperCycleDecision(
                PaperCycleStage.EXECUTION_PLAN, PaperCycleOutcome.BLOCKED_CONVENTION,
                tuple(rejects), candidate_status=status, risk_result=risk_result,
                venue_results=tuple(venue_results),
            )

        return PaperCycleDecision(
            PaperCycleStage.EXECUTION_PLAN, PaperCycleOutcome.READY_FOR_EXECUTION_GATEWAY,
            tuple(rejects), candidate_status=status, risk_result=risk_result,
            venue_results=tuple(venue_results), planned_orders=tuple(orders),
        )
