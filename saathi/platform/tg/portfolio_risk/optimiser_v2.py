"""Portfolio Optimiser V2 — composes research_lab portfolio builder + baselines."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.portfolio_risk.models import AUTHORITY_VALUES, DEFAULT_MAX_LEVERAGE, OptimiserState
from saathi.platform.tg.portfolio_risk.storage import PortfolioRiskStore, evidence_hash, _uid
from saathi.platform.tg.portfolio_risk.analytics import _asset_returns


class PortfolioOptimiserV2:
    """Research-only optimiser wrapping M276 portfolio construction with V2 reporting."""

    def __init__(self, store: PortfolioRiskStore):
        self.store = store

    def optimise(
        self,
        symbols: list[str],
        *,
        method: str = "inverse_volatility",
        constraints: dict[str, Any] | None = None,
        seed: int = 42,
        n_bars: int = 80,
    ) -> dict[str, Any]:
        constraints = dict(constraints or {})
        constraints.setdefault("maximum_asset_weight", 0.35)
        constraints.setdefault("leverage_limit", DEFAULT_MAX_LEVERAGE)
        constraints.setdefault("turnover_limit", 1.0)
        constraints.setdefault("concentration_limit", 0.40)
        constraints.setdefault("gross_exposure", 1.0)
        constraints.setdefault("net_exposure", 1.0)
        constraints.setdefault("cash_minimum", 0.05)
        constraints.setdefault("minimum_weight", 0.0)

        if float(constraints.get("leverage_limit", 1.0)) > DEFAULT_MAX_LEVERAGE + 1e-9:
            result = {
                "ok": False,
                "state": OptimiserState.REJECTED.value,
                "code": "HIDDEN_LEVERAGE",
                "message": "leverage_limit exceeds policy",
                **AUTHORITY_VALUES,
            }
            return result

        returns_by = {s: _asset_returns(s, n_bars, seed + i) for i, s in enumerate(symbols)}

        try:
            from saathi.platform.tg.research_lab.portfolio_builder import PortfolioBuilder
            from saathi.platform.tg.research_lab.storage import ResearchLabStore
            # ephemeral store path beside risk db
            rl_path = str(self.store.db_path).replace("portfolio_risk", "pr_opt_rl")
            if rl_path == str(self.store.db_path):
                rl_path = str(self.store.db_path) + ".rl"
            builder = PortfolioBuilder(ResearchLabStore(rl_path))
            out = builder.build(symbols, returns_by, method=method, constraints=constraints, seed=seed)
        except Exception as e:
            out = {
                "ok": False,
                "state": OptimiserState.INFEASIBLE.value,
                "code": "OPTIMISER_ERROR",
                "message": str(e),
                **AUTHORITY_VALUES,
            }

        # Normalize state
        if out.get("ok"):
            out["state"] = out.get("state") or OptimiserState.READY.value
            out["optimiser_version"] = "v2"
            out["composes"] = "M276_PortfolioBuilder"
        else:
            out["state"] = out.get("state") or OptimiserState.INFEASIBLE.value
            out["optimiser_version"] = "v2"

        out["baselines_required"] = True
        out["authorizes_execution"] = False
        out.update({k: v for k, v in AUTHORITY_VALUES.items() if k not in out})

        eh = evidence_hash(out)
        out["evidence_hash"] = eh
        oid = _uid("opt")
        self.store.execute(
            "INSERT INTO pr_optimisations(id, method, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
            (oid, method, __import__("json").dumps(out, sort_keys=True, default=str), eh, time.time()),
        )
        out["optimisation_id"] = oid
        self.store.audit("optimiser.v2", subject=oid, detail={"method": method, "ok": out.get("ok")})
        return out
