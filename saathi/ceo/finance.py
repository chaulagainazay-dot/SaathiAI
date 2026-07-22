"""M14 Financial Command Center — actual / estimated / forecast kept SEPARATE.

An estimate is never returned as an actual. Personal and business scopes are
explicitly labeled and never merged. Forecasts reuse executive.forecast_linear.
"""
from __future__ import annotations

from saathi.ceo.models import FinancialState


def financial_summary(store, owner: str) -> dict:
    """Aggregate financial entries by state — actual/estimated/forecast/unknown
    are reported separately, never summed into one 'revenue' number."""
    entries = store.financial_entries(owner)
    by_state = {s.value: {"revenue": 0.0, "expense": 0.0, "count": 0}
                for s in FinancialState}
    for e in entries:
        bucket = by_state.setdefault(e["state"], {"revenue": 0.0, "expense": 0.0, "count": 0})
        if e["kind"] == "revenue":
            bucket["revenue"] += e["amount_usd"]
        elif e["kind"] == "expense":
            bucket["expense"] += e["amount_usd"]
        bucket["count"] += 1

    actual = by_state.get("actual", {})
    return {
        "by_state": by_state,
        "actual_revenue": round(actual.get("revenue", 0.0), 2),
        "actual_expense": round(actual.get("expense", 0.0), 2),
        "actual_net": round(actual.get("revenue", 0.0) - actual.get("expense", 0.0), 2),
        "note": ("Actuals only. Estimated and forecast figures are reported "
                 "separately and are NEVER counted as actual revenue."),
        "has_actuals": actual.get("count", 0) > 0,
    }


def forecast_revenue(history: list[float], horizon_days: int) -> dict:
    """Linear forecast (reuses executive.forecast_linear). Clearly labeled as a
    projection with assumptions — never a guaranteed outcome."""
    from saathi.executive import forecast_linear
    if len(history) < 2:
        return {"available": False, "reason": "need >=2 historical points",
                "state": FinancialState.UNKNOWN.value}
    f = forecast_linear(history, horizon_days)
    return {"available": True, "state": FinancialState.FORECAST.value,
            "projected": getattr(f, "projected", None) if hasattr(f, "projected") else None,
            "model": "linear", "horizon_days": horizon_days,
            "assumptions": ["trend continues", "no external shock"],
            "confidence": "low", "raw": f.__dict__ if hasattr(f, "__dict__") else str(f)}


def budget_variance(store, budget_id: str) -> dict:
    b = store.get_budget(budget_id)
    if not b:
        raise KeyError(budget_id)
    remaining = b["approved_usd"] - b["actual_usd"] - b["committed_usd"]
    return {
        "approved": b["approved_usd"], "committed": b["committed_usd"],
        "actual": b["actual_usd"], "forecast": b["forecast_usd"],
        "remaining": round(remaining, 2),
        "variance": round(b["approved_usd"] - b["actual_usd"], 2),
        "over_budget": b["actual_usd"] > b["approved_usd"],
        "warning": b["actual_usd"] >= b["approved_usd"] * b["warn_fraction"],
    }
