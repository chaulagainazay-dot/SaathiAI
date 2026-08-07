"""M62.4 — strategy structural validation + statistical sufficiency / bias controls.

Two layers:

1. ``validate_strategy`` — STRUCTURAL, runs before any backtest. Rejects the classes
   of unsafe strategy that must never run:
     * FUTURE_RETURN_FEATURE   — a feature with forward_offset > 0 (look-ahead)
     * UNBOUNDED / EXCESSIVE_LEVERAGE — sizing fraction > 1 or > risk cap
     * dangling signal references to unknown features
     * invalid lookback / precision / Decimals
   This is a fail-closed gate: any structural error blocks the run.

2. ``evaluate_backtest`` — STATISTICAL sufficiency + bias checks over completed
   results. "Validated" here means TECHNICALLY sound, NOT profitable. A strategy can
   be technically valid and unattractive; both facts are reported.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

from saathi.platform.strategy.models import (
    StrategyDefinition, SizingMethod, FeatureKind, D,
)
from saathi.platform.strategy.metrics import Metric, MetricStatus


# ── validation outcomes ───────────────────────────────────────────────────────
class ValidationOutcome(str):
    PASS_TECHNICAL = "PASS_TECHNICAL"
    PASS_WITH_WARNINGS = "PASS_WITH_WARNINGS"
    INSUFFICIENT_SAMPLE = "INSUFFICIENT_SAMPLE"
    OVERFIT_SUSPECTED = "OVERFIT_SUSPECTED"
    UNSTABLE_PARAMETERS = "UNSTABLE_PARAMETERS"
    COST_SENSITIVE = "COST_SENSITIVE"
    EXCESSIVE_DRAWDOWN = "EXCESSIVE_DRAWDOWN"
    DATA_QUALITY_FAILURE = "DATA_QUALITY_FAILURE"
    FAILED_BIAS_CHECK = "FAILED_BIAS_CHECK"
    REJECTED_STRUCTURAL = "REJECTED_STRUCTURAL"


@dataclass
class Finding:
    code: str
    severity: str          # info | warning | critical
    detail: str = ""

    def to_public(self) -> dict[str, str]:
        return {"code": self.code, "severity": self.severity, "detail": self.detail}


@dataclass
class ValidationResult:
    outcome: str
    findings: list[Finding] = field(default_factory=list)
    technically_valid: bool = False

    def to_public(self) -> dict[str, Any]:
        return {"outcome": self.outcome, "technically_valid": self.technically_valid,
                "findings": [f.to_public() for f in self.findings]}


# ── 1. structural validation ─────────────────────────────────────────────────
def validate_strategy(defn: StrategyDefinition) -> list[Finding]:
    findings: list[Finding] = []
    names = defn.feature_names

    for f in defn.features:
        if f.forward_offset > 0:
            findings.append(Finding("FUTURE_RETURN_FEATURE", "critical",
                                    f"feature {f.name} reads {f.forward_offset} bars into the future"))
        if f.lookback < 1:
            findings.append(Finding("INVALID_LOOKBACK", "critical", f"feature {f.name} lookback {f.lookback} < 1"))
        if f.source not in ("close", "open", "high", "low", "volume"):
            findings.append(Finding("INVALID_SOURCE", "critical", f"feature {f.name} source {f.source}"))

    for i, s in enumerate(defn.signals):
        if s.left not in names:
            findings.append(Finding("DANGLING_SIGNAL_REF", "critical", f"signal[{i}] left {s.left} not a feature"))
        # right may be a feature or a numeric literal
        if s.right not in names:
            try:
                Decimal(str(s.right))
            except (InvalidOperation, ValueError, TypeError):
                findings.append(Finding("DANGLING_SIGNAL_REF", "critical", f"signal[{i}] right {s.right} not a feature/number"))

    # sizing / leverage
    try:
        cap = min(D(defn.sizing.max_position_fraction), D(defn.risk_max_position_fraction))
        if cap > Decimal("1"):
            findings.append(Finding("EXCESSIVE_LEVERAGE_REQUEST", "critical",
                                    f"position fraction {cap} > 1.0 (leverage not authorized)"))
        if defn.sizing.method == SizingMethod.EQUITY_FRACTION and D(defn.sizing.value) > Decimal("1"):
            findings.append(Finding("UNBOUNDED_POSITION_SIZE", "critical",
                                    f"equity fraction {defn.sizing.value} > 1.0"))
        if D(defn.sizing.value) < 0:
            findings.append(Finding("NEGATIVE_SIZE", "critical", "negative sizing value"))
    except (InvalidOperation, ValueError, TypeError):
        findings.append(Finding("INVALID_DECIMAL", "critical", "sizing contains an invalid Decimal"))

    if not defn.instrument_universe:
        findings.append(Finding("EMPTY_UNIVERSE", "critical", "no instruments"))
    if not defn.signals:
        findings.append(Finding("NO_SIGNALS", "warning", "strategy has no signal rules"))
    return findings


def is_runnable(defn: StrategyDefinition) -> tuple[bool, list[Finding]]:
    findings = validate_strategy(defn)
    critical = any(f.severity == "critical" for f in findings)
    return (not critical, findings)


# ── 2. statistical sufficiency + bias checks ─────────────────────────────────
@dataclass
class SufficiencyPolicy:
    min_observations: int = 20
    min_trades: int = 5
    min_oos_observations: int = 5
    max_drawdown: Decimal = field(default_factory=lambda: Decimal("0.40"))
    max_concentration: Decimal = field(default_factory=lambda: Decimal("1.0"))
    max_single_trade_pnl_share: Decimal = field(default_factory=lambda: Decimal("0.80"))


def _val(m: dict[str, Metric], key: str) -> Decimal | None:
    metric = m.get(key)
    if metric is None or metric.value is None:
        return None
    return D(metric.value)


def evaluate_backtest(
    metrics: dict[str, Metric],
    *,
    oos_observations: int = 0,
    trade_pnls: list[Decimal] | None = None,
    data_quality_ok: bool = True,
    cost_sensitive: bool = False,
    param_unstable: bool = False,
    walk_forward_consistent: bool = True,
    policy: SufficiencyPolicy | None = None,
) -> ValidationResult:
    policy = policy or SufficiencyPolicy()
    findings: list[Finding] = []

    if not data_quality_ok:
        findings.append(Finding("DATA_QUALITY_FAILURE", "critical", "dataset failed quality gate"))
        return ValidationResult(ValidationOutcome.DATA_QUALITY_FAILURE, findings, technically_valid=False)

    obs = _val(metrics, "number_of_observations") or Decimal("0")
    tc = _val(metrics, "trade_count") or Decimal("0")

    insufficient = False
    if obs < policy.min_observations:
        findings.append(Finding("INSUFFICIENT_OBSERVATIONS", "warning", f"{obs} < {policy.min_observations}"))
        insufficient = True
    if tc < policy.min_trades:
        findings.append(Finding("INSUFFICIENT_TRADES", "warning", f"{tc} < {policy.min_trades}"))
        insufficient = True
    if oos_observations < policy.min_oos_observations:
        findings.append(Finding("INSUFFICIENT_OOS", "warning", f"{oos_observations} < {policy.min_oos_observations}"))
        insufficient = True

    # bias / robustness
    dd = _val(metrics, "max_drawdown")
    excessive_dd = dd is not None and dd > policy.max_drawdown
    if excessive_dd:
        findings.append(Finding("EXCESSIVE_DRAWDOWN", "critical", f"max drawdown {dd} > {policy.max_drawdown}"))

    single_trade = False
    if trade_pnls:
        total = sum((p for p in trade_pnls if p > 0), Decimal("0"))
        if total > 0:
            top = max(trade_pnls)
            if top > 0 and (top / total) > policy.max_single_trade_pnl_share:
                single_trade = True
                findings.append(Finding("SINGLE_TRADE_DOMINANCE", "critical",
                                        f"one trade is {(top/total):.2f} of gross profit"))

    if cost_sensitive:
        findings.append(Finding("COST_SENSITIVE", "warning", "profitable only under low costs"))
    if param_unstable or not walk_forward_consistent:
        findings.append(Finding("UNSTABLE_PARAMETERS", "warning", "performance not stable across neighbours/folds"))

    # decide outcome (order: hardest failure first)
    technically_valid = not (excessive_dd or single_trade)
    if excessive_dd:
        outcome = ValidationOutcome.EXCESSIVE_DRAWDOWN
    elif single_trade:
        outcome = ValidationOutcome.FAILED_BIAS_CHECK
    elif insufficient:
        outcome = ValidationOutcome.INSUFFICIENT_SAMPLE
    elif param_unstable or not walk_forward_consistent:
        outcome = ValidationOutcome.UNSTABLE_PARAMETERS
    elif cost_sensitive:
        outcome = ValidationOutcome.COST_SENSITIVE
    elif findings:
        outcome = ValidationOutcome.PASS_WITH_WARNINGS
    else:
        outcome = ValidationOutcome.PASS_TECHNICAL

    return ValidationResult(outcome, findings, technically_valid=technically_valid)
