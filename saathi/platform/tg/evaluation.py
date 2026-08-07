"""M173/M183 — Strategy evaluation and comparison.

PAPER_ELIGIBLE requires authoritative non-fixture data + walk-forward + stress.
No LIVE_APPROVED / PROFITABLE / GUARANTEED verdicts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from saathi.platform.tg.domain import PerformanceMetrics, StrategyEvaluationVerdict
from saathi.platform.tg.data_contract import DataClassification, is_authoritative, NON_AUTHORITATIVE


# Forbidden verdict names (must never exist)
FORBIDDEN_VERDICTS = frozenset({
    "LIVE_APPROVED", "PRODUCTION_READY", "PROFITABLE", "GUARANTEED", "SAFE_TO_TRADE_REAL_FUNDS",
})


@dataclass
class StrategyComparison:
    strategies: list[str]
    metrics: dict[str, dict[str, Any]]
    ranking: list[str]
    verdicts: dict[str, str]
    scorecards: dict[str, dict[str, Any]] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    paper_only: bool = True
    live_approved: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "strategies": list(self.strategies),
            "metrics": dict(self.metrics),
            "ranking": list(self.ranking),
            "verdicts": dict(self.verdicts),
            "scorecards": dict(self.scorecards),
            "notes": list(self.notes),
            "paper_only": True,
            "live_approved": False,
            "disclaimer": (
                "Comparison is research-only. Historical/simulated performance is not "
                "future performance. Fixture/synthetic results are not market evidence. "
                "No strategy is live-approved."
            ),
        }


@dataclass
class EligibilityContext:
    """Evidence required for PAPER_ELIGIBLE."""
    data_classification: str = DataClassification.FIXTURE_TEST_ONLY.value
    trade_count: int = 0
    oos_evaluated: bool = False
    walk_forward_evaluated: bool = False
    walk_forward_consistent: bool = False
    costs_included: bool = False
    stress_completed: bool = False
    robustness_verdict: str = ""
    critical_robustness_failure: bool = False
    max_drawdown: Decimal = field(default_factory=lambda: Decimal("1"))
    max_drawdown_limit: Decimal = field(default_factory=lambda: Decimal("0.25"))
    parameter_stable: bool = False
    reconciled: bool = True
    policy_risk_passed: bool = False
    strategy_version_immutable: bool = False
    audit_complete: bool = False
    suspended: bool = False
    rejected: bool = False


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
        eligibility: EligibilityContext | None = None,
    ) -> StrategyEvaluationVerdict:
        if rejected or (eligibility and eligibility.rejected):
            return StrategyEvaluationVerdict.REJECTED
        if suspended or (eligibility and eligibility.suspended):
            return StrategyEvaluationVerdict.PAPER_SUSPENDED

        m = metrics
        if eligibility is not None:
            return self._evaluate_strict(m, eligibility)

        # Legacy multi-factor path (non-authoritative research scoring)
        if m.number_of_trades < 5:
            return StrategyEvaluationVerdict.INSUFFICIENT_EVIDENCE
        if m.max_drawdown > Decimal("0.40") or m.max_consecutive_losses >= 10:
            return StrategyEvaluationVerdict.REJECTED

        score = 0
        if m.number_of_trades >= 20:
            score += 1
        if m.max_drawdown <= Decimal("0.20"):
            score += 1
        if m.profit_factor is not None and m.profit_factor >= Decimal("1.1"):
            score += 1
        if m.sharpe is not None and m.sharpe >= Decimal("0.5"):
            score += 1
        if m.estimated_fees + m.estimated_slippage >= 0:
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

        # Without authoritative eligibility context, never grant PAPER_ELIGIBLE
        if score >= 4:
            return StrategyEvaluationVerdict.PAPER_APPROVAL_REQUIRED
        if score >= 2:
            return StrategyEvaluationVerdict.RESEARCH_ONLY
        return StrategyEvaluationVerdict.INSUFFICIENT_EVIDENCE

    def _evaluate_strict(
        self,
        metrics: PerformanceMetrics,
        el: EligibilityContext,
    ) -> StrategyEvaluationVerdict:
        """PAPER_ELIGIBLE requires full evidence set (M183)."""
        cls = el.data_classification
        if cls in {c.value for c in NON_AUTHORITATIVE} or not is_authoritative(cls):
            # Non-authoritative data can never promote to PAPER_ELIGIBLE
            if el.trade_count < 5 and metrics.number_of_trades < 5:
                return StrategyEvaluationVerdict.INSUFFICIENT_EVIDENCE
            if metrics.max_drawdown > Decimal("0.40"):
                return StrategyEvaluationVerdict.REJECTED
            return StrategyEvaluationVerdict.RESEARCH_ONLY

        required = [
            ("authoritative_data", is_authoritative(cls)),
            ("sufficient_trades", el.trade_count >= 20 or metrics.number_of_trades >= 20),
            ("oos", el.oos_evaluated),
            ("walk_forward", el.walk_forward_evaluated and el.walk_forward_consistent),
            ("costs", el.costs_included),
            ("stress", el.stress_completed and not el.critical_robustness_failure),
            ("drawdown", el.max_drawdown <= el.max_drawdown_limit),
            ("params", el.parameter_stable),
            ("reconciled", el.reconciled),
            ("policy_risk", el.policy_risk_passed),
            ("immutable", el.strategy_version_immutable),
            ("audit", el.audit_complete),
        ]
        failed = [name for name, ok in required if not ok]
        if not failed:
            return StrategyEvaluationVerdict.PAPER_ELIGIBLE
        if el.critical_robustness_failure or metrics.max_drawdown > Decimal("0.40"):
            return StrategyEvaluationVerdict.REJECTED
        if len(failed) <= 3 and el.walk_forward_evaluated:
            return StrategyEvaluationVerdict.PAPER_APPROVAL_REQUIRED
        if el.trade_count >= 5 or metrics.number_of_trades >= 5:
            return StrategyEvaluationVerdict.RESEARCH_ONLY
        return StrategyEvaluationVerdict.INSUFFICIENT_EVIDENCE

    def scorecard(
        self,
        strategy_slug: str,
        metrics: PerformanceMetrics | None,
        *,
        eligibility: EligibilityContext | None = None,
        walk_forward: dict[str, Any] | None = None,
        stress: dict[str, Any] | None = None,
        data_classification: str = "",
        notes: list[str] | None = None,
    ) -> dict[str, Any]:
        el = eligibility or EligibilityContext(data_classification=data_classification or "FIXTURE_TEST_ONLY")
        m = metrics or PerformanceMetrics()
        verdict = self.evaluate(m, eligibility=el)
        return {
            "strategy": strategy_slug,
            "verdict": verdict.value,
            "data_classification": el.data_classification or data_classification,
            "authoritative": is_authoritative(el.data_classification or data_classification),
            "metrics": m.to_public() if metrics else None,
            "walk_forward_summary": {
                "consistent": (walk_forward or {}).get("walk_forward_consistent"),
                "n_folds": (walk_forward or {}).get("n_folds"),
                "worst_dd": (walk_forward or {}).get("worst_fold_drawdown"),
                "parameter_stability": (walk_forward or {}).get("parameter_stability"),
            } if walk_forward else None,
            "stress_summary": {
                "verdict": (stress or {}).get("robustness_verdict"),
                "promote_blocked": (stress or {}).get("promote_blocked"),
                "critical_failures": (stress or {}).get("critical_failures"),
            } if stress else None,
            "eligibility_checklist": {
                "authoritative_non_fixture": is_authoritative(el.data_classification),
                "sufficient_trade_count": el.trade_count >= 20 or m.number_of_trades >= 20,
                "oos_evaluated": el.oos_evaluated,
                "walk_forward_evaluated": el.walk_forward_evaluated,
                "costs_included": el.costs_included,
                "stress_completed": el.stress_completed,
                "no_critical_robustness_failure": not el.critical_robustness_failure,
                "acceptable_drawdown": el.max_drawdown <= el.max_drawdown_limit,
                "parameter_stability": el.parameter_stable,
                "reconciled": el.reconciled,
                "policy_risk_passed": el.policy_risk_passed,
                "immutable_version": el.strategy_version_immutable,
                "audit_complete": el.audit_complete,
            },
            "notes": list(notes or []),
            "paper_only": True,
            "live_authorized": False,
            "forbidden_verdicts_absent": True,
            "disclaimer": (
                "All money is simulated. Historical results do not predict future results. "
                "Operator approval does not eliminate financial risk."
            ),
        }

    def compare(
        self,
        results: dict[str, PerformanceMetrics],
        *,
        include_baseline: str = "no_trade",
        eligibility_map: dict[str, EligibilityContext] | None = None,
        scorecards: dict[str, dict[str, Any]] | None = None,
    ) -> StrategyComparison:
        strategies = list(results.keys())
        metrics_pub = {k: v.to_public() for k, v in results.items()}
        el_map = eligibility_map or {}
        verdicts = {
            k: self.evaluate(v, eligibility=el_map.get(k)).value
            for k, v in results.items()
        }
        cards = scorecards or {
            k: self.scorecard(k, v, eligibility=el_map.get(k)) for k, v in results.items()
        }

        def rank_key(name: str) -> tuple:
            m = results[name]
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
            "No LIVE_APPROVED / PROFITABLE / GUARANTEED verdict exists.",
            "PAPER_ELIGIBLE requires authoritative non-fixture data and full evidence.",
            "Fixture and synthetic results are research/demo only.",
            "PAPER TRADING ONLY — NO LIVE ORDERS — SIMULATED FUNDS.",
        ]
        if include_baseline and include_baseline not in strategies:
            notes.append(f"Baseline '{include_baseline}' not present in this comparison set.")
        return StrategyComparison(
            strategies=strategies,
            metrics=metrics_pub,
            ranking=ranking,
            verdicts=verdicts,
            scorecards=cards,
            notes=notes,
        )
