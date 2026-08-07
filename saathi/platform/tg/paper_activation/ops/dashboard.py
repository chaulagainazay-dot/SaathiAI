"""M215 — Operations dashboard read model (paper only)."""
from __future__ import annotations

from typing import Any

from saathi.platform.tg.paper_activation.ops.models import LLM_BOUNDARY, PAPER_POSTURE, TERMINAL_VERDICT


class OperationsDashboard:
    def __init__(
        self,
        gov: Any,
        *,
        campaign_mgr: Any,
        monitor: Any,
        graduation: Any,
        intelligence: Any,
        analytics: Any,
        evidence: Any,
        simulation: Any | None = None,
    ):
        self.gov = gov
        self.campaign_mgr = campaign_mgr
        self.monitor = monitor
        self.graduation = graduation
        self.intelligence = intelligence
        self.analytics = analytics
        self.evidence = evidence
        self.simulation = simulation

    def overview(self) -> dict[str, Any]:
        health = self.monitor.assess(persist=True)
        camps = self.campaign_mgr.list_campaigns_full()
        rankings = self.graduation.rankings()
        port_rank = self.analytics.strategy_ranking()
        recs = self.intelligence.list_recommendations(limit=20)
        evidence = self.evidence.list_evidence(limit=20)
        incidents = self.gov.list_incidents() if hasattr(self.gov, "list_incidents") else {"incidents": []}
        jobs = self.gov.store.list_jobs()
        storage = self.gov.storage_status() if hasattr(self.gov, "storage_status") else self.gov.store.health()
        workers = {
            "worker_id": getattr(self.gov, "worker_id", None),
            "health": health.get("components", {}).get("worker_health"),
        }
        timeline = sorted(
            [
                {
                    "campaign_id": c["id"],
                    "strategy_slug": c.get("strategy_slug"),
                    "status": c.get("status"),
                    "start_date": c.get("start_date"),
                    "planned_end_date": c.get("planned_end_date"),
                    "actual_end_date": c.get("actual_end_date"),
                }
                for c in camps
            ],
            key=lambda x: x.get("start_date") or x.get("planned_end_date") or 0,
            reverse=True,
        )
        # latest graduation per campaign
        grad_status = rankings.get("strategies") or []

        return {
            "title": "Paper Operations Dashboard",
            "labels": {
                "paper_only": "PAPER ONLY",
                "no_live": "NO LIVE TRADING",
            },
            "posture": {**PAPER_POSTURE, "llm_boundary": LLM_BOUNDARY},
            "terminal_verdict_target": TERMINAL_VERDICT,
            "campaign_overview": {
                "total": len(camps),
                "by_status": _count_by(camps, "status"),
                "campaigns": camps[:50],
            },
            "strategy_rankings": rankings,
            "portfolio_rankings": port_rank,
            "operational_health": health,
            "risk_center": health.get("components", {}).get("risk_health"),
            "evidence_center": evidence,
            "incident_center": incidents,
            "recovery_center": health.get("components", {}).get("recovery_readiness"),
            "scheduler": {"jobs": jobs, "disabled_by_default": True},
            "storage": storage,
            "workers": workers,
            "campaign_timeline": timeline[:50],
            "graduation_status": grad_status,
            "recommendations": recs,
            "certification_reports": evidence.get("evidence") or [],
            "paper_only": True,
            "live_authorized": False,
            "disclaimer": PAPER_POSTURE["disclaimer"],
        }


def _count_by(items: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for i in items:
        k = str(i.get(key) or "UNKNOWN")
        out[k] = out.get(k, 0) + 1
    return out
