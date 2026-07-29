"""M173 — Strategy evaluation and comparison.

Promotion is never based on return alone. No LIVE_APPROVED verdict.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from saathi.platform.tg.domain import PerformanceMetrics, StrategyEvaluationVerdict


@dataclass
class StrategyComparison:
    strategies: list[str]
    metrics: dict[str, dict[str, Any]]
    ranking: list[str]
    verdicts: dict[str, str]
    notes: list[str] = field(default_factory=list)
    paper_only: bool = True
    live_approved: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "strategies": list(self.strategies),
            "metrics": dict(self.metrics),
            "ranking": list(self.ranking),
            "verdicts": dict(self.verdicts),
            "notes": list(self.notes),
            "paper_only": True,
            "live_approved": False,
            "disclaimer": (
                "Comparison is research-only. Historical/simulated performance is not "
                "future performance. No strategy is live-approved."
            ),
        }


class StrategyEvaluator:
    def evaluate(
        self,
        metrics: PerformanceMetrics,
        *,
        parameter_sensitivity: Decimal = Decimal("0"),
        regime_dependence: Decimal = Decimal("0"),
        oos_consistent: bool = False,
        walk_forward_consistent: bool = False,
        suspended: bool = False,
        rejected: bool = False,
    ) -> StrategyEvaluationVerdict:
        if rejected:
            return StrategyEvaluationVerdict.REJECTED
        if suspended:
            return StrategyEvaluationVerdict.PAPER_SUSPENDED

        m = metrics
        if m.number_of_trades < 5:
            return StrategyEvaluationVerdict.INSUFFICIENT_EVIDENCE

        # Hard rejects on risk
        if m.max_drawdown > Decimal("0.40") or m.max_consecutive_losses >= 10:
            return StrategyEvaluationVerdict.REJECTED

        # Multi-factor eligibility — not return alone
        score = 0
        if m.number_of_trades >= 20:
            score += 1
        if m.max_drawdown <= Decimal("0.20"):
            score += 1
        if m.profit_factor is not None and m.profit_factor >= Decimal("1.1"):
            score += 1
        if m.sharpe is not None and m.sharpe >= Decimal("0.5"):
            score += 1
        if m.estimated_fees + m.estimated_slippage < abs(m.total_return) * Decimal("100") + Decimal("1"):
            score += 1
        if oos_consistent:
            score += 2
        if walk_forward_consistent:
            score += 2
        if parameter_sensitivity > Decimal("0.5"):
            score -= 1
        if regime_dependence > Decimal("0.8"):
            score -= 1
        if m.max_consecutive_losses >= 5:
            score -= 1

        if score >= 6 and oos_consistent:
            return StrategyEvaluationVerdict.PAPER_ELIGIBLE
        if score >= 4:
            return StrategyEvaluationVerdict.PAPER_APPROVAL_REQUIRED
        if score >= 2:
            return StrategyEvaluationVerdict.RESEARCH_ONLY
        return StrategyEvaluationVerdict.INSUFFICIENT_EVIDENCE

    def compare(
        self,
        results: dict[str, PerformanceMetrics],
        *,
        include_baseline: str = "no_trade",
    ) -> StrategyComparison:
        strategies = list(results.keys())
        metrics_pub = {k: v.to_public() for k, v in results.items()}
        verdicts = {k: self.evaluate(v).value for k, v in results.items()}

        def rank_key(name: str) -> tuple:
            m = results[name]
            # Prefer lower drawdown, higher profit factor, more trades — NOT return alone
            pf = m.profit_factor if m.profit_factor is not None else Decimal("0")
            return (
                -float(m.max_drawdown),
                float(pf),
                m.number_of_trades,
                float(m.total_return),
            )

        ranking = sorted(strategies, key=rank_key, reverse=True)
        notes = [
            "Ranking prioritizes drawdown, profit factor, and trade count over raw return.",
            "No LIVE_APPROVED verdict exists in this foundation.",
            "Baseline no-trade strategy should be included for relative comparison.",
            "PAPER TRADING ONLY — NO LIVE ORDERS — SIMULATED FUNDS.",
        ]
        if include_baseline and include_baseline not in strategies:
            notes.append(f"Baseline '{include_baseline}' not present in this comparison set.")
        return StrategyComparison(
            strategies=strategies,
            metrics=metrics_pub,
            ranking=ranking,
            verdicts=verdicts,
            notes=notes,
        )
