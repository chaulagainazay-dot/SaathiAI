"""M14 CEO agent — bounded proposals only.

Reuses the M10 `ceo` agent (already registered with can_self_approve=False,
READ_ONLY risk ceiling). The CEO agent may PROPOSE decisions/missions/budget
allocations backed by real CEO OS records, but cannot self-approve, spend,
publish, deploy, send externally, or invent unavailable metrics. Every proposal
is persisted as a `proposed` decision or a recommendation — never auto-executed.
"""
from __future__ import annotations

from saathi.ceo.store import CEOStore
from saathi.ceo.models import EvidenceTier


class CEOAgent:
    def __init__(self, store: CEOStore | None = None, service=None):
        self.store = store or CEOStore()
        self._service = service

    def _svc(self):
        if self._service is None:
            from saathi.ceo.service import CEOService
            self._service = CEOService(self.store)
        return self._service

    def propose_decision(self, owner: str, *, question: str, context: str = "",
                        options: list | None = None, recommendation: str = "") -> dict:
        """Persist a PROPOSED decision. Only an authorized human may finalize it
        (protected states enforced by the store/API)."""
        did = self.store.add_decision(
            owner=owner, question=question, context=context, options=options,
            recommendation=recommendation,
            provenance={"source": "ceo_agent", "authority": "internal",
                       "evidence_tier": EvidenceTier.RECOMMENDED.value})
        return {"decision_id": did, "status": "proposed",
                "note": "agent proposal — requires human approval to finalize"}

    def recommend_missions(self, owner: str) -> list[dict]:
        """Evidence-backed mission recommendations from real risks/opportunities.
        Recommendations are NOT executed — the user converts them."""
        recs = []
        for r in self.store.list_risks(owner, status="open")[:3]:
            if r["score"] >= 40:
                recs.append({"kind": "risk_mitigation", "risk_id": r["id"],
                            "objective": f"Mitigate risk: {r['title']}",
                            "evidence": [f"risk score {r['score']}"],
                            "tier": EvidenceTier.RECOMMENDED.value})
        for o in self.store.list_opportunities(owner)[:3]:
            if o["status"] == "identified":
                recs.append({"kind": "opportunity", "opportunity_id": o["id"],
                            "objective": f"Pursue: {o['title']}",
                            "evidence": [f"opportunity score {o['score']}"],
                            "tier": EvidenceTier.RECOMMENDED.value})
        return recs

    def cannot_do(self) -> list[str]:
        """Explicit bounds — surfaced in the UI so the agent's limits are visible."""
        return ["self-approve decisions", "spend money", "publish content",
                "deploy", "send external messages", "modify protected data",
                "invent unavailable metrics", "declare completion without evidence"]
