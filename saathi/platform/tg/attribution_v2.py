"""ATTRIBUTION-V2 — multi-dimension performance attribution over REAL records.

Answers "what produced the return?" across the dimensions the program actually
trades: strategy, asset, venue, benchmark, cost drag, drawdown, and the outcomes
Guardian prevented.

Distinct from the existing research `PerformanceAttribution` (Brinson-lite over
SYNTHETIC return series, labelled research-only): this operates strictly on
supplied realized/shadow records and never fabricates a return. If a dimension is
not observable, it is reported as DATA_INSUFFICIENT rather than silently zero.

Deterministic Decimal arithmetic. Read-only: attribution explains, it never sizes,
approves, or executes.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum

from saathi.platform.trading_models import D as _parse_financial


class AttributionStatus(str, Enum):
    OK = "OK"
    DATA_INSUFFICIENT = "DATA_INSUFFICIENT"
    RECONCILIATION_REQUIRED = "RECONCILIATION_REQUIRED"
    AMBIGUOUS_PROVENANCE = "AMBIGUOUS_PROVENANCE"


class EvidenceClass(str, Enum):
    """How strongly a number is supported. These must never be merged.

    ACCOUNTING is derived from records of what actually happened.
    COUNTERFACTUAL is what a frozen rule says WOULD have happened to a decision
    that was never executed — an estimate, never a fact about the book.
    OBSERVATIONAL is context: a relationship in time with no causal claim.
    """

    ACCOUNTING = "ACCOUNTING_ATTRIBUTION"
    COUNTERFACTUAL = "COUNTERFACTUAL_ESTIMATE"
    OBSERVATIONAL = "OBSERVATIONAL_ASSOCIATION"


class CounterfactualOutcome(str, Enum):
    AVOIDED_LOSS = "COUNTERFACTUAL_AVOIDED_LOSS"
    MISSED_GAIN = "COUNTERFACTUAL_MISSED_GAIN"
    NEUTRAL = "COUNTERFACTUAL_NEUTRAL"
    INSUFFICIENT_DATA = "COUNTERFACTUAL_INSUFFICIENT_DATA"


LABEL = "RESEARCH_ATTRIBUTION_NOT_OFFICIAL_GIPS"

#: Bumped whenever the arithmetic changes, so a stored report can be told apart
#: from one this build would produce.
CALCULATION_VERSION = "attribution/v2.1.0"
#: The counterfactual rule is frozen and versioned so a horizon can never be
#: chosen after seeing the outcome.
COUNTERFACTUAL_METHOD_VERSION = "counterfactual/v1.0.0-single-forward-mark"


def _dec(v) -> Decimal:
    """Parse under FINANCIAL-NUMERIC-1.

    Previously ``Decimal(str(v))``, which accepted "NaN" and "Infinity" — an
    attribution report could therefore carry a non-finite number into a total, a
    comparison, or a reconciliation check. Delegating means attribution inherits
    the fail-closed contract instead of restating a weaker one.
    """
    return _parse_financial(v)


@dataclass(frozen=True)
class AttributionRecord:
    """One realized (or shadow) outcome attributable to a decision.

    ``cost`` remains the total so existing callers are unaffected. Where the
    components are known they are carried too, because "costs were 90" answers
    much less than "60 fee, 20 spread, 10 slippage" — the first cannot tell you
    which lever to pull.
    """

    strategy_id: str
    symbol: str
    venue: str
    asset_class: str
    gross_pnl: Decimal
    cost: Decimal
    benchmark_pnl: Decimal | None = None
    guardian_blocked: bool = False
    # Optional decomposition. None means "not reported", never "zero".
    fee: Decimal | None = None
    spread_cost: Decimal | None = None
    slippage_cost: Decimal | None = None
    notional: Decimal | None = None
    #: Set when a fill cannot be traced to exactly one strategy.
    strategy_ambiguous: bool = False

    @property
    def net_pnl(self) -> Decimal:
        return self.gross_pnl - self.cost

    @property
    def has_cost_breakdown(self) -> bool:
        return None not in (self.fee, self.spread_cost, self.slippage_cost)

    def cost_components_reconcile(self) -> bool:
        """The parts must equal the whole, or the breakdown is not usable."""
        if not self.has_cost_breakdown:
            return False
        return self.fee + self.spread_cost + self.slippage_cost == self.cost


@dataclass(frozen=True)
class DecisionLayerRecord:
    """What each authority did to one strategy's request, as a transformation.

    Deliberately NOT a return. "Construction removed 12% of requested exposure" is
    an accounting fact about the decision; "construction earned us 2%" is a
    counterfactual claim that needs a counterfactual method to support it. This
    record carries the first and refuses to imply the second.
    """

    strategy_id: str
    symbol: str
    requested_weight: Decimal
    constructed_weight: Decimal | None = None
    risk_adjusted_weight: Decimal | None = None
    guardian_outcome: str = "PASSED"
    construction_reason_codes: tuple = ()
    risk_reason_codes: tuple = ()
    guardian_reason_codes: tuple = ()

    @property
    def construction_delta(self) -> Decimal | None:
        if self.constructed_weight is None:
            return None
        return self.constructed_weight - self.requested_weight

    @property
    def risk_delta(self) -> Decimal | None:
        if self.risk_adjusted_weight is None or self.constructed_weight is None:
            return None
        return self.risk_adjusted_weight - self.constructed_weight

    @property
    def final_weight(self) -> Decimal:
        """Exposure actually reaching execution. A block is zero, not the proposal."""
        if self.guardian_outcome != "PASSED":
            return Decimal("0")
        for candidate in (self.risk_adjusted_weight, self.constructed_weight):
            if candidate is not None:
                return candidate
        return self.requested_weight


@dataclass(frozen=True)
class CounterfactualRecord:
    """A blocked proposal and what the market did afterwards.

    An ESTIMATE under a frozen rule, never an accounting fact. It has no execution
    authority: nothing reads it to unblock, size or re-propose anything.
    """

    strategy_id: str
    symbol: str
    blocked_by: str
    reference_price: Decimal
    quantity: Decimal
    forward_price: Decimal | None = None
    reason_codes: tuple = ()

    @property
    def forward_pnl(self) -> Decimal | None:
        if self.forward_price is None:
            return None
        return (self.forward_price - self.reference_price) * self.quantity

    def classify(self) -> str:
        pnl = self.forward_pnl
        if pnl is None:
            return CounterfactualOutcome.INSUFFICIENT_DATA.value
        if pnl > 0:
            # The trade would have made money, so blocking it cost us.
            return CounterfactualOutcome.MISSED_GAIN.value
        if pnl < 0:
            return CounterfactualOutcome.AVOIDED_LOSS.value
        return CounterfactualOutcome.NEUTRAL.value


def _group(records, key) -> dict:
    out: dict[str, dict] = {}
    for r in records:
        k = getattr(r, key)
        bucket = out.setdefault(k, {"gross": Decimal("0"), "cost": Decimal("0"), "net": Decimal("0"), "count": 0})
        bucket["gross"] += r.gross_pnl
        bucket["cost"] += r.cost
        bucket["net"] += r.net_pnl
        bucket["count"] += 1
    return out


def max_drawdown(equity_path) -> Decimal:
    """Max peak-to-trough drawdown of a cumulative equity path."""
    peak = None
    worst = Decimal("0")
    for v in equity_path:
        x = _dec(v)
        peak = x if peak is None else max(peak, x)
        worst = max(worst, peak - x)
    return worst


def attribute(records, *, equity_path=None) -> dict:
    """Attribute realized performance across every observable dimension."""
    records = list(records)
    executed = [r for r in records if not r.guardian_blocked]
    blocked = [r for r in records if r.guardian_blocked]

    if not records:
        return {
            "status": AttributionStatus.DATA_INSUFFICIENT.value,
            "label": LABEL,
            "detail": "no attribution records supplied",
        }

    gross = sum((r.gross_pnl for r in executed), Decimal("0"))
    cost = sum((r.cost for r in executed), Decimal("0"))
    net = gross - cost

    # Benchmark contribution is only reported when every executed record has one —
    # a partial benchmark would misattribute the remainder to skill.
    if executed and all(r.benchmark_pnl is not None for r in executed):
        benchmark = sum((r.benchmark_pnl for r in executed), Decimal("0"))
        excess = net - benchmark
        benchmark_status = AttributionStatus.OK.value
    else:
        benchmark = None
        excess = None
        benchmark_status = AttributionStatus.DATA_INSUFFICIENT.value

    return {
        "status": AttributionStatus.OK.value,
        "label": LABEL,
        "totals": {
            "gross_pnl": gross,
            "cost_drag": cost,
            "net_pnl": net,
            "records": len(executed),
        },
        "by_strategy": _group(executed, "strategy_id"),
        "by_asset": _group(executed, "symbol"),
        "by_venue": _group(executed, "venue"),
        "by_asset_class": _group(executed, "asset_class"),
        "benchmark": {
            "status": benchmark_status,
            "benchmark_pnl": benchmark,
            "excess_vs_benchmark": excess,
        },
        "guardian": {
            "blocked_count": len(blocked),
            "blocked_symbols": sorted({r.symbol for r in blocked}),
            "note": "blocked decisions produced no exposure; their PnL is not claimed",
        },
        "risk": {
            "max_drawdown": max_drawdown(equity_path) if equity_path else None,
            "status": (
                AttributionStatus.OK.value if equity_path else AttributionStatus.DATA_INSUFFICIENT.value
            ),
        },
        "authorizes_execution": False,
    }


def reconciles(result: dict) -> bool:
    """Contributions must sum to the reported net — attribution never leaks PnL."""
    if result.get("status") != AttributionStatus.OK.value:
        return False
    net = result["totals"]["net_pnl"]
    for dimension in ("by_strategy", "by_asset", "by_venue", "by_asset_class"):
        total = sum((b["net"] for b in result[dimension].values()), Decimal("0"))
        if total != net:
            return False
    return True


# ── PERFORMANCE-ATTRIBUTION-V2 ──────────────────────────────────────────────


def cost_decomposition(records) -> dict:
    """Split cost into fee / spread / slippage where every record reports them.

    All-or-nothing on purpose. A partial decomposition would attribute the
    unreported records' costs to whichever component happened to be present,
    which is worse than admitting the split is unavailable.
    """
    executed = [r for r in records if not r.guardian_blocked]
    if not executed:
        return {"status": AttributionStatus.DATA_INSUFFICIENT.value, "detail": "no executed records"}
    if not all(r.has_cost_breakdown for r in executed):
        missing = sum(1 for r in executed if not r.has_cost_breakdown)
        return {
            "status": AttributionStatus.DATA_INSUFFICIENT.value,
            "detail": f"{missing} of {len(executed)} records report no cost breakdown",
            "total_cost": sum((r.cost for r in executed), Decimal("0")),
        }
    mismatched = [r.symbol for r in executed if not r.cost_components_reconcile()]
    if mismatched:
        return {
            "status": AttributionStatus.RECONCILIATION_REQUIRED.value,
            "detail": f"cost components do not sum to total cost for {sorted(set(mismatched))}",
        }
    fee = sum((r.fee for r in executed), Decimal("0"))
    spread = sum((r.spread_cost for r in executed), Decimal("0"))
    slippage = sum((r.slippage_cost for r in executed), Decimal("0"))
    return {
        "status": AttributionStatus.OK.value,
        "evidence": EvidenceClass.ACCOUNTING.value,
        "fee_drag": fee,
        "spread_drag": spread,
        "slippage_drag": slippage,
        "total_cost": fee + spread + slippage,
    }


def turnover(records, *, average_portfolio_value=None) -> dict:
    """One-way turnover: traded notional over average portfolio value.

    The convention is named because gross, one-way and round-trip turnover differ
    by a factor of two and an unnamed number is not comparable to anything.
    """
    executed = [r for r in records if not r.guardian_blocked]
    traded = [r for r in executed if r.notional is not None]
    if not traded:
        return {"status": AttributionStatus.DATA_INSUFFICIENT.value,
                "detail": "no record reports a traded notional", "convention": "ONE_WAY"}
    total = sum((abs(r.notional) for r in traded), Decimal("0"))
    if average_portfolio_value is None:
        return {"status": AttributionStatus.DATA_INSUFFICIENT.value,
                "detail": "average portfolio value not supplied",
                "traded_notional": total, "convention": "ONE_WAY"}
    avg = _dec(average_portfolio_value)
    if avg <= 0:
        return {"status": AttributionStatus.DATA_INSUFFICIENT.value,
                "detail": "average portfolio value must be positive",
                "traded_notional": total, "convention": "ONE_WAY"}
    return {
        "status": AttributionStatus.OK.value,
        "evidence": EvidenceClass.ACCOUNTING.value,
        "convention": "ONE_WAY",
        "traded_notional": total,
        "turnover_ratio": total / avg,
        "reported_by": len(traded),
        "executed_records": len(executed),
    }


def decision_layer_attribution(layers) -> dict:
    """How each authority transformed the strategy's request.

    Reported as EXPOSURE DELTAS, never as returns. "Construction removed 12
    percentage points" is an accounting fact about the decision; "construction
    earned 2%" would be a counterfactual claim this function does not make.
    """
    layers = list(layers)
    if not layers:
        return {"status": AttributionStatus.DATA_INSUFFICIENT.value, "detail": "no decision records"}

    requested = sum((l.requested_weight for l in layers), Decimal("0"))
    constructed = sum((l.constructed_weight for l in layers if l.constructed_weight is not None), Decimal("0"))
    final = sum((l.final_weight for l in layers), Decimal("0"))

    construction_deltas = [l.construction_delta for l in layers if l.construction_delta is not None]
    risk_deltas = [l.risk_delta for l in layers if l.risk_delta is not None]
    blocked = [l for l in layers if l.guardian_outcome != "PASSED"]

    def _reasons(attr):
        out: dict[str, int] = {}
        for l in layers:
            for code in getattr(l, attr):
                out[code] = out.get(code, 0) + 1
        return out

    return {
        "status": AttributionStatus.OK.value,
        "evidence": EvidenceClass.ACCOUNTING.value,
        "requested_exposure": requested,
        "constructed_exposure": constructed,
        "final_exposure": final,
        "construction": {
            "removed_exposure": sum(construction_deltas, Decimal("0")),
            "records": len(construction_deltas),
            "reason_codes": _reasons("construction_reason_codes"),
        },
        "risk": {
            "removed_exposure": sum(risk_deltas, Decimal("0")),
            "records": len(risk_deltas),
            "reason_codes": _reasons("risk_reason_codes"),
        },
        "guardian": {
            "blocked": len(blocked),
            "blocked_exposure": sum((l.risk_adjusted_weight or l.constructed_weight or l.requested_weight
                                     for l in blocked), Decimal("0")),
            "reason_codes": _reasons("guardian_reason_codes"),
        },
        "note": "exposure transformations, not returns — a removed weight is not a realized gain",
    }


def guardian_counterfactual(counterfactuals) -> dict:
    """Classify what happened after Guardian blocked each proposal.

    An ESTIMATE under a frozen, versioned rule. Guardian's decisions are not
    revisited and nothing here can unblock, size or re-propose a trade.
    """
    records = list(counterfactuals)
    if not records:
        # The authority declaration belongs on EVERY branch: "we had no data" must
        # not be the one shape of this result that forgets to say it cannot execute.
        return {"status": AttributionStatus.DATA_INSUFFICIENT.value,
                "evidence": EvidenceClass.COUNTERFACTUAL.value,
                "method_version": COUNTERFACTUAL_METHOD_VERSION,
                "blocked": 0, "measured": 0, "unmeasured": 0, "outcomes": {},
                "net_forward_pnl_of_blocked": None,
                "authorizes_execution": False,
                "detail": "no blocked proposals recorded"}

    buckets: dict[str, int] = {}
    measured = [r for r in records if r.forward_pnl is not None]
    for r in records:
        c = r.classify()
        buckets[c] = buckets.get(c, 0) + 1
    net = sum((r.forward_pnl for r in measured), Decimal("0")) if measured else None
    return {
        "status": AttributionStatus.OK.value,
        "evidence": EvidenceClass.COUNTERFACTUAL.value,
        "method_version": COUNTERFACTUAL_METHOD_VERSION,
        "blocked": len(records),
        "measured": len(measured),
        "unmeasured": len(records) - len(measured),
        "outcomes": buckets,
        # Positive means the blocks cost us; negative means they protected us.
        "net_forward_pnl_of_blocked": net,
        "authorizes_execution": False,
        "note": "estimate under a frozen rule; not part of realized PnL and never added to it",
    }


def _canonical(value):
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _canonical(v) for k, v in sorted(value.items())}
    if isinstance(value, (list, tuple)):
        return [_canonical(v) for v in value]
    return value


def report_id(payload: dict) -> str:
    """Deterministic id over the report content.

    Same canonical inputs and same calculation version produce the same id, which
    is what makes recomputation after a restart checkable rather than merely
    plausible.
    """
    blob = json.dumps(_canonical(payload), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()[:32]


def performance_attribution_report(
    records,
    *,
    layers=(),
    counterfactuals=(),
    equity_path=None,
    average_portfolio_value=None,
    period_start=None,
    period_end=None,
    benchmark_version=None,
    policy_versions=None,
    valuation_currency="USDT",
    mode="SHADOW",
) -> dict:
    """The whole picture, with each number labelled by how strongly it is supported.

    A DERIVED VIEW. It opens no store, mutates nothing, and holds no execution
    authority — the canonical records remain the only truth.
    """
    records = list(records)
    base = attribute(records, equity_path=equity_path)

    ambiguous = [r for r in records if getattr(r, "strategy_ambiguous", False)]
    strategy_block = dict(base.get("by_strategy") or {})
    strategy_status = (
        AttributionStatus.AMBIGUOUS_PROVENANCE.value if ambiguous else AttributionStatus.OK.value
    )

    body = {
        "calculation_version": CALCULATION_VERSION,
        "mode": mode,
        "valuation_currency": valuation_currency,
        "period_start": period_start,
        "period_end": period_end,
        "benchmark_version": benchmark_version,
        "policy_versions": dict(policy_versions or {}),
        "accounting": {
            "evidence": EvidenceClass.ACCOUNTING.value,
            "status": base.get("status"),
            "totals": base.get("totals"),
            "by_asset": base.get("by_asset"),
            "by_venue": base.get("by_venue"),
            "by_asset_class": base.get("by_asset_class"),
            "reconciles": reconciles(base),
        },
        "by_strategy": {
            "status": strategy_status,
            "evidence": EvidenceClass.ACCOUNTING.value,
            "contributions": strategy_block,
            "ambiguous_records": len(ambiguous),
            "detail": (
                "one or more fills could not be traced to exactly one strategy"
                if ambiguous else None
            ),
        },
        "costs": cost_decomposition(records),
        "turnover": turnover(records, average_portfolio_value=average_portfolio_value),
        "benchmark": {**(base.get("benchmark") or {}), "evidence": EvidenceClass.ACCOUNTING.value,
                      "version": benchmark_version},
        "risk": base.get("risk"),
        "decision_layers": decision_layer_attribution(layers),
        "guardian_counterfactual": guardian_counterfactual(counterfactuals),
        "authorizes_execution": False,
        "label": LABEL,
    }
    return {**body, "report_id": report_id(body)}
