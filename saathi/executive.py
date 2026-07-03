"""Executive Intelligence (M4) — SaathiAI's daily CEO.

Not another subsystem — the layer that makes the existing ones work together:
observe everything → prioritize → predict → recommend → explain why.

Engines built here (deterministic, testable — AP-17):
  * Decision Engine       — recommendations that always answer why / impact / confidence / risk
  * Goal Alignment Engine — every action scored against the $7.9M dream
  * Forecast Engine       — project a metric forward from its trend
  * Execution Score Engine— a daily 0-100 execution score, trended
  * Executive Briefing    — assembles the prioritized "what should I do next" morning brief

Ties into: CEO Dashboard (snapshot), KPI Engine (north stars), Revenue (Dream Meter),
Learning Runtime (evidence for recommendations).
"""
from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Callable

DREAM_TARGET = 7_938_838.98


class Priority(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


# ── Decision Engine ────────────────────────────────────────────────────────
@dataclass
class Recommendation:
    title: str
    why: str                        # evidence, never a black box
    expected_impact_usd: float
    confidence: float               # 0..1
    risk: float                     # 0..1
    cost_usd: float = 0.0
    time_hours: float = 0.0
    goal_contribution: float = 0.0  # fraction of the dream this moves

    @property
    def priority_score(self) -> float:
        """Deterministic: impact × confidence × (1 - risk), net of cost."""
        net = max(0.0, self.expected_impact_usd - self.cost_usd)
        return round(net * self.confidence * (1.0 - self.risk), 2)

    @property
    def priority(self) -> Priority:
        s = self.priority_score
        return Priority.HIGH if s >= 300 else Priority.MEDIUM if s >= 50 else Priority.LOW


class DecisionEngine:
    def __init__(self) -> None:
        self._recs: list[Recommendation] = []

    def add(self, rec: Recommendation) -> None:
        self._recs.append(rec)

    def top(self, n: int = 5) -> list[Recommendation]:
        return sorted(self._recs, key=lambda r: r.priority_score, reverse=True)[:n]


# ── Goal Alignment Engine ──────────────────────────────────────────────────
@dataclass
class Alignment:
    expected_revenue_usd: float
    contribution_pct: float          # of the dream target
    priority: Priority


def align_to_goal(expected_revenue_usd: float, target: float = DREAM_TARGET) -> Alignment:
    """Every action scored: does this move me toward $7,938,838.98?"""
    contribution = round(expected_revenue_usd / target * 100, 4) if target else 0.0
    if expected_revenue_usd >= 500:
        pr = Priority.HIGH
    elif expected_revenue_usd >= 50:
        pr = Priority.MEDIUM
    else:
        pr = Priority.LOW
    return Alignment(expected_revenue_usd, contribution, pr)


# ── Forecast Engine ────────────────────────────────────────────────────────
@dataclass
class Forecast:
    current: float
    horizon_days: int
    projected: float
    probability: float


def forecast_linear(history: list[float], horizon_days: int,
                    probability: float = 0.7) -> Forecast:
    """Project a daily-series metric forward from its average daily change.
    Deterministic and explainable — no opaque model."""
    if len(history) < 2:
        cur = history[-1] if history else 0.0
        return Forecast(cur, horizon_days, cur, 0.5)
    deltas = [history[i + 1] - history[i] for i in range(len(history) - 1)]
    avg_daily = sum(deltas) / len(deltas)
    current = history[-1]
    projected = round(current + avg_daily * horizon_days, 2)
    return Forecast(current, horizon_days, projected, probability)


# ── Execution Score Engine ─────────────────────────────────────────────────
@dataclass
class ExecutionScore:
    score: int                       # 0..100
    completed: int
    delayed: int
    blocked: int
    revenue_usd: float
    knowledge_learned: int
    automation_pct: float
    goal_progress_pct: float


def compute_execution_score(*, completed: int, delayed: int, blocked: int,
                            revenue_usd: float, knowledge_learned: int,
                            automation_pct: float, goal_progress_pct: float) -> ExecutionScore:
    total = completed + delayed + blocked
    throughput = (completed / total) if total else 0.0
    # weighted blend, 0..1
    raw = (0.45 * throughput
           + 0.20 * automation_pct
           + 0.15 * min(1.0, revenue_usd / 200.0)
           + 0.10 * min(1.0, knowledge_learned / 5.0)
           + 0.10 * min(1.0, goal_progress_pct / 0.05))
    return ExecutionScore(
        score=round(raw * 100), completed=completed, delayed=delayed, blocked=blocked,
        revenue_usd=revenue_usd, knowledge_learned=knowledge_learned,
        automation_pct=automation_pct, goal_progress_pct=goal_progress_pct)


_SCHEMA = """
CREATE TABLE IF NOT EXISTS execution_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    score INTEGER NOT NULL,
    detail_json TEXT,
    recorded_at REAL NOT NULL
);
"""


class ExecutionScoreEngine:
    def __init__(self, db_path: "str | Path", now: Callable[[], float] = time.time):
        Path(str(db_path)).parent.mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(str(db_path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript(_SCHEMA)
        self.db.commit()
        self._now = now

    def record(self, es: ExecutionScore) -> None:
        import json
        self.db.execute("INSERT INTO execution_scores (score, detail_json, recorded_at)"
                        " VALUES (?,?,?)", (es.score, json.dumps(es.__dict__), self._now()))
        self.db.commit()

    def recent_scores(self, n: int = 7) -> list[int]:
        rows = self.db.execute("SELECT score FROM execution_scores ORDER BY id DESC LIMIT ?",
                              (n,)).fetchall()
        return [r["score"] for r in rows][::-1]

    def trend(self, n: int = 7) -> str:
        s = self.recent_scores(n)
        if len(s) < 2:
            return "flat"
        return "improving" if s[-1] > s[0] else "declining" if s[-1] < s[0] else "flat"


# ── Executive Briefing (assembles the CEO morning brief) ───────────────────
@dataclass
class ExecutiveBriefing:
    priority_score: int
    top_actions: list[Recommendation]
    execution: ExecutionScore | None
    execution_trend: str
    dream_progress_pct: float

    def render(self, name: str = "Ajay") -> str:
        lines = [f"Good morning {name}.", "",
                 f"Today's Priority Score: {self.priority_score}/100",
                 f"🎯 Dream progress: {self.dream_progress_pct:.4%}", ""]
        if self.execution:
            lines.append(f"⚡ Execution yesterday: {self.execution.score}/100 "
                         f"({self.execution.completed} done · {self.execution.delayed} delayed · "
                         f"{self.execution.blocked} blocked) — trend {self.execution_trend}")
            lines.append("")
        lines.append("Top actions:")
        for i, r in enumerate(self.top_actions, 1):
            lines.append(f"{i}. {r.title} — {r.why} "
                         f"(impact ${r.expected_impact_usd:.0f}, {r.confidence:.0%} conf, "
                         f"{r.priority.value})")
        return "\n".join(lines)


def build_briefing(*, decisions: DecisionEngine, dream_progress_pct: float,
                   execution: ExecutionScore | None = None,
                   execution_trend: str = "flat", top_n: int = 5) -> ExecutiveBriefing:
    top = decisions.top(top_n)
    # overall priority score = normalized average of the top actions' scores
    if top:
        avg = sum(min(100, r.priority_score / 10) for r in top) / len(top)
        priority_score = round(avg)
    else:
        priority_score = 0
    return ExecutiveBriefing(priority_score, top, execution, execution_trend, dream_progress_pct)
