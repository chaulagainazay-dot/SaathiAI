"""Event → Episode bridge — every infrastructure interaction becomes learning.

Subscribes to the Event Fabric and records an Episode for each completed,
learnable interaction (a conversation reply, a connector execution, a browser
fetch). This is app-layer wiring: it may import both the Event Fabric
(infrastructure) and the Learning Runtime (`integration.ingest_episode`), and is
installed once at server startup. The recorder is injectable for tests.
"""
from __future__ import annotations

from typing import Callable

# event name → (department, intent) for the Episode
_EPISODE_EVENTS = {
    "conversation.completed": ("executive", "conversation"),
    "connector.executed":     ("infrastructure", "connector_execute"),
    "browser.finished":       ("infrastructure", "browser_fetch"),
    "browser.published":      ("ai_studio", "publish"),        # video went live → learning
    "browser.failed":         ("ai_studio", "publish"),        # publish failed → learning
}


def install(bus, record_episode: Callable[..., int] | None = None) -> Callable[[], None]:
    """Wire the bridge onto a bus. Returns an uninstall callable."""
    if record_episode is None:
        from saathi.integration import ingest_episode as record_episode

    def _make(department: str, intent: str):
        def handler(event):
            payload = getattr(event, "payload", {}) or {}
            # a fetch/execute that failed is still a (negative) learning signal
            outcome = "failure" if payload.get("ok") is False or payload.get("error") else "success"
            try:
                record_episode(
                    agent="infrastructure", department=department,
                    product=str(payload.get("product", "platform")),
                    intent=intent, action=getattr(event, "name", intent),
                    result=str(payload)[:400], outcome=outcome, metadata=payload)
            except Exception:
                pass   # a broken recorder must never break the emitting call
        return handler

    unsubs = [bus.subscribe(ev, _make(dept, intent))
              for ev, (dept, intent) in _EPISODE_EVENTS.items()]

    def uninstall():
        for u in unsubs:
            try:
                u()
            except Exception:
                pass

    return uninstall
