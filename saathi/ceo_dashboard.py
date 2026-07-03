"""CEO Dashboard — the first screen you open every morning (M3 Phase A).

Turns the platform's invisible event streams into one operating view. Event-first
(AP-13): every subsystem already publishes to the Event Fabric; this subscribes
and aggregates — no subsystem is polled, no new coupling.

    {storage, learning, knowledge, publishing, governance} events
        → Event Fabric → CEODashboard.snapshot() / .briefing()

Honest by construction (Dev Rule #1): sections show what is actually wired.
Revenue / crypto / POS read 0 until those products are integrated — shown as
"not yet connected" rather than faked.

Testable in isolation (AP-12): construct, register on any bus, publish events,
assert the snapshot; render the briefing as a string.
"""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from saathi.events import Event, EventBus, WILDCARD


@dataclass
class _Sections:
    # AI Studio
    videos_published: int = 0
    videos_blocked: int = 0
    renders: int = 0
    # Discovery
    publishes_with_seo: int = 0
    # Learning
    knowledge_promoted: int = 0
    reviews_pending: int = 0
    knowledge_rejected: int = 0
    lessons_extracted: int = 0
    improvement_proposals: int = 0
    # Knowledge Graph
    kg_nodes: int = 0
    kg_edges: int = 0
    # Documentation
    doc_proposals: int = 0
    # Infrastructure (storage)
    disk_pct: float | None = None
    rendering_paused: bool = False
    emergency: bool = False


class CEODashboard:
    def __init__(self, goal_target: float = 7_938_838.98, recent_limit: int = 30):
        self.s = _Sections()
        self.goal_target = goal_target
        self.revenue_total = 0.0            # not yet wired — stays 0 honestly
        self.notifications: deque[dict] = deque(maxlen=recent_limit)

    # ── event ingestion ───────────────────────────────────────────────────
    def on_event(self, e: Event) -> None:
        n, p = e.name, e.payload
        s = self.s
        if n in ("publish.completed",):
            s.videos_published += 1
            s.publishes_with_seo += 1
        elif n == "publish.blocked":
            s.videos_blocked += 1
        elif n in ("render_started", "render_completed"):
            s.renders += 1
        elif n == "knowledge.promoted":
            s.knowledge_promoted += 1
        elif n == "knowledge.review_enqueued":
            s.reviews_pending += 1
        elif n == "knowledge.rejected":
            s.knowledge_rejected += 1
        elif n == "learning.lesson_extracted":
            s.lessons_extracted += 1
        elif n == "learning.improvement_proposal":
            s.improvement_proposals += 1
        elif n == "kg.node_created":
            s.kg_nodes += 1
        elif n == "kg.edge_created":
            s.kg_edges += 1
        elif n == "doc.proposal_created":
            s.doc_proposals += 1
        elif n in ("storage_warning", "storage.warning"):
            s.disk_pct = p.get("disk_pct", s.disk_pct)
            s.rendering_paused = True
            self._notify(f"⚠️ Storage {p.get('disk_pct', 0):.0%}")
        elif n in ("storage_critical", "storage.disk.full"):
            s.disk_pct = p.get("disk_pct", s.disk_pct)
            s.emergency = True
            s.rendering_paused = True
            self._notify(f"🚨 Storage CRITICAL {p.get('disk_pct', 0):.0%}")

    def _notify(self, text: str) -> None:
        self.notifications.appendleft(text)

    def register(self, bus: EventBus) -> None:
        bus.subscribe(WILDCARD, self.on_event)

    # ── revenue (wired later by Business/Financial OS) ────────────────────
    def record_revenue(self, amount: float) -> None:
        self.revenue_total += amount

    @property
    def goal_progress(self) -> float:
        return min(1.0, self.revenue_total / self.goal_target) if self.goal_target else 0.0

    # ── views ─────────────────────────────────────────────────────────────
    def snapshot(self) -> dict:
        s = self.s
        return {
            "dream": {
                "goal": self.goal_target,
                "revenue_total": self.revenue_total,
                "progress": round(self.goal_progress, 6),
                "connected": self.revenue_total > 0,
            },
            "ai_studio": {"published": s.videos_published, "blocked": s.videos_blocked,
                          "renders": s.renders},
            "discovery": {"publishes_with_seo": s.publishes_with_seo},
            "learning": {"promoted": s.knowledge_promoted, "pending_reviews": s.reviews_pending,
                         "rejected": s.knowledge_rejected, "lessons": s.lessons_extracted,
                         "improvement_proposals": s.improvement_proposals},
            "knowledge_graph": {"nodes": s.kg_nodes, "edges": s.kg_edges},
            "documentation": {"proposals": s.doc_proposals},
            "infrastructure": {"disk_pct": s.disk_pct, "rendering_paused": s.rendering_paused,
                               "emergency": s.emergency},
            "notifications": list(self.notifications)[:10],
        }

    def briefing(self, name: str = "Ajay") -> str:
        """The morning CEO briefing (text — pushable to Telegram)."""
        s = self.s
        d = self.snapshot()["dream"]
        goal_line = (f"${self.revenue_total:,.0f} / ${self.goal_target:,.0f}"
                     f" ({self.goal_progress:.2%})" if self.revenue_total > 0
                     else f"$0 / ${self.goal_target:,.0f} — revenue not yet connected")
        lines = [
            f"Good morning {name}.",
            "",
            f"🎯 Dream: {goal_line}",
            "",
            f"📺 AI Studio: {s.videos_published} published · {s.videos_blocked} blocked by Discovery · {s.renders} renders",
            f"🧠 Learning: {s.knowledge_promoted} promoted · {s.reviews_pending} pending review · "
            f"{s.lessons_extracted} lessons · {s.improvement_proposals} improvement proposals",
            f"🕸️ Knowledge Graph: {s.kg_nodes} nodes · {s.kg_edges} relationships",
            f"📚 Docs: {s.doc_proposals} proposals awaiting review",
        ]
        if s.disk_pct is not None:
            state = "EMERGENCY" if s.emergency else ("paused" if s.rendering_paused else "ok")
            lines.append(f"💾 Storage: {s.disk_pct:.0%} used ({state})")
        if self.notifications:
            lines += ["", "⚠️ Notifications:"] + [f"  {x}" for x in list(self.notifications)[:5]]
        return "\n".join(lines)


# ── process-wide live dashboard (subscribed to the global Event Fabric) ────
_dashboard: CEODashboard | None = None


def get_dashboard() -> CEODashboard:
    """The live CEO dashboard, wired to the global bus on first use (AP-13)."""
    global _dashboard
    if _dashboard is None:
        from saathi.events import bus
        _dashboard = CEODashboard()
        _dashboard.register(bus)
    return _dashboard


def send_morning_briefing() -> str:
    """Scheduler entry point: push the CEO briefing to Telegram. Returns the text."""
    text = get_dashboard().briefing()
    try:
        from saathi import telegram_bot
        telegram_bot._send(text)
    except Exception:
        pass
    return text
