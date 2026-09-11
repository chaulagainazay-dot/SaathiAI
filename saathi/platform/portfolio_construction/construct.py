"""Target weight constructors (deterministic, no leverage/shorts)."""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from saathi.platform.fund_ledger.money import D, q_money
from saathi.platform.portfolio_construction.models import (
    RC_EQUAL_WEIGHT_BASELINE,
    RC_FIXED_TARGET,
    RC_NO_ELIGIBLE_UNIVERSE,
    RC_SIGNAL_STRENGTH_INCREASE,
    RC_SHORTS_DISABLED,
    RC_TARGET_REDUCED_CASH_BUFFER,
    RC_TARGET_REDUCED_GROSS_EXPOSURE,
    RC_TARGET_REDUCED_MAX_POSITION_LIMIT,
    RC_WEIGHT_SUM_INVALID,
    TargetAllocation,
    UniverseMember,
    UniverseStatus,
)
from saathi.platform.portfolio_construction.policy import ConstructionPolicy, DEFAULT_POLICY


class ConstructionError(ValueError):
    def __init__(self, code: str, detail: str = ""):
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


def eligible_members(universe: Iterable[UniverseMember]) -> list[UniverseMember]:
    return [u for u in universe if u.status == UniverseStatus.ELIGIBLE]


def equal_weight_targets(
    universe: list[UniverseMember],
    *,
    policy: ConstructionPolicy = DEFAULT_POLICY,
    nav: Decimal,
) -> tuple[list[TargetAllocation], Decimal, list[str]]:
    """Equal weight among eligible assets; cash_weight = max(min_cash_buffer, residual)."""
    elig = eligible_members(universe)
    warnings: list[str] = []
    if not elig:
        raise ConstructionError(RC_NO_ELIGIBLE_UNIVERSE, "no eligible securities")
    cash_w = D(policy.min_cash_buffer)
    investable = Decimal("1") - cash_w
    if investable <= 0:
        raise ConstructionError(RC_TARGET_REDUCED_CASH_BUFFER, "cash buffer leaves no investable weight")
    n = len(elig)
    raw = investable / Decimal(n)
    # cap per position
    w = min(raw, D(policy.max_position_weight))
    if w < raw:
        warnings.append(RC_TARGET_REDUCED_MAX_POSITION_LIMIT)
        # recompute cash residual after cap
        total_pos = w * Decimal(n)
        if total_pos > D(policy.max_gross_exposure):
            scale = D(policy.max_gross_exposure) / total_pos
            w = q_money(w * scale)
            warnings.append(RC_TARGET_REDUCED_GROSS_EXPOSURE)
            total_pos = w * Decimal(n)
        cash_w = Decimal("1") - total_pos
        if cash_w < D(policy.min_cash_buffer):
            # reduce positions further to restore cash buffer
            investable2 = Decimal("1") - D(policy.min_cash_buffer)
            w = min(investable2 / Decimal(n), D(policy.max_position_weight))
            cash_w = Decimal("1") - w * Decimal(n)
            warnings.append(RC_TARGET_REDUCED_CASH_BUFFER)
    else:
        cash_w = Decimal("1") - w * Decimal(n)

    targets = []
    for m in elig:
        tw = q_money(w)
        targets.append(
            TargetAllocation(
                security_id=m.security_id,
                symbol=m.symbol,
                target_weight=tw,
                target_notional=q_money(D(nav) * tw),
                reason_codes=[RC_EQUAL_WEIGHT_BASELINE],
            )
        )
    return targets, q_money(cash_w), warnings


def fixed_target_weights(
    weights: dict[str, Decimal],
    universe: list[UniverseMember],
    *,
    policy: ConstructionPolicy = DEFAULT_POLICY,
    nav: Decimal,
    symbol_by_id: dict[str, str] | None = None,
) -> tuple[list[TargetAllocation], Decimal, list[str]]:
    """Validate and accept externally supplied target weights (security_id → weight)."""
    symbol_by_id = symbol_by_id or {m.security_id: m.symbol for m in universe}
    elig_ids = {m.security_id for m in eligible_members(universe)}
    warnings: list[str] = []
    if not weights:
        raise ConstructionError(RC_NO_ELIGIBLE_UNIVERSE, "empty weight map")
    for sid in weights:
        if sid not in elig_ids:
            raise ConstructionError(RC_WEIGHT_SUM_INVALID, f"non-eligible or unknown {sid}")
        if D(weights[sid]) < 0:
            raise ConstructionError(RC_SHORTS_DISABLED, f"negative weight for {sid}")
        if D(weights[sid]) > D(policy.max_position_weight) + policy.weight_sum_tolerance:
            if policy.clip_overweight_targets:
                weights[sid] = D(policy.max_position_weight)
                warnings.append(RC_TARGET_REDUCED_MAX_POSITION_LIMIT)
            else:
                raise ConstructionError(RC_TARGET_REDUCED_MAX_POSITION_LIMIT, f"{sid} exceeds max position")
    s = sum((D(v) for v in weights.values()), Decimal("0"))
    cash_w = Decimal("1") - s
    if cash_w < -policy.weight_sum_tolerance:
        raise ConstructionError(RC_WEIGHT_SUM_INVALID, f"weights sum {s} > 1")
    if cash_w < 0:
        cash_w = Decimal("0")
    if cash_w + policy.weight_sum_tolerance < D(policy.min_cash_buffer):
        raise ConstructionError(RC_TARGET_REDUCED_CASH_BUFFER, f"cash weight {cash_w} below buffer")
    if s > D(policy.max_gross_exposure) + policy.weight_sum_tolerance:
        raise ConstructionError(RC_TARGET_REDUCED_GROSS_EXPOSURE, f"gross {s}")

    targets = []
    for sid, w in weights.items():
        tw = q_money(w)
        if tw == 0:
            continue
        targets.append(
            TargetAllocation(
                security_id=sid,
                symbol=symbol_by_id.get(sid, sid),
                target_weight=tw,
                target_notional=q_money(D(nav) * tw),
                reason_codes=[RC_FIXED_TARGET],
            )
        )
    return targets, q_money(cash_w), warnings


def signal_proportional_targets(
    universe: list[UniverseMember],
    *,
    policy: ConstructionPolicy = DEFAULT_POLICY,
    nav: Decimal,
) -> tuple[list[TargetAllocation], Decimal, list[str]]:
    """Weight by signal_strength among eligible; falls back to equal if no signals."""
    elig = eligible_members(universe)
    if not elig:
        raise ConstructionError(RC_NO_ELIGIBLE_UNIVERSE, "no eligible")
    strengths = []
    for m in elig:
        s = D(m.signal_strength) if m.signal_strength is not None else Decimal("0")
        if s < 0:
            raise ConstructionError(RC_SHORTS_DISABLED, "negative signal")
        strengths.append(s)
    total = sum(strengths, Decimal("0"))
    if total <= 0:
        return equal_weight_targets(universe, policy=policy, nav=nav)
    cash_w = D(policy.min_cash_buffer)
    investable = Decimal("1") - cash_w
    warnings: list[str] = []
    raw_weights = []
    for m, s in zip(elig, strengths):
        w = investable * (s / total)
        if w > D(policy.max_position_weight):
            w = D(policy.max_position_weight)
            warnings.append(RC_TARGET_REDUCED_MAX_POSITION_LIMIT)
        raw_weights.append((m, w))
    ssum = sum((w for _, w in raw_weights), Decimal("0"))
    if ssum > D(policy.max_gross_exposure):
        scale = D(policy.max_gross_exposure) / ssum
        raw_weights = [(m, q_money(w * scale)) for m, w in raw_weights]
        warnings.append(RC_TARGET_REDUCED_GROSS_EXPOSURE)
        ssum = sum((w for _, w in raw_weights), Decimal("0"))
    # renorm into investable if under after caps
    if ssum < investable and ssum > 0:
        # leave extra as cash
        pass
    cash_w = Decimal("1") - ssum
    if cash_w < D(policy.min_cash_buffer):
        scale = (Decimal("1") - D(policy.min_cash_buffer)) / ssum if ssum else Decimal("0")
        raw_weights = [(m, q_money(w * scale)) for m, w in raw_weights]
        cash_w = Decimal("1") - sum((w for _, w in raw_weights), Decimal("0"))
        warnings.append(RC_TARGET_REDUCED_CASH_BUFFER)
    targets = [
        TargetAllocation(
            security_id=m.security_id,
            symbol=m.symbol,
            target_weight=q_money(w),
            target_notional=q_money(D(nav) * w),
            reason_codes=[RC_SIGNAL_STRENGTH_INCREASE],
        )
        for m, w in raw_weights
        if w > 0
    ]
    return targets, q_money(cash_w), warnings


def risk_budget_constrained(
    targets: list[TargetAllocation],
    cash_weight: Decimal,
    *,
    policy: ConstructionPolicy = DEFAULT_POLICY,
    nav: Decimal,
) -> tuple[list[TargetAllocation], Decimal, list[str]]:
    """Apply hard caps to existing targets with reason codes (no opaque optimizer)."""
    warnings: list[str] = []
    adjusted = []
    for t in targets:
        w = D(t.target_weight)
        codes = list(t.reason_codes)
        if w > D(policy.max_position_weight):
            w = D(policy.max_position_weight)
            codes.append(RC_TARGET_REDUCED_MAX_POSITION_LIMIT)
            warnings.append(RC_TARGET_REDUCED_MAX_POSITION_LIMIT)
        adjusted.append(
            TargetAllocation(
                security_id=t.security_id,
                symbol=t.symbol,
                target_weight=q_money(w),
                target_notional=q_money(D(nav) * w),
                target_quantity=t.target_quantity,
                reason_codes=codes,
            )
        )
    ssum = sum((D(t.target_weight) for t in adjusted), Decimal("0"))
    if ssum > D(policy.max_gross_exposure):
        scale = D(policy.max_gross_exposure) / ssum
        adjusted = [
            TargetAllocation(
                security_id=t.security_id,
                symbol=t.symbol,
                target_weight=q_money(D(t.target_weight) * scale),
                target_notional=q_money(D(nav) * D(t.target_weight) * scale),
                reason_codes=list(t.reason_codes) + [RC_TARGET_REDUCED_GROSS_EXPOSURE],
            )
            for t in adjusted
        ]
        warnings.append(RC_TARGET_REDUCED_GROSS_EXPOSURE)
        ssum = sum((D(t.target_weight) for t in adjusted), Decimal("0"))
    cash = Decimal("1") - ssum
    if cash < D(policy.min_cash_buffer):
        scale = (Decimal("1") - D(policy.min_cash_buffer)) / ssum if ssum else Decimal("0")
        adjusted = [
            TargetAllocation(
                security_id=t.security_id,
                symbol=t.symbol,
                target_weight=q_money(D(t.target_weight) * scale),
                target_notional=q_money(D(nav) * D(t.target_weight) * scale),
                reason_codes=list(t.reason_codes) + [RC_TARGET_REDUCED_CASH_BUFFER],
            )
            for t in adjusted
        ]
        warnings.append(RC_TARGET_REDUCED_CASH_BUFFER)
        cash = Decimal("1") - sum((D(t.target_weight) for t in adjusted), Decimal("0"))
    return adjusted, q_money(cash), warnings
