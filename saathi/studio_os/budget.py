"""M13 cost/budget controls — dry-run estimates + hard stop.

Never silently exceed the configured budget. A generation is refused when it
would push the project over budget; a warning threshold surfaces before that.
"""
from __future__ import annotations

from dataclasses import dataclass

# indicative unit costs (USD) — local providers are free; cloud rows are the
# estimates used for dry-run planning, not billed here.
UNIT_COST = {
    "llm_tokens": 0.000002,      # per token
    "image": 0.0,                # local pillow/ffmpeg = free
    "image_cloud": 0.04,         # per image (cloud estimate)
    "video_sec": 0.0,            # local ffmpeg = free
    "video_sec_cloud": 0.10,     # per second (cloud estimate)
    "tts_char": 0.0,             # local say = free
    "tts_char_cloud": 0.00003,   # per char (cloud estimate)
    "render_sec": 0.0,           # local = free
    "publish_op": 0.0,
}

WARN_FRACTION = 0.8


class BudgetExceeded(Exception):
    pass


@dataclass
class Estimate:
    kind: str
    units: float

    @property
    def cost_usd(self) -> float:
        return round(self.units * UNIT_COST.get(self.kind, 0.0), 6)


def estimate_total(items: list[Estimate]) -> float:
    return round(sum(e.cost_usd for e in items), 6)


def check_and_reserve(store, project_id: str, estimate_cost: float) -> dict:
    """Hard stop: refuse if this cost would exceed the project budget.
    Returns {ok, warn, remaining} or raises BudgetExceeded."""
    p = store.get_project(project_id)
    if not p:
        raise KeyError(project_id)
    budget = p["budget_usd"]
    spent = p["cost_usd"]
    projected = spent + estimate_cost
    if projected > budget:
        raise BudgetExceeded(
            f"budget hard stop: spent ${spent:.4f} + est ${estimate_cost:.4f} "
            f"> budget ${budget:.2f}")
    return {"ok": True, "warn": projected >= budget * WARN_FRACTION,
            "remaining": round(budget - projected, 4)}


def dry_run(items: list[Estimate], budget_usd: float) -> dict:
    total = estimate_total(items)
    return {"estimated_total_usd": total, "budget_usd": budget_usd,
            "within_budget": total <= budget_usd,
            "by_kind": {e.kind: e.cost_usd for e in items}}
