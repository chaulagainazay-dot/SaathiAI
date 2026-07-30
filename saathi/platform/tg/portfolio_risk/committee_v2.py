"""Investment Committee V2 — portfolio-aware synthesis over M254 committee."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.portfolio_risk.models import AUTHORITY_VALUES
from saathi.platform.tg.portfolio_risk.storage import PortfolioRiskStore, evidence_hash, _uid


class InvestmentCommitteeV2:
    """Extends M254 committee with portfolio risk context."""

    def __init__(self, store: PortfolioRiskStore):
        self.store = store

    def review(
        self,
        *,
        instrument: str = "PORTFOLIO",
        analytics: dict[str, Any] | None = None,
        limits: dict[str, Any] | None = None,
        scenarios: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        analytics = analytics or {}
        limits = limits or {}
        scenarios = scenarios or {}
        a = analytics.get("analytics") or {}

        context = {
            "regime": "mixed",
            "trend": "up" if float(a.get("sharpe_ratio") or 0) > 0 else "down",
            "valuation": "fair",
            "volatility": float(a.get("volatility") or 0.15),
            "beta": float(a.get("portfolio_beta") or 1.0),
            "concentration": float((analytics.get("diversification") or {}).get("top_weight") or 0.2),
        }

        from saathi.platform.tg.intelligence.committee import InvestmentCommittee
        base = InvestmentCommittee().review(instrument=instrument, context=context)

        # Portfolio risk overlay votes
        risk_state = limits.get("state", "WITHIN_LIMITS")
        worst = (scenarios.get("stress_dashboard") or {}).get("worst_scenario") or {}
        worst_loss = float(worst.get("portfolio_loss_pct") or 0)

        overlay = {
            "role": "portfolio_risk_officer_v2",
            "action": "REDUCE" if risk_state == "BREACHED" or worst_loss > 0.15 else (
                "HOLD" if risk_state == "WARNING" else base.get("synthesis", {}).get("final_recommendation", "HOLD")
            ),
            "confidence": 0.7 if risk_state != "WITHIN_LIMITS" else 0.55,
            "rationale": f"limits={risk_state}; worst_scenario_loss={worst_loss:.2%}",
            "limits_state": risk_state,
            "diversification_ratio": (analytics.get("diversification") or {}).get("ratio"),
            "es_95": a.get("expected_shortfall_95"),
        }

        synthesis = dict(base.get("synthesis") or {})
        synthesis["committee_version"] = "v2"
        synthesis["portfolio_aware"] = True
        synthesis["risk_overlay"] = overlay
        if risk_state == "BREACHED":
            synthesis["final_recommendation"] = "REDUCE"
            synthesis["consensus"] = "MAJORITY"
            synthesis["v2_override_reason"] = "exposure_or_drawdown_breach"

        result = {
            "ok": True,
            "committee_version": "v2",
            "composes": "M254_InvestmentCommittee",
            "instrument": instrument,
            "base_committee": base,
            "risk_overlay": overlay,
            "synthesis": synthesis,
            "authorizes_execution": False,
            "not_investment_advice": True,
            **AUTHORITY_VALUES,
        }
        eh = evidence_hash(result)
        result["evidence_hash"] = eh
        cid = _uid("cm")
        self.store.execute(
            "INSERT INTO pr_committee(id, instrument, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
            (cid, instrument, __import__("json").dumps(result, sort_keys=True, default=str), eh, time.time()),
        )
        result["committee_id"] = cid
        return result
