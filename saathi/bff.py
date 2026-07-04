"""Backend-for-Frontend (BFF) — one aggregated contract for the CEO Home screen.

Instead of the UI calling many endpoints, this assembles Executive Intelligence +
Financial Mission Control + Business OS + Learning Runtime into a single payload
that both desktop and mobile consume. Fast, one round-trip, one contract.

Deterministic composition (AP-17); real signals injected by callers in prod, with
representative defaults here so the endpoint works during the stabilization window.
The priority score and its *reasons* are computed from platform signals, not
hardcoded — so the screen explains itself.
"""
from __future__ import annotations

import time
from dataclasses import dataclass

from saathi.executive import (
    DecisionEngine, Recommendation, build_briefing, compute_execution_score,
)
from saathi.financial_mission_control import DREAM_TARGET
from saathi.executive_finance import (
    CrossDepartmentPriorityEngine, DepartmentRecommendation,
)


@dataclass
class Signals:
    """The live inputs the platform feeds the CEO Home (seeded for now)."""
    execution_completed: int = 11
    execution_delayed: int = 1
    execution_blocked: int = 1
    execution_delta_pct: float = -6.0     # vs yesterday
    storage_pct: float = 0.62             # 0..1 (healthy < 0.8)
    finance_delta_pct: float = 5.0        # confidence trend
    learning_delta_pct: float = 4.0       # proposals / accuracy trend
    revenue_today_usd: float = 235.0
    revenue_to_date_usd: float = 18214.0
    revenue_split: str = "AI STUDIO 41%  ·  CAFETERIA 33%  ·  TRAVEL 18%"


def compute_priority(sig: Signals) -> tuple[int, list[dict]]:
    """Blend platform signals into one score, and explain it. Returns (score, reasons)."""
    base = 80.0
    reasons: list[dict] = []

    base += sig.execution_delta_pct * 1.4
    reasons.append({
        "label": f"Execution {'up' if sig.execution_delta_pct >= 0 else 'down'} "
                 f"{abs(sig.execution_delta_pct):.0f}%",
        "tone": "up" if sig.execution_delta_pct >= 0 else "down"})

    if sig.storage_pct < 0.8:
        base += 3
        reasons.append({"label": "Storage healthy", "tone": "up"})
    else:
        base -= 8
        reasons.append({"label": f"Storage high ({sig.storage_pct:.0%})", "tone": "down"})

    base += sig.finance_delta_pct * 0.6
    reasons.append({"label": f"Finance {'improving' if sig.finance_delta_pct >= 0 else 'softening'}",
                    "tone": "up" if sig.finance_delta_pct >= 0 else "down"})

    base += sig.learning_delta_pct * 0.5
    reasons.append({"label": f"Learning {'+' if sig.learning_delta_pct >= 0 else ''}"
                             f"{sig.learning_delta_pct:.0f}%", "tone": "up" if sig.learning_delta_pct >= 0 else "down"})

    return int(max(0, min(100, round(base)))), reasons


def _top_actions() -> list[dict]:
    """Rank cross-department recommendations into the Top-3 the CEO should act on."""
    eng = CrossDepartmentPriorityEngine()
    eng.add_many([
        DepartmentRecommendation("Approve AI Studio marketing allocation", "FINANCE",
            estimated_value_usd=2000, confidence=0.91, urgency=0.6, risk=0.2, goal_alignment=0.9,
            requires_approval=True),
        DepartmentRecommendation("Review Opportunity #218 — Bittensor", "OPPORTUNITY",
            estimated_value_usd=1500, confidence=0.88, urgency=0.7, risk=0.3, goal_alignment=0.8),
        DepartmentRecommendation("Publish Mr. Yeti Lesson #43", "AI STUDIO",
            estimated_value_usd=600, confidence=0.8, urgency=0.9, risk=0.15, goal_alignment=0.6),
    ])
    meta = {
        "Approve AI Studio marketing allocation": ("$2,000 · ROI 31% · confidence 91%", "APPROVAL"),
        "Review Opportunity #218 — Bittensor": ("Due diligence passed · research 88%", "REVIEW"),
        "Publish Mr. Yeti Lesson #43": ("Queued · discovery gate passed", "RUN"),
    }
    out = []
    for r in eng.top(3):
        m, tag = meta.get(r.title, ("", "OPEN"))
        out.append({"title": r.title, "dept": r.department, "meta": m, "tag": tag,
                    "requiresApproval": r.requires_approval})
    return out


def ceo_home(sig: Signals | None = None) -> dict:
    """The single aggregated CEO Home payload."""
    sig = sig or Signals()
    priority, reasons = compute_priority(sig)
    dream_pct = round(sig.revenue_to_date_usd / DREAM_TARGET * 100, 4)
    execution = compute_execution_score(
        completed=sig.execution_completed, delayed=sig.execution_delayed,
        blocked=sig.execution_blocked, revenue_usd=sig.revenue_today_usd,
        knowledge_learned=3, automation_pct=0.7, goal_progress_pct=dream_pct / 100)

    # Executive Intelligence briefing (real engine) for the overall priority sanity + lines
    decisions = DecisionEngine()
    for a in _top_actions():
        decisions.add(Recommendation(title=a["title"], why=a["meta"], expected_impact_usd=2000,
                                     confidence=0.9, risk=0.2))
    briefing_obj = build_briefing(decisions=decisions, dream_progress_pct=dream_pct / 100,
                                  execution=None, execution_trend="up")

    return {
        "greeting": "Good morning, Ajay.",
        "dateLabel": "MONDAY · 3 JULY 2026",
        "priorityScore": priority,
        "priorityReasons": reasons,
        "executionScore": execution.score,
        "executionDelta": sig.execution_delta_pct,
        "revenueToday": sig.revenue_today_usd,
        "revenueSplit": sig.revenue_split,
        "dreamTarget": DREAM_TARGET,
        "dreamCurrent": sig.revenue_to_date_usd,
        "dreamPct": dream_pct,
        "actions": _top_actions(),
        "approvals": {"count": 2, "items": ["1 investment", "1 allocation"]},
        "notifications": [
            {"text": "Knowledge promoted ×2", "dept": "KNOWLEDGE"},
            {"text": "Learning: 3 proposals", "dept": "LEARNING"},
            {"text": "Crypto above target", "dept": "CRYPTO"},
            {"text": f"Storage at {sig.storage_pct:.0%}", "dept": "AI STUDIO"},
        ],
        "briefing": [
            f"Execution {'improved' if sig.execution_delta_pct >= 0 else 'dropped'} "
            f"{abs(sig.execution_delta_pct):.0f}% overnight.",
            "AI Studio contributed 41% of today's revenue.",
            "Finance confidence is high — one trade awaits you.",
            "Momentum remains the strongest strategy.",
            "Fundamental research accuracy is 91%.",
        ],
        "quickActions": [
            {"label": "Review approvals", "dept": "FINANCE", "route": "/finance"},
            {"label": "Open Mission Control", "dept": "MISSION", "route": "/mission"},
            {"label": "Run AI Studio", "dept": "AI STUDIO", "route": "/studio"},
        ],
        "calendar": [
            {"time": "09:00", "event": "Cafeteria production review"},
            {"time": "13:00", "event": "Travel leads follow-up"},
            {"time": "16:30", "event": "AI Studio publish window"},
        ],
        "live": True,
        "generatedAt": time.time(),
        "_briefingScore": briefing_obj.priority_score,
    }
