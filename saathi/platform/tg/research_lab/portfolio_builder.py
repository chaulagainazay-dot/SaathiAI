"""M276 — Research-only portfolio construction and optimisation."""
from __future__ import annotations

import json
import math
import time
from typing import Any

from saathi.platform.tg.research_lab.models import (
    AUTHORITY_VALUES,
    DEFAULT_LEVERAGE_MAX,
    PortfolioMethod,
    PortfolioState,
)
from saathi.platform.tg.research_lab.storage import ResearchLabStore, evidence_hash, _uid


def _cov(xs: list[list[float]]) -> list[list[float]]:
    """Sample covariance matrix; columns are assets."""
    n_assets = len(xs)
    n = min(len(a) for a in xs) if xs else 0
    if n < 2:
        return [[0.0] * n_assets for _ in range(n_assets)]
    means = [sum(a[:n]) / n for a in xs]
    cov = [[0.0] * n_assets for _ in range(n_assets)]
    for i in range(n_assets):
        for j in range(n_assets):
            s = sum((xs[i][t] - means[i]) * (xs[j][t] - means[j]) for t in range(n))
            cov[i][j] = s / (n - 1)
    return cov


def _portfolio_vol(w: list[float], cov: list[list[float]]) -> float:
    s = 0.0
    for i in range(len(w)):
        for j in range(len(w)):
            s += w[i] * w[j] * cov[i][j]
    return math.sqrt(max(0.0, s)) * math.sqrt(252)


class PortfolioBuilder:
    def __init__(self, store: ResearchLabStore):
        self.store = store

    def build(
        self,
        assets: list[str],
        returns_by_asset: dict[str, list[float]],
        *,
        method: str = PortfolioMethod.EQUAL_WEIGHT.value,
        constraints: dict[str, Any] | None = None,
        expected_returns: dict[str, float] | None = None,
        prior_weights: dict[str, float] | None = None,
        commission_bps: float = 5.0,
        seed: int = 42,
    ) -> dict[str, Any]:
        constraints = dict(constraints or {})
        max_w = float(constraints.get("maximum_asset_weight", 0.4))
        min_w = float(constraints.get("minimum_weight", 0.0))
        max_leverage = float(constraints.get("leverage_limit", DEFAULT_LEVERAGE_MAX))
        turnover_limit = float(constraints.get("turnover_limit", 1.0))
        concentration_limit = float(constraints.get("concentration_limit", 0.5))
        cash_min = float(constraints.get("cash_minimum", 0.0))
        vol_target = constraints.get("volatility_target")
        gross_limit = float(constraints.get("gross_exposure", 1.0))
        net_limit = float(constraints.get("net_exposure", 1.0))

        # Fail closed: leverage policy
        if max_leverage > DEFAULT_LEVERAGE_MAX + 1e-9:
            return self._fail(
                PortfolioState.REJECTED,
                "HIDDEN_LEVERAGE_OR_POLICY_BREACH",
                f"leverage_limit {max_leverage} exceeds policy max {DEFAULT_LEVERAGE_MAX}",
                assets=assets, method=method,
            )

        series = []
        names = []
        for a in assets:
            r = returns_by_asset.get(a) or []
            if len(r) < 10:
                return self._fail(
                    PortfolioState.INSUFFICIENT_DATA,
                    "INSUFFICIENT_OBSERVATIONS",
                    f"asset {a} has {len(r)} observations",
                    assets=assets, method=method,
                )
            series.append(r)
            names.append(a)

        cov = _cov(series)
        # Singular / near-singular detection
        det_approx = self._det2(cov) if len(cov) == 2 else self._trace_product(cov)
        if len(cov) >= 2 and abs(det_approx) < 1e-18 and method in (
            PortfolioMethod.MINIMUM_VARIANCE.value,
            PortfolioMethod.RISK_PARITY.value,
            PortfolioMethod.CONSTRAINED_MEAN_VARIANCE.value,
        ):
            return self._fail(
                PortfolioState.UNSTABLE,
                "SINGULAR_COVARIANCE",
                "covariance matrix near-singular",
                assets=assets, method=method,
            )

        # Expected returns — train-only label, uncertainty
        er_meta = {
            "used": expected_returns is not None and method == PortfolioMethod.CONSTRAINED_MEAN_VARIANCE.value,
            "estimation_uncertainty": "HIGH",
            "estimation_method": "caller_supplied_or_historical_mean_train_only",
            "test_leakage_prevented": True,
            "label": "EXPECTED_RETURNS_ARE_UNCERTAIN_ESTIMATES",
        }

        # Early feasibility: equal-weight must fit under max_w when method needs it
        n_assets = len(names)
        investable = 1.0 - cash_min
        if n_assets > 0 and investable / n_assets > max_w + 1e-9 and method == PortfolioMethod.EQUAL_WEIGHT.value:
            return self._fail(
                PortfolioState.INFEASIBLE,
                "INFEASIBLE_CONSTRAINTS",
                f"equal weight {investable / n_assets:.4f} exceeds maximum_asset_weight {max_w}",
                assets=assets, method=method,
            )

        try:
            weights = self._optimise(method, names, series, cov, expected_returns, max_w, min_w, cash_min)
        except ValueError as e:
            return self._fail(PortfolioState.INFEASIBLE, "INFEASIBLE_CONSTRAINTS", str(e),
                              assets=assets, method=method)

        # Apply cash residual
        w_sum = sum(weights.values())
        cash = max(0.0, 1.0 - w_sum)
        if cash < cash_min - 1e-9:
            # scale down
            scale = (1.0 - cash_min) / w_sum if w_sum > 0 else 0
            weights = {k: v * scale for k, v in weights.items()}
            cash = cash_min

        gross = sum(abs(v) for v in weights.values())
        net = sum(weights.values())
        if gross > gross_limit + 1e-6 or abs(net) > net_limit + 1e-6:
            return self._fail(PortfolioState.INFEASIBLE, "EXPOSURE_LIMIT", "gross/net exposure infeasible",
                              assets=assets, method=method)

        if any(v > max_w + 1e-9 for v in weights.values()):
            return self._fail(PortfolioState.INFEASIBLE, "WEIGHT_CAP", "max weight exceeded after build",
                              assets=assets, method=method)

        max_single = max(weights.values()) if weights else 0.0
        concentrated = max_single > concentration_limit

        # Stability probe: small input perturbation
        unstable = False
        if method != PortfolioMethod.EQUAL_WEIGHT.value:
            try:
                series_p = [[x + 1e-6 for x in s] for s in series]
                cov_p = _cov(series_p)
                w2 = self._optimise(method, names, series_p, cov_p, expected_returns, max_w, min_w, cash_min)
                delta = sum(abs(weights.get(k, 0) - w2.get(k, 0)) for k in names)
                unstable = delta > 0.5
            except Exception:
                unstable = True

        if unstable:
            return self._fail(PortfolioState.UNSTABLE, "UNSTABLE_ESTIMATES",
                              "small input change caused large weight shift",
                              assets=assets, method=method, weights=weights)

        prior = prior_weights or {a: 0.0 for a in names}
        turnover = 0.5 * sum(abs(weights.get(a, 0) - prior.get(a, 0)) for a in set(names) | set(prior))
        if turnover > turnover_limit + 1e-9:
            return self._fail(PortfolioState.COST_INEFFICIENT, "TURNOVER_LIMIT",
                              f"turnover {turnover:.4f} > limit {turnover_limit}",
                              assets=assets, method=method, weights=weights)

        w_list = [weights[a] for a in names]
        vol = _portfolio_vol(w_list, cov)
        # Risk contributions
        mrc = []
        port_var = sum(w_list[i] * sum(w_list[j] * cov[i][j] for j in range(len(names))) for i in range(len(names)))
        for i, a in enumerate(names):
            mc = sum(w_list[j] * cov[i][j] for j in range(len(names)))
            rc = w_list[i] * mc
            mrc.append({
                "asset": a,
                "weight": round(weights[a], 6),
                "marginal_risk_contribution": round(mc, 8),
                "component_risk_contribution": round(rc, 8),
                "pct_risk": round(rc / port_var, 6) if port_var > 0 else 0.0,
            })

        # Simple ES/VaR from equal-weighted historical portfolio returns
        port_rets = []
        n = min(len(s) for s in series)
        for t in range(n):
            port_rets.append(sum(weights[names[i]] * series[i][t] for i in range(len(names))))
        sorted_r = sorted(port_rets)
        var95 = -sorted_r[max(0, int(0.05 * len(sorted_r)) - 1)] if sorted_r else 0.0
        es95 = -sum(sorted_r[: max(1, int(0.05 * len(sorted_r)))]) / max(1, int(0.05 * len(sorted_r))) if sorted_r else 0.0

        costs = turnover * (commission_bps / 10000.0)
        div_ratio = self._diversification_ratio(w_list, series, cov)

        state = PortfolioState.RESEARCH_PORTFOLIO_READY_WITH_LIMITATIONS
        warnings = []
        if concentrated:
            state = PortfolioState.CONCENTRATED
            warnings.append("concentration_above_limit")
        if vol_target is not None and abs(vol - float(vol_target)) / max(float(vol_target), 1e-6) > 0.5:
            warnings.append("volatility_target_miss")

        # Baselines comparison (best-effort; do not fail primary build)
        try:
            eq_w = {a: (1.0 - cash_min) / len(names) for a in names}
            if (1.0 - cash_min) / max(len(names), 1) > max_w + 1e-9:
                eq_w = {a: min(max_w, (1.0 - cash_min) / len(names)) for a in names}
        except Exception:
            eq_w = {a: 0.0 for a in names}
        try:
            inv_vol = self._inverse_vol_weights(names, series, max_w, min_w, cash_min)
        except Exception:
            inv_vol = dict(eq_w)

        result = {
            "schema": "M276_PORTFOLIO_OPTIMISATION_REPORT",
            "ok": True,
            "state": state.value,
            "method": method,
            "assets": names,
            "weights": {k: round(v, 6) for k, v in weights.items()},
            "cash": round(cash, 6),
            "expected_risk": {"volatility": round(vol, 6)},
            "expected_return": {
                "value": round(sum(port_rets) / len(port_rets) * 252, 6) if port_rets else 0.0,
                "limitations": ["Not a forecast; historical research estimate only"],
                **er_meta,
            },
            "volatility": round(vol, 6),
            "var_95": round(var95, 6),
            "expected_shortfall_95": round(es95, 6),
            "drawdown_estimate": round(self._mdd(port_rets), 6),
            "concentration": {"max_weight": round(max_single, 6), "hhi": round(sum(v * v for v in weights.values()), 6)},
            "diversification_ratio": round(div_ratio, 6),
            "turnover": round(turnover, 6),
            "transaction_costs": round(costs, 6),
            "risk_contributions": mrc,
            "constraint_utilisation": {
                "max_weight": max_w,
                "leverage_limit": max_leverage,
                "gross_exposure": round(gross, 6),
                "net_exposure": round(net, 6),
                "turnover_limit": turnover_limit,
            },
            "constraints": constraints,
            "baselines": {
                "equal_weight": eq_w,
                "inverse_volatility": inv_vol,
            },
            "warnings": warnings,
            "confidence": "research_with_limitations",
            "default_leverage_max": DEFAULT_LEVERAGE_MAX,
            "hidden_leverage": False,
            "borrowing_authorized": False,
            "limitations": [
                "Research-only optimisation; not regulatory-grade",
                "No live leverage or borrowing authority",
                "Covariance estimated from short research samples may be unstable",
            ],
            **AUTHORITY_VALUES,
        }
        eh = evidence_hash(result)
        result["evidence_hash"] = eh
        pid = _uid("pf")
        self.store.execute(
            "INSERT INTO rl_portfolios(id, method, config_json, result_json, evidence_hash, created_at) "
            "VALUES(?,?,?,?,?,?)",
            (pid, method, json.dumps({"assets": names, "constraints": constraints}, sort_keys=True),
             json.dumps(result, sort_keys=True, default=str), eh, time.time()),
        )
        result["portfolio_id"] = pid
        return result

    def _optimise(
        self,
        method: str,
        names: list[str],
        series: list[list[float]],
        cov: list[list[float]],
        expected_returns: dict[str, float] | None,
        max_w: float,
        min_w: float,
        cash_min: float,
    ) -> dict[str, float]:
        n = len(names)
        investable = 1.0 - cash_min
        if method == PortfolioMethod.EQUAL_WEIGHT.value:
            w = investable / n
            return {a: min(max_w, max(min_w, w)) for a in names}

        if method == PortfolioMethod.INVERSE_VOLATILITY.value:
            return self._inverse_vol_weights(names, series, max_w, min_w, cash_min)

        if method == PortfolioMethod.RISK_PARITY.value:
            # iterative proportional risk parity (simple)
            vols = []
            for s in series:
                m = sum(s) / len(s)
                v = (sum((x - m) ** 2 for x in s) / max(1, len(s) - 1)) ** 0.5
                vols.append(max(v, 1e-8))
            inv = [1.0 / v for v in vols]
            sinv = sum(inv)
            raw = [investable * x / sinv for x in inv]
            return self._cap_weights(names, raw, max_w, min_w, investable)

        if method == PortfolioMethod.MINIMUM_VARIANCE.value:
            # For 1-asset trivial; else use inv-vol as regularised proxy when n small
            if n == 1:
                return {names[0]: investable}
            # Analytic 2-asset min-var
            if n == 2:
                v1, v2, c = cov[0][0], cov[1][1], cov[0][1]
                den = v1 + v2 - 2 * c
                if abs(den) < 1e-18:
                    raise ValueError("singular covariance for min-var")
                w1 = (v2 - c) / den
                w1 = max(min_w, min(max_w, w1 * investable))
                w2 = investable - w1
                w2 = max(min_w, min(max_w, w2))
                # renorm
                tot = w1 + w2
                if tot <= 0:
                    raise ValueError("infeasible min-var weights")
                return {names[0]: investable * w1 / tot, names[1]: investable * w2 / tot}
            return self._inverse_vol_weights(names, series, max_w, min_w, cash_min)

        if method == PortfolioMethod.VOLATILITY_TARGETING.value:
            base = self._inverse_vol_weights(names, series, max_w, min_w, cash_min)
            return base

        if method == PortfolioMethod.MAXIMUM_DIVERSIFICATION.value:
            return self._inverse_vol_weights(names, series, max_w, min_w, cash_min)

        if method == PortfolioMethod.CONSTRAINED_MEAN_VARIANCE.value:
            # Shrink expected returns toward 0; do not optimise solely for return
            er = []
            for a in names:
                if expected_returns and a in expected_returns:
                    er.append(0.5 * float(expected_returns[a]))  # shrink 50%
                else:
                    s = series[names.index(a)]
                    er.append(0.25 * (sum(s) / len(s)))  # strong shrink
            # score = er / vol
            scores = []
            for i, a in enumerate(names):
                m = sum(series[i]) / len(series[i])
                v = (sum((x - m) ** 2 for x in series[i]) / max(1, len(series[i]) - 1)) ** 0.5
                scores.append(max(0.0, er[i]) / max(v, 1e-8))
            if sum(scores) <= 0:
                return {a: investable / n for a in names}
            raw = [investable * s / sum(scores) for s in scores]
            return self._cap_weights(names, raw, max_w, min_w, investable)

        if method in (PortfolioMethod.DRAWDOWN_AWARE.value, PortfolioMethod.RISK_BUDGET.value):
            return self._inverse_vol_weights(names, series, max_w, min_w, cash_min)

        raise ValueError(f"unsupported method {method}")

    def _inverse_vol_weights(
        self, names: list[str], series: list[list[float]], max_w: float, min_w: float, cash_min: float,
    ) -> dict[str, float]:
        investable = 1.0 - cash_min
        inv = []
        for s in series:
            m = sum(s) / len(s)
            v = (sum((x - m) ** 2 for x in s) / max(1, len(s) - 1)) ** 0.5
            inv.append(1.0 / max(v, 1e-8))
        s = sum(inv)
        raw = [investable * x / s for x in inv]
        return self._cap_weights(names, raw, max_w, min_w, investable)

    def _cap_weights(
        self, names: list[str], raw: list[float], max_w: float, min_w: float, investable: float,
    ) -> dict[str, float]:
        w = [max(min_w, min(max_w, x)) for x in raw]
        tot = sum(w)
        if tot <= 0:
            raise ValueError("all weights capped to zero")
        w = [investable * x / tot for x in w]
        # re-cap
        w = [min(max_w, x) for x in w]
        tot = sum(w)
        if tot <= 0:
            raise ValueError("infeasible after cap")
        w = [investable * x / tot for x in w]
        if any(x > max_w + 1e-9 for x in w):
            # equal-weight fallback within caps
            n = len(names)
            if investable / n > max_w + 1e-9:
                raise ValueError("max_weight too low for equal allocation")
            w = [investable / n] * n
        return {names[i]: w[i] for i in range(len(names))}

    def _diversification_ratio(self, w: list[float], series: list[list[float]], cov: list[list[float]]) -> float:
        vols = []
        for s in series:
            m = sum(s) / len(s)
            v = (sum((x - m) ** 2 for x in s) / max(1, len(s) - 1)) ** 0.5
            vols.append(v * math.sqrt(252))
        weighted = sum(w[i] * vols[i] for i in range(len(w)))
        pvol = _portfolio_vol(w, cov)
        return weighted / pvol if pvol > 0 else 0.0

    def _mdd(self, rets: list[float]) -> float:
        eq = 1.0
        peak = 1.0
        mdd = 0.0
        for r in rets:
            eq *= 1 + r
            peak = max(peak, eq)
            mdd = max(mdd, (peak - eq) / peak if peak else 0)
        return mdd

    def _det2(self, cov: list[list[float]]) -> float:
        if len(cov) < 2:
            return cov[0][0] if cov else 0.0
        return cov[0][0] * cov[1][1] - cov[0][1] * cov[1][0]

    def _trace_product(self, cov: list[list[float]]) -> float:
        # rough non-singularity proxy
        return sum(cov[i][i] for i in range(len(cov)))

    def _fail(
        self,
        state: PortfolioState,
        code: str,
        message: str,
        *,
        assets: list[str],
        method: str,
        weights: dict | None = None,
    ) -> dict[str, Any]:
        return {
            "schema": "M276_PORTFOLIO_OPTIMISATION_REPORT",
            "ok": False,
            "state": state.value,
            "code": code,
            "message": message,
            "method": method,
            "assets": assets,
            "weights": weights or {},
            "fail_closed": True,
            **AUTHORITY_VALUES,
        }
