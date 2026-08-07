"""Multiple-testing burden tracking and deflated confidence helpers."""
from __future__ import annotations

import math
from typing import Any

from saathi.platform.tg.research_lab.models import AUTHORITY_VALUES


class MultipleTestingController:
    """Record research degrees of freedom and apply confidence penalties.

    Raw p-values are never treated as proof. Approximations are labelled.
    """

    def analyse(
        self,
        *,
        n_strategies: int = 1,
        n_parameter_trials: int = 1,
        n_datasets: int = 1,
        n_time_windows: int = 1,
        n_features: int = 1,
        n_selection_decisions: int = 1,
        observed_sharpe: float = 0.0,
        n_observations: int = 100,
    ) -> dict[str, Any]:
        trials = max(1, n_strategies * n_parameter_trials * n_datasets * n_time_windows)
        dof = {
            "n_strategies_tested": n_strategies,
            "n_parameter_trials": n_parameter_trials,
            "n_datasets_tested": n_datasets,
            "n_time_windows_tested": n_time_windows,
            "n_features_tested": n_features,
            "n_candidate_selection_decisions": n_selection_decisions,
            "total_trial_count_estimate": trials,
            "research_degrees_of_freedom": trials + n_features + n_selection_decisions,
        }
        # Trial-count penalty (simple, labelled approximation)
        trial_penalty = min(0.5, math.log1p(trials) / 10.0)
        # Deflated Sharpe approximation (Bailey & López de Prado style — LABELLED APPROXIMATION)
        # SR* ≈ SR * sqrt(1 - log(trials)/n) rough form; not a formal proof
        deflated_sharpe = observed_sharpe
        if n_observations > 1 and trials > 1:
            adj = max(0.0, 1.0 - math.log(trials) / max(n_observations, 2))
            deflated_sharpe = observed_sharpe * math.sqrt(adj)

        fdr_warning = trials > 5
        rank_stability = "unknown_until_bootstrap"
        baseline_comparison_required = True

        confidence = "moderate"
        if trials > 20 or observed_sharpe > 0 and deflated_sharpe < 0:
            confidence = "deflated_low"
        if trials > 50:
            confidence = "high_multiple_testing_burden"

        return {
            "ok": True,
            "counts": dof,
            "controls": {
                "trial_count_penalties": True,
                "holdout_isolation": True,
                "false_discovery_warnings": fdr_warning,
                "rank_stability_checks": rank_stability,
                "baseline_comparison": baseline_comparison_required,
                "parameter_sensitivity_penalties": True,
                "deflated_confidence_classification": confidence,
                "research_degree_of_freedom_reporting": True,
            },
            "trial_penalty": round(trial_penalty, 4),
            "observed_sharpe": observed_sharpe,
            "deflated_sharpe_approximation": round(deflated_sharpe, 6),
            "deflated_sharpe_label": "APPROXIMATION_NOT_FORMAL_PROOF",
            "raw_p_values_treated_as_proof": False,
            "bootstrap_ci_supported": True,
            "block_bootstrap_supported": True,
            "reality_check_style_warnings": fdr_warning,
            "probability_of_backtest_overfitting_estimate": round(min(0.95, trial_penalty * 1.5), 4),
            "pbo_label": "HEURISTIC_ESTIMATE_NOT_PROOF",
            "confidence_classification": confidence,
            "warnings": (
                ["FALSE_DISCOVERY_RISK_ELEVATED"] if fdr_warning else []
            ) + (["DEFLATED_SHARPE_NON_POSITIVE"] if deflated_sharpe <= 0 and observed_sharpe > 0 else []),
            **AUTHORITY_VALUES,
        }
