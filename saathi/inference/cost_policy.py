"""M21.2 / M24 — Deterministic cost metadata, estimation, and policy enforcement.

Uses Decimal for enforcement arithmetic (no binary float ceilings).
Does not fetch live pricing.

M24: daily budget authority is the durable governance store.
``InMemoryDailyCostStore`` remains for isolated unit tests only — not
production authority (see ``process_daily_store`` / ``durable_daily_store``).
"""
from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from enum import Enum
from typing import Any, Optional, Protocol


class CostStatus(str, Enum):
    KNOWN = "known"
    ESTIMATED = "estimated"
    STALE = "stale"
    UNKNOWN = "unknown"
    ZERO_MARGINAL = "zero_marginal"
    NOT_APPLICABLE = "not_applicable"


SUPPORTED_CURRENCIES = frozenset({"USD"})
_STALE_SECONDS_DEFAULT = 90 * 24 * 3600  # 90 days
_MICRO = Decimal("0.000001")
_MILLION = Decimal("1000000")


def _d(value: Any) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        d = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return d


def _q(d: Decimal) -> Decimal:
    return d.quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class PricingMetadata:
    """Versioned pricing row (from provider policy, not live web)."""

    currency: str = "USD"
    input_cost_per_million: Optional[str] = None  # decimal string
    output_cost_per_million: Optional[str] = None
    request_fixed_cost: Optional[str] = None
    cost_source: str = "provider_policy"
    cost_confidence: str = "unknown"  # known | estimated | stale | unknown | zero_marginal
    cost_updated_at: float = 0.0
    zero_marginal: bool = False
    known: bool = False
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def status(self, *, now: Optional[float] = None, stale_after: float = _STALE_SECONDS_DEFAULT) -> CostStatus:
        if self.zero_marginal:
            return CostStatus.ZERO_MARGINAL
        if not self.known and not self.input_cost_per_million and not self.output_cost_per_million:
            return CostStatus.UNKNOWN
        ts = float(self.cost_updated_at or 0.0)
        tnow = float(now if now is not None else time.time())
        # Versioned provider_policy pricing is not calendar-stale unless confidence says so
        src = (self.cost_source or "")
        if ts > 0 and (tnow - ts) > stale_after and not src.startswith("m21.2.provider_policy"):
            return CostStatus.STALE
        if self.cost_confidence == "stale":
            return CostStatus.STALE
        if self.cost_confidence == "estimated" or not self.known:
            if self.input_cost_per_million or self.output_cost_per_million:
                return CostStatus.ESTIMATED
            return CostStatus.UNKNOWN
        return CostStatus.KNOWN


@dataclass(frozen=True)
class CostEstimate:
    input_tokens_estimate: int
    output_tokens_ceiling: int
    input_unit_cost: str  # decimal string USD
    output_unit_cost: str
    fixed_cost: str
    estimated_total: str
    maximum_possible: str
    currency: str
    status: CostStatus
    cost_source: str
    cost_confidence: str
    pricing_freshness: str  # fresh | stale | n/a
    reason_code: str = "ok"
    notes: str = ""

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @property
    def total_decimal(self) -> Decimal:
        return _d(self.estimated_total) or Decimal("0")

    @property
    def maximum_decimal(self) -> Decimal:
        return _d(self.maximum_possible) or Decimal("0")


@dataclass(frozen=True)
class CostPolicyVerdict:
    allowed: bool
    reason_code: str
    explanation: str
    estimate: Optional[CostEstimate] = None
    ceiling_applied: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason_code": self.reason_code,
            "explanation": self.explanation,
            "estimate": self.estimate.to_dict() if self.estimate else None,
            "ceiling_applied": self.ceiling_applied,
        }


class DailyCostStore(Protocol):
    """Testable accounting interface — M24 durable authority via DurableDailyCostStore."""

    def get_daily_spend(self, caller_id: str, day_key: str) -> Decimal: ...

    def add_spend(self, caller_id: str, day_key: str, amount: Decimal) -> None: ...


class InMemoryDailyCostStore:
    """TEST_FAKE only — process-local, not production authority (M24).

    Production and default paths must use ``DurableDailyCostStore`` /
    ``durable_daily_store()``. Release checks flag any production import of
    this class as authoritative spend mutation.
    """

    authority = "test_fake_process_local"

    def __init__(self) -> None:
        self._spend: dict[tuple[str, str], Decimal] = {}

    def get_daily_spend(self, caller_id: str, day_key: str) -> Decimal:
        return self._spend.get((caller_id, day_key), Decimal("0"))

    def add_spend(self, caller_id: str, day_key: str, amount: Decimal) -> None:
        if isinstance(amount, float):
            raise TypeError("binary float money rejected")
        key = (caller_id, day_key)
        self._spend[key] = self.get_daily_spend(caller_id, day_key) + Decimal(str(amount))


class DurableDailyCostStore:
    """M24 authoritative daily cost view over the durable governance store."""

    authority = "canonical_durable"

    def __init__(self, store: Any = None) -> None:
        self._store = store

    def _gov(self) -> Any:
        if self._store is not None:
            return self._store
        from saathi.inference.governance_store import get_governance_store

        return get_governance_store()

    def get_daily_spend(self, caller_id: str, day_key: str) -> Decimal:
        return self._gov().get_daily_spend(caller_id, day_key)

    def add_spend(self, caller_id: str, day_key: str, amount: Decimal) -> None:
        """Direct add_spend is not the production path — use reservations.

        Provided for protocol compatibility in tests that settle via ledger;
        production must reserve → settle through governance_store.
        """
        if isinstance(amount, float):
            raise TypeError("binary float money rejected")
        # Record as a zero-scope settled usage only when explicitly invoked.
        # Prefer reserve/settle. This path creates a synthetic settled entry.
        from saathi.inference.governance_store import ACTUAL

        gov = self._gov()
        attempt_id = f"legacy_add:{caller_id}:{day_key}:{amount}:{gov.now()}"
        rsv = gov.reserve_budget(
            request_id=f"legacy_add:{caller_id}",
            attempt_id=attempt_id,
            caller_id=caller_id,
            provider_id="system",
            amount=Decimal(str(amount)),
            zero_cost=Decimal(str(amount)) == 0,
            daily_budget=None,
        )
        gov.mark_attempt_started(rsv["reservation_id"])
        gov.settle_reservation(
            rsv["reservation_id"],
            actual_cost=Decimal(str(amount)),
            usage_status=ACTUAL,
            notes="legacy_add_spend",
        )


def durable_daily_store() -> DurableDailyCostStore:
    """Canonical production daily cost store (M24)."""
    return DurableDailyCostStore()


def process_daily_store() -> DailyCostStore:
    """Return the production daily cost authority (durable as of M24).

    Name preserved for compatibility. No longer returns process-local state.
    """
    return durable_daily_store()


def estimate_input_tokens(text: str, *, chars_per_token: int = 4) -> int:
    """Conservative char-based estimate (deterministic)."""
    n = max(0, len(text or ""))
    cpt = max(1, int(chars_per_token))
    return max(1, (n + cpt - 1) // cpt) if n else 0


def validate_pricing(pricing: PricingMetadata) -> list[str]:
    errors: list[str] = []
    cur = (pricing.currency or "").upper()
    if cur and cur not in SUPPORTED_CURRENCIES:
        errors.append(f"unsupported_currency:{cur}")
    for label, raw in (
        ("input", pricing.input_cost_per_million),
        ("output", pricing.output_cost_per_million),
        ("fixed", pricing.request_fixed_cost),
    ):
        if raw is None or raw == "":
            continue
        d = _d(raw)
        if d is None:
            errors.append(f"malformed_price:{label}")
        elif d < 0:
            errors.append(f"negative_price:{label}")
        elif d > Decimal("1000000"):
            errors.append(f"extreme_price:{label}")
    return errors


def estimate_cost(
    pricing: PricingMetadata,
    *,
    input_tokens: int,
    output_tokens_ceiling: int,
    now: Optional[float] = None,
) -> CostEstimate:
    """Deterministic cost estimate. Unknown paid → status UNKNOWN (not zero)."""
    errs = validate_pricing(pricing)
    status = pricing.status(now=now)
    freshness = "n/a"
    if pricing.cost_updated_at:
        st = pricing.status(now=now)
        freshness = "stale" if st is CostStatus.STALE else "fresh"

    if pricing.zero_marginal:
        return CostEstimate(
            input_tokens_estimate=max(0, int(input_tokens)),
            output_tokens_ceiling=max(0, int(output_tokens_ceiling)),
            input_unit_cost="0",
            output_unit_cost="0",
            fixed_cost="0",
            estimated_total="0",
            maximum_possible="0",
            currency=(pricing.currency or "USD").upper(),
            status=CostStatus.ZERO_MARGINAL,
            cost_source=pricing.cost_source,
            cost_confidence="zero_marginal",
            pricing_freshness=freshness,
            reason_code="zero_marginal",
            notes=pricing.notes,
        )

    if errs:
        return CostEstimate(
            input_tokens_estimate=max(0, int(input_tokens)),
            output_tokens_ceiling=max(0, int(output_tokens_ceiling)),
            input_unit_cost="0",
            output_unit_cost="0",
            fixed_cost="0",
            estimated_total="0",
            maximum_possible="0",
            currency=(pricing.currency or "USD").upper(),
            status=CostStatus.UNKNOWN,
            cost_source=pricing.cost_source,
            cost_confidence="invalid",
            pricing_freshness=freshness,
            reason_code="invalid_pricing",
            notes=";".join(errs),
        )

    in_m = _d(pricing.input_cost_per_million)
    out_m = _d(pricing.output_cost_per_million)
    fixed = _d(pricing.request_fixed_cost) or Decimal("0")

    if in_m is None and out_m is None and not pricing.zero_marginal:
        return CostEstimate(
            input_tokens_estimate=max(0, int(input_tokens)),
            output_tokens_ceiling=max(0, int(output_tokens_ceiling)),
            input_unit_cost="0",
            output_unit_cost="0",
            fixed_cost=str(_q(fixed)),
            estimated_total="0",
            maximum_possible="0",
            currency=(pricing.currency or "USD").upper(),
            status=CostStatus.UNKNOWN,
            cost_source=pricing.cost_source,
            cost_confidence="unknown",
            pricing_freshness=freshness,
            reason_code="unknown_pricing",
            notes="unknown price is not treated as zero for paid paths",
        )

    in_m = in_m or Decimal("0")
    out_m = out_m or Decimal("0")
    it = Decimal(max(0, int(input_tokens)))
    ot = Decimal(max(0, int(output_tokens_ceiling)))
    # cost = tokens/1e6 * per_million + fixed
    est = (it / _MILLION) * in_m + (ot / _MILLION) * out_m + fixed
    # maximum uses full output ceiling (same for pilot)
    maximum = est
    conf = pricing.cost_confidence if pricing.known else "estimated"
    if status is CostStatus.STALE:
        conf = "stale"
    return CostEstimate(
        input_tokens_estimate=int(it),
        output_tokens_ceiling=int(ot),
        input_unit_cost=str(_q(in_m)),
        output_unit_cost=str(_q(out_m)),
        fixed_cost=str(_q(fixed)),
        estimated_total=str(_q(est)),
        maximum_possible=str(_q(maximum)),
        currency=(pricing.currency or "USD").upper(),
        status=status if status is not CostStatus.UNKNOWN else CostStatus.ESTIMATED,
        cost_source=pricing.cost_source,
        cost_confidence=conf,
        pricing_freshness=freshness,
        reason_code="ok",
        notes=pricing.notes,
    )


def enforce_cost_policy(
    estimate: CostEstimate,
    *,
    request_ceiling: Optional[float | str | Decimal] = None,
    caller_ceiling: Optional[float | str | Decimal] = None,
    provider_ceiling: Optional[float | str | Decimal] = None,
    cloud_fallback: bool = False,
    paid_provider: bool = False,
    allow_unknown_paid: bool = False,
    daily_budget: Optional[float | str | Decimal] = None,
    daily_spent: Optional[Decimal] = None,
    currency: str = "USD",
) -> CostPolicyVerdict:
    """Fail closed for automatic paid fallback when price unknown/stale/over ceiling."""
    cur = (estimate.currency or currency or "USD").upper()
    if cur not in SUPPORTED_CURRENCIES:
        return CostPolicyVerdict(
            False,
            "currency_mismatch",
            f"Unsupported currency {cur}",
            estimate=estimate,
        )

    if paid_provider or cloud_fallback:
        if estimate.status in {CostStatus.UNKNOWN, CostStatus.NOT_APPLICABLE}:
            if not allow_unknown_paid:
                return CostPolicyVerdict(
                    False,
                    "unknown_pricing",
                    "Unknown paid pricing — automatic fallback denied",
                    estimate=estimate,
                )
        if estimate.status is CostStatus.STALE and cloud_fallback:
            return CostPolicyVerdict(
                False,
                "stale_pricing",
                "Stale pricing — automatic paid fallback denied",
                estimate=estimate,
            )
        if estimate.reason_code == "invalid_pricing":
            return CostPolicyVerdict(
                False,
                "invalid_pricing",
                "Malformed pricing metadata — fail closed",
                estimate=estimate,
            )

    total = estimate.maximum_decimal
    for label, raw in (
        ("request", request_ceiling),
        ("caller", caller_ceiling),
        ("provider", provider_ceiling),
    ):
        if raw is None:
            continue
        ceil = _d(raw)
        if ceil is None:
            return CostPolicyVerdict(False, "malformed_ceiling", f"Invalid {label} ceiling", estimate)
        if ceil < 0:
            return CostPolicyVerdict(False, "negative_ceiling", f"Negative {label} ceiling", estimate)
        if ceil == 0 and paid_provider and total > 0:
            return CostPolicyVerdict(
                False,
                f"{label}_ceiling",
                f"{label} cost ceiling is zero — paid spend denied",
                estimate=estimate,
                ceiling_applied=str(ceil),
            )
        if ceil > 0 and total > ceil:
            return CostPolicyVerdict(
                False,
                f"{label}_ceiling",
                f"Estimated cost exceeds {label} ceiling",
                estimate=estimate,
                ceiling_applied=str(ceil),
            )

    if daily_budget is not None:
        bud = _d(daily_budget)
        spent = daily_spent if daily_spent is not None else Decimal("0")
        if bud is not None and bud > 0 and (spent + total) > bud:
            return CostPolicyVerdict(
                False,
                "daily_budget",
                "Daily caller budget would be exceeded (durable accounting)",
                estimate=estimate,
                ceiling_applied=str(bud),
            )

    return CostPolicyVerdict(True, "ok", "Cost policy satisfied", estimate=estimate)
