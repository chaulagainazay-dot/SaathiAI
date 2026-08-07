"""M248–M255 Institutional Investment Intelligence service facade.

PAPER ONLY. NO BROKER. NO API KEYS. NO LIVE TRADING.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from saathi.platform.tg.intelligence.backtest_v2 import BacktestEngineV2
from saathi.platform.tg.intelligence.committee import InvestmentCommittee
from saathi.platform.tg.intelligence.explainable import ExplainableInvestmentAI
from saathi.platform.tg.intelligence.models import (
    AUTHORITY_VALUES,
    ENGINE_VERSION,
    II_POSTURE,
    LLM_BOUNDARY,
    MAX_STATE,
    SCHEMA_VERSION,
    TERMINAL_STATEMENTS,
    TERMINAL_VERDICT,
)
from saathi.platform.tg.intelligence.monte_carlo import MonteCarloRiskEngine
from saathi.platform.tg.intelligence.portfolio_engine import (
    DEFAULT_PAPER_PORTFOLIO,
    PortfolioIntelligenceEngine,
)
from saathi.platform.tg.intelligence.security import IntelligenceSecurity
from saathi.platform.tg.intelligence.store import IntelligenceStore, _uid, evidence_hash
from saathi.platform.tg.intelligence.strategy_registry import StrategyRegistryEngine
from saathi.platform.tg.intelligence.walk_forward_v2 import WalkForwardEngine


class IntelligenceError(Exception):
    def __init__(self, code: str, message: str):
        self.code = code
        self.message = message
        super().__init__(f"{code}: {message}")


class InstitutionalIntelligenceService:
    def __init__(self, db_path: str | Path | None = None, repo_root: Path | None = None):
        self.store = IntelligenceStore(db_path)
        self.repo_root = Path(repo_root) if repo_root else Path(__file__).resolve().parents[4]
        self.strategies = StrategyRegistryEngine()
        self.portfolio = PortfolioIntelligenceEngine()
        self.backtester = BacktestEngineV2()
        self.walk_forward = WalkForwardEngine()
        self.monte_carlo = MonteCarloRiskEngine()
        self.explainer = ExplainableInvestmentAI()
        self.committee = InvestmentCommittee()
        self.security = IntelligenceSecurity(self.repo_root)
        self.bootstrap()

    def bootstrap(self) -> None:
        if not self.store.list_watchlists():
            self.store.upsert_watchlist("core_paper", ["SPY", "QQQ", "EFA", "TLT", "GLD"])
            self.store.upsert_watchlist("research", ["AAPL", "MSFT", "NVDA", "AMZN"])
        if not self.store.list_alerts(limit=1):
            self.store.add_alert(
                "system",
                "info",
                "Institutional intelligence engine online (paper only)",
                {"milestones": "M248-M255"},
            )

    def posture(self) -> dict[str, Any]:
        return {
            **II_POSTURE,
            "schema_version": SCHEMA_VERSION,
            "engine_version": ENGINE_VERSION,
            "milestones": "M248-M255",
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
                "strategy_registry": True,
                "portfolio_intelligence": True,
                "backtesting_v2": True,
                "walk_forward": True,
                "monte_carlo": True,
                "explainable_ai": True,
                "investment_committee": True,
                "command_center": True,
            },
            "limitations": [
                "No live broker connectivity",
                "No live market data dependency",
                "Synthetic/offline bars used when historical sets absent",
                "Committee agents are deterministic specialists, not external LLMs with live data",
                "VaR/ES are research metrics, not regulatory capital figures",
                "Single-host SQLite intelligence store",
            ],
            **AUTHORITY_VALUES,
        }

    # ── M248 ──────────────────────────────────────────────────────────────
    def list_strategies(self, category: str | None = None) -> dict[str, Any]:
        return self.strategies.list_strategies(category)

    def get_strategy(self, strategy_id: str) -> dict[str, Any]:
        s = self.strategies.get(strategy_id)
        if not s:
            return {"ok": False, "code": "STRATEGY_NOT_FOUND", "strategy_id": strategy_id, **AUTHORITY_VALUES}
        return {"ok": True, "strategy": s, **AUTHORITY_VALUES}

    def strategy_categories(self) -> dict[str, Any]:
        return self.strategies.categories()

    def strategy_run(
        self,
        strategy_id: str,
        bars: list[dict[str, float]] | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.strategies.run_signal(strategy_id, bars=bars, params=params)
        self.store.audit("strategy.run", subject=strategy_id, detail={"ok": result.get("ok")})
        return result

    # ── M249 ──────────────────────────────────────────────────────────────
    def portfolio_overview(self, portfolio: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.portfolio.analyze(portfolio)

    def portfolio_risk(self, portfolio: dict[str, Any] | None = None) -> dict[str, Any]:
        return self.portfolio.risk_report(portfolio)

    def portfolio_report(self, portfolio: dict[str, Any] | None = None) -> dict[str, Any]:
        overview = self.portfolio.analyze(portfolio)
        risk = self.portfolio.risk_report(portfolio)
        return {
            "title": "Paper Portfolio Institutional Report",
            "generated_at": time.time(),
            "overview": overview,
            "risk": risk,
            "disclaimer": "SIMULATED — PAPER ONLY — NOT REAL MONEY",
            **AUTHORITY_VALUES,
        }

    def analytics(self, portfolio: dict[str, Any] | None = None) -> dict[str, Any]:
        o = self.portfolio.analyze(portfolio)
        return {
            "allocation": o["allocation"],
            "diversification": o["diversification"],
            "concentration": o["concentration"],
            "pnl": {
                "unrealised": o["unrealised_pnl"],
                "realised": o["realised_pnl"],
                "total": o["total_pnl"],
            },
            "risk_metrics": {
                "beta": o["portfolio_beta"],
                "volatility": o["volatility_annualized"],
                "sharpe": o["sharpe_ratio"],
                "sortino": o["sortino_ratio"],
                "max_drawdown": o["maximum_drawdown"],
                "var": o["var"],
            },
            "exposures": {
                "sector": o["sector_exposure"],
                "geographic": o["geographic_exposure"],
                "asset_class": o["asset_class_exposure"],
            },
            "correlation": o["correlation"],
            **AUTHORITY_VALUES,
        }

    # ── M250 ──────────────────────────────────────────────────────────────
    def backtest(self, strategy_id: str = "tf_dual_ma", **kwargs: Any) -> dict[str, Any]:
        result = self.backtester.run(strategy_id, **kwargs)
        if result.get("ok"):
            rid = self.store.save_run(
                "ii_backtests",
                strategy_id=strategy_id,
                result=result,
                evidence_hash=result.get("evidence_hash"),
            )
            result["run_id"] = rid
            self.store.audit("backtest.run", subject=strategy_id, detail={"run_id": rid})
        return result

    def backtest_compare(self, strategy_ids: list[str] | None = None, **kwargs: Any) -> dict[str, Any]:
        return self.backtester.compare(strategy_ids, **kwargs)

    def list_backtests(self, limit: int = 20) -> dict[str, Any]:
        rows = self.store.fetchall(
            "SELECT id, strategy_id, evidence_hash, created_at FROM ii_backtests ORDER BY created_at DESC LIMIT ?",
            (limit,),
        )
        return {"count": len(rows), "runs": rows, **AUTHORITY_VALUES}

    # ── M251 ──────────────────────────────────────────────────────────────
    def run_walk_forward(self, strategy_id: str = "tf_dual_ma", **kwargs: Any) -> dict[str, Any]:
        result = self.walk_forward.run(strategy_id, **kwargs)
        if result.get("ok"):
            rid = self.store.save_run(
                "ii_walk_forwards",
                strategy_id=strategy_id,
                result=result,
                evidence_hash=result.get("evidence_hash"),
            )
            result["run_id"] = rid
            self.store.audit("walk_forward.run", subject=strategy_id, detail={"run_id": rid})
        return result

    # ── M252 ──────────────────────────────────────────────────────────────
    def run_monte_carlo(self, returns: list[float] | None = None, **kwargs: Any) -> dict[str, Any]:
        result = self.monte_carlo.simulate(returns, **kwargs)
        if result.get("ok"):
            rid = self.store.save_run(
                "ii_simulations",
                kind="monte_carlo",
                seed=int(kwargs.get("seed", 42)),
                result=result,
                evidence_hash=result.get("evidence_hash"),
            )
            result["run_id"] = rid
            self.store.audit("monte_carlo.run", detail={"run_id": rid, "seed": kwargs.get("seed", 42)})
        return result

    # ── M253 ──────────────────────────────────────────────────────────────
    def explain(
        self,
        instrument: str = "SPY",
        action: str | None = None,
        strategy_id: str | None = None,
        context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        context = context or {}
        signal = None
        if strategy_id:
            run = self.strategies.run_signal(strategy_id)
            signal = run.get("signal")
            if action is None and signal:
                action = signal.get("action")
        action = action or "HOLD"
        port = self.portfolio.analyze()
        explanation = self.explainer.explain(
            instrument=instrument,
            action=action,
            strategy_id=strategy_id,
            signal=signal,
            portfolio_context=port,
            market_context=context,
        )
        self.store.audit("explain", subject=instrument, detail={"action": action})
        return explanation

    # ── M254 ──────────────────────────────────────────────────────────────
    def committee_review(
        self,
        instrument: str = "SPY",
        context: dict[str, Any] | None = None,
        *,
        persist: bool = True,
    ) -> dict[str, Any]:
        context = context or {}
        review = self.committee.review(instrument=instrument, context=context)
        explanation = self.explainer.explain(
            instrument=instrument,
            action=review["final_recommendation"],
            market_context={
                **context,
                "confidence": review["committee_confidence"],
                "reason": f"committee_{review['consensus'].lower()}",
            },
        )
        result = {
            **review,
            "explanation": explanation,
        }
        if persist:
            did = self.store.save_decision(
                instrument=instrument,
                action=review["final_recommendation"],
                confidence=float(review["committee_confidence"]),
                explanation=explanation,
                committee=review,
            )
            result["decision_id"] = did
            self.store.audit("committee.review", subject=instrument, detail={"decision_id": did})
            self.store.add_alert(
                "committee",
                "info",
                f"Committee {review['final_recommendation']} on {instrument} ({review['consensus']})",
                {"decision_id": did},
            )
        return result

    # ── M255 Command Center ───────────────────────────────────────────────
    def dashboard(self) -> dict[str, Any]:
        strategies = self.list_strategies()
        portfolio = self.portfolio_overview()
        risk = self.portfolio_risk()
        decisions = self.store.list_decisions(limit=10)
        alerts = self.store.list_alerts(limit=10)
        watchlists = self.store.list_watchlists()
        timeline = self.store.list_audit(limit=20)
        conf_trend = [
            {"t": d["created_at"], "confidence": d["confidence"], "action": d["action"], "instrument": d["instrument"]}
            for d in reversed(decisions)
        ]
        return {
            "title": "Portfolio Command Center",
            "sections": {
                "strategy_library": {
                    "count": strategies["count"],
                    "categories": strategies["categories"],
                },
                "portfolio_overview": {
                    "equity": portfolio["allocation"]["equity"],
                    "cash": portfolio["allocation"]["cash"],
                    "unrealised_pnl": portfolio["unrealised_pnl"],
                    "realised_pnl": portfolio["realised_pnl"],
                },
                "risk_dashboard": risk["risk_summary"],
                "performance_dashboard": {
                    "sharpe": portfolio["sharpe_ratio"],
                    "sortino": portfolio["sortino_ratio"],
                    "max_drawdown": portfolio["maximum_drawdown"],
                    "volatility": portfolio["volatility_annualized"],
                },
                "backtests": self.list_backtests(limit=5),
                "monte_carlo": {"status": "available", "endpoint": "simulations/monte-carlo"},
                "walk_forward": {"status": "available", "endpoint": "simulations/walk-forward"},
                "investment_committee": {"status": "available", "roles": 6},
                "explainable_recommendations": {"status": "available"},
                "historical_decisions": decisions,
                "confidence_trends": conf_trend,
                "watchlists": watchlists,
                "alerts": alerts,
                "decision_timeline": timeline,
            },
            "ui_route": "/trading/intelligence",
            "api_prefix": "/api/v1/platform/tg/intelligence",
            "broker_controls": False,
            "credential_controls": False,
            "connection_controls": False,
            "planning_and_analysis_only": True,
            **AUTHORITY_VALUES,
        }

    def decisions(self, limit: int = 50) -> dict[str, Any]:
        return {"decisions": self.store.list_decisions(limit=limit), **AUTHORITY_VALUES}

    def watchlists(self) -> dict[str, Any]:
        return {"watchlists": self.store.list_watchlists(), **AUTHORITY_VALUES}

    def upsert_watchlist(self, name: str, symbols: list[str]) -> dict[str, Any]:
        wid = self.store.upsert_watchlist(name, symbols)
        self.store.audit("watchlist.upsert", subject=name, detail={"symbols": symbols})
        return {"ok": True, "id": wid, "name": name, "symbols": symbols, **AUTHORITY_VALUES}

    def alerts(self, limit: int = 50) -> dict[str, Any]:
        return {"alerts": self.store.list_alerts(limit=limit), **AUTHORITY_VALUES}

    def timeline(self, limit: int = 100) -> dict[str, Any]:
        return {"events": self.store.list_audit(limit=limit), **AUTHORITY_VALUES}

    def confidence_trends(self, limit: int = 50) -> dict[str, Any]:
        dec = self.store.list_decisions(limit=limit)
        trend = [
            {
                "t": d["created_at"],
                "confidence": d["confidence"],
                "action": d["action"],
                "instrument": d["instrument"],
            }
            for d in reversed(dec)
        ]
        return {"trend": trend, "count": len(trend), **AUTHORITY_VALUES}

    def default_portfolio(self) -> dict[str, Any]:
        return dict(DEFAULT_PAPER_PORTFOLIO)

    def refuse_broker(self, target: str = "") -> dict[str, Any]:
        return self.security.refuse_broker_connect(target)

    def refuse_credentials(self, value: str | None = None) -> dict[str, Any]:
        return self.security.refuse_credentials(value)

    def refuse_order(self) -> dict[str, Any]:
        return self.security.refuse_order()

    def security_scan(self) -> dict[str, Any]:
        return self.security.full_scan()

    def certify(self) -> dict[str, Any]:
        """Produce certification verdict for institutional intelligence package."""
        strategies = self.list_strategies()
        cats = {s["category"] for s in strategies["strategies"]}
        port = self.portfolio_overview()
        bt = self.backtest("tf_dual_ma", seed=42)
        bt2 = self.backtest("tf_dual_ma", seed=42)
        wf = self.run_walk_forward("tf_dual_ma", seed=42)
        mc1 = self.run_monte_carlo(n_simulations=100, seed=7)
        mc2 = self.run_monte_carlo(n_simulations=100, seed=7)
        committee = self.committee_review("SPY", context={"trend": "up", "regime": "risk_on"}, persist=True)
        explanation = self.explain("SPY", strategy_id="tf_dual_ma")
        sec = self.security_scan()
        broker_block = self.refuse_broker("alpaca")
        cred_block = self.refuse_credentials("secret")
        order_block = self.refuse_order()

        hard_ok = (
            strategies["count"] >= 11
            and len(cats) >= 11
            and port["paper_only"] is True
            and bt.get("ok") is True
            and bt.get("evidence_hash") == bt2.get("evidence_hash")
            and wf.get("ok") is True
            and wf.get("invariants", {}).get("optimized_on_evaluation_set") is False
            and mc1.get("ok") is True
            and mc1.get("evidence_hash") == mc2.get("evidence_hash")
            and committee.get("final_recommendation")
            and explanation.get("investor_readable") is True
            and sec.get("ok") is True
            and broker_block.get("ok") is False
            and cred_block.get("ok") is False
            and order_block.get("ok") is False
            and AUTHORITY_VALUES["LIVE_TRADING_AUTHORIZED"] is False
        )
        verdict = TERMINAL_VERDICT if hard_ok else "M248_M255_IMPLEMENTED_NOT_VERIFIED"
        result = {
            "verdict": verdict,
            "hard_gates_pass": hard_ok,
            "checks": {
                "strategy_count": strategies["count"],
                "categories_covered": sorted(cats),
                "portfolio_paper_only": port["paper_only"],
                "backtest_deterministic": bt.get("evidence_hash") == bt2.get("evidence_hash"),
                "walk_forward_no_test_opt": wf.get("invariants", {}).get("optimized_on_evaluation_set") is False,
                "monte_carlo_repeatable": mc1.get("evidence_hash") == mc2.get("evidence_hash"),
                "committee_synthesised": bool(committee.get("final_recommendation")),
                "explanation_human_readable": explanation.get("investor_readable") is True,
                "security_ok": sec.get("ok"),
                "broker_refused": broker_block.get("ok") is False,
                "credentials_refused": cred_block.get("ok") is False,
                "orders_refused": order_block.get("ok") is False,
            },
            "statements": list(TERMINAL_STATEMENTS),
            "max_state": MAX_STATE,
            **AUTHORITY_VALUES,
        }
        eh = evidence_hash(result)
        result["evidence_hash"] = eh
        self.store.execute(
            """INSERT INTO ii_certifications(id, verdict, result_json, evidence_hash, created_at)
               VALUES(?,?,?,?,?)""",
            (_uid("cert"), verdict, json.dumps(result, default=str), eh, time.time()),
        )
        self.store.audit("certify", detail={"verdict": verdict, "hard_ok": hard_ok})
        return result


_default: InstitutionalIntelligenceService | None = None


def default_intelligence() -> InstitutionalIntelligenceService:
    global _default
    if _default is None:
        _default = InstitutionalIntelligenceService()
    return _default


def reset_intelligence_for_tests(db_path: str | Path | None = None) -> InstitutionalIntelligenceService:
    global _default
    if _default is not None:
        try:
            _default.store.close()
        except Exception:
            pass
    _default = InstitutionalIntelligenceService(db_path=db_path)
    return _default
