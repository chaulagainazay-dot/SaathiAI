"""M253 — Explainable Investment AI.

Every recommendation includes human-readable why / evidence / risks / invalidation.
"""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.intelligence.models import AUTHORITY_VALUES, ConfidenceBand


def _band(confidence: float) -> str:
    if confidence < 0.25:
        return ConfidenceBand.VERY_LOW.value
    if confidence < 0.4:
        return ConfidenceBand.LOW.value
    if confidence < 0.6:
        return ConfidenceBand.MODERATE.value
    if confidence < 0.8:
        return ConfidenceBand.HIGH.value
    return ConfidenceBand.VERY_HIGH.value


class ExplainableInvestmentAI:
    """Produce structured, human-readable investment explanations."""

    def explain(
        self,
        *,
        instrument: str = "SPY",
        action: str = "HOLD",
        strategy_id: str | None = None,
        signal: dict[str, Any] | None = None,
        portfolio_context: dict[str, Any] | None = None,
        market_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        signal = signal or {}
        portfolio_context = portfolio_context or {}
        market_context = market_context or {}
        action = (action or signal.get("action") or "HOLD").upper()
        conf = float(signal.get("confidence", market_context.get("confidence", 0.5)))
        conf = max(0.0, min(1.0, conf))
        reason = signal.get("reason") or market_context.get("reason") or "neutral_assessment"

        supporting = self._supporting(action, instrument, signal, market_context)
        conflicting = self._conflicting(action, instrument, signal, market_context)
        assumptions = [
            "Analysis uses paper/offline or fixture data only",
            "No live broker quotes or order book",
            "Transaction costs are modelled, not guaranteed",
            "Past simulated behaviour is not future performance",
        ]
        if strategy_id:
            assumptions.append(f"Signal evaluated under strategy '{strategy_id}' rules")

        risks = [
            "Model risk: indicators may fail in regime shifts",
            "Liquidity risk under stressed markets",
            "Gap risk overnight or over weekends",
            "Concentration risk if position oversized relative to portfolio",
        ]
        if portfolio_context.get("concentration", {}).get("top_position_weight", 0) > 0.3:
            risks.append("Current paper portfolio already shows elevated concentration")

        upside = self._upside(action, conf, signal)
        downside = self._downside(action, conf, signal)
        invalidation = self._invalidation(action, signal)
        historical = {
            "note": "Comparable offline behaviour only",
            "similar_setups": market_context.get("similar_setups", [
                "Trend continuation after MA alignment (research fixture)",
                "Mean-reversion bounce from lower band (research fixture)",
            ]),
            "historical_win_rate_label": "NON_AUTHORITATIVE_FIXTURE",
        }
        comparable = [
            {
                "situation": "Prior offline uptrend pullback",
                "outcome_label": "SIMULATED",
                "lesson": "Confirm higher-timeframe trend before entry",
            },
            {
                "situation": "False breakout under low volume",
                "outcome_label": "SIMULATED",
                "lesson": "Require volume confirmation for breakouts",
            },
        ]

        narrative = self._narrative(
            instrument, action, conf, reason, supporting, conflicting, upside, downside
        )

        explanation = {
            "instrument": instrument,
            "action": action,
            "strategy_id": strategy_id,
            "why": narrative["why"],
            "why_now": narrative["why_now"],
            "supporting_evidence": supporting,
            "conflicting_evidence": conflicting,
            "assumptions": assumptions,
            "risks": risks,
            "confidence": round(conf, 4),
            "confidence_band": _band(conf),
            "historical_behaviour": historical,
            "comparable_situations": comparable,
            "expected_upside": upside,
            "expected_downside": downside,
            "invalidation_conditions": invalidation,
            "human_summary": narrative["summary"],
            "investor_readable": True,
            "not_financial_advice": True,
            "disclaimer": (
                "Research explanation for paper portfolios only. "
                "Not investment advice. Not a live order. Not a guarantee."
            ),
            **AUTHORITY_VALUES,
        }
        return explanation

    def _supporting(self, action, instrument, signal, ctx) -> list[str]:
        items = []
        if signal.get("sma20") and signal.get("sma50"):
            if signal["sma20"] > signal["sma50"]:
                items.append(f"{instrument}: short MA above long MA (trend support)")
            else:
                items.append(f"{instrument}: short MA below long MA (downtrend structure)")
        if signal.get("reason"):
            items.append(f"Primary signal reason: {signal['reason']}")
        if action in ("BUY", "INCREASE"):
            items.append("Positive setup relative to strategy entry rules")
        elif action in ("SELL", "REDUCE", "AVOID"):
            items.append("Risk or exit conditions favoured by strategy rules")
        else:
            items.append("No high-conviction edge; holding preserves optionality")
        if ctx.get("regime"):
            items.append(f"Regime context: {ctx['regime']}")
        if not items:
            items.append("Insufficient structured evidence; defaulting to caution")
        return items

    def _conflicting(self, action, instrument, signal, ctx) -> list[str]:
        items = [
            "Offline/fixture data may not reflect live microstructure",
            "Macro shocks can invalidate technical structure quickly",
        ]
        if action == "BUY":
            items.append("Entry may be late if move already extended")
            items.append("Opportunity cost if mean reversion occurs first")
        elif action == "SELL":
            items.append("Selling may cut a long-term winner too early")
        if ctx.get("elevated_vol"):
            items.append("Elevated volatility increases false-signal rate")
        return items

    def _upside(self, action, conf, signal) -> dict[str, Any]:
        base = 0.03 + conf * 0.07
        if action in ("SELL", "AVOID", "REDUCE"):
            return {
                "label": "risk_reduction_benefit",
                "expected_return_if_correct": round(base * 0.5, 4),
                "note": "Primary benefit is downside avoided, not upside capture",
            }
        return {
            "label": "expected_upside_if_thesis_holds",
            "expected_return_if_correct": round(base, 4),
            "horizon": signal.get("holding") or "strategy_default",
            "note": "Illustrative model range for paper research only",
        }

    def _downside(self, action, conf, signal) -> dict[str, Any]:
        base = 0.02 + (1 - conf) * 0.08
        return {
            "label": "expected_downside_if_thesis_fails",
            "expected_loss_if_wrong": round(base, 4),
            "stop_reference": signal.get("stop_loss_logic") or "strategy_stop",
            "note": "Not a guaranteed loss bound; gaps can exceed stops",
        }

    def _invalidation(self, action, signal) -> list[str]:
        items = [
            "Thesis invalidated if strategy exit conditions fire",
            "Kill-switch or risk limit breach forces flat paper posture",
            "Data quality failure or stale marks suspend recommendations",
        ]
        if action in ("BUY", "INCREASE"):
            items.append("Break of key support / MA structure invalidates long thesis")
            items.append("Volume collapse or failed breakout cancels entry quality")
        elif action in ("SELL", "REDUCE"):
            items.append("Reclaim of structure with volume may invalidate short/reduce thesis")
        return items

    def _narrative(self, instrument, action, conf, reason, supporting, conflicting, upside, downside):
        why = (
            f"Recommendation is {action} on {instrument} because the paper strategy signal "
            f"({reason}) aligns with the current offline assessment at confidence {conf:.0%}."
        )
        why_now = (
            f"Timing is driven by the latest evaluated bar/signal state for {instrument}. "
            f"Supporting factors: {supporting[0] if supporting else 'n/a'}. "
            f"Key tension: {conflicting[0] if conflicting else 'n/a'}."
        )
        summary = (
            f"{action} {instrument} (paper). Confidence {_band(conf)} ({conf:.0%}). "
            f"If correct, illustrative upside ~{upside.get('expected_return_if_correct', 0):.1%}; "
            f"if wrong, illustrative downside ~{downside.get('expected_loss_if_wrong', 0):.1%}. "
            f"Not live trading advice."
        )
        return {"why": why, "why_now": why_now, "summary": summary}
