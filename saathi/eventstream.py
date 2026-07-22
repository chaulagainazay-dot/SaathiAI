"""Live event stream (M5.1 Sprint 2) — the platform breathing over SSE.

Bridges the in-process Event Fabric to a Server-Sent Events stream the CEO
Companion subscribes to. One stream; every client stays synchronized. Each event
is enriched with the department it belongs to and (when relevant) a human title +
action, so the UI can light the right node and slide in an actionable notification.

During the stabilization window real events are sparse, so a demo cycler emits
representative beats (trade.executed, revenue.recorded, …) — the OS visibly lives.
Turn it off with ?demo=0 to see only real Event-Fabric traffic.
"""
from __future__ import annotations

import asyncio
import json
import time

from saathi.events import _events_py

bus = _events_py.bus

# event-name → (department, tone). Anything unmapped is routed to MISSION.
_DEPT = {
    "trade.": "FINANCE", "investment.": "FINANCE", "execution.": "FINANCE",
    "revenue.": "CAFETERIA", "opportunity.": "OPPORTUNITY", "research.": "KNOWLEDGE",
    "learning.": "LEARNING", "knowledge.": "KNOWLEDGE", "portfolio.": "FINANCE",
    "publish.": "AI STUDIO", "video.": "AI STUDIO", "content.": "AI STUDIO",
    "financial_mission_control.": "MISSION", "executive.": "EXECUTIVE",
    "cafeteria.": "CAFETERIA", "travel.": "TRAVEL",
}


def dept_for(name: str) -> str:
    for prefix, dept in _DEPT.items():
        if name.startswith(prefix):
            return dept
    return "MISSION"


def enrich(name: str, payload: dict) -> dict:
    """Attach dept + optional actionable title so the UI can react."""
    dept = payload.get("dept") or dept_for(name)
    ev = {"name": name, "dept": dept, "payload": payload, "ts": time.time()}
    # actionable presentation (Sprint 3): every notification offers a decision
    title = payload.get("title")
    action = payload.get("action")
    tone = payload.get("tone")
    if not title:
        if name == "trade.executed":
            title = f"Trade filled: {payload.get('symbol','?')} {payload.get('pnl_usd',0):+.0f}"
            action, tone = "View", "up"
        elif name == "revenue.recorded":
            title = f"Revenue +${payload.get('amount_usd',0):.0f} · {dept.title()}"
            action, tone = "View", "up"
        elif name == "video.published":
            title = f"Video #{payload.get('id','?')} published."
            action, tone = "Analytics", "up"
        elif name == "learning.completed":
            title = f"Learning: {payload.get('proposals',0)} new proposals."
            action, tone = "Review", "info"
        elif name == "knowledge.promoted":
            title = f"Knowledge promoted ×{payload.get('count',1)}."
            action, tone = "View", "info"
        elif name == "approval.required":
            title = payload.get("text", "An action needs your approval.")
            action, tone = "Approve", "warn"
    if title:
        ev["title"], ev["action"], ev["tone"] = title, action or "Open", tone or "info"
    return ev


# demo beats that make the platform visibly breathe (stabilization only)
DEMO = [
    ("trade.executed", {"symbol": "TAO", "pnl_usd": 320}),
    ("revenue.recorded", {"amount_usd": 235, "dept": "CAFETERIA"}),
    ("learning.completed", {"proposals": 2}),
    ("video.published", {"id": 58}),
    ("knowledge.promoted", {"count": 2}),
    ("approval.required", {"text": "2 investments waiting for L4 approval.", "dept": "FINANCE"}),
    ("portfolio.rebalanced", {"dept": "FINANCE", "title": "Portfolio drift within tolerance.", "action": "View", "tone": "info"}),
    ("travel.lead", {"dept": "TRAVEL", "title": "Lead waiting 3 days — call now?", "action": "Call", "tone": "warn"}),
]


def _sse(ev: dict) -> str:
    return f"data: {json.dumps(ev)}\n\n"


async def sse_stream(demo: bool = True, demo_interval: float = 4.0):
    """Async generator of SSE frames. Real Event-Fabric events flow immediately;
    when idle, demo beats keep the OS alive (if demo)."""
    loop = asyncio.get_running_loop()
    queue: asyncio.Queue = asyncio.Queue()

    def _handler(event):
        # bus may publish from any thread → hop back to this request's loop
        loop.call_soon_threadsafe(queue.put_nowait, enrich(event.name, event.payload))

    unsub = bus.subscribe("*", _handler)
    di = 0
    try:
        yield _sse({"name": "stream.connected", "dept": "MISSION", "ts": time.time()})
        while True:
            try:
                ev = await asyncio.wait_for(queue.get(), timeout=demo_interval)
            except asyncio.TimeoutError:
                if demo:
                    name, payload = DEMO[di % len(DEMO)]
                    di += 1
                    ev = enrich(name, dict(payload))
                else:
                    ev = {"name": "heartbeat", "ts": time.time()}
            yield _sse(ev)
    finally:
        unsub()
