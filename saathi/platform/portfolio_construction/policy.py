"""Construction / rebalance policy defaults (deterministic PAPER)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ConstructionPolicy:
    version: str = "portfolio-construction/v2.0.0-configured-conservative"
    assumption_status: str = "CONFIGURED_POLICY_ASSUMPTION"
    # cash
    min_cash_buffer: Decimal = Decimal("0.05")  # 5% NAV reserved as cash weight
    # concentration (aligned with risk budget defaults)
    max_position_weight: Decimal = Decimal("0.15")
    max_top3_concentration: Decimal = Decimal("0.40")
    max_top5_concentration: Decimal = Decimal("0.60")
    max_gross_exposure: Decimal = Decimal("1.00")
    # drift / min trade
    rebalance_drift_threshold: Decimal = Decimal("0.02")  # 2% weight
    min_trade_notional: Decimal = Decimal("100")  # absolute currency
    min_weight_delta: Decimal = Decimal("0.005")  # 0.5%
    # turnover (informational soft)
    soft_turnover_limit: Decimal = Decimal("0.50")
    # rounding
    weight_sum_tolerance: Decimal = Decimal("0.0001")
    # proposal TTL seconds (default 24h)
    default_ttl_seconds: float = 86400.0
    # leverage/shorts
    leverage_enabled: bool = False
    shorts_enabled: bool = False
    # clip vs reject when hard limit exceeded by incoming fixed target
    clip_overweight_targets: bool = False  # prefer reject/explain over silent clip

    # V2 intent-to-candidate construction.  These are intentionally simple,
    # conservative, versioned assumptions; they are not claimed to be
    # institutionally calibrated or derived from strategy backtest returns.
    base_candidate_weight: Decimal = Decimal("0.10")
    max_crypto_exposure: Decimal = Decimal("0.20")
    max_nepse_exposure: Decimal = Decimal("0.00")
    missing_liquidity_cap: Decimal = Decimal("0.05")
    volatility_target: Decimal = Decimal("0.20")
    volatility_lookback_returns: int = 90
    volatility_min_observations: int = 60
    correlation_lookback_returns: int = 90
    correlation_min_observations: int = 60
    high_correlation_threshold: Decimal = Decimal("0.75")
    correlated_cluster_cap: Decimal = Decimal("0.15")
    crypto_annualization_days: int = 365
    nepse_annualization_days: int = 252
    moderate_drawdown: Decimal = Decimal("0.05")
    elevated_drawdown: Decimal = Decimal("0.10")
    severe_drawdown: Decimal = Decimal("0.15")
    moderate_drawdown_factor: Decimal = Decimal("0.75")
    elevated_drawdown_factor: Decimal = Decimal("0.50")

    def to_public(self) -> dict:
        return {
            "version": self.version,
            "assumption_status": self.assumption_status,
            "min_cash_buffer": str(self.min_cash_buffer),
            "max_position_weight": str(self.max_position_weight),
            "max_top3_concentration": str(self.max_top3_concentration),
            "max_top5_concentration": str(self.max_top5_concentration),
            "max_gross_exposure": str(self.max_gross_exposure),
            "rebalance_drift_threshold": str(self.rebalance_drift_threshold),
            "min_trade_notional": str(self.min_trade_notional),
            "min_weight_delta": str(self.min_weight_delta),
            "soft_turnover_limit": str(self.soft_turnover_limit),
            "weight_sum_tolerance": str(self.weight_sum_tolerance),
            "default_ttl_seconds": self.default_ttl_seconds,
            "leverage_enabled": self.leverage_enabled,
            "shorts_enabled": self.shorts_enabled,
            "clip_overweight_targets": self.clip_overweight_targets,
            "base_candidate_weight": str(self.base_candidate_weight),
            "max_crypto_exposure": str(self.max_crypto_exposure),
            "max_nepse_exposure": str(self.max_nepse_exposure),
            "missing_liquidity_cap": str(self.missing_liquidity_cap),
            "volatility_target": str(self.volatility_target),
            "volatility_lookback_returns": self.volatility_lookback_returns,
            "volatility_min_observations": self.volatility_min_observations,
            "correlation_lookback_returns": self.correlation_lookback_returns,
            "correlation_min_observations": self.correlation_min_observations,
            "high_correlation_threshold": str(self.high_correlation_threshold),
            "correlated_cluster_cap": str(self.correlated_cluster_cap),
            "crypto_annualization_days": self.crypto_annualization_days,
            "nepse_annualization_days": self.nepse_annualization_days,
            "moderate_drawdown": str(self.moderate_drawdown),
            "elevated_drawdown": str(self.elevated_drawdown),
            "severe_drawdown": str(self.severe_drawdown),
            "moderate_drawdown_factor": str(self.moderate_drawdown_factor),
            "elevated_drawdown_factor": str(self.elevated_drawdown_factor),
        }


DEFAULT_POLICY = ConstructionPolicy()
