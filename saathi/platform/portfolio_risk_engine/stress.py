"""Deterministic stress scenarios over canonical positions (no LLM)."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from saathi.platform.fund_ledger.money import D, q_money
from saathi.platform.portfolio_risk_engine.metrics import portfolio_metrics


@dataclass(frozen=True)
class RiskScenario:
    scenario_id: str
    name: str
    # uniform mark shock for all positions, or per-symbol overrides
    market_shock: Decimal = Decimal("0")  # e.g. -0.05
    symbol_shocks: tuple[tuple[str, Decimal], ...] = ()

    def to_public(self) -> dict:
        return {
            "scenario_id": self.scenario_id,
            "name": self.name,
            "market_shock": str(self.market_shock),
            "symbol_shocks": {k: str(v) for k, v in self.symbol_shocks},
        }


DEFAULT_SCENARIOS = (
    RiskScenario("mkt_m5", "market -5%", market_shock=Decimal("-0.05")),
    RiskScenario("mkt_m10", "market -10%", market_shock=Decimal("-0.10")),
    RiskScenario("largest_m15", "largest position -15%", market_shock=Decimal("0")),  # special
    RiskScenario("top3_m10", "top 3 positions -10%", market_shock=Decimal("0")),
)


def apply_scenario(state: dict[str, Any], scenario: RiskScenario) -> dict[str, Any]:
    positions = list(state.get("positions") or [])
    if not positions:
        cash = D(state.get("cash") or "0")
        return {
            "scenario": scenario.to_public(),
            "projected_nav": str(q_money(cash)),
            "loss": "0.00",
            "loss_pct": "0.00",
            "drawdown_proxy": "0.00",
            "metrics": portfolio_metrics({**state, "nav": str(cash), "positions": []}),
        }

    # rank by weight for special scenarios
    ranked = sorted(positions, key=lambda p: D(p.get("weight") or p.get("market_value") or 0), reverse=True)
    largest_sym = ranked[0].get("symbol") if ranked else None
    top3 = {p.get("symbol") for p in ranked[:3]}

    shocked = []
    for p in positions:
        sym = p.get("symbol")
        qty = D(p.get("quantity") or 0)
        # recover mark from mv/qty or avg_cost
        mv = D(p.get("market_value") or 0)
        mark = (mv / qty) if qty != 0 else D(p.get("avg_cost") or 0)
        shock = D(scenario.market_shock)
        for s, sh in scenario.symbol_shocks:
            if s == sym:
                shock = D(sh)
        if scenario.scenario_id == "largest_m15" and sym == largest_sym:
            shock = Decimal("-0.15")
        elif scenario.scenario_id == "top3_m10" and sym in top3:
            shock = Decimal("-0.10")
        elif scenario.scenario_id in ("largest_m15", "top3_m10"):
            shock = Decimal("0")
        new_mark = mark * (Decimal("1") + shock)
        new_mv = q_money(qty * new_mark)
        shocked.append({**p, "market_value": str(new_mv), "mark_stale": False})

    cash = D(state.get("cash") or "0")
    pv = sum((D(p["market_value"]) for p in shocked), Decimal("0"))
    nav = q_money(cash + pv)
    base_nav = D(state.get("nav") or "0")
    loss = q_money(nav - base_nav)
    loss_pct = q_money(loss / base_nav) if base_nav != 0 else Decimal("0")
    proj = {
        **state,
        "cash": str(q_money(cash)),
        "positions": shocked,
        "positions_value": str(q_money(pv)),
        "nav": str(nav),
        "paper_nav": str(nav),
        "exposure": {
            "gross": str(q_money(pv)),
            "net": str(q_money(pv)),
            "long": str(q_money(pv)),
            "short": "0.00",
            "cash_weight": str(q_money(cash / nav) if nav > 0 else Decimal("0")),
        },
    }
    # recompute weights
    for p in shocked:
        mv = D(p["market_value"])
        p["weight"] = str(q_money(mv / nav) if nav > 0 else Decimal("0"))
    return {
        "scenario": scenario.to_public(),
        "projected_nav": str(nav),
        "base_nav": str(q_money(base_nav)),
        "loss": str(loss),
        "loss_pct": str(loss_pct),
        "drawdown_proxy": str(q_money(-loss_pct) if loss_pct < 0 else Decimal("0")),
        "metrics": portfolio_metrics(proj),
        "mode": "PAPER",
    }


def run_default_stress(state: dict[str, Any]) -> list[dict]:
    return [apply_scenario(state, s) for s in DEFAULT_SCENARIOS]
