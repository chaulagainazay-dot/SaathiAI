"""M248 — Structured Strategy Registry.

Institutional strategy catalog with full metadata. Paper / research only.
"""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.intelligence.models import (
    AUTHORITY_VALUES,
    STRATEGY_CATEGORIES,
    RiskProfile,
    SizingModel,
)

# Full strategy definitions. Each is deterministic research metadata only.
_STRATEGIES: list[dict[str, Any]] = [
    {
        "id": "mom_rs_equity",
        "category": "momentum",
        "name": "Relative Strength Momentum",
        "description": "Ranks equities by multi-horizon relative strength; long top decile with trend filter.",
        "supported_markets": ["equities", "etf"],
        "supported_assets": ["US_LARGE_CAP", "US_MID_CAP", "SECTOR_ETF"],
        "required_indicators": ["returns_21d", "returns_63d", "returns_126d", "sma_200"],
        "entry_conditions": ["rank_top_decile", "price_above_sma_200", "volume_above_avg"],
        "exit_conditions": ["rank_below_median", "price_below_sma_200", "time_stop_63d"],
        "stop_loss_logic": "ATR(14)*2.5 trailing from entry high",
        "take_profit_logic": "None fixed; scale-out at +2R optional",
        "sizing_model": SizingModel.VOLATILITY_TARGET.value,
        "expected_holding_period": "21-63 trading days",
        "risk_profile": RiskProfile.MODERATE.value,
        "confidence_model": "rank_stability * trend_alignment * volume_confirm",
        "required_confirmations": ["trend_filter", "liquidity_floor"],
        "limitations": ["crowding risk", "regime-dependent", "turnover/tax drag"],
    },
    {
        "id": "mr_bollinger_reversion",
        "category": "mean_reversion",
        "name": "Bollinger Band Mean Reversion",
        "description": "Fade 2-sigma deviations in range-bound markets with RSI confirmation.",
        "supported_markets": ["equities", "etf", "fx_paper"],
        "supported_assets": ["LIQUID_EQUITY", "INDEX_ETF"],
        "required_indicators": ["bollinger_20_2", "rsi_14", "atr_14"],
        "entry_conditions": ["close_below_lower_band", "rsi_below_30", "regime_not_trending"],
        "exit_conditions": ["close_above_mid_band", "rsi_above_50", "time_stop_10d"],
        "stop_loss_logic": "Beyond lower band by 1.5*ATR",
        "take_profit_logic": "Mid-band or +1.5R",
        "sizing_model": SizingModel.FIXED_FRACTIONAL.value,
        "expected_holding_period": "2-10 trading days",
        "risk_profile": RiskProfile.MODERATE.value,
        "confidence_model": "band_distance * rsi_extreme * regime_score",
        "required_confirmations": ["range_regime", "no_earnings_within_3d"],
        "limitations": ["fails in strong trends", "gap risk", "needs liquid names"],
    },
    {
        "id": "tf_dual_ma",
        "category": "trend_following",
        "name": "Dual Moving Average Trend",
        "description": "Classic dual-MA crossover with ATR stops and volatility targeting.",
        "supported_markets": ["equities", "etf", "futures_paper", "crypto_paper"],
        "supported_assets": ["INDEX", "SECTOR_ETF", "MAJOR_CRYPTO_PAPER"],
        "required_indicators": ["sma_50", "sma_200", "atr_14"],
        "entry_conditions": ["sma_50_cross_above_sma_200", "atr_filter_ok"],
        "exit_conditions": ["sma_50_cross_below_sma_200", "trailing_stop_hit"],
        "stop_loss_logic": "ATR(14)*3 from entry; trail after +1R",
        "take_profit_logic": "Trail only (trend following)",
        "sizing_model": SizingModel.VOLATILITY_TARGET.value,
        "expected_holding_period": "20-200 trading days",
        "risk_profile": RiskProfile.MODERATE.value,
        "confidence_model": "ma_separation * slope_consistency",
        "required_confirmations": ["volatility_target_feasible"],
        "limitations": ["whipsaw in ranges", "late entries/exits", "drawdown clusters"],
    },
    {
        "id": "bo_donchian",
        "category": "breakout",
        "name": "Donchian Channel Breakout",
        "description": "Enter on N-day high/low breakouts with volume expansion.",
        "supported_markets": ["equities", "futures_paper", "crypto_paper"],
        "supported_assets": ["LIQUID_EQUITY", "INDEX", "MAJOR_CRYPTO_PAPER"],
        "required_indicators": ["donchian_20", "donchian_55", "volume_sma_20"],
        "entry_conditions": ["close_above_donchian_high_20", "volume_gt_1_5x_avg"],
        "exit_conditions": ["close_below_donchian_low_10", "time_stop_40d"],
        "stop_loss_logic": "Donchian low of last 10 bars or 2*ATR",
        "take_profit_logic": "Trail with Donchian mid / ATR",
        "sizing_model": SizingModel.FIXED_FRACTIONAL.value,
        "expected_holding_period": "5-40 trading days",
        "risk_profile": RiskProfile.AGGRESSIVE.value,
        "confidence_model": "breakout_quality * volume_expansion * false_breakout_filter",
        "required_confirmations": ["volume_expansion", "no_major_news_blackout"],
        "limitations": ["false breakouts", "gap risk", "high turnover"],
    },
    {
        "id": "vol_regime_switch",
        "category": "volatility",
        "name": "Volatility Regime Switch",
        "description": "Allocate between risk-on and defensive based on realised/implied vol regime.",
        "supported_markets": ["equities", "etf"],
        "supported_assets": ["SPY", "QQQ", "TLT", "GLD", "CASH"],
        "required_indicators": ["realised_vol_20", "vix_proxy", "corr_spy_tlt"],
        "entry_conditions": ["vol_regime_change", "rebalance_threshold_exceeded"],
        "exit_conditions": ["regime_revert", "scheduled_rebalance"],
        "stop_loss_logic": "Portfolio heat > 6% daily → defensive sleeve",
        "take_profit_logic": "N/A (allocation strategy)",
        "sizing_model": SizingModel.EQUAL_WEIGHT.value,
        "expected_holding_period": "continuous rebalance monthly",
        "risk_profile": RiskProfile.CONSERVATIVE.value,
        "confidence_model": "regime_persistence * vol_forecast_error",
        "required_confirmations": ["data_quality_ok"],
        "limitations": ["proxy VIX only offline", "lagged regime detection"],
    },
    {
        "id": "dca_core_equity",
        "category": "dca",
        "name": "Core Equity Dollar-Cost Average",
        "description": "Scheduled equal notional purchases into a core equity basket.",
        "supported_markets": ["equities", "etf"],
        "supported_assets": ["BROAD_MARKET_ETF", "WORLD_ETF"],
        "required_indicators": ["calendar_schedule", "cash_available"],
        "entry_conditions": ["schedule_date", "cash_above_reserve"],
        "exit_conditions": ["goal_horizon_reached", "manual_stop"],
        "stop_loss_logic": "None at unit level; portfolio max-DD alert only",
        "take_profit_logic": "None (accumulation)",
        "sizing_model": SizingModel.DCA_SCHEDULE.value,
        "expected_holding_period": "multi-year",
        "risk_profile": RiskProfile.CONSERVATIVE.value,
        "confidence_model": "horizon_alignment * fee_efficiency",
        "required_confirmations": ["cash_budget_ok"],
        "limitations": ["no tactical edge claimed", "path-dependent opportunity cost"],
    },
    {
        "id": "value_pb_pe",
        "category": "value_investing",
        "name": "Classic Value Screen",
        "description": "Long low P/B and P/E names with quality filter and sector neutrality.",
        "supported_markets": ["equities"],
        "supported_assets": ["US_LARGE_CAP", "US_MID_CAP"],
        "required_indicators": ["pe_ttm", "pb", "roe", "debt_to_equity"],
        "entry_conditions": ["pe_bottom_quintile", "pb_bottom_quintile", "roe_above_sector_median"],
        "exit_conditions": ["valuation_normalize", "quality_break", "rebalance_quarterly"],
        "stop_loss_logic": "Hard stop -25% or thesis invalidation",
        "take_profit_logic": "Valuation mean reversion to sector median",
        "sizing_model": SizingModel.EQUAL_WEIGHT.value,
        "expected_holding_period": "6-24 months",
        "risk_profile": RiskProfile.MODERATE.value,
        "confidence_model": "value_spread * quality_score * sector_neutral_residual",
        "required_confirmations": ["fundamental_data_fresh", "no_distress_flags"],
        "limitations": ["value traps", "accounting restatement risk", "slow feedback"],
    },
    {
        "id": "growth_sales_accel",
        "category": "growth_investing",
        "name": "Sales Acceleration Growth",
        "description": "Own names with accelerating revenue and positive estimate revisions.",
        "supported_markets": ["equities"],
        "supported_assets": ["US_GROWTH", "NASDAQ_LISTED"],
        "required_indicators": ["sales_yoy", "sales_accel", "eps_revision", "rs_63d"],
        "entry_conditions": ["sales_accel_positive", "eps_revision_up", "rs_above_median"],
        "exit_conditions": ["sales_decel", "revision_down", "rs_bottom_quartile"],
        "stop_loss_logic": "ATR-based or -15% hard stop",
        "take_profit_logic": "Trailing with RS deterioration",
        "sizing_model": SizingModel.VOLATILITY_TARGET.value,
        "expected_holding_period": "3-12 months",
        "risk_profile": RiskProfile.AGGRESSIVE.value,
        "confidence_model": "accel_strength * revision_breadth * momentum_confirm",
        "required_confirmations": ["liquidity", "no_going_concern"],
        "limitations": ["high valuation risk", "crowding", "narrative fragility"],
    },
    {
        "id": "swing_pullback",
        "category": "swing_trading",
        "name": "Trend Pullback Swing",
        "description": "Buy pullbacks to rising MAs in established uptrends.",
        "supported_markets": ["equities", "etf", "crypto_paper"],
        "supported_assets": ["LIQUID_EQUITY", "INDEX_ETF"],
        "required_indicators": ["sma_20", "sma_50", "rsi_14", "atr_14"],
        "entry_conditions": ["uptrend_sma20_above_sma50", "pullback_to_sma20", "rsi_recover_from_40"],
        "exit_conditions": ["target_2R", "structure_break", "time_stop_15d"],
        "stop_loss_logic": "Below swing low or 1.5*ATR",
        "take_profit_logic": "Scale 50% at 2R; trail remainder",
        "sizing_model": SizingModel.FIXED_FRACTIONAL.value,
        "expected_holding_period": "3-15 trading days",
        "risk_profile": RiskProfile.MODERATE.value,
        "confidence_model": "trend_quality * pullback_depth * volume_dry_up",
        "required_confirmations": ["higher_timeframe_trend"],
        "limitations": ["overnight gap", "news events", "false pullbacks"],
    },
    {
        "id": "scalp_microstructure_paper",
        "category": "scalping",
        "name": "Paper Microstructure Scalp",
        "description": "Very short-horizon edge simulation for research; not production-ready.",
        "supported_markets": ["equities_paper", "crypto_paper"],
        "supported_assets": ["HIGHLY_LIQUID"],
        "required_indicators": ["spread", "microprice", "order_imbalance_proxy"],
        "entry_conditions": ["spread_tight", "imbalance_threshold", "no_auction"],
        "exit_conditions": ["target_ticks", "time_stop_minutes", "spread_widens"],
        "stop_loss_logic": "Hard tick stop + inventory limit",
        "take_profit_logic": "Fixed ticks or mid reversion",
        "sizing_model": SizingModel.FIXED_NOTIONAL.value,
        "expected_holding_period": "seconds to minutes (simulated bars)",
        "risk_profile": RiskProfile.SPECULATIVE.value,
        "confidence_model": "spread_stability * fill_assumption_quality",
        "required_confirmations": ["offline_tick_or_bar_proxy"],
        "limitations": [
            "no live order book",
            "fill model is assumption-heavy",
            "not suitable for live trading claims",
        ],
    },
    {
        "id": "lt_buy_hold_core",
        "category": "long_term_investing",
        "name": "Long-Term Core Buy-and-Hold",
        "description": "Strategic multi-asset core allocation with annual rebalance bands.",
        "supported_markets": ["equities", "etf", "bonds_paper"],
        "supported_assets": ["WORLD_EQUITY", "BOND_ETF", "CASH"],
        "required_indicators": ["allocation_drift", "rebalance_band"],
        "entry_conditions": ["policy_allocation_set", "cash_deployed_per_policy"],
        "exit_conditions": ["rebalance_band_hit", "policy_change"],
        "stop_loss_logic": "None unit-level; portfolio DD monitoring only",
        "take_profit_logic": "None (strategic)",
        "sizing_model": SizingModel.EQUAL_WEIGHT.value,
        "expected_holding_period": "multi-year",
        "risk_profile": RiskProfile.CONSERVATIVE.value,
        "confidence_model": "policy_clarity * cost_efficiency * diversification",
        "required_confirmations": ["policy_documented"],
        "limitations": ["no alpha claim", "inflation/rate path risk"],
    },
]


def _public(s: dict[str, Any]) -> dict[str, Any]:
    return {
        **s,
        "paper_only": True,
        "live_authorized": False,
        "broker_required": False,
        "fingerprint": f"{s['id']}:{s['category']}:v1",
    }


class StrategyRegistryEngine:
    """Structured strategy system (M248)."""

    def __init__(self):
        self._by_id = {s["id"]: s for s in _STRATEGIES}

    def list_strategies(self, category: str | None = None) -> dict[str, Any]:
        items = [_public(s) for s in _STRATEGIES]
        if category:
            items = [s for s in items if s["category"] == category]
        return {
            "count": len(items),
            "categories": list(STRATEGY_CATEGORIES),
            "strategies": items,
            **AUTHORITY_VALUES,
        }

    def get(self, strategy_id: str) -> dict[str, Any] | None:
        s = self._by_id.get(strategy_id)
        if not s:
            return None
        return _public(s)

    def categories(self) -> dict[str, Any]:
        counts: dict[str, int] = {c: 0 for c in STRATEGY_CATEGORIES}
        for s in _STRATEGIES:
            counts[s["category"]] = counts.get(s["category"], 0) + 1
        return {
            "categories": [
                {"id": c, "count": counts.get(c, 0)} for c in STRATEGY_CATEGORIES
            ],
            "total_strategies": len(_STRATEGIES),
            **AUTHORITY_VALUES,
        }

    def run_signal(
        self,
        strategy_id: str,
        bars: list[dict[str, float]] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Deterministic paper signal from synthetic/offline bars. No broker."""
        s = self.get(strategy_id)
        if not s:
            return {"ok": False, "code": "STRATEGY_NOT_FOUND", "strategy_id": strategy_id, **AUTHORITY_VALUES}
        bars = bars or self._default_bars()
        params = params or {}
        closes = [float(b.get("close", b.get("c", 0))) for b in bars]
        signal = self._eval(s, closes, params)
        return {
            "ok": True,
            "strategy_id": strategy_id,
            "category": s["category"],
            "signal": signal,
            "bars_used": len(closes),
            "deterministic": True,
            "paper_only": True,
            **AUTHORITY_VALUES,
        }

    def _default_bars(self, n: int = 60) -> list[dict[str, float]]:
        # Deterministic synthetic upward drift with mild noise via hash-like LCG
        out = []
        px = 100.0
        state = 42
        for i in range(n):
            state = (1103515245 * state + 12345) & 0x7FFFFFFF
            noise = ((state % 1000) / 1000.0 - 0.5) * 0.01
            px = px * (1.0 + 0.001 + noise)
            out.append({"close": round(px, 6), "volume": 1_000_000 + (state % 50000)})
        return out

    def _eval(self, s: dict[str, Any], closes: list[float], params: dict[str, Any]) -> dict[str, Any]:
        if len(closes) < 5:
            return {"action": "HOLD", "confidence": 0.0, "reason": "insufficient_bars"}
        cat = s["category"]
        last = closes[-1]
        sma20 = sum(closes[-20:]) / min(20, len(closes)) if closes else last
        sma50 = sum(closes[-50:]) / min(50, len(closes)) if closes else last
        ret5 = (last / closes[-6] - 1.0) if len(closes) > 5 else 0.0
        high20 = max(closes[-20:]) if len(closes) >= 20 else max(closes)
        low20 = min(closes[-20:]) if len(closes) >= 20 else min(closes)

        action = "HOLD"
        conf = 0.4
        reason = "neutral"

        if cat in ("momentum", "trend_following", "growth_investing"):
            if last > sma20 > sma50 and ret5 > 0:
                action, conf, reason = "BUY", min(0.85, 0.5 + ret5 * 10), "uptrend_momentum"
            elif last < sma20 < sma50 and ret5 < 0:
                action, conf, reason = "SELL", min(0.85, 0.5 + abs(ret5) * 10), "downtrend_momentum"
        elif cat in ("mean_reversion",):
            mid = (high20 + low20) / 2
            if last < low20 * 1.01:
                action, conf, reason = "BUY", 0.65, "oversold_band"
            elif last > high20 * 0.99:
                action, conf, reason = "SELL", 0.65, "overbought_band"
            else:
                reason = f"near_mid_{mid:.2f}"
        elif cat == "breakout":
            if last >= high20:
                action, conf, reason = "BUY", 0.7, "donchian_breakout_high"
            elif last <= low20:
                action, conf, reason = "SELL", 0.7, "donchian_breakout_low"
        elif cat in ("dca", "long_term_investing", "value_investing"):
            action, conf, reason = "BUY", 0.55, "strategic_accumulate"
        elif cat == "volatility":
            rets = [(closes[i] / closes[i - 1] - 1) for i in range(1, len(closes))]
            vol = (sum(r * r for r in rets[-20:]) / max(1, min(20, len(rets)))) ** 0.5
            if vol > 0.02:
                action, conf, reason = "REDUCE", 0.6, "elevated_vol_regime"
            else:
                action, conf, reason = "HOLD", 0.5, "calm_vol_regime"
        elif cat == "swing_trading":
            if last > sma50 and last < sma20 * 1.01 and ret5 > -0.02:
                action, conf, reason = "BUY", 0.62, "pullback_in_uptrend"
        elif cat == "scalping":
            action, conf, reason = "WATCH", 0.35, "scalp_research_only_no_live_book"

        # Optional param override for tests
        if params.get("force_action"):
            action = str(params["force_action"]).upper()
            conf = float(params.get("force_confidence", conf))

        return {
            "action": action,
            "confidence": round(conf, 4),
            "reason": reason,
            "last_price": round(last, 6),
            "sma20": round(sma20, 6),
            "sma50": round(sma50, 6),
            "stop_loss_logic": s["stop_loss_logic"],
            "take_profit_logic": s["take_profit_logic"],
            "sizing_model": s["sizing_model"],
        }
