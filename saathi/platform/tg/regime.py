"""M168 — Deterministic Market Regime Detector.

LLM may summarize but must not determine the regime.
Fail-closed to UNKNOWN when required data is missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from saathi.platform.tg.domain import MarketRegime, MarketSnapshot


@dataclass
class RegimeAssessment:
    labels: list[str]
    primary: str
    confidence: Decimal
    factors: dict[str, Any]
    explanation: str
    fail_closed: bool = False
    source: str = "regime_engine"
    llm_determined: bool = False

    def to_public(self) -> dict[str, Any]:
        return {
            "labels": list(self.labels),
            "primary": self.primary,
            "confidence": str(self.confidence),
            "factors": dict(self.factors),
            "explanation": self.explanation,
            "fail_closed": self.fail_closed,
            "source": self.source,
            "llm_determined": False,
            "deterministic": True,
        }


class MarketRegimeEngine:
    """Rule-based regime classifier. Combined labels allowed."""

    def __init__(
        self,
        *,
        trend_threshold: Decimal = Decimal("0.03"),
        high_vol_threshold: Decimal = Decimal("0.04"),
        low_liquidity_threshold: Decimal = Decimal("5000"),
        sideways_band: Decimal = Decimal("0.015"),
    ):
        self.trend_threshold = trend_threshold
        self.high_vol_threshold = high_vol_threshold
        self.low_liquidity_threshold = low_liquidity_threshold
        self.sideways_band = sideways_band

    def evaluate(self, snapshot: MarketSnapshot) -> RegimeAssessment:
        factors: dict[str, Any] = {}
        labels: list[str] = []

        # Fail-closed when critical data missing
        if not snapshot.symbol or snapshot.last_price <= 0:
            return RegimeAssessment(
                labels=[MarketRegime.UNKNOWN.value],
                primary=MarketRegime.UNKNOWN.value,
                confidence=Decimal("0"),
                factors={"reason": "missing_price_or_symbol"},
                explanation="Required market data missing; fail-closed to UNKNOWN.",
                fail_closed=True,
            )

        if snapshot.data_quality not in ("VALID", "GAPPED"):
            return RegimeAssessment(
                labels=[MarketRegime.UNKNOWN.value],
                primary=MarketRegime.UNKNOWN.value,
                confidence=Decimal("0"),
                factors={"data_quality": snapshot.data_quality, "reason": "data_quality_not_tradeable"},
                explanation=f"Data quality {snapshot.data_quality} not sufficient; UNKNOWN.",
                fail_closed=True,
            )

        closes = [b.close for b in snapshot.bars] if snapshot.bars else [snapshot.last_price]
        if len(closes) < 3:
            return RegimeAssessment(
                labels=[MarketRegime.UNKNOWN.value],
                primary=MarketRegime.UNKNOWN.value,
                confidence=Decimal("0.2"),
                factors={"bars": len(closes), "reason": "insufficient_history"},
                explanation="Insufficient bar history for regime classification.",
                fail_closed=True,
            )

        # Trend measure: return over window
        base = closes[0]
        trend_ret = (closes[-1] - base) / base if base > 0 else Decimal("0")
        factors["trend_return"] = str(trend_ret)
        factors["benchmark_return"] = str(snapshot.benchmark_return)
        factors["breadth"] = str(snapshot.breadth)
        factors["volatility"] = str(snapshot.volatility)
        factors["gap_pct"] = str(snapshot.gap_pct)
        factors["event_risk"] = snapshot.event_risk
        factors["avg_traded_value"] = str(snapshot.avg_traded_value)
        factors["liquidity_proxy"] = str(snapshot.volume * snapshot.last_price)

        # Volatility
        rets = []
        for i in range(1, len(closes)):
            if closes[i - 1] > 0:
                rets.append((closes[i] - closes[i - 1]) / closes[i - 1])
        if snapshot.volatility > 0:
            vol = snapshot.volatility
        elif len(rets) >= 2:
            mean = sum(rets, Decimal("0")) / Decimal(len(rets))
            var = sum((r - mean) ** 2 for r in rets) / Decimal(len(rets) - 1)
            vol = var  # use variance scale; compare to threshold carefully
            # approximate std
            guess = var / 2 if var > 1 else (var if var > 0 else Decimal("0"))
            for _ in range(12):
                if guess == 0:
                    break
                guess = (guess + var / guess) / 2
            vol = guess
        else:
            vol = Decimal("0")
        factors["computed_volatility"] = str(vol)

        if vol >= self.high_vol_threshold:
            labels.append(MarketRegime.HIGH_VOLATILITY.value)

        # Liquidity
        liq = snapshot.avg_traded_value if snapshot.avg_traded_value > 0 else snapshot.volume * snapshot.last_price
        if liq < self.low_liquidity_threshold:
            labels.append(MarketRegime.LOW_LIQUIDITY.value)

        # Event risk
        if snapshot.event_risk or snapshot.earnings_window:
            labels.append(MarketRegime.EVENT_RISK.value)

        # Trend / sideways
        if trend_ret >= self.trend_threshold:
            labels.append(MarketRegime.BULL_TREND.value)
        elif trend_ret <= -self.trend_threshold:
            labels.append(MarketRegime.BEAR_TREND.value)
        elif abs(trend_ret) <= self.sideways_band:
            labels.append(MarketRegime.SIDEWAYS.value)
        else:
            # mild trend — still assign primary direction weakly
            if trend_ret > 0:
                labels.append(MarketRegime.BULL_TREND.value)
            else:
                labels.append(MarketRegime.BEAR_TREND.value)

        # Conflicting signals note
        factors["conflicting"] = (
            MarketRegime.BULL_TREND.value in labels
            and MarketRegime.BEAR_TREND.value in labels
        )
        if factors["conflicting"]:
            # should not happen with exclusive trend rules; fail soft to UNKNOWN primary
            labels = [l for l in labels if l not in (
                MarketRegime.BULL_TREND.value, MarketRegime.BEAR_TREND.value
            )]
            labels.append(MarketRegime.UNKNOWN.value)

        if not labels:
            labels = [MarketRegime.UNKNOWN.value]

        # Primary: prefer directional, else first
        priority = [
            MarketRegime.EVENT_RISK.value,
            MarketRegime.LOW_LIQUIDITY.value,
            MarketRegime.HIGH_VOLATILITY.value,
            MarketRegime.BEAR_TREND.value,
            MarketRegime.BULL_TREND.value,
            MarketRegime.SIDEWAYS.value,
            MarketRegime.UNKNOWN.value,
        ]
        primary = MarketRegime.UNKNOWN.value
        for p in priority:
            if p in labels:
                primary = p
                break

        # Confidence from explicit rules
        conf = Decimal("0.4")
        if len(closes) >= 10:
            conf += Decimal("0.2")
        if snapshot.data_quality == "VALID":
            conf += Decimal("0.2")
        if abs(trend_ret) >= self.trend_threshold:
            conf += Decimal("0.1")
        if vol > 0:
            conf += Decimal("0.1")
        if conf > Decimal("1"):
            conf = Decimal("1")

        explanation = (
            f"Regime primary={primary} labels={labels}; "
            f"trend_return={trend_ret}, vol={vol}, liq={liq}, "
            f"event_risk={snapshot.event_risk}."
        )
        return RegimeAssessment(
            labels=labels,
            primary=primary,
            confidence=conf,
            factors=factors,
            explanation=explanation,
            fail_closed=primary == MarketRegime.UNKNOWN.value and conf < Decimal("0.3"),
        )

    def strategy_compatible(
        self,
        assessment: RegimeAssessment,
        strategy_regimes: list[str],
    ) -> tuple[bool, str]:
        if not strategy_regimes:
            return False, "strategy declares no compatible regimes"
        if assessment.primary == MarketRegime.UNKNOWN.value and assessment.fail_closed:
            return False, "regime UNKNOWN fail-closed"
        # Compatible if any overlap (including strategy accepting UNKNOWN)
        overlap = set(assessment.labels) & set(strategy_regimes)
        if not overlap and MarketRegime.UNKNOWN.value not in strategy_regimes:
            return False, f"regime {assessment.labels} incompatible with {strategy_regimes}"
        if overlap:
            return True, f"compatible via {sorted(overlap)}"
        return False, "no overlapping regime labels"
