"""Runtime estimator for research jobs (heuristic, labelled)."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.research_orchestrator.models import AUTHORITY_VALUES


class RuntimeEstimator:
    """Estimate runtime/budget from job kind — deterministic heuristics only."""

    KIND_BASE = {
        "noop": (0.5, 1.0),
        "strategy_compare": (2.0, 5.0),
        "research_lab_bootstrap": (5.0, 15.0),
        "robustness": (3.0, 8.0),
        "regime": (2.0, 4.0),
        "portfolio": (2.0, 5.0),
        "fail_probe": (0.1, 1.0),
    }

    def estimate(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        config = config or {}
        kind = config.get("kind", "noop")
        base_rt, base_budget = self.KIND_BASE.get(kind, (1.0, 2.0))
        n_strategies = len(config.get("strategy_ids") or []) or 1
        trials = int(config.get("trial_count") or 1)
        rt = base_rt * (1 + 0.1 * (n_strategies - 1)) * max(1, trials) ** 0.5
        budget = base_budget * max(1, n_strategies) * max(1, min(trials, 10)) ** 0.5
        return {
            "ok": True,
            "kind": kind,
            "estimated_runtime_sec": round(rt, 3),
            "budget_units": round(budget, 3),
            "method": "deterministic_heuristic",
            "label": "ESTIMATE_NOT_GUARANTEE",
            "limitations": ["Heuristic only; not a wall-clock SLA"],
            **AUTHORITY_VALUES,
        }
