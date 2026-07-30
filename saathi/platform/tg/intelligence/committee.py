"""M254 — Investment Committee multi-agent synthesis.

Specialist agents produce independent opinions; TG synthesises one recommendation.
"""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.intelligence.models import AUTHORITY_VALUES, CommitteeRole, RecommendationAction


class InvestmentCommittee:
    """Multi-specialist paper investment committee."""

    ROLES = [
        CommitteeRole.MACRO,
        CommitteeRole.TECHNICAL,
        CommitteeRole.FUNDAMENTAL,
        CommitteeRole.QUANT,
        CommitteeRole.RISK,
        CommitteeRole.PORTFOLIO,
    ]

    def review(
        self,
        *,
        instrument: str = "SPY",
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        regime = context.get("regime", "mixed")
        trend = context.get("trend", "up")
        valuation = context.get("valuation", "fair")
        vol = float(context.get("volatility", 0.15))
        beta = float(context.get("beta", 1.0))
        concentration = float(context.get("concentration", 0.2))

        opinions = [
            self._macro(instrument, regime, vol),
            self._technical(instrument, trend, vol),
            self._fundamental(instrument, valuation),
            self._quant(instrument, trend, vol, beta),
            self._risk(instrument, vol, concentration),
            self._portfolio(instrument, concentration, beta),
        ]

        # Vote tally
        votes: dict[str, int] = {}
        weighted: dict[str, float] = {}
        for op in opinions:
            a = op["action"]
            votes[a] = votes.get(a, 0) + 1
            weighted[a] = weighted.get(a, 0.0) + float(op["confidence"])

        # Final action: max weighted confidence among majority-eligible
        final_action = max(weighted.items(), key=lambda kv: (votes.get(kv[0], 0), kv[1]))[0]
        agree = [op for op in opinions if op["action"] == final_action]
        dissent = [op for op in opinions if op["action"] != final_action]
        avg_conf = sum(op["confidence"] for op in opinions) / len(opinions)
        consensus_conf = sum(op["confidence"] for op in agree) / len(agree) if agree else avg_conf

        # Agreement score
        agreement_ratio = len(agree) / len(opinions)
        if agreement_ratio >= 5 / 6:
            consensus = "STRONG_CONSENSUS"
        elif agreement_ratio >= 0.5:
            consensus = "MAJORITY"
        elif agreement_ratio >= 1 / 3:
            consensus = "SPLIT"
        else:
            consensus = "NO_CONSENSUS"

        synthesis = {
            "instrument": instrument,
            "final_recommendation": final_action,
            "consensus": consensus,
            "agreement_ratio": round(agreement_ratio, 4),
            "committee_confidence": round(consensus_conf, 4),
            "average_member_confidence": round(avg_conf, 4),
            "voting_summary": {
                "votes": votes,
                "weighted_confidence": {k: round(v, 4) for k, v in weighted.items()},
                "majority_action": max(votes.items(), key=lambda kv: kv[1])[0],
            },
            "agreements": [
                {"role": op["role"], "action": op["action"], "rationale": op["rationale"]}
                for op in agree
            ],
            "disagreements": [
                {"role": op["role"], "action": op["action"], "rationale": op["rationale"]}
                for op in dissent
            ],
            "dissenting_opinions": [
                {
                    "role": op["role"],
                    "action": op["action"],
                    "confidence": op["confidence"],
                    "rationale": op["rationale"],
                    "key_risk": op.get("key_risk"),
                }
                for op in dissent
            ],
            "opinions": opinions,
            "synthesis_notes": self._notes(final_action, consensus, agree, dissent),
            "paper_only": True,
            "not_an_order": True,
            **AUTHORITY_VALUES,
        }
        return synthesis

    def _macro(self, instrument, regime, vol):
        if regime in ("risk_off", "recession"):
            action, conf, rat = RecommendationAction.REDUCE.value, 0.62, "Macro regime risk-off; favour defence"
        elif regime in ("risk_on", "expansion"):
            action, conf, rat = RecommendationAction.BUY.value, 0.58, "Macro expansion supports risk assets"
        else:
            action, conf, rat = RecommendationAction.HOLD.value, 0.5, "Mixed macro; wait for clearer regime"
        if vol > 0.25:
            conf *= 0.9
            rat += "; elevated vol softens conviction"
        return self._op(CommitteeRole.MACRO, action, conf, rat, "policy/growth shock")

    def _technical(self, instrument, trend, vol):
        if trend == "up":
            action, conf, rat = RecommendationAction.BUY.value, 0.64, "Price structure and trend filters constructive"
        elif trend == "down":
            action, conf, rat = RecommendationAction.SELL.value, 0.64, "Downtrend structure; avoid catching knives"
        else:
            action, conf, rat = RecommendationAction.HOLD.value, 0.48, "Range-bound; no clean technical edge"
        return self._op(CommitteeRole.TECHNICAL, action, conf, rat, "false breakout")

    def _fundamental(self, instrument, valuation):
        if valuation == "cheap":
            action, conf, rat = RecommendationAction.BUY.value, 0.6, "Valuation discount vs history/peers"
        elif valuation == "expensive":
            action, conf, rat = RecommendationAction.REDUCE.value, 0.55, "Rich multiples compress forward returns"
        else:
            action, conf, rat = RecommendationAction.HOLD.value, 0.5, "Fair value; fundamentals neutral"
        return self._op(CommitteeRole.FUNDAMENTAL, action, conf, rat, "earnings miss / guidance cut")

    def _quant(self, instrument, trend, vol, beta):
        score = (0.2 if trend == "up" else -0.2 if trend == "down" else 0.0) - max(0, vol - 0.2)
        if score > 0.05:
            action, conf = RecommendationAction.BUY.value, 0.57
            rat = "Factor/score composite positive after vol adjustment"
        elif score < -0.05:
            action, conf = RecommendationAction.SELL.value, 0.57
            rat = "Factor/score composite negative after vol adjustment"
        else:
            action, conf = RecommendationAction.HOLD.value, 0.5
            rat = "Quant composite near zero; no edge"
        if beta > 1.3:
            rat += "; high beta increases path volatility"
        return self._op(CommitteeRole.QUANT, action, conf, rat, "factor crowding / model decay")

    def _risk(self, instrument, vol, concentration):
        if vol > 0.22 or concentration > 0.35:
            action, conf, rat = (
                RecommendationAction.REDUCE.value,
                0.7,
                "Risk limits: elevated vol or concentration argues smaller size",
            )
        elif vol < 0.12 and concentration < 0.2:
            action, conf, rat = RecommendationAction.HOLD.value, 0.55, "Risk budget available; no forced cut"
        else:
            action, conf, rat = RecommendationAction.HOLD.value, 0.52, "Risk within policy bands"
        return self._op(CommitteeRole.RISK, action, conf, rat, "tail event / gap beyond stop")

    def _portfolio(self, instrument, concentration, beta):
        if concentration > 0.3:
            action, conf, rat = (
                RecommendationAction.REDUCE.value,
                0.66,
                "Portfolio construction: trim to restore diversification",
            )
        elif beta > 1.2:
            action, conf, rat = RecommendationAction.HOLD.value, 0.5, "Maintain but avoid increasing high-beta load"
        else:
            action, conf, rat = RecommendationAction.HOLD.value, 0.54, "Fits policy allocation; no rebalance urgent"
        return self._op(CommitteeRole.PORTFOLIO, action, conf, rat, "allocation drift / correlation spike")

    def _op(self, role: CommitteeRole, action: str, conf: float, rationale: str, key_risk: str) -> dict[str, Any]:
        return {
            "role": role.value,
            "action": action,
            "confidence": round(max(0.0, min(1.0, conf)), 4),
            "rationale": rationale,
            "key_risk": key_risk,
            "independent": True,
            "paper_only": True,
        }

    def _notes(self, final, consensus, agree, dissent) -> list[str]:
        notes = [
            f"Synthesised action {final} under {consensus}.",
            f"{len(agree)} specialists agree; {len(dissent)} dissent.",
        ]
        if dissent:
            roles = ", ".join(d["role"] for d in dissent)
            notes.append(f"Dissent recorded from: {roles}.")
        notes.append("Committee output is advisory for paper portfolios only — not an order.")
        return notes
