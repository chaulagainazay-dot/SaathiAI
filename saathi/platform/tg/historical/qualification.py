"""M190 — Deterministic strategy qualification and evidence scorecards.

PAPER_ELIGIBLE only when all mandatory gates pass.
No LIVE verdict. LLM cannot approve or alter metrics.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from saathi.platform.tg.data_contract import DataClassification, is_authoritative, NON_AUTHORITATIVE
from saathi.platform.tg.domain import PerformanceMetrics, StrategyEvaluationVerdict
from saathi.platform.tg.historical.models import DataQualityVerdict
from saathi.platform.tg.historical.monte_carlo import MonteCarloVerdict


# Forbidden names — must never be emitted
FORBIDDEN = frozenset({
    "LIVE_APPROVED", "PRODUCTION_READY", "PROFITABLE", "GUARANTEED",
    "SAFE_TO_TRADE_REAL_FUNDS", "LIVE_ELIGIBLE",
})


@dataclass
class QualificationGates:
    """All mandatory PAPER_ELIGIBLE conditions (visible checklist)."""

    non_fixture_authoritative_dataset: bool = False
    accepted_data_quality: bool = False
    sufficient_date_coverage: bool = False
    sufficient_trade_count: bool = False
    untouched_final_oos: bool = False
    walk_forward_completed: bool = False
    stress_completed: bool = False
    monte_carlo_completed: bool = False
    realistic_fees: bool = False
    realistic_spread: bool = False
    realistic_slippage: bool = False
    corporate_actions_validated: bool = False
    no_critical_data_quality_failure: bool = False
    no_look_ahead_leakage: bool = False
    no_unresolved_reconciliation: bool = False
    acceptable_drawdown: bool = False
    acceptable_risk_of_ruin: bool = False
    parameter_stability: bool = False
    no_critical_cost_sensitivity: bool = False
    no_critical_regime_dependence: bool = False
    immutable_strategy_version: bool = False
    immutable_dataset_version: bool = False
    complete_evidence_journal: bool = False
    policy_compatibility: bool = False
    deterministic_risk_controls: bool = False
    owner_approval_still_required: bool = True  # always true — never auto-activates paper

    def all_mandatory_pass(self) -> bool:
        # owner_approval_still_required is informational always True
        checks = [
            self.non_fixture_authoritative_dataset,
            self.accepted_data_quality,
            self.sufficient_date_coverage,
            self.sufficient_trade_count,
            self.untouched_final_oos,
            self.walk_forward_completed,
            self.stress_completed,
            self.monte_carlo_completed,
            self.realistic_fees,
            self.realistic_spread,
            self.realistic_slippage,
            self.corporate_actions_validated,
            self.no_critical_data_quality_failure,
            self.no_look_ahead_leakage,
            self.no_unresolved_reconciliation,
            self.acceptable_drawdown,
            self.acceptable_risk_of_ruin,
            self.parameter_stability,
            self.no_critical_cost_sensitivity,
            self.no_critical_regime_dependence,
            self.immutable_strategy_version,
            self.immutable_dataset_version,
            self.complete_evidence_journal,
            self.policy_compatibility,
            self.deterministic_risk_controls,
        ]
        return all(checks)

    def failed(self) -> list[str]:
        failed = []
        for k, v in self.__dict__.items():
            if k == "owner_approval_still_required":
                continue
            if not v:
                failed.append(k)
        return failed

    def to_public(self) -> dict[str, Any]:
        d = {k: bool(v) for k, v in self.__dict__.items()}
        d["all_mandatory_pass"] = self.all_mandatory_pass()
        d["failed_gates"] = self.failed()
        d["owner_approval_still_required"] = True
        return d


def _dec(v: Any, default: str = "0") -> Decimal:
    if v is None:
        return Decimal(default)
    try:
        return Decimal(str(v))
    except Exception:
        return Decimal(default)


def build_gates_from_evidence(
    *,
    data_classification: str,
    quality_verdict: str = "",
    coverage_ratio: float = 0.0,
    date_span_days: float = 0.0,
    min_coverage_days: float = 60.0,
    trade_count: int = 0,
    min_trades: int = 20,
    walk_forward: dict[str, Any] | None = None,
    stress: dict[str, Any] | None = None,
    monte_carlo: dict[str, Any] | None = None,
    metrics: PerformanceMetrics | None = None,
    fee_bps: str = "0",
    spread_model: str = "",
    slippage_bps: str = "0",
    corporate_action_status: str = "NONE",
    look_ahead_ok: bool = True,
    reconciled: bool = True,
    max_drawdown_limit: Decimal = Decimal("0.25"),
    parameter_stable: bool = False,
    regime_critical_failure: bool = False,
    strategy_immutable: bool = True,
    dataset_immutable: bool = True,
    journal_complete: bool = True,
    policy_ok: bool = True,
    risk_controls_ok: bool = True,
) -> QualificationGates:
    cls = data_classification
    authoritative = is_authoritative(cls)
    wf = walk_forward or {}
    st = stress or {}
    mc = monte_carlo or {}
    m = metrics or PerformanceMetrics()

    q_ok = quality_verdict in (
        DataQualityVerdict.ACCEPTED.value,
        DataQualityVerdict.ACCEPTED_WITH_WARNINGS.value,
        "",  # allow empty when not imported path but still need other gates fail
    )
    # For synthetic, quality may be n/a — still fail authoritative
    if not quality_verdict and not authoritative:
        q_ok = False

    mc_verdict = str(mc.get("monte_carlo_verdict", ""))
    mc_done = mc.get("status") == "COMPLETE" and mc_verdict not in (
        MonteCarloVerdict.INSUFFICIENT_TRADES.value,
        MonteCarloVerdict.INSUFFICIENT_EVIDENCE.value,
        "",
    )
    ror_ok = mc_verdict not in (
        MonteCarloVerdict.RISK_OF_RUIN_UNACCEPTABLE.value,
        MonteCarloVerdict.TAIL_RISK_HIGH.value,
        MonteCarloVerdict.INSUFFICIENT_TRADES.value,
        MonteCarloVerdict.INSUFFICIENT_EVIDENCE.value,
    )
    try:
        ror = float(mc.get("risk_of_ruin") or "1")
        if ror >= 0.10:
            ror_ok = False
    except (TypeError, ValueError):
        pass

    cost_critical = bool(st.get("promote_blocked")) or str(st.get("robustness_verdict", "")) in (
        "COST_SENSITIVE", "FRAGILE", "PARAMETER_UNSTABLE",
    )

    return QualificationGates(
        non_fixture_authoritative_dataset=authoritative,
        accepted_data_quality=q_ok and quality_verdict not in (
            DataQualityVerdict.REJECTED.value,
            DataQualityVerdict.QUARANTINED.value,
            DataQualityVerdict.INSUFFICIENT_COVERAGE.value,
        ),
        sufficient_date_coverage=(date_span_days >= min_coverage_days) or (coverage_ratio >= 0.7 and date_span_days >= 30),
        sufficient_trade_count=trade_count >= min_trades or m.number_of_trades >= min_trades,
        untouched_final_oos=bool(wf.get("final_test_untouched")),
        walk_forward_completed=wf.get("status") == "COMPLETE" and int(wf.get("n_folds") or 0) >= 1,
        stress_completed=st.get("status") == "COMPLETE",
        monte_carlo_completed=mc_done,
        realistic_fees=_dec(fee_bps) > 0,
        realistic_spread=bool(spread_model) and spread_model != "zero",
        realistic_slippage=_dec(slippage_bps) > 0,
        corporate_actions_validated=corporate_action_status in (
            "NONE", "APPLIED", "VALIDATED", "NOT_APPLICABLE",
        ),
        no_critical_data_quality_failure=quality_verdict not in (
            DataQualityVerdict.REJECTED.value,
            DataQualityVerdict.QUARANTINED.value,
        ),
        no_look_ahead_leakage=look_ahead_ok,
        no_unresolved_reconciliation=reconciled,
        acceptable_drawdown=abs(m.max_drawdown) <= max_drawdown_limit,
        acceptable_risk_of_ruin=ror_ok and mc_done,
        parameter_stability=parameter_stable or bool(wf.get("walk_forward_consistent")),
        no_critical_cost_sensitivity=not cost_critical,
        no_critical_regime_dependence=not regime_critical_failure,
        immutable_strategy_version=strategy_immutable,
        immutable_dataset_version=dataset_immutable,
        complete_evidence_journal=journal_complete,
        policy_compatibility=policy_ok,
        deterministic_risk_controls=risk_controls_ok,
        owner_approval_still_required=True,
    )


def qualify_strategy(
    strategy_slug: str,
    *,
    metrics: PerformanceMetrics | None = None,
    gates: QualificationGates | None = None,
    data_classification: str = "FIXTURE_TEST_ONLY",
    walk_forward: dict[str, Any] | None = None,
    stress: dict[str, Any] | None = None,
    monte_carlo: dict[str, Any] | None = None,
    regime_matrix: dict[str, Any] | None = None,
    restrictions: list[str] | None = None,
    notes: list[str] | None = None,
    dimensions: dict[str, Any] | None = None,
) -> dict[str, Any]:
    m = metrics or PerformanceMetrics()
    g = gates or build_gates_from_evidence(
        data_classification=data_classification,
        trade_count=m.number_of_trades,
        walk_forward=walk_forward,
        stress=stress,
        monte_carlo=monte_carlo,
        metrics=m,
    )

    # Hard rejects
    if data_classification in {c.value for c in NON_AUTHORITATIVE} or not is_authoritative(data_classification):
        # Fixture/synthetic can never be PAPER_ELIGIBLE
        if m.number_of_trades < 5:
            verdict = StrategyEvaluationVerdict.INSUFFICIENT_EVIDENCE
        elif abs(m.max_drawdown) > Decimal("0.40"):
            verdict = StrategyEvaluationVerdict.REJECTED
        else:
            verdict = StrategyEvaluationVerdict.RESEARCH_ONLY
    elif g.all_mandatory_pass():
        verdict = StrategyEvaluationVerdict.PAPER_ELIGIBLE
    elif abs(m.max_drawdown) > Decimal("0.40") or (
        monte_carlo and monte_carlo.get("monte_carlo_verdict")
        == MonteCarloVerdict.RISK_OF_RUIN_UNACCEPTABLE.value
    ):
        verdict = StrategyEvaluationVerdict.REJECTED
    elif g.walk_forward_completed and len(g.failed()) <= 5:
        verdict = StrategyEvaluationVerdict.PAPER_APPROVAL_REQUIRED
    elif m.number_of_trades >= 5:
        verdict = StrategyEvaluationVerdict.RESEARCH_ONLY
    else:
        verdict = StrategyEvaluationVerdict.INSUFFICIENT_EVIDENCE

    assert verdict.value not in FORBIDDEN

    # Dimension scores (visible components; combined is optional transparency only)
    dims = dimensions or {
        "evidence_quality": 1.0 if g.non_fixture_authoritative_dataset and g.accepted_data_quality else 0.2,
        "robustness": 1.0 if g.walk_forward_completed and g.stress_completed and g.monte_carlo_completed else 0.3,
        "drawdown_control": 1.0 if g.acceptable_drawdown else 0.2,
        "cost_resilience": 1.0 if g.no_critical_cost_sensitivity and g.realistic_fees else 0.3,
        "regime_stability": 0.5 if not g.no_critical_regime_dependence else 0.8,
        "parameter_stability": 1.0 if g.parameter_stability else 0.3,
        "operational_integrity": 1.0 if g.immutable_strategy_version and g.immutable_dataset_version else 0.2,
        "risk_containment": 1.0 if g.acceptable_risk_of_ruin and g.deterministic_risk_controls else 0.2,
    }
    weighted = sum(dims.values()) / max(1, len(dims))

    return {
        "strategy": strategy_slug,
        "verdict": verdict.value,
        "data_classification": data_classification,
        "authoritative": is_authoritative(data_classification),
        "gates": g.to_public(),
        "dimensions": dims,
        "weighted_score_visible": round(weighted, 4),
        "weighted_score_note": "Components remain visible; weighted score is not a sole promotion gate.",
        "restrictions": list(restrictions or []),
        "regime_matrix_summary": {
            "regimes": list((regime_matrix or {}).keys()),
            "note": "Restrictions may limit paper eligibility to specific regimes.",
        } if regime_matrix else None,
        "metrics": m.to_public() if metrics else None,
        "walk_forward": {
            "status": (walk_forward or {}).get("status"),
            "consistent": (walk_forward or {}).get("walk_forward_consistent"),
            "n_folds": (walk_forward or {}).get("n_folds"),
            "final_test_untouched": (walk_forward or {}).get("final_test_untouched"),
        } if walk_forward else None,
        "stress": {
            "status": (stress or {}).get("status"),
            "verdict": (stress or {}).get("robustness_verdict"),
            "promote_blocked": (stress or {}).get("promote_blocked"),
        } if stress else None,
        "monte_carlo": {
            "status": (monte_carlo or {}).get("status"),
            "verdict": (monte_carlo or {}).get("monte_carlo_verdict"),
            "risk_of_ruin": (monte_carlo or {}).get("risk_of_ruin"),
            "seed": (monte_carlo or {}).get("seed"),
        } if monte_carlo else None,
        "notes": list(notes or []) + [
            "PAPER RESEARCH ONLY — NO LIVE ORDERS",
            "Historical results are not future results.",
            "Eligibility is not profitability.",
            "Owner approval still required before paper activation.",
            "LLM cannot approve qualification or alter metrics.",
        ],
        "paper_only": True,
        "live_authorized": False,
        "live_verdict_exists": False,
        "owner_approval_required": True,
        "llm_may_approve": False,
        "llm_may_alter_metrics": False,
    }
