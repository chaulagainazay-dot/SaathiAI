"""Scenario and stress dashboards (research-only)."""
from __future__ import annotations

import time
from typing import Any

from saathi.platform.tg.portfolio_risk.models import AUTHORITY_VALUES
from saathi.platform.tg.portfolio_risk.storage import PortfolioRiskStore, evidence_hash, _uid


SCENARIOS = [
    {"name": "equity_drawdown_10", "shock": {"equity_etf": -0.10, "bond_etf": 0.02, "commodity_etf": 0.01}},
    {"name": "equity_drawdown_20", "shock": {"equity_etf": -0.20, "bond_etf": 0.03, "commodity_etf": 0.02}},
    {"name": "rates_up", "shock": {"bond_etf": -0.08, "equity_etf": -0.04, "commodity_etf": -0.02}},
    {"name": "risk_off_correlation", "shock": {"equity_etf": -0.12, "bond_etf": -0.03, "commodity_etf": 0.05}},
    {"name": "vol_spike", "shock": {"_vol_mult": 2.0, "equity_etf": -0.06}},
    {"name": "liquidity_stress", "shock": {"equity_etf": -0.08, "_slippage_extra": 0.01}},
]


class ScenarioEngine:
    def __init__(self, store: PortfolioRiskStore):
        self.store = store

    def run(self, analytics: dict[str, Any]) -> dict[str, Any]:
        positions = analytics.get("positions") or []
        equity = float((analytics.get("analytics") or {}).get("equity") or 1.0)
        cash = float((analytics.get("analytics") or {}).get("cash") or 0.0)

        results = []
        for sc in SCENARIOS:
            shock = sc["shock"]
            pnl = 0.0
            contrib = []
            for pos in positions:
                ac = pos.get("asset_class", "equity_etf")
                # map
                key = ac if ac in shock else (
                    "equity_etf" if "equity" in ac else (
                        "bond_etf" if "bond" in ac else (
                            "commodity_etf" if "commodity" in ac else "equity_etf"
                        )
                    )
                )
                sh = float(shock.get(key, shock.get("equity_etf", 0.0)))
                mv = float(pos.get("market_value", 0))
                loss = mv * sh
                pnl += loss
                contrib.append({"symbol": pos.get("symbol"), "shock": sh, "pnl": round(loss, 4)})
            extra_slip = float(shock.get("_slippage_extra", 0)) * abs(
                sum(float(p.get("market_value", 0)) for p in positions)
            )
            pnl -= extra_slip
            new_equity = equity + pnl
            mdd_proxy = max(0.0, -pnl / equity) if equity else 0.0
            es_proxy = max(0.0, -pnl / equity) * 1.1 if equity else 0.0
            results.append({
                "name": sc["name"],
                "portfolio_pnl": round(pnl, 4),
                "portfolio_loss_pct": round(-pnl / equity, 6) if equity else 0.0,
                "equity_after": round(new_equity, 4),
                "drawdown_proxy": round(mdd_proxy, 6),
                "es_proxy": round(es_proxy, 6),
                "contributions": contrib,
                "cash_unchanged": cash,
            })

        # Dashboards
        stress_dashboard = {
            "worst_scenario": min(results, key=lambda r: r["portfolio_pnl"]) if results else None,
            "scenarios": results,
        }
        liq = {
            "liquidity_stress_loss": next((r["portfolio_pnl"] for r in results if r["name"] == "liquidity_stress"), 0),
            "note": "Simulated liquidity shock — not live order-book depth",
        }
        es_dash = {
            "baseline_es_95": (analytics.get("analytics") or {}).get("expected_shortfall_95"),
            "scenario_es_proxies": {r["name"]: r["es_proxy"] for r in results},
            "label": "RESEARCH_ES_NOT_REGULATORY",
        }

        out = {
            "ok": True,
            "schema": "M296_SCENARIO_ENGINE",
            "stress_dashboard": stress_dashboard,
            "liquidity_dashboard": liq,
            "expected_shortfall_dashboard": es_dash,
            "scenario_count": len(results),
            **AUTHORITY_VALUES,
        }
        eh = evidence_hash(out)
        out["evidence_hash"] = eh
        sid = _uid("scn")
        self.store.execute(
            "INSERT INTO pr_scenarios(id, name, result_json, evidence_hash, created_at) VALUES(?,?,?,?,?)",
            (sid, "batch", __import__("json").dumps(out, sort_keys=True, default=str), eh, time.time()),
        )
        out["scenario_run_id"] = sid
        return out
