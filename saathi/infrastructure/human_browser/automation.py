"""Automation Center backend — status + health score the cockpit consumes.

Aggregates: Mac Agent heartbeat (queue poll), vision readiness, signing-secret
readiness, and RunStore stats into one snapshot + a Browser Health Score.
Executive Intelligence consumes the score — if automation reliability drops, the
Priority Score should drop.
"""
from __future__ import annotations

import os
import time


def status(*, queue=None, store=None, now: float | None = None) -> dict:
    from .queue import InMemoryQueue  # noqa
    from .run_store import default_store
    from .vision_verifier import VisionVerifier
    now = time.time() if now is None else now
    if queue is None:
        from . import default_queue as queue
    store = store or default_store()

    last_poll = queue.last_claim_at() if hasattr(queue, "last_claim_at") else 0.0
    agent_online = bool(last_poll) and (now - last_poll) < 90       # heartbeat: polled within 90s
    vision_ready = VisionVerifier().available()
    secret_ready = bool(os.getenv("HUMAN_BROWSER_SECRET"))

    s = store.stats(window_hours=24, now=now)
    success_pct = round(100 * s["success_rate"])
    # health blends reliability with readiness of the moving parts
    ready_pct = round(100 * sum([agent_online, vision_ready, secret_ready]) / 3)
    overall = round(0.6 * success_pct + 0.4 * ready_pct)

    return {
        "health": {
            "overall": overall,
            "success_rate": success_pct,
            "runs_today": s["runs"],
            "failures_today": s["failures"],
            "avg_publish_ms": s["avg_duration_ms"],
            "last_success": s["last_success"],
        },
        "components": {
            "agent": {"online": agent_online, "light": _light(agent_online),
                      "last_poll": last_poll or None},
            "vision": {"ready": vision_ready, "light": _light(vision_ready)},
            "queue": {"ready": secret_ready, "light": _light(secret_ready)},
        },
        "recent_runs": store.list(limit=10),
    }


def _light(ok: bool) -> str:
    return "🟢" if ok else "🔴"
