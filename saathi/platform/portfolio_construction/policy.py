"""Construction / rebalance policy defaults (deterministic PAPER)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class ConstructionPolicy:
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

    def to_public(self) -> dict:
        return {
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
        }


DEFAULT_POLICY = ConstructionPolicy()
