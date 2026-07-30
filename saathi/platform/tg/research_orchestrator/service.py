"""M280–M287 Autonomous Research Orchestrator service facade.

RESEARCH ONLY. OFFLINE-FIRST. NO BROKER. NO ORDERS. NO LIVE TRADING.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from saathi.platform.tg.research_orchestrator.budget import ComputeBudgetManager
from saathi.platform.tg.research_orchestrator.calendar import ResearchCalendar
from saathi.platform.tg.research_orchestrator.dependencies import DependencyGraph
from saathi.platform.tg.research_orchestrator.errors import OrchestratorError
from saathi.platform.tg.research_orchestrator.estimator import RuntimeEstimator
from saathi.platform.tg.research_orchestrator.journal import (
    FailureAnalysis,
    HypothesisTracker,
    ResearchJournal,
)
from saathi.platform.tg.research_orchestrator.models import (
    AUTHORITY_VALUES,
    DEFAULT_MAX_WORKERS,
    ENGINE_VERSION,
    LLM_BOUNDARY,
    MAX_STATE,
    ORCH_POSTURE,
    SCHEMA_VERSION,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
    JobPriority,
)
from saathi.platform.tg.research_orchestrator.queue import ExperimentQueue
from saathi.platform.tg.research_orchestrator.registries import (
    DatasetRegistryView,
    FeatureRegistryView,
    ModelRegistry,
    StrategyRegistryV2,
)
from saathi.platform.tg.research_orchestrator.scheduler import ExperimentScheduler
from saathi.platform.tg.research_orchestrator.security import OrchestratorSecurity
from saathi.platform.tg.research_orchestrator.sessions import ResearchSessionManager
from saathi.platform.tg.research_orchestrator.storage import OrchestratorStore
from saathi.platform.tg.research_orchestrator.templates import TemplateRegistry
from saathi.platform.tg.research_orchestrator.workers import WorkerPool


class ResearchOrchestratorService:
    def __init__(
        self,
        db_path: str | Path | None = None,
        repo_root: Path | None = None,
        max_workers: int = DEFAULT_MAX_WORKERS,
    ):
        self.store = OrchestratorStore(db_path)
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        self.queue = ExperimentQueue(self.store)
        self.workers = WorkerPool(self.store, max_workers=max_workers)
        self.budget = ComputeBudgetManager(self.store)
        self.deps = DependencyGraph(self.store)
        self.scheduler = ExperimentScheduler(
            self.store, self.queue, self.workers, self.budget, self.deps,
        )
        self.estimator = RuntimeEstimator()
        self.templates = TemplateRegistry(self.store)
        self.models = ModelRegistry(self.store)
        self.strategies = StrategyRegistryV2()
        self.features = FeatureRegistryView()
        self.datasets = DatasetRegistryView()
        self.hypotheses = HypothesisTracker(self.store)
        self.journal = ResearchJournal(self.store)
        self.failures = FailureAnalysis(self.store)
        self.sessions = ResearchSessionManager(self.store)
        self.calendar = ResearchCalendar()
        self.security = OrchestratorSecurity(self.repo_root)

    def posture(self) -> dict[str, Any]:
        return {
            **ORCH_POSTURE,
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M280-M287",
            "terminal_verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "llm_boundary": dict(LLM_BOUNDARY),
            **AUTHORITY_VALUES,
        }

    def terminal_verdict(self) -> dict[str, Any]:
        return {
            "verdict": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "statements": list(TERMINAL_STATEMENTS),
            "capabilities": {
                "experiment_queue": True,
                "scheduler": True,
                "worker_pool": True,
                "priority_queue": True,
                "retry_resume_cancel": True,
                "dependency_graph": True,
                "compute_budget": True,
                "runtime_estimator": True,
                "research_calendar": True,
                "templates": True,
                "model_registry": True,
                "strategy_registry_v2": True,
                "feature_registry": True,
                "dataset_registry_integration": True,
                "lab_notebook": True,
                "research_journal": True,
                "hypothesis_tracking": True,
                "failure_analysis": True,
                "research_sessions": True,
                "job_replay": True,
                "version_promotion": True,
                "dashboard": True,
            },
            "limitations": [
                "In-process workers only",
                "No distributed cluster",
                "No broker or order execution",
                "Logical compute budget only",
            ],
            **AUTHORITY_VALUES,
        }

    # ── Queue / schedule ─────────────────────────────────────────────────
    def enqueue_job(
        self,
        name: str,
        config: dict[str, Any] | None = None,
        *,
        priority: str = JobPriority.NORMAL.value,
        template_id: str | None = None,
        depends_on: list[str] | None = None,
        max_retries: int = 2,
        actor: str = "system",
    ) -> dict[str, Any]:
        config = dict(config or {})
        if template_id and not config:
            tpl = self.templates.get(template_id)
            if tpl.get("ok"):
                config = dict(tpl["body"])
        est = self.estimator.estimate(config)
        return self.queue.enqueue(
            name,
            config,
            priority=priority,
            template_id=template_id,
            depends_on=depends_on,
            budget_units=est["budget_units"],
            estimated_runtime_sec=est["estimated_runtime_sec"],
            max_retries=max_retries,
            actor=actor,
        )

    def list_jobs(self, state: str | None = None) -> dict[str, Any]:
        return self.queue.list(state)

    def get_job(self, job_id: str) -> dict[str, Any]:
        return self.queue.get(job_id)

    def tick(self, max_jobs: int = 1) -> dict[str, Any]:
        return self.scheduler.tick(max_jobs=max_jobs)

    def cancel_job(self, job_id: str, reason: str = "cancelled", **kw: Any) -> dict[str, Any]:
        return self.scheduler.cancel(job_id, reason=reason, **kw)

    def suspend_job(self, job_id: str, **kw: Any) -> dict[str, Any]:
        return self.scheduler.suspend(job_id, **kw)

    def resume_job(self, job_id: str, **kw: Any) -> dict[str, Any]:
        return self.scheduler.resume(job_id, **kw)

    def replay_job(self, job_id: str) -> dict[str, Any]:
        return self.scheduler.replay(job_id)

    def estimate(self, config: dict | None = None) -> dict[str, Any]:
        return self.estimator.estimate(config)

    def budget_status(self) -> dict[str, Any]:
        return self.budget.status()

    def workers_status(self) -> dict[str, Any]:
        return self.workers.list()

    def dependency_graph(self) -> dict[str, Any]:
        return self.deps.graph_snapshot()

    # ── Templates / registries ───────────────────────────────────────────
    def list_templates(self) -> dict[str, Any]:
        return self.templates.list()

    def promote_template(self, template_id: str, **kw: Any) -> dict[str, Any]:
        return self.templates.promote(template_id, **kw)

    def list_models(self) -> dict[str, Any]:
        return self.models.list()

    def register_model(self, name: str, **meta: Any) -> dict[str, Any]:
        return self.models.register(name, **meta)

    def list_strategies_v2(self, category: str | None = None) -> dict[str, Any]:
        return self.strategies.list(category)

    def list_features(self) -> dict[str, Any]:
        return self.features.list()

    def list_datasets(self, state: str | None = None) -> dict[str, Any]:
        return self.datasets.list(state)

    # ── Journal / hypotheses / sessions ──────────────────────────────────
    def create_hypothesis(self, statement: str) -> dict[str, Any]:
        return self.hypotheses.create(statement)

    def list_hypotheses(self) -> dict[str, Any]:
        return self.hypotheses.list()

    def write_journal(self, title: str, body: str, **kw: Any) -> dict[str, Any]:
        return self.journal.write(title, body, **kw)

    def list_journal(self) -> dict[str, Any]:
        return self.journal.list()

    def notebook(self) -> dict[str, Any]:
        return self.journal.notebook()

    def failure_analysis(self) -> dict[str, Any]:
        return self.failures.analyse()

    def open_session(self, name: str, **kw: Any) -> dict[str, Any]:
        return self.sessions.open(name, **kw)

    def list_sessions(self) -> dict[str, Any]:
        return self.sessions.list()

    def get_session(self, session_id: str) -> dict[str, Any]:
        return self.sessions.get(session_id)

    def research_calendar(self) -> dict[str, Any]:
        return self.calendar.list_slots()

    # ── Bootstrap / dashboard ────────────────────────────────────────────
    def bootstrap_demo_pipeline(self) -> dict[str, Any]:
        sess = self.sessions.open("m280_demo_session", seed=42)
        hyp = self.hypotheses.create(
            "Equal-weight multi-strategy compare is schedulable under budget constraints"
        )
        jnl = self.journal.write(
            "M280 bootstrap",
            "Autonomous research orchestrator demo session opened",
            kind="session",
            refs={"session_id": sess["session_id"]},
        )
        # parent job
        parent = self.enqueue_job(
            "demo_noop_parent",
            {"kind": "noop", "seed": 42},
            priority="HIGH",
        )
        # dependent compare
        child = self.enqueue_job(
            "demo_strategy_compare",
            {"kind": "strategy_compare", "strategy_ids": ["tf_dual_ma", "mom_rs_equity"], "seed": 42},
            priority="NORMAL",
            depends_on=[parent["job_id"]],
            template_id="tpl_strategy_compare_v1",
        )
        self.sessions.attach_job(sess["session_id"], parent["job_id"])
        self.sessions.attach_job(sess["session_id"], child["job_id"])
        self.hypotheses.link_job(hyp["hypothesis_id"], child["job_id"])
        self.models.register("demo_research_model", version="v1", kind="research_placeholder")

        tick1 = self.tick(max_jobs=5)
        # second tick if child still queued after parent
        tick2 = self.tick(max_jobs=5)
        ran = list(tick1.get("ran") or []) + list(tick2.get("ran") or [])

        # promote a template
        promo = self.templates.promote("tpl_noop_v1", actor="system")

        self.hypotheses.update_status(
            hyp["hypothesis_id"],
            "EVALUATED",
            evidence={"jobs_ran": len(ran)},
        )
        self.sessions.close(sess["session_id"])

        return {
            "ok": True,
            "session_id": sess["session_id"],
            "hypothesis_id": hyp["hypothesis_id"],
            "journal_entry_id": jnl.get("entry_id"),
            "parent_job_id": parent["job_id"],
            "child_job_id": child["job_id"],
            "ran": ran,
            "queue": self.queue.stats(),
            "workers": self.workers.list(),
            "budget": self.budget.status(),
            "templates_count": self.templates.list().get("count"),
            "promotion": promo,
            "failures": self.failures.analyse(),
            **AUTHORITY_VALUES,
        }

    def dashboard(self) -> dict[str, Any]:
        return {
            "title": "Autonomous Research Orchestrator Control Center",
            "verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "statements": list(TERMINAL_STATEMENTS),
            "overview": {
                "queue": self.queue.stats(),
                "workers": self.workers.list(),
                "budget": self.budget.status(),
                "templates": self.templates.list().get("count"),
                "hypotheses": self.hypotheses.list().get("count"),
                "sessions": self.sessions.list().get("count"),
            },
            "calendar": self.calendar.list_slots(),
            "labels": {
                "RESEARCH_ONLY": True,
                "OFFLINE_FIRST": True,
                "NO_BROKER_CONNECTIVITY": True,
                "NO_ORDER_EXECUTION": True,
                "NO_LIVE_TRADING": True,
                "DETERMINISTIC_ORCHESTRATION": True,
            },
            **AUTHORITY_VALUES,
        }

    def evidence_bundle(self) -> dict[str, Any]:
        return {
            "queue": self.queue.stats(),
            "templates": self.templates.list(),
            "failures": self.failures.analyse(),
            "security": self.security_scan(),
            "threat_model": self.threat_model(),
            **AUTHORITY_VALUES,
        }

    def refuse_broker(self, target: str = "") -> dict[str, Any]:
        return self.security.refuse_broker(target)

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return self.security.refuse_credentials(value)

    def refuse_order(self) -> dict[str, Any]:
        return self.security.refuse_order()

    def refuse_canary(self) -> dict[str, Any]:
        return self.security.refuse_canary()

    def refuse_paper_execution(self) -> dict[str, Any]:
        return self.security.refuse_paper_execution()

    def security_scan(self) -> dict[str, Any]:
        return self.security.full_scan()

    def threat_model(self) -> dict[str, Any]:
        return self.security.threat_model()

    def certify(self) -> dict[str, Any]:
        from saathi.platform.tg.research_orchestrator.certification import certify_orchestrator
        return certify_orchestrator(self)


_default: ResearchOrchestratorService | None = None


def default_research_orchestrator() -> ResearchOrchestratorService:
    global _default
    if _default is None:
        _default = ResearchOrchestratorService()
    return _default


def reset_research_orchestrator_for_tests(
    db_path: str | Path | None = None,
) -> ResearchOrchestratorService:
    global _default
    if _default is not None:
        try:
            _default.store.close()
        except Exception:
            pass
    _default = ResearchOrchestratorService(db_path=db_path)
    return _default
