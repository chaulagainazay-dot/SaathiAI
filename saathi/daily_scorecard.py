"""Daily Scorecard — instruments Ajay's success rule for the stabilization window.

    Every day, SaathiAI should make ≥1 business decision, automate ≥1 task,
    learn from ≥1 real outcome, help generate measurable revenue, and Ajay should
    Reflect — answer "what surprised me today?" (captured as a reflection Episode).

Pure measurement of data the platform already produces (Episodes + Revenue) — NO
new architecture, in keeping with the stabilization freeze. It classifies today's
Episodes into the four criteria and reports met/unmet, so the 8 AM briefing holds
the rule accountable instead of leaving it on paper.

Deterministic (AP-17); episode source + revenue + clock injected (AP-12).
"""
from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime

# intent substrings → criterion (an episode may satisfy more than one)
DECISION = ("recommend", "decision", "ceo_approve", "ceo_run", "allocate",
            "pipeline", "verdict", "approve", "briefing")
AUTOMATION = ("content_", "daily_discovery", "research_pass", "execute_trade",
              "publish", "factory", "discovery", "opportunity", "scan")
LEARNING = ("learning", "trade_closed", "analytics", "promotion", "improvement",
            "compare", "pattern", "research", "ielts", "coach", "practice")
REFLECT = ("reflection", "reflect", "surprised")


@dataclass
class Scorecard:
    decision: int
    automation: int
    learning: int
    revenue_usd: float
    reflect: int = 0

    @property
    def met(self) -> dict[str, bool]:
        return {"decision": self.decision > 0, "automation": self.automation > 0,
                "learning": self.learning > 0, "revenue": self.revenue_usd > 0,
                "reflect": self.reflect > 0}

    @property
    def score(self) -> int:
        return sum(self.met.values())

    @property
    def complete(self) -> bool:
        return self.score == 5

    @property
    def missing(self) -> list[str]:
        return [k for k, v in self.met.items() if not v]

    def render(self) -> str:
        m = self.met
        mark = lambda k: "✅" if m[k] else "⬜"
        return (f"📊  Today {self.score}/5   "
                f"{mark('decision')} decide  {mark('automation')} automate  "
                f"{mark('learning')} learn  {mark('revenue')} earn  {mark('reflect')} reflect"
                + (f"  (${self.revenue_usd:,.0f})" if self.revenue_usd else ""))


def _hits(intent: str, markers) -> bool:
    return any(m in intent for m in markers)


def score(episodes: list[dict], revenue_usd: float) -> Scorecard:
    d = sum(1 for e in episodes if _hits(e.get("intent", ""), DECISION))
    a = sum(1 for e in episodes if _hits(e.get("intent", ""), AUTOMATION))
    l = sum(1 for e in episodes if _hits(e.get("intent", ""), LEARNING))
    r = sum(1 for e in episodes if _hits(e.get("intent", ""), REFLECT))
    return Scorecard(decision=d, automation=a, learning=l,
                     revenue_usd=float(revenue_usd or 0), reflect=r)


def _today_start(now: float) -> float:
    dt = datetime.fromtimestamp(now)
    return datetime(dt.year, dt.month, dt.day).timestamp()


def today_scorecard(*, now: float | None = None) -> Scorecard:
    """Best-effort live scorecard from Platform Memory + Revenue Engine."""
    now = now or time.time()
    start = _today_start(now)
    episodes: list[dict] = []
    try:
        from saathi.integration import get_platform_memory
        for e in get_platform_memory().episodes(limit=1000):
            if getattr(e, "created_at", 0) >= start:
                episodes.append({"intent": getattr(e, "intent", ""),
                                 "outcome": getattr(e, "outcome", "")})
    except Exception:
        pass
    revenue = 0.0
    try:
        from saathi.revenue import get_revenue_engine
        revenue = get_revenue_engine().today_usd()
    except Exception:
        pass
    return score(episodes, revenue)
