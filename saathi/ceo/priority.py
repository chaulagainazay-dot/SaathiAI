"""M14 priority engine — deterministic + fully inspectable.

Every score is the sum of transparent, weighted factors with a per-factor
explanation. No opaque LLM score controls execution; an LLM may only *recommend*
weight adjustments, which remain visible and overridable.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from saathi.ceo.models import PRIORITY_WEIGHTS


@dataclass
class PriorityInput:
    revenue_impact: float = 0.0        # 0..1
    customer_impact: float = 0.0       # 0..1
    strategic_alignment: float = 0.0   # 0..1
    risk_reduction: float = 0.0        # 0..1
    dependency_blocking: bool = False
    deadline_days: float | None = None
    low_risk: bool = False
    provider_unavailable: bool = False
    high_effort: bool = False


@dataclass
class PriorityScore:
    score: int
    factors: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"score": self.score, "factors": self.factors}


def score(inp: PriorityInput, weights: dict | None = None) -> PriorityScore:
    """Deterministic weighted score with an explanation for every applied factor."""
    w = {**PRIORITY_WEIGHTS, **(weights or {})}
    factors: list[dict] = []
    total = 0.0

    def add(label: str, amount: float, why: str):
        nonlocal total
        if amount:
            total += amount
            factors.append({"label": label, "points": round(amount, 1), "why": why})

    add("Revenue impact", inp.revenue_impact * w["revenue_impact"],
        f"{int(inp.revenue_impact * 100)}% revenue weight")
    add("Customer impact", inp.customer_impact * w["customer_impact"],
        f"{int(inp.customer_impact * 100)}% customer weight")
    add("Strategic alignment", inp.strategic_alignment * w["strategic_alignment"],
        f"{int(inp.strategic_alignment * 100)}% strategic")
    add("Risk reduction", inp.risk_reduction * w["risk_reduction"],
        f"{int(inp.risk_reduction * 100)}% risk reduction")
    if inp.dependency_blocking:
        add("Blocks other work", w["dependency_blocking"], "unblocks dependent items")
    if inp.deadline_days is not None and inp.deadline_days <= 7:
        urgency = w["deadline_urgency"] * (1 - inp.deadline_days / 7)
        add("Deadline urgency", urgency, f"deadline in {inp.deadline_days:.0f} days")
    if inp.low_risk:
        add("Low implementation risk", w["low_risk_bonus"], "safe/reversible")
    if inp.provider_unavailable:
        add("Required provider unavailable", w["provider_unavailable_penalty"],
            "cannot execute until provider configured")
    if inp.high_effort:
        add("High effort", w["high_effort_penalty"], "large implementation cost")

    return PriorityScore(score=int(max(0, min(100, round(total)))), factors=factors)


def rank(items: list[tuple[str, PriorityInput]], weights: dict | None = None) -> list[dict]:
    """Rank (id, input) pairs; each result carries its full explanation."""
    scored = [{"id": iid, **score(inp, weights).to_dict()} for iid, inp in items]
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored
