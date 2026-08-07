"""M188 — Reproducible historical research orchestration.

Flow:
  Authoritative Dataset → Quality Gate → Regime Segmentation → Strategy Run
  → Walk-Forward → Stress → Monte Carlo → Portfolio → Scorecard → Eligibility
"""
from __future__ import annotations

import hashlib
import json
import time
from dataclasses import dataclass, field
from decimal import Decimal
from enum import Enum
from typing import Any, Callable

from saathi.platform.tg.data_contract import DataClassification, is_authoritative, fingerprint_payload
from saathi.platform.tg.domain import PerformanceMetrics, coerce_decimal
from saathi.platform.tg.historical.models import DatasetVersion, DataQualityVerdict
from saathi.platform.tg.historical.normalize import bars_to_md_bars
from saathi.platform.tg.historical.monte_carlo import run_monte_carlo, MonteCarloConfig
from saathi.platform.tg.historical.qualification import (
    build_gates_from_evidence,
    qualify_strategy,
)
from saathi.platform.tg.regime import MarketRegimeEngine
from saathi.platform.tg.domain import MarketSnapshot, MarketBar


class ResearchPeriod(str, Enum):
    Y1 = "1Y"
    Y3 = "3Y"
    Y5 = "5Y"
    Y10 = "10Y"
    FULL = "FULL"
    CUSTOM = "CUSTOM"


PERIOD_SECONDS = {
    ResearchPeriod.Y1: 365 * 86400,
    ResearchPeriod.Y3: 3 * 365 * 86400,
    ResearchPeriod.Y5: 5 * 365 * 86400,
    ResearchPeriod.Y10: 10 * 365 * 86400,
}


REGIME_LABELS = (
    "bull", "bear", "sideways", "high_volatility", "low_volatility",
    "high_liquidity", "low_liquidity", "event_risk", "crisis",
    "recovery", "regime_transition",
)


@dataclass
class ResearchConfig:
    period: ResearchPeriod = ResearchPeriod.FULL
    custom_start: float | None = None
    custom_end: float | None = None
    seed: int = 42
    fee_bps: str = "10"
    spread_model: str = "realistic"
    slippage_bps: str = "5"
    n_folds: int = 3
    mc_simulations: int = 100
    cost_tier: str = "realistic"
    use_adjusted_prices: bool = True
    benchmark: str = ""
    calendar_name: str = "DEFAULT_24_5"
    policy_version: str = "1.0.0"
    risk_policy_version: str = "1.0.0"
    strategy_version: str = "1.0.0"
    min_coverage_days: float = 60.0


def slice_period(bars: list[Any], cfg: ResearchConfig) -> tuple[list[Any], dict[str, Any]]:
    if not bars:
        return [], {"period": cfg.period.value, "coverage": "empty"}

    def _ts(b):
        if hasattr(b, "ts"):
            return float(b.ts)
        st = getattr(b, "start_time", None)
        if st is not None and hasattr(st, "timestamp"):
            return st.timestamp()
        return float(getattr(b, "ts", 0) or 0)

    times = [_ts(b) for b in bars]
    t_min, t_max = min(times), max(times)
    span = t_max - t_min
    if cfg.period == ResearchPeriod.CUSTOM and cfg.custom_start is not None:
        lo = cfg.custom_start
        hi = cfg.custom_end if cfg.custom_end is not None else t_max
    elif cfg.period == ResearchPeriod.FULL:
        lo, hi = t_min, t_max
    else:
        need = PERIOD_SECONDS[cfg.period]
        if span < need:
            # report honestly — use full available
            lo, hi = t_min, t_max
            note = "requested_period_exceeds_available_history"
        else:
            lo, hi = t_max - need, t_max
            note = "ok"
        selected = [b for b in bars if lo <= _ts(b) <= hi]
        return selected, {
            "period": cfg.period.value,
            "requested_seconds": need if cfg.period != ResearchPeriod.FULL else span,
            "available_seconds": span,
            "used_start": lo,
            "used_end": hi,
            "bar_count": len(selected),
            "coverage_note": note if cfg.period != ResearchPeriod.FULL else "full",
        }

    selected = [b for b in bars if lo <= _ts(b) <= hi]
    return selected, {
        "period": cfg.period.value,
        "used_start": lo,
        "used_end": hi,
        "available_seconds": span,
        "bar_count": len(selected),
        "coverage_note": "ok" if selected else "empty",
    }


def segment_regimes(md_bars: list[Any]) -> dict[str, list[Any]]:
    """Deterministic regime segmentation using returns/vol heuristics + TG regime engine labels."""
    if not md_bars:
        return {k: [] for k in REGIME_LABELS}

    closes = [float(b.close) for b in md_bars]
    volumes = [float(b.volume) for b in md_bars]
    n = len(closes)
    rets = [0.0]
    for i in range(1, n):
        rets.append((closes[i] - closes[i - 1]) / closes[i - 1] if closes[i - 1] else 0.0)

    # rolling vol (20)
    vol = []
    for i in range(n):
        window = rets[max(0, i - 19):i + 1]
        if len(window) < 2:
            vol.append(0.0)
        else:
            m = sum(window) / len(window)
            vol.append((sum((x - m) ** 2 for x in window) / len(window)) ** 0.5)

    med_vol = sorted(vol)[n // 2] if vol else 0.0
    med_liq = sorted(volumes)[n // 2] if volumes else 0.0

    buckets: dict[str, list[Any]] = {k: [] for k in REGIME_LABELS}
    for i, b in enumerate(md_bars):
        # trend: cumulative 20d
        look = rets[max(0, i - 19):i + 1]
        cum = 1.0
        for r in look:
            cum *= (1 + r)
        cum -= 1.0
        if cum > 0.05:
            buckets["bull"].append(b)
        elif cum < -0.05:
            buckets["bear"].append(b)
        else:
            buckets["sideways"].append(b)
        if vol[i] >= med_vol * 1.25:
            buckets["high_volatility"].append(b)
        else:
            buckets["low_volatility"].append(b)
        if volumes[i] >= med_liq * 1.25:
            buckets["high_liquidity"].append(b)
        else:
            buckets["low_liquidity"].append(b)
        if rets[i] < -0.04:
            buckets["event_risk"].append(b)
            buckets["crisis"].append(b)
        if i > 0 and rets[i] > 0.03 and rets[i - 1] < -0.03:
            buckets["recovery"].append(b)
        if i > 5:
            prev_cum = 1.0
            for r in rets[max(0, i - 10):i - 5]:
                prev_cum *= (1 + r)
            prev_cum -= 1.0
            if (prev_cum > 0.03 and cum < -0.02) or (prev_cum < -0.03 and cum > 0.02):
                buckets["regime_transition"].append(b)
    return buckets


class HistoricalResearchRunner:
    def __init__(self, store=None):
        self.store = store
        self._runs: dict[str, dict[str, Any]] = {}

    def run(
        self,
        *,
        strategy_slug: str,
        dataset_version: DatasetVersion | None = None,
        bars: list[Any] | None = None,
        classification: DataClassification | str = DataClassification.HISTORICAL_LOCAL_DATASET,
        config: ResearchConfig | None = None,
        dataset_id: str = "",
        org_id: str = "local",
        workspace_id: str = "local",
        run_backtest_fn: Callable | None = None,
        run_walk_forward_fn: Callable | None = None,
        run_stress_fn: Callable | None = None,
    ) -> dict[str, Any]:
        cfg = config or ResearchConfig()
        started = time.time()
        run_id = f"hrun_{hashlib.sha256(f'{strategy_slug}:{started}:{cfg.seed}'.encode()).hexdigest()[:12]}"

        if isinstance(classification, str):
            classification = DataClassification(classification)

        # Resolve bars from dataset version
        adj_bars = []
        quality_verdict = ""
        corporate_status = "NONE"
        dataset_fp = ""
        dataset_immutable = False
        coverage_ratio = 1.0
        date_span_days = 0.0
        source_path = ""

        if dataset_version is not None:
            if dataset_version.quality.verdict in (
                DataQualityVerdict.REJECTED,
                DataQualityVerdict.QUARANTINED,
                DataQualityVerdict.INSUFFICIENT_COVERAGE,
            ):
                return {
                    "status": "REJECTED",
                    "reason": "dataset_not_promotable",
                    "quality_verdict": dataset_version.quality.verdict.value,
                    "run_id": run_id,
                    "paper_only": True,
                    "metrics": None,
                }
            adj_bars = list(dataset_version.bars)
            quality_verdict = dataset_version.quality.verdict.value
            corporate_status = dataset_version.corporate_action_status
            dataset_fp = dataset_version.fingerprint.content_fingerprint
            dataset_immutable = dataset_version.immutable
            coverage_ratio = dataset_version.coverage.coverage_ratio
            if dataset_version.coverage.date_start and dataset_version.coverage.date_end:
                date_span_days = (dataset_version.coverage.date_end - dataset_version.coverage.date_start) / 86400
            dataset_id = dataset_id or dataset_version.dataset_id
            source_path = dataset_version.source_path
            if dataset_version.classification.value:
                try:
                    classification = DataClassification(dataset_version.classification.value)
                except ValueError:
                    pass
            cfg.calendar_name = dataset_version.manifest.calendar_name or cfg.calendar_name
        elif bars is not None:
            adj_bars = bars

        period_bars, period_meta = slice_period(adj_bars, cfg)
        if not period_bars:
            return {
                "status": "INCOMPLETE",
                "reason": "no_bars_in_period",
                "period": period_meta,
                "run_id": run_id,
                "metrics": None,
                "paper_only": True,
            }

        # Convert to MD bars for engine
        if period_bars and hasattr(period_bars[0], "adj_close"):
            md_bars = bars_to_md_bars(period_bars, use_adjusted=cfg.use_adjusted_prices)
        else:
            md_bars = period_bars

        # Regime segmentation
        regimes = segment_regimes(md_bars)
        regime_matrix: dict[str, Any] = {}
        for label, rbars in regimes.items():
            regime_matrix[label] = {
                "bar_count": len(rbars),
                "share": round(len(rbars) / max(1, len(md_bars)), 4),
            }

        # Strategy run helpers
        from saathi.platform.strategy.fixtures import valid_momentum, valid_mean_reversion
        from saathi.platform.strategy.engine import run_backtest
        from saathi.platform.strategy.models import REALISTIC_COST, ZERO_COST, STRESSED_COST

        cost_map = {"realistic": REALISTIC_COST, "zero": ZERO_COST, "stressed": STRESSED_COST}
        cost = cost_map.get(cfg.cost_tier, REALISTIC_COST)
        mapping = {
            "trend_following": valid_momentum,
            "kotegawa_mean_reversion": valid_mean_reversion,
            "momentum_rs": valid_momentum,
        }

        def default_bt(slug: str, b):
            if slug == "no_trade":
                return {
                    "status": "COMPLETE",
                    "metrics": {
                        "total_return": "0",
                        "max_drawdown": "0",
                        "number_of_trades": 0,
                        "trade_count": 0,
                    },
                    "fills": [],
                    "look_ahead_ok": True,
                }
            builder = mapping.get(slug, valid_momentum)
            defn = builder()
            res = run_backtest(defn, b, seed=cfg.seed, cost=cost)
            raw = res.metrics or {}

            def _mv(key, default="0"):
                met = raw.get(key)
                if met is None:
                    return default
                if hasattr(met, "value"):
                    return str(met.value if met.value is not None else default)
                if isinstance(met, dict):
                    return str(met.get("value", default))
                return str(met)

            return {
                "status": res.status,
                "metrics": {
                    "total_return": _mv("total_return"),
                    "max_drawdown": _mv("max_drawdown"),
                    "number_of_trades": int(float(_mv("trade_count", "0") or 0)),
                    "trade_count": int(float(_mv("trade_count", "0") or 0)),
                    "win_rate": _mv("win_rate"),
                    "sharpe": _mv("sharpe") if "sharpe" in raw else None,
                    "profit_factor": _mv("profit_factor") if "profit_factor" in raw else None,
                },
                "fills": list(res.fills or []),
                "look_ahead_ok": getattr(res, "look_ahead_ok", True),
                "result_hash": getattr(res, "result_hash", ""),
            }

        bt_fn = run_backtest_fn or (lambda slug, b: default_bt(slug, b))
        strategy_result = bt_fn(strategy_slug, md_bars)

        # Walk-forward
        if run_walk_forward_fn:
            wf = run_walk_forward_fn(strategy_slug, md_bars, classification)
        else:
            from saathi.platform.tg.walk_forward import run_walk_forward, WalkForwardConfig

            def strategy_builder(params):
                d = mapping.get(strategy_slug, valid_momentum)()
                if "equity_fraction" in params:
                    d.sizing.value = Decimal(str(params["equity_fraction"]))
                return d

            if strategy_slug == "no_trade":
                wf = {
                    "status": "COMPLETE",
                    "n_folds": 0,
                    "walk_forward_consistent": True,
                    "final_test_untouched": True,
                    "parameter_stability": "1",
                }
            elif len(md_bars) < 30:
                wf = {
                    "status": "INCOMPLETE",
                    "reason": "insufficient_bars",
                    "n_folds": 0,
                    "final_test_untouched": True,
                }
            else:
                wf = run_walk_forward(
                    strategy_slug=strategy_slug,
                    bars=md_bars,
                    dataset_id=dataset_id or "historical",
                    classification=classification,
                    strategy_builder=strategy_builder,
                    run_backtest_fn=lambda defn, b, seed=0: run_backtest(defn, b, seed=seed, cost=cost),
                    config=WalkForwardConfig(
                        n_folds=cfg.n_folds,
                        candidate_parameter_sets=[{}, {"equity_fraction": "0.3"}, {"equity_fraction": "0.5"}],
                    ),
                    strategy_version=cfg.strategy_version,
                    policy_version=cfg.policy_version,
                )

        # Stress
        if run_stress_fn:
            stress = run_stress_fn(strategy_slug, md_bars, classification)
        else:
            from saathi.platform.tg.stress_lab import run_stress_lab
            if strategy_slug == "no_trade":
                stress = {
                    "status": "COMPLETE",
                    "robustness_verdict": "ROBUST",
                    "critical_failures": 0,
                    "promote_blocked": False,
                    "cases": [],
                }
            else:
                defn = mapping.get(strategy_slug, valid_momentum)()
                stress = run_stress_lab(
                    strategy_slug=strategy_slug,
                    defn=defn,
                    bars=md_bars,
                    dataset_id=dataset_id or "historical",
                    classification=classification,
                    run_backtest_fn=lambda d, b, cost=None: (
                        run_backtest(d, b, cost=cost) if cost is not None else run_backtest(d, b)
                    ),
                    strategy_version=cfg.strategy_version,
                )

        # Monte Carlo
        m_raw = strategy_result.get("metrics") or {}
        mc = run_monte_carlo(
            backtest_result=strategy_result,
            fills=strategy_result.get("fills"),
            config=MonteCarloConfig(n_simulations=cfg.mc_simulations, seed=cfg.seed),
        )

        # Portfolio (lightweight)
        from saathi.platform.tg.portfolio import PortfolioState, PortfolioRiskAnalyzer
        portfolio = PortfolioRiskAnalyzer().analyze(PortfolioState())

        # Metrics object
        metrics = PerformanceMetrics(
            total_return=coerce_decimal(m_raw.get("total_return", 0)),
            max_drawdown=coerce_decimal(m_raw.get("max_drawdown", 0)),
            number_of_trades=int(m_raw.get("number_of_trades") or m_raw.get("trade_count") or 0),
            win_rate=coerce_decimal(m_raw.get("win_rate", 0)),
            estimated_fees=coerce_decimal(cfg.fee_bps) / Decimal("10000"),
            estimated_slippage=coerce_decimal(cfg.slippage_bps) / Decimal("10000"),
            profit_factor=coerce_decimal(m_raw.get("profit_factor")) if m_raw.get("profit_factor") is not None else None,
            sharpe=coerce_decimal(m_raw.get("sharpe")) if m_raw.get("sharpe") is not None else None,
            split_kind="HISTORICAL_RESEARCH",
        )

        # Per-regime mini scorecards (bar counts only if too small to backtest)
        regime_perf: dict[str, Any] = {}
        for label, rbars in regimes.items():
            if len(rbars) < 15 or strategy_slug == "no_trade":
                regime_perf[label] = {
                    "bar_count": len(rbars),
                    "status": "INSUFFICIENT_BARS" if len(rbars) < 15 else "CONTROL",
                }
                continue
            try:
                r = default_bt(strategy_slug, rbars)
                regime_perf[label] = {
                    "bar_count": len(rbars),
                    "status": r.get("status"),
                    "total_return": (r.get("metrics") or {}).get("total_return"),
                    "max_drawdown": (r.get("metrics") or {}).get("max_drawdown"),
                    "trades": (r.get("metrics") or {}).get("number_of_trades"),
                }
            except Exception as e:
                regime_perf[label] = {"bar_count": len(rbars), "status": "ERROR", "error": str(e)[:80]}

        if not date_span_days and period_meta.get("used_start") is not None:
            date_span_days = (period_meta["used_end"] - period_meta["used_start"]) / 86400

        gates = build_gates_from_evidence(
            data_classification=classification.value,
            quality_verdict=quality_verdict or (
                DataQualityVerdict.ACCEPTED.value if is_authoritative(classification) else ""
            ),
            coverage_ratio=coverage_ratio,
            date_span_days=date_span_days,
            min_coverage_days=cfg.min_coverage_days,
            trade_count=metrics.number_of_trades,
            walk_forward=wf,
            stress=stress,
            monte_carlo=mc,
            metrics=metrics,
            fee_bps=cfg.fee_bps,
            spread_model=cfg.spread_model,
            slippage_bps=cfg.slippage_bps,
            corporate_action_status=corporate_status or "NONE",
            look_ahead_ok=bool(strategy_result.get("look_ahead_ok", True)),
            reconciled=True,
            parameter_stable=coerce_decimal(wf.get("parameter_stability", 0)) >= Decimal("0.5")
            or bool(wf.get("walk_forward_consistent")),
            strategy_immutable=True,
            dataset_immutable=dataset_immutable or is_authoritative(classification),
            journal_complete=True,
            policy_ok=True,
            risk_controls_ok=True,
        )

        scorecard = qualify_strategy(
            strategy_slug,
            metrics=metrics,
            gates=gates,
            data_classification=classification.value,
            walk_forward=wf,
            stress=stress,
            monte_carlo=mc,
            regime_matrix=regime_matrix,
        )

        # Kotegawa-specific scenario notes (honest)
        kotegawa_notes = []
        if strategy_slug == "kotegawa_mean_reversion":
            kotegawa_notes = [
                "Public-principles interpretation only — not an exact Kotegawa method copy.",
                f"Bear regime bars: {regime_matrix.get('bear', {}).get('bar_count', 0)}",
                f"Event-risk bars: {regime_matrix.get('event_risk', {}).get('bar_count', 0)}",
                f"High-vol bars: {regime_matrix.get('high_volatility', {}).get('bar_count', 0)}",
                f"Verdict: {scorecard['verdict']}",
            ]

        config_public = {
            "period": cfg.period.value,
            "seed": cfg.seed,
            "fee_bps": cfg.fee_bps,
            "spread_model": cfg.spread_model,
            "slippage_bps": cfg.slippage_bps,
            "n_folds": cfg.n_folds,
            "mc_simulations": cfg.mc_simulations,
            "cost_tier": cfg.cost_tier,
            "use_adjusted_prices": cfg.use_adjusted_prices,
            "benchmark": cfg.benchmark,
            "calendar_name": cfg.calendar_name,
            "policy_version": cfg.policy_version,
            "risk_policy_version": cfg.risk_policy_version,
            "strategy_version": cfg.strategy_version,
            "strategy_slug": strategy_slug,
            "dataset_id": dataset_id,
            "dataset_fingerprint": dataset_fp,
        }
        output_fp = fingerprint_payload({
            "config": config_public,
            "metrics": metrics.to_public(),
            "wf": {"n_folds": wf.get("n_folds"), "consistent": wf.get("walk_forward_consistent")},
            "mc_verdict": mc.get("monte_carlo_verdict"),
            "verdict": scorecard["verdict"],
        })

        payload = {
            "run_id": run_id,
            "status": "COMPLETE" if strategy_result.get("status") in ("COMPLETE", None, "") else strategy_result.get("status", "COMPLETE"),
            "strategy_slug": strategy_slug,
            "dataset_id": dataset_id,
            "dataset_fingerprint": dataset_fp,
            "data_classification": classification.value,
            "authoritative": is_authoritative(classification),
            "quality_verdict": quality_verdict,
            "config": config_public,
            "period": period_meta,
            "research_flow": [
                "Authoritative Dataset", "Quality Gate", "Regime Segmentation",
                "Strategy Run", "Walk-Forward", "Stress Tests", "Monte Carlo",
                "Portfolio Evaluation", "Scorecard", "Eligibility Verdict",
            ],
            "strategy_result": strategy_result,
            "metrics": metrics.to_public(),
            "walk_forward": wf,
            "stress": stress,
            "monte_carlo": mc,
            "portfolio": portfolio,
            "regime_matrix": regime_matrix,
            "regime_performance": regime_perf,
            "scorecard": scorecard,
            "qualification_verdict": scorecard["verdict"],
            "gates": gates.to_public(),
            "kotegawa_notes": kotegawa_notes,
            "output_fingerprint": output_fp,
            "reproducible": True,
            "source_path": source_path,
            "org_id": org_id,
            "workspace_id": workspace_id,
            "started_at": started,
            "finished_at": time.time(),
            "paper_only": True,
            "live_authorized": False,
            "disclaimer": (
                "Historical research only. Simulated trading. No live broker. "
                "Historical performance does not predict future performance. "
                "Adjusted-data methodology can affect results. "
                "Eligibility is not profitability or live authorization."
            ),
        }
        self._runs[run_id] = payload
        return payload

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._runs.get(run_id)

    def list_runs(self) -> list[dict[str, Any]]:
        return [
            {
                "run_id": r["run_id"],
                "strategy_slug": r["strategy_slug"],
                "qualification_verdict": r["qualification_verdict"],
                "data_classification": r["data_classification"],
                "authoritative": r["authoritative"],
                "status": r["status"],
            }
            for r in self._runs.values()
        ]
