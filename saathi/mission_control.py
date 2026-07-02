"""Mission Control — live system state, fed by the Event Fabric (AP-13).

Event-first: instead of the dashboard polling each service, every subsystem
publishes events and Mission Control *subscribes*. The dashboard reads a
snapshot that events keep current — no cron, no refresh loop.

    subsystem → Event Fabric → MissionControlState (updated instantly)
                                     ↑ dashboard reads snapshot()

Independently testable (AP-12): construct one, register on any EventBus,
publish events, assert the snapshot. No server, no real dashboard.
"""
from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from saathi.events import Event, EventBus, STORAGE_EVENTS


@dataclass
class StorageHealth:
    disk_pct: float | None = None
    rendering_paused: bool = False
    emergency: bool = False
    last_cleanup_freed_bytes: int = 0
    last_cleanup_kind: str | None = None
    renders_allowed: int = 0
    renders_blocked: int = 0
    updated_at: float | None = None


class MissionControlState:
    """Holds the live snapshot the dashboard renders. Updated only by events."""

    def __init__(self, recent_limit: int = 50, capability_registry=None):
        self.storage = StorageHealth()
        self.recent_events: deque[dict] = deque(maxlen=recent_limit)
        self.event_counts: dict[str, int] = {}
        if capability_registry is None:
            from saathi.capabilities import registry as capability_registry
        self.capabilities = capability_registry

    # --- the single entry point: every event flows through here ----------
    def on_event(self, event: Event) -> None:
        self.recent_events.appendleft({"name": event.name, "payload": event.payload, "ts": event.ts})
        self.event_counts[event.name] = self.event_counts.get(event.name, 0) + 1
        self._apply_storage(event)

    def _apply_storage(self, e: Event) -> None:
        p = e.payload
        touched = True
        if e.name in ("storage_warning", STORAGE_EVENTS["warning"]):
            self.storage.disk_pct = p.get("disk_pct", self.storage.disk_pct)
            self.storage.rendering_paused = True
            self.storage.emergency = False
        elif e.name in ("storage_critical", STORAGE_EVENTS["disk_full"]):
            self.storage.disk_pct = p.get("disk_pct", self.storage.disk_pct)
            self.storage.rendering_paused = True
            self.storage.emergency = True
        elif e.name == STORAGE_EVENTS["cleanup_finished"]:
            self.storage.last_cleanup_freed_bytes = p.get("bytes_freed", 0)
            self.storage.last_cleanup_kind = p.get("kind")
        elif e.name == STORAGE_EVENTS["render_allowed"]:
            self.storage.renders_allowed += 1
        elif e.name == STORAGE_EVENTS["render_blocked"]:
            self.storage.renders_blocked += 1
        else:
            touched = False
        if touched:
            self.storage.updated_at = time.time()

    def register(self, bus: EventBus) -> None:
        """Subscribe to every event on the fabric (event-first, AP-13)."""
        from saathi.events import WILDCARD
        bus.subscribe(WILDCARD, self.on_event)

    # --- what the dashboard reads ----------------------------------------
    def snapshot(self) -> dict[str, Any]:
        s = self.storage
        return {
            "storage": {
                "disk_pct": s.disk_pct,
                "rendering_paused": s.rendering_paused,
                "emergency": s.emergency,
                "last_cleanup_freed_bytes": s.last_cleanup_freed_bytes,
                "last_cleanup_kind": s.last_cleanup_kind,
                "renders_allowed": s.renders_allowed,
                "renders_blocked": s.renders_blocked,
                "updated_at": s.updated_at,
            },
            "event_counts": dict(self.event_counts),
            "recent_events": list(self.recent_events)[:20],
            "capabilities": self.capabilities.snapshot(),
        }
