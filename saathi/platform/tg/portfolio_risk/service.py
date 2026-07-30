"""M296–M303 Institutional Portfolio & Risk Intelligence service facade.

PAPER / RESEARCH ONLY. NO BROKER. NO ORDERS. NO LIVE TRADING.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.portfolio_risk.analytics import PortfolioAnalytics
from saathi.platform.tg.portfolio_risk.attribution import PerformanceAttribution
from saathi.platform.tg.portfolio_risk.committee_v2 import InvestmentCommitteeV2
from saathi.platform.tg.portfolio_risk.errors import PortfolioRiskError
from saathi.platform.tg.portfolio_risk.limits import LimitsEngine
from saathi.platform.tg.portfolio_risk.models import (
    AUTHORITY_VALUES,
    DEFAULT_DEMO_PORTFOLIO,
    ENGINE_VERSION,
    LLM_BOUNDARY,
    MAX_STATE,
    PR_POSTURE,
    SCHEMA_VERSION,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.portfolio_risk.optimiser_v2 import PortfolioOptimiserV2
from saathi.platform.tg.portfolio_risk.scenarios import ScenarioEngine
from saathi.platform.tg.portfolio_risk.security import PortfolioRiskSecurity
from saathi.platform.tg.portfolio_risk.sizing import PositionSizingEngine
from saathi.platform.tg.portfolio_risk.storage import PortfolioRiskStore, evidence_hash, _uid


class PortfolioRiskService:
    def __init__(self, db_path: str | Path | None = None, repo_root: Path | None = None):
        self.store = PortfolioRiskStore(db_path)
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        self.analytics_engine = PortfolioAnalytics()
        self.limits_engine = LimitsEngine()
        self.sizing_engine = PositionSizingEngine()
        self.optimiser = PortfolioOptimiserV2(self.store)
        self.scenarios = ScenarioEngine(self.store)
        self.committee = InvestmentCommitteeV2(self.store)
        self.attribution_engine = PerformanceAttribution()
        self.security = PortfolioRiskSecurity(self.repo_root)

    def posture(self) -> dict[str, Any]:
        return {
            **PR_POSTURE,
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M296-M303",
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
                "portfolio_analytics": True,
                "position_attribution": True,
                "risk_attribution": True,
                "factor_exposure": True,
                "beta_exposure": True,
                "sector_exposure": True,
                "correlation_engine": True,
                "diversification_engine": True,
                "risk_budgeting": True,
                "portfolio_optimiser_v2": True,
                "dynamic_allocation": True,
                "position_sizing": True,
                "drawdown_manager": True,
                "exposure_limits": True,
                "scenario_engine": True,
                "stress_dashboard": True,
                "liquidity_dashboard": True,
                "expected_shortfall_dashboard": True,
                "performance_attribution": True,
                "investment_committee_v2": True,
            },
            "limitations": [
                "Not regulatory-grade risk capital",
                "Not investment advice",
                "Paper/research portfolios only",
                "No broker or order execution",
            ],
            **AUTHORITY_VALUES,
        }

    def _resolve_portfolio(self, portfolio: dict | None = None, portfolio_id: str | None = None) -> dict[str, Any]:
        if portfolio:
            return portfolio
        # Try paper simulation portfolio if id provided
        if portfolio_id:
            try:
                from saathi.platform.tg.paper_simulation.service import default_paper_simulation
                ps = default_paper_simulation()
                got = ps.get_portfolio(portfolio_id)
                if got.get("ok"):
                    pf = got["portfolio"]
                    positions = []
                    for p in got.get("positions") or []:
                        positions.append({
                            "symbol": p["symbol"],
                            "quantity": p["quantity"],
                            "avg_cost": p["avg_cost"],
                            "mark": p["mark"],
                            "sector": "Unknown",
                            "geography": "Unknown",
                            "asset_class": "equity_etf" if not str(p["symbol"]).endswith("USDT") else "crypto",
                            "beta": 1.0,
                        })
                    return {
                        "id": portfolio_id,
                        "name": pf.get("name", "Paper Sim"),
                        "cash": pf.get("cash", 0),
                        "positions": positions,
                        "realized_pnl": 0,
                    }
            except Exception:
                pass
        return dict(DEFAULT_DEMO_PORTFOLIO)

    def analyze(self, portfolio: dict | None = None, portfolio_id: str | None = None) -> dict[str, Any]:
        p = self._resolve_portfolio(portfolio, portfolio_id)
        result = self.analytics_engine.analyze(p)
        eh = evidence_hash(result)
        result["evidence_hash"] = eh
        sid = _uid("snap")
        self.store.execute(
            "INSERT INTO pr_snapshots(id, portfolio_id, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
            (sid, result.get("portfolio_id", "demo"), json.dumps(result, sort_keys=True, default=str), eh, time.time()),
        )
        result["snapshot_id"] = sid
        return result

    def evaluate_limits(self, analytics: dict | None = None, **kw: Any) -> dict[str, Any]:
        analytics = analytics or self.analyze(**kw)
        return self.limits_engine.evaluate(analytics)

    def size_positions(self, symbols: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        symbols = symbols or ["SPY", "QQQ", "TLT", "GLD"]
        return self.sizing_engine.size(symbols, **kw)

    def dynamic_allocation(self, weights: dict[str, float], **kw: Any) -> dict[str, Any]:
        return self.sizing_engine.dynamic_allocation(weights, **kw)

    def optimise(self, symbols: list[str] | None = None, **kw: Any) -> dict[str, Any]:
        symbols = symbols or ["SPY", "QQQ", "EFA", "TLT", "GLD"]
        return self.optimiser.optimise(symbols, **kw)

    def run_scenarios(self, analytics: dict | None = None, **kw: Any) -> dict[str, Any]:
        analytics = analytics or self.analyze(**kw)
        return self.scenarios.run(analytics)

    def performance_attribution(self, analytics: dict | None = None, **kw: Any) -> dict[str, Any]:
        analytics = analytics or self.analyze(**kw)
        return self.attribution_engine.attribute(analytics)

    def committee_review(self, analytics: dict | None = None, **kw: Any) -> dict[str, Any]:
        analytics = analytics or self.analyze()
        limits = self.evaluate_limits(analytics)
        scenarios = self.run_scenarios(analytics)
        return self.committee.review(analytics=analytics, limits=limits, scenarios=scenarios, **kw)

    def bootstrap_demo_pipeline(self) -> dict[str, Any]:
        analytics = self.analyze()
        limits = self.evaluate_limits(analytics)
        attribution = self.performance_attribution(analytics)
        sizing = self.size_positions(
            [p["symbol"] for p in analytics.get("positions") or []],
            equity=float(analytics["analytics"]["equity"]),
            method="inverse_volatility",
        )
        dyn = self.dynamic_allocation(sizing["weights"], regime="normal", vol_scale=1.0)
        opt = self.optimise(
            [p["symbol"] for p in analytics.get("positions") or []],
            method="inverse_volatility",
        )
        scenarios = self.run_scenarios(analytics)
        committee = self.committee_review(analytics=analytics)
        return {
            "ok": True,
            "analytics": analytics,
            "limits": limits,
            "attribution": attribution,
            "sizing": sizing,
            "dynamic_allocation": dyn,
            "optimisation": opt,
            "scenarios": scenarios,
            "committee": committee,
            **AUTHORITY_VALUES,
        }

    def dashboard(self) -> dict[str, Any]:
        pipe = self.bootstrap_demo_pipeline()
        return {
            "title": "Institutional Portfolio & Risk Intelligence Control Center",
            "verdict_target": TERMINAL_VERDICT,
            "max_state": MAX_STATE,
            "statements": list(TERMINAL_STATEMENTS),
            "overview": {
                "equity": pipe["analytics"]["analytics"]["equity"],
                "leverage": pipe["analytics"]["analytics"]["leverage"],
                "var_95": pipe["analytics"]["analytics"]["var_95"],
                "es_95": pipe["analytics"]["analytics"]["expected_shortfall_95"],
                "max_drawdown": pipe["analytics"]["analytics"]["maximum_drawdown"],
                "limits_state": pipe["limits"]["state"],
                "diversification_ratio": pipe["analytics"]["diversification"]["ratio"],
                "committee_action": pipe["committee"]["synthesis"]["final_recommendation"],
            },
            "factor_exposure": pipe["analytics"]["factor_exposure"],
            "sector_exposure": pipe["analytics"]["sector_exposure"],
            "stress_dashboard": pipe["scenarios"]["stress_dashboard"],
            "liquidity_dashboard": pipe["scenarios"]["liquidity_dashboard"],
            "expected_shortfall_dashboard": pipe["scenarios"]["expected_shortfall_dashboard"],
            "labels": {
                "PAPER_RESEARCH_ONLY": True,
                "NOT_INVESTMENT_ADVICE": True,
                "NOT_REGULATORY_GRADE_RISK": True,
                "NO_BROKER_CONNECTIVITY": True,
                "NO_ORDER_EXECUTION": True,
                "NO_LIVE_TRADING": True,
            },
            **AUTHORITY_VALUES,
        }

    def evidence_bundle(self) -> dict[str, Any]:
        return {
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

    def refuse_live(self) -> dict[str, Any]:
        return self.security.refuse_live()

    def security_scan(self) -> dict[str, Any]:
        return self.security.full_scan()

    def threat_model(self) -> dict[str, Any]:
        return self.security.threat_model()

    def certify(self) -> dict[str, Any]:
        from saathi.platform.tg.portfolio_risk.certification import certify_portfolio_risk
        return certify_portfolio_risk(self)


_default: PortfolioRiskService | None = None


def default_portfolio_risk() -> PortfolioRiskService:
    global _default
    if _default is None:
        _default = PortfolioRiskService()
    return _default


def reset_portfolio_risk_for_tests(db_path: str | Path | None = None) -> PortfolioRiskService:
    global _default
    if _default is not None:
        try:
            _default.store.close()
        except Exception:
            pass
    _default = PortfolioRiskService(db_path=db_path)
    return _default
