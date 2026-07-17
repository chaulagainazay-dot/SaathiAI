"""M24 — Provider governance service (reservation protocol + recovery CLI surface).

Single orchestration layer over DurableGovernanceStore for:
  reserve → execute → settle/release
  circuit outcomes
  stale reservation recovery
  operator controls

Adapters and callers must not write ledger rows directly — use this service
or governance_store methods invoked from the decision/execution path.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

from saathi.inference.cost_policy import CostEstimate, CostStatus
from saathi.inference.governance_errors import GovernanceError, GovernanceErrorCode
from saathi.inference.governance_store import (
    ACTUAL,
    ESTIMATED,
    ZERO,
    DurableGovernanceStore,
    get_governance_store,
)


def new_attempt_id() -> str:
    return f"att_{uuid.uuid4().hex}"


def new_request_id() -> str:
    return f"req_{uuid.uuid4().hex}"


@dataclass(frozen=True)
class AttemptPlan:
    request_id: str
    attempt_id: str
    attempt_number: int
    caller_id: str
    provider_id: str
    model_id: str
    reservation_id: str
    reserved_amount: str
    currency: str
    zero_cost: bool


class GovernanceService:
    """Canonical orchestration for durable provider governance."""

    def __init__(self, store: Optional[DurableGovernanceStore] = None) -> None:
        self._store = store

    @property
    def store(self) -> DurableGovernanceStore:
        return self._store or get_governance_store()

    def reserve_for_attempt(
        self,
        *,
        request_id: str,
        caller_id: str,
        provider_id: str,
        model_id: str = "",
        estimate: Optional[CostEstimate] = None,
        amount: Optional[Any] = None,
        daily_budget: Optional[Any] = None,
        attempt_id: Optional[str] = None,
        attempt_number: int = 1,
        currency: str = "USD",
        paid_provider: bool = False,
        zero_marginal: bool = False,
        idempotency_key: Optional[str] = None,
    ) -> AttemptPlan:
        """Create reservation before provider transport.

        Zero-marginal local providers get an explicit zero reservation.
        Paid providers with unknown cost fail closed (no reservation).
        """
        att = attempt_id or new_attempt_id()
        zero = bool(zero_marginal)
        cur = currency
        if estimate is not None:
            cur = estimate.currency or currency
            if estimate.status is CostStatus.ZERO_MARGINAL:
                zero = True
            if paid_provider and estimate.status in {
                CostStatus.UNKNOWN,
                CostStatus.NOT_APPLICABLE,
            }:
                raise GovernanceError(
                    GovernanceErrorCode.COST_UNKNOWN,
                    "Unknown paid pricing — reservation denied",
                )
            amt = Decimal("0") if zero else estimate.maximum_decimal
        elif amount is not None:
            amt = Decimal("0") if zero else amount
        else:
            amt = Decimal("0")
            zero = True

        rsv = self.store.reserve_budget(
            request_id=request_id,
            attempt_id=att,
            caller_id=caller_id,
            provider_id=provider_id,
            model_id=model_id,
            currency=cur,
            amount=amt if not isinstance(amt, Decimal) else amt,
            daily_budget=daily_budget,
            idempotency_key=idempotency_key or f"res:{att}",
            zero_cost=zero,
        )
        return AttemptPlan(
            request_id=request_id,
            attempt_id=att,
            attempt_number=int(attempt_number),
            caller_id=caller_id,
            provider_id=provider_id,
            model_id=model_id,
            reservation_id=rsv["reservation_id"],
            reserved_amount=str(rsv["reserved_amount"]),
            currency=str(rsv["currency"]),
            zero_cost=zero,
        )

    def begin_attempt(self, plan: AttemptPlan) -> None:
        """Mark reservation as execution-started (crash recovery signal)."""
        self.store.mark_attempt_started(plan.reservation_id)

    def settle_attempt(
        self,
        plan: AttemptPlan,
        *,
        actual_cost: Any = None,
        input_units: int = 0,
        output_units: int = 0,
        estimated_only: bool = False,
    ) -> dict[str, Any]:
        if actual_cost is None:
            actual_cost = plan.reserved_amount if plan.zero_cost else plan.reserved_amount
        status = ZERO if plan.zero_cost else (ESTIMATED if estimated_only else ACTUAL)
        if plan.zero_cost:
            actual_cost = "0"
        return self.store.settle_reservation(
            plan.reservation_id,
            actual_cost=actual_cost,
            input_units=input_units,
            output_units=output_units,
            usage_status=status,
            idempotency_key=f"usg:{plan.attempt_id}",
        )

    def release_attempt(
        self, plan: AttemptPlan, *, reason: str = "pre_transport_release"
    ) -> dict[str, Any]:
        return self.store.release_reservation(
            plan.reservation_id, reason_code=reason
        )

    def recover(self) -> dict[str, Any]:
        return self.store.recover_stale_reservations()

    def readiness(self) -> dict[str, Any]:
        return self.store.readiness()


_SVC: Optional[GovernanceService] = None


def get_governance_service(
    *, store: Optional[DurableGovernanceStore] = None
) -> GovernanceService:
    global _SVC
    if store is not None:
        return GovernanceService(store)
    if _SVC is None:
        _SVC = GovernanceService()
    return _SVC
