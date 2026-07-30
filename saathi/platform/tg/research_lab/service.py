"""M272–M279 Multi-Strategy Research Lab service facade.

RESEARCH ONLY. OFFLINE-FIRST. NO BROKER. NO API KEYS. NO LIVE TRADING.
Maximum authority: RESEARCH_PORTFOLIO_AND_PAPER_CANDIDATE_EVALUATION_ONLY
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from saathi.platform.tg.research_lab.candidate_promotion import CandidatePromotionEngine
from saathi.platform.tg.research_lab.comparison import StrategyComparisonEngine
from saathi.platform.tg.research_lab.ensemble import EnsembleEngine
from saathi.platform.tg.research_lab.errors import ResearchLabError
from saathi.platform.tg.research_lab.experiment_registry import ExperimentRegistry
from saathi.platform.tg.research_lab.experiment_runner import ExperimentRunner
from saathi.platform.tg.research_lab.lineage import LineageTracker
from saathi.platform.tg.research_lab.models import (
    AUTHORITY_VALUES,
    ENGINE_VERSION,
    LLM_BOUNDARY,
    MAX_STATE,
    PRESERVED_OOS_FAILURES,
    RL_POSTURE,
    SCHEMA_VERSION,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.research_lab.portfolio_builder import PortfolioBuilder
from saathi.platform.tg.research_lab.regime_classifier import RegimeClassifier
from saathi.platform.tg.research_lab.regime_validation import RegimeValidationEngine
from saathi.platform.tg.research_lab.regimes import list_default_definitions
from saathi.platform.tg.research_lab.robustness import RobustnessEngine
from saathi.platform.tg.research_lab.security import ResearchLabSecurity
from saathi.platform.tg.research_lab.storage import ResearchLabStore
from saathi.platform.tg.research_lab.strategy_universe import StrategyUniverse
from saathi.platform.tg.research_lab.stress_testing import StressTestingEngine


class ResearchLabService:
    def __init__(self, db_path: str | Path | None = None, repo_root: Path | None = None):
        self.store = ResearchLabStore(db_path)
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        self.registry = ExperimentRegistry(self.store, self.repo_root)
        self.universe = StrategyUniverse()
        self.comparison = StrategyComparisonEngine(self.store)
        self.robustness = RobustnessEngine(self.store)
        self.regimes = RegimeClassifier(self.store)
        self.regime_val = RegimeValidationEngine()
        self.portfolio = PortfolioBuilder(self.store)
        self.ensemble = EnsembleEngine(self.store)
        self.stress = StressTestingEngine(self.store)
        self.candidates = CandidatePromotionEngine(self.store)
        self.lineage = LineageTracker(self.store)
        self.security = ResearchLabSecurity(self.repo_root)
        self.runner = ExperimentRunner(
            self.registry, self.comparison, self.robustness, self.regimes,
            self.regime_val, self.portfolio, self.ensemble, self.stress, self.candidates,
        )

    def posture(self) -> dict[str, Any]:
        return {
            **RL_POSTURE,
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M272-M279",
            "terminal_verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "llm_boundary": dict(LLM_BOUNDARY),
            "preserved_oos_failures": list(PRESERVED_OOS_FAILURES),
            **AUTHORITY_VALUES,
        }

    def terminal_verdict(self) -> dict[str, Any]:
        return {
            "verdict": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "statements": list(TERMINAL_STATEMENTS),
            "capabilities": {
                "experiment_registry": True,
                "multi_strategy_comparison": True,
                "robustness_overfitting": True,
                "regime_intelligence": True,
                "portfolio_optimisation": True,
                "strategy_ensembles": True,
                "stress_testing": True,
                "candidate_promotion": True,
                "control_center": True,
            },
            "limitations": [
                "Research-only; not investment advice",
                "No broker connectivity or order execution",
                "PAPER_CANDIDATE does not authorize execution",
                "Portfolio optimisation is not regulatory-grade",
                "Preserved M270 OOS failures are valid research results",
            ],
            **AUTHORITY_VALUES,
        }

    # ── M272 Experiments ─────────────────────────────────────────────────
    def create_experiment(self, name: str, **kwargs: Any) -> dict[str, Any]:
        return self.registry.create(name, **kwargs)

    def pre_register(self, experiment_id: str, experiment_version: str = "v1", **kw: Any) -> dict[str, Any]:
        return self.registry.pre_register(experiment_id, experiment_version, **kw)

    def list_experiments(self, status: str | None = None) -> dict[str, Any]:
        return self.registry.list(status)

    def get_experiment(self, experiment_id: str, experiment_version: str = "v1") -> dict[str, Any]:
        return self.registry.get(experiment_id, experiment_version)

    def run_experiment(self, experiment_id: str, experiment_version: str = "v1", **kw: Any) -> dict[str, Any]:
        return self.runner.run(experiment_id, experiment_version, **kw)

    def replay_experiment(self, experiment_id: str, experiment_version: str = "v1") -> dict[str, Any]:
        return self.registry.replay(experiment_id, experiment_version)

    def experiment_lineage(self, experiment_id: str) -> dict[str, Any]:
        return self.registry.lineage(experiment_id)

    def export_registry(self) -> dict[str, Any]:
        return self.registry.export_registry()

    # ── M273 Comparison ──────────────────────────────────────────────────
    def compare_strategies(self, strategy_ids: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        if not strategy_ids:
            listed = self.universe.list_strategies()
            strategy_ids = [s["id"] for s in (listed.get("strategies") or [])[:5]]
        return self.comparison.compare(strategy_ids, **kw)

    # ── M274 Robustness ──────────────────────────────────────────────────
    def analyse_robustness(self, strategy_id: str, **kw: Any) -> dict[str, Any]:
        return self.robustness.analyse(strategy_id, **kw)

    # ── M275 Regimes ─────────────────────────────────────────────────────
    def regime_definitions(self) -> dict[str, Any]:
        return list_default_definitions()

    def build_regimes(self, train_returns: list[float] | None = None) -> dict[str, Any]:
        if train_returns is None:
            from saathi.platform.tg.research_lab.comparison import _simulate_strategy_returns
            train_returns = _simulate_strategy_returns("tf_dual_ma", n=90, seed=42)["returns"]
        return self.regimes.build_definitions(train_returns)

    def classify_regimes(self, returns: list[float] | None = None, definitions: list | None = None) -> dict[str, Any]:
        if returns is None:
            from saathi.platform.tg.research_lab.comparison import _simulate_strategy_returns
            returns = _simulate_strategy_returns("tf_dual_ma", n=120, seed=42)["returns"]
        if definitions is None:
            definitions = self.build_regimes(returns[: int(len(returns) * 0.6)])["definitions"]
        return self.regimes.classify(returns, definitions)

    def validate_regimes(self, strategy_id: str = "tf_dual_ma") -> dict[str, Any]:
        from saathi.platform.tg.research_lab.comparison import _simulate_strategy_returns
        rets = _simulate_strategy_returns(strategy_id, n=120, seed=42)["returns"]
        defs = self.build_regimes(rets[:72])["definitions"]
        cls = self.regimes.classify(rets, defs)
        series = cls.get("series_full_bounded") or []
        # pad simple
        while len(series) < len(rets):
            series.append({"labels": {"trend": "UNKNOWN"}, "state": "REGIME_UNKNOWN"})
        return self.regime_val.validate_strategy_by_regime(rets, series[: len(rets)], strategy_id=strategy_id)

    # ── M276 Portfolio ───────────────────────────────────────────────────
    def build_portfolio(
        self,
        assets: list[str],
        returns_by_asset: dict[str, list[float]],
        **kw: Any,
    ) -> dict[str, Any]:
        return self.portfolio.build(assets, returns_by_asset, **kw)

    def optimise_portfolio(self, **kw: Any) -> dict[str, Any]:
        return self.portfolio.build(**kw)

    # ── M277 Ensemble ────────────────────────────────────────────────────
    def build_ensemble(self, strategy_ids: list[str], **kw: Any) -> dict[str, Any]:
        return self.ensemble.build(strategy_ids, **kw)

    # ── M278 Stress + Candidates ─────────────────────────────────────────
    def run_stress(self, weights: dict[str, float], returns_by_asset: dict[str, list[float]], **kw: Any) -> dict[str, Any]:
        return self.stress.run(weights, returns_by_asset, **kw)

    def evaluate_candidate(self, subject_type: str, subject_id: str, **kw: Any) -> dict[str, Any]:
        return self.candidates.evaluate(subject_type, subject_id, **kw)

    def list_candidates(self, state: str | None = None) -> dict[str, Any]:
        return self.candidates.list(state)

    def get_candidate(self, candidate_id: str) -> dict[str, Any]:
        return self.candidates.get(candidate_id)

    def reject_candidate(self, candidate_id: str, reason: str, **kw: Any) -> dict[str, Any]:
        return self.candidates.reject(candidate_id, reason, **kw)

    def revoke_candidate(self, candidate_id: str, reason: str, **kw: Any) -> dict[str, Any]:
        return self.candidates.revoke(candidate_id, reason, **kw)

    def request_candidate_review(self, candidate_id: str, *, actor: str) -> dict[str, Any]:
        return self.candidates.human_approve_paper_candidate(candidate_id, actor=actor, with_limitations=True)

    # ── Bootstrap / dashboard ────────────────────────────────────────────
    def bootstrap_demo_pipeline(self) -> dict[str, Any]:
        """Deterministic offline demo pipeline for certification and UI.

        Idempotent: if the demo experiment already completed, returns a replay.
        """
        exp = self.create_experiment(
            name="m272_demo_multi_strategy_lab",
            description="Bounded multi-strategy research lab demo",
            research_question="Do multi-strategy ensembles improve research robustness vs single dual-MA?",
            hypothesis="Equal-weight ensemble of registry strategies is more robust than tf_dual_ma alone under common costs",
            strategy_ids=["tf_dual_ma", "mom_rs_equity", "mr_bollinger_reversion", "bo_donchian"],
            instrument_universe=["DEMO", "AAPL", "BTCUSDT"],
            fixed_parameters={"sma_fast": 10, "sma_slow": 20},
            trial_count=1,
            random_seed=42,
            transaction_cost_model={"commission_bps": 5.0},
            slippage_model={"slippage_bps": 8.0},
            limitations=["Demo uses synthetic paths plus preserved M270 historical OOS failures"],
        )
        eid = exp["experiment_id"]
        ver = exp["experiment_version"]
        current = self.registry.get(eid, ver)
        status = (current or {}).get("status")

        if status in ("COMPLETED", "FAILED"):
            replay = self.registry.replay(eid, ver)
            result = replay.get("result") or {}
            return {
                "ok": True,
                "idempotent_replay": True,
                "pre_registered": True,
                "experiment_id": eid,
                "experiment_version": ver,
                "config_checksum": exp["config_checksum"],
                "comparison": result.get("comparison"),
                "robustness": result.get("robustness"),
                "regimes": result.get("regimes"),
                "portfolio": result.get("portfolio"),
                "ensemble": result.get("ensemble"),
                "stress": result.get("stress"),
                "candidate": result.get("candidate"),
                "preserved_oos_failures": result.get("preserved_oos_failures") or list(PRESERVED_OOS_FAILURES),
                **AUTHORITY_VALUES,
            }

        if status == "DRAFT":
            self.pre_register(eid, ver)
            status = "PRE_REGISTERED"
        if status == "PRE_REGISTERED":
            self.registry.mark_ready(eid, ver)
        run = self.run_experiment(eid, ver)
        return {
            "ok": True,
            "pre_registered": True,
            "experiment_id": eid,
            "experiment_version": ver,
            "config_checksum": exp["config_checksum"],
            "comparison": run.get("comparison"),
            "robustness": run.get("robustness"),
            "regimes": run.get("regimes"),
            "portfolio": run.get("portfolio"),
            "ensemble": run.get("ensemble"),
            "stress": run.get("stress"),
            "candidate": run.get("candidate"),
            "preserved_oos_failures": run.get("preserved_oos_failures") or list(PRESERVED_OOS_FAILURES),
            **AUTHORITY_VALUES,
        }

    def dashboard(self) -> dict[str, Any]:
        exps = self.registry.list(limit=50)
        by_status: dict[str, int] = {}
        for e in exps.get("experiments") or []:
            st = e.get("status") or "UNKNOWN"
            by_status[st] = by_status.get(st, 0) + 1
        cands = self.candidates.list(limit=50)
        cand_by: dict[str, int] = {}
        for c in cands.get("candidates") or []:
            st = c.get("state") or "UNKNOWN"
            cand_by[st] = cand_by.get(st, 0) + 1
        return {
            "title": "Multi-Strategy Research Lab Control Center",
            "verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "statements": list(TERMINAL_STATEMENTS),
            "overview": {
                "experiment_count": exps.get("count", 0),
                "by_status": by_status,
                "candidate_count": cands.get("count", 0),
                "candidates_by_state": cand_by,
                "paper_candidates": cand_by.get("PAPER_CANDIDATE", 0) + cand_by.get("PAPER_CANDIDATE_WITH_LIMITATIONS", 0),
                "preserved_oos_failures": list(PRESERVED_OOS_FAILURES),
                "dataset_status": "BOUNDED_REAL_HISTORICAL_DATA_VALIDATED_WITH_LIMITATIONS",
            },
            "experiments": (exps.get("experiments") or [])[:20],
            "candidates": (cands.get("candidates") or [])[:20],
            "labels": {
                "RESEARCH_ONLY": True,
                "OFFLINE_FIRST": True,
                "PAPER_CANDIDATE_DOES_NOT_AUTHORISE_ORDER_EXECUTION": True,
                "NO_BROKER_CONNECTIVITY": True,
                "NO_ACCOUNT_ACCESS": True,
                "NO_CREDENTIALS": True,
                "NO_LIVE_TRADING": True,
            },
            **AUTHORITY_VALUES,
        }

    def evidence_bundle(self) -> dict[str, Any]:
        return {
            "registry": self.export_registry(),
            "security": self.security_scan(),
            "threat_model": self.threat_model(),
            "preserved_oos_failures": list(PRESERVED_OOS_FAILURES),
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
        from saathi.platform.tg.research_lab.certification import certify_research_lab
        return certify_research_lab(self)


_default: ResearchLabService | None = None


def default_research_lab() -> ResearchLabService:
    global _default
    if _default is None:
        _default = ResearchLabService()
    return _default


def reset_research_lab_for_tests(db_path: str | Path | None = None) -> ResearchLabService:
    global _default
    if _default is not None:
        try:
            _default.store.close()
        except Exception:
            pass
    _default = ResearchLabService(db_path=db_path)
    return _default
