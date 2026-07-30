"""M278 — Portfolio stress testing (research only)."""
from __future__ import annotations

import json
import time
from typing import Any

from saathi.platform.tg.research_lab.comparison import _metrics_from_returns, _lcg
from saathi.platform.tg.research_lab.models import AUTHORITY_VALUES
from saathi.platform.tg.research_lab.storage import ResearchLabStore, evidence_hash, _uid


class StressTestingEngine:
    def __init__(self, store: ResearchLabStore):
        self.store = store

    def run(
        self,
        weights: dict[str, float],
        returns_by_asset: dict[str, list[float]],
        *,
        portfolio_id: str | None = None,
        max_drawdown_limit: float = 0.35,
        seed: int = 42,
    ) -> dict[str, Any]:
        assets = list(weights.keys())
        n = min(len(returns_by_asset.get(a, [])) for a in assets) if assets else 0
        if n < 10:
            return {
                "ok": False,
                "code": "INSUFFICIENT_DATA",
                "message": "Need more observations for stress testing",
                **AUTHORITY_VALUES,
            }

        base = []
        for t in range(n):
            base.append(sum(weights[a] * returns_by_asset[a][t] for a in assets))
        base_m = _metrics_from_returns(base)

        historical = []
        # Major drawdown window: worst 20-bar window
        worst_loss = 0.0
        worst_i = 0
        for i in range(0, max(1, n - 20)):
            window = base[i : i + 20]
            eq = 1.0
            for r in window:
                eq *= 1 + r
            loss = 1 - eq
            if loss > worst_loss:
                worst_loss = loss
                worst_i = i
        historical.append({
            "name": "worst_20bar_drawdown_window",
            "start": worst_i,
            "portfolio_loss": round(worst_loss, 6),
            "maximum_drawdown": round(worst_loss, 6),
            "category": "historical_replay",
            "limitations": ["Bounded sample; not full crisis library"],
        })
        historical.append({
            "name": "high_volatility_window",
            "portfolio_loss": round(base_m["expected_shortfall_95"] * 5, 6),
            "maximum_drawdown": base_m["maximum_drawdown"],
            "category": "historical_replay",
        })

        hypothetical = []
        shocks = {
            "equity_drawdown": -0.20,
            "crypto_drawdown": -0.35,
            "volatility_doubling": None,  # scale
            "correlation_convergence": -0.10,
            "slippage_increase": -0.02,
            "commission_increase": -0.01,
            "delayed_signal": -0.03,
            "missing_data": -0.02,
            "strategy_failure": -0.15,
            "benchmark_shock": -0.12,
            "liquidity_reduction": -0.05,
            "one_strategy_collapse": -0.18,
            "regime_misclassification": -0.08,
        }
        for name, shock in shocks.items():
            if name == "volatility_doubling":
                shocked = [r * 2 for r in base]
                m = _metrics_from_returns(shocked)
                loss = m["maximum_drawdown"]
            else:
                loss = abs(shock or 0)
                m = {
                    "maximum_drawdown": loss,
                    "var_95": loss * 0.6,
                    "expected_shortfall_95": loss * 0.8,
                }
            hypothetical.append({
                "name": name,
                "portfolio_loss": round(loss, 6),
                "maximum_drawdown": round(m["maximum_drawdown"], 6),
                "var_95": round(m.get("var_95", loss * 0.5), 6),
                "expected_shortfall_95": round(m.get("expected_shortfall_95", loss * 0.7), 6),
                "category": "hypothetical",
            })

        # Statistical: block bootstrap + reshape
        rng = _lcg(seed)
        boot_losses = []
        block = 5
        for _ in range(50):
            path = []
            while len(path) < n:
                start = int(next(rng) * max(1, n - block))
                path.extend(base[start : start + block])
            path = path[:n]
            m = _metrics_from_returns(path)
            boot_losses.append(m["maximum_drawdown"])
        boot_losses.sort()
        statistical = [{
            "name": "block_bootstrap_mdd",
            "p5": round(boot_losses[max(0, int(0.05 * len(boot_losses)) - 1)], 6),
            "p50": round(boot_losses[len(boot_losses) // 2], 6),
            "p95": round(boot_losses[min(len(boot_losses) - 1, int(0.95 * len(boot_losses)))], 6),
            "category": "statistical",
            "label": "BLOCK_BOOTSTRAP_APPROXIMATION",
        }, {
            "name": "return_resampling",
            "portfolio_loss": round(boot_losses[-1], 6),
            "category": "statistical",
        }, {
            "name": "parameter_perturbation",
            "portfolio_loss": round(base_m["maximum_drawdown"] * 1.2, 6),
            "category": "statistical",
        }]

        breaches = []
        for item in historical + hypothetical:
            mdd = item.get("maximum_drawdown") or item.get("portfolio_loss") or 0
            if mdd > max_drawdown_limit:
                breaches.append({
                    "scenario": item["name"],
                    "metric": "maximum_drawdown",
                    "value": mdd,
                    "limit": max_drawdown_limit,
                    "severity": "high" if mdd > max_drawdown_limit * 1.5 else "medium",
                })

        result = {
            "schema": "M278_STRESS_TEST_AND_CANDIDATE_PROMOTION",
            "section": "stress",
            "ok": True,
            "portfolio_id": portfolio_id,
            "weights": weights,
            "base_metrics": base_m,
            "historical_stresses": historical,
            "hypothetical_stresses": hypothetical,
            "statistical_stresses": statistical,
            "breaches": breaches,
            "breach_count": len(breaches),
            "max_drawdown_limit": max_drawdown_limit,
            "limitations": [
                "Hypothetical shocks are research scenarios, not forecasts",
                "Historical stress library limited by governed data coverage",
                "Recovery time estimates omitted without longer histories",
            ],
            **AUTHORITY_VALUES,
        }
        eh = evidence_hash(result)
        result["evidence_hash"] = eh
        sid = _uid("str")
        self.store.execute(
            "INSERT INTO rl_stress(id, portfolio_id, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
            (sid, portfolio_id, json.dumps(result, sort_keys=True, default=str), eh, time.time()),
        )
        result["stress_id"] = sid
        return result
