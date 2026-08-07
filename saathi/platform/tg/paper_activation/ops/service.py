"""M208–M215 Operational Graduation Service.

Composes durable paper governance with multi-campaign ops, monitoring,
graduation, intelligence, analytics, simulation, evidence, and dashboard.
PAPER ONLY. Live trading never authorized.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.platform.tg.paper_activation.durable.service import (
    DurableGovError,
    DurablePaperGovernanceService,
    default_durable_gov,
    reset_durable_gov_for_tests,
)
from saathi.platform.tg.paper_activation.ops.analytics_adv import AdvancedAnalytics
from saathi.platform.tg.paper_activation.ops.campaign_manager import MultiCampaignManager
from saathi.platform.tg.paper_activation.ops.dashboard import OperationsDashboard
from saathi.platform.tg.paper_activation.ops.evidence import EvidenceService
from saathi.platform.tg.paper_activation.ops.graduation import GraduationEngine
from saathi.platform.tg.paper_activation.ops.intelligence import OperationalIntelligence
from saathi.platform.tg.paper_activation.ops.models import (
    ENGINE_VERSION,
    LLM_BOUNDARY,
    PAPER_POSTURE,
    SCHEMA_VERSION,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.paper_activation.ops.monitoring import OperationalMonitor
from saathi.platform.tg.paper_activation.ops.simulation import OperationalSimulation, SCENARIOS


class OperationalGraduationService:
    """Facade for M208–M215. Delegates portfolio/order authority to durable gov."""

    def __init__(self, gov: DurablePaperGovernanceService | None = None, db_path: str | Path | None = None):
        self.gov = gov or DurablePaperGovernanceService(db_path=db_path)
        self.campaigns = MultiCampaignManager(self.gov)
        self.campaigns.ensure_schema()
        self.monitor = OperationalMonitor(self.gov)
        self.graduation = GraduationEngine(self.gov, self.campaigns)
        self.intelligence = OperationalIntelligence(self.gov, self.monitor)
        self.analytics = AdvancedAnalytics(self.gov)
        self.simulation = OperationalSimulation(self.gov)
        self.evidence = EvidenceService(
            self.gov,
            graduation=self.graduation,
            monitor=self.monitor,
            analytics=self.analytics,
            simulation=self.simulation,
            campaign_mgr=self.campaigns,
        )
        self.dashboard = OperationsDashboard(
            self.gov,
            campaign_mgr=self.campaigns,
            monitor=self.monitor,
            graduation=self.graduation,
            intelligence=self.intelligence,
            analytics=self.analytics,
            evidence=self.evidence,
            simulation=self.simulation,
        )

    # ── posture ──────────────────────────────────────────────────────────────
    def posture(self) -> dict[str, Any]:
        base = self.gov.posture()
        return {
            **base,
            **PAPER_POSTURE,
            "ops": {
                "schema_version": SCHEMA_VERSION,
                "engine_version": ENGINE_VERSION,
                "milestones": "M208-M215",
                "terminal_verdict_target": TERMINAL_VERDICT,
            },
            "llm_boundary": {**base.get("llm_boundary", {}), **LLM_BOUNDARY},
            "disclaimer": PAPER_POSTURE["disclaimer"],
        }

    def terminal_verdict(self) -> dict[str, Any]:
        return {
            "verdict": TERMINAL_VERDICT,
            "paper_only": True,
            "live_trading_authorized": False,
            "strategy_auto_promoted_to_live": False,
            "statements": [
                "THE SYSTEM REMAINS PAPER ONLY.",
                "LIVE TRADING IS NOT AUTHORIZED.",
                "NO STRATEGY IS AUTOMATICALLY PROMOTED TO LIVE EXECUTION.",
            ],
            "limitations": [
                "Single-host SQLite",
                "Graduation is paper research-stage only",
                "Owner human sign-off not claimed",
                "Browser soft-gate possible on cold Next compile",
            ],
        }

    # ── M208 campaigns ───────────────────────────────────────────────────────
    def campaign_create(self, **kwargs: Any) -> dict[str, Any]:
        return self.campaigns.create_campaign(**kwargs)

    def campaign_clone(self, campaign_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.campaigns.clone_campaign(campaign_id, **kwargs)

    def campaign_compare(self, campaign_ids: list[str]) -> dict[str, Any]:
        return self.campaigns.compare_campaigns(campaign_ids)

    def campaign_resume(self, campaign_id: str, *, operator_identity: str) -> dict[str, Any]:
        return self.campaigns.resume(campaign_id, operator_identity=operator_identity)

    def campaign_archive(self, campaign_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.campaigns.archive(campaign_id, **kwargs)

    def campaign_schedule(self, campaign_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.campaigns.schedule_campaign(campaign_id, **kwargs)

    def campaign_update(self, campaign_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.campaigns.update_notes_metadata(campaign_id, **kwargs)

    def campaign_set_dependencies(self, campaign_id: str, depends_on: list[str]) -> dict[str, Any]:
        return self.campaigns.set_dependencies(campaign_id, depends_on)

    def campaign_get(self, campaign_id: str) -> dict[str, Any]:
        return {"campaign": self.campaigns.get_campaign_full(campaign_id), "paper_only": True}

    def list_campaigns(self, **kwargs: Any) -> dict[str, Any]:
        return {"campaigns": self.campaigns.list_campaigns_full(**kwargs), "paper_only": True}

    def create_group(self, **kwargs: Any) -> dict[str, Any]:
        return {"group": self.campaigns.create_group(**kwargs), "paper_only": True}

    def list_groups(self, **kwargs: Any) -> dict[str, Any]:
        return {"groups": self.campaigns.list_groups(**kwargs), "paper_only": True}

    def create_template(self, **kwargs: Any) -> dict[str, Any]:
        return {"template": self.campaigns.create_template(**kwargs), "paper_only": True}

    def list_templates(self, **kwargs: Any) -> dict[str, Any]:
        return {"templates": self.campaigns.list_templates(**kwargs), "paper_only": True}

    # ── M209 monitoring ──────────────────────────────────────────────────────
    def health(self, **kwargs: Any) -> dict[str, Any]:
        return self.monitor.assess(**kwargs)

    def campaign_health(self, campaign_id: str) -> dict[str, Any]:
        return self.monitor.campaign_health(campaign_id)

    # ── M210 graduation ──────────────────────────────────────────────────────
    def graduate(self, campaign_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.graduation.evaluate(campaign_id, **kwargs)

    def graduation_history(self, campaign_id: str) -> dict[str, Any]:
        return {
            "evaluations": self.graduation.list_for_campaign(campaign_id),
            "paper_only": True,
            "live_authorized": False,
        }

    def strategy_rankings(self) -> dict[str, Any]:
        return self.graduation.rankings()

    # ── M211 intelligence ────────────────────────────────────────────────────
    def scan_intelligence(self, **kwargs: Any) -> dict[str, Any]:
        return self.intelligence.scan(**kwargs)

    def recommendations(self, **kwargs: Any) -> dict[str, Any]:
        return self.intelligence.list_recommendations(**kwargs)

    # ── M212 analytics ───────────────────────────────────────────────────────
    def rolling_analytics(self, portfolio_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.analytics.rolling_stats(portfolio_id, **kwargs)

    def record_equity(self, portfolio_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.analytics.record_equity_point(portfolio_id, **kwargs)

    def campaign_report(self, campaign_id: str) -> dict[str, Any]:
        return self.analytics.campaign_report(campaign_id)

    def weekly_report(self) -> dict[str, Any]:
        return self.analytics.weekly_report()

    def monthly_report(self) -> dict[str, Any]:
        return self.analytics.monthly_report()

    def comparison_report(self, campaign_ids: list[str]) -> dict[str, Any]:
        return self.analytics.comparison_report(campaign_ids)

    # ── M213 simulation ──────────────────────────────────────────────────────
    def simulate(self, scenario: str, **kwargs: Any) -> dict[str, Any]:
        return self.simulation.run(scenario, **kwargs)

    def simulate_suite(self, **kwargs: Any) -> dict[str, Any]:
        return self.simulation.run_suite(**kwargs)

    def list_scenarios(self) -> dict[str, Any]:
        return {"scenarios": sorted(SCENARIOS), "paper_only": True}

    # ── M214 evidence ────────────────────────────────────────────────────────
    def certify_campaign(self, campaign_id: str, **kwargs: Any) -> dict[str, Any]:
        return self.evidence.certify_campaign(campaign_id, **kwargs)

    def list_evidence(self, **kwargs: Any) -> dict[str, Any]:
        return self.evidence.list_evidence(**kwargs)

    def get_evidence(self, evidence_id: str) -> dict[str, Any]:
        return self.evidence.get_evidence(evidence_id)

    # ── M215 dashboard ───────────────────────────────────────────────────────
    def ops_dashboard(self) -> dict[str, Any]:
        return self.dashboard.overview()

    # ── pass-through durable essentials ──────────────────────────────────────
    def __getattr__(self, name: str) -> Any:
        # Allow tests/API to use durable methods via ops service
        return getattr(self.gov, name)


_default_ops: OperationalGraduationService | None = None


def default_ops_gov(db_path: str | Path | None = None) -> OperationalGraduationService:
    global _default_ops
    if _default_ops is None:
        _default_ops = OperationalGraduationService(db_path=db_path)
    return _default_ops


def reset_ops_gov_for_tests(db_path: str | Path | None = None) -> OperationalGraduationService:
    global _default_ops
    if _default_ops is not None:
        try:
            _default_ops.gov.store.close()
        except Exception:
            pass
    # also reset durable singleton
    reset_durable_gov_for_tests(db_path)
    gov = default_durable_gov(db_path)
    _default_ops = OperationalGraduationService(gov=gov)
    return _default_ops


__all__ = [
    "OperationalGraduationService",
    "DurableGovError",
    "default_ops_gov",
    "reset_ops_gov_for_tests",
    "TERMINAL_VERDICT",
]
