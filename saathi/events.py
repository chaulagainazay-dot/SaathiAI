"""Event Fabric — the platform's generic pub/sub nervous system (SES-012, lightweight form).

This is the general Event Fabric every department publishes to — distinct from
``saathi/agents/bus.py``, which is the IELTS-domain student-error bus.

Lightweight by design: in-process, async-first, zero external dependencies.
The public API (``subscribe`` / ``publish``) is what callers use; the transport
underneath can later become NATS without any caller changing (AP-11: the brain
publishes intent, the transport just carries it).

Handlers may be sync or async. A handler that raises does not break the publish
for other subscribers — the error is captured and (optionally) surfaced, so one
bad subscriber can't take down the fabric (failure isolation, AP-12).
"""
from __future__ import annotations

import asyncio
import inspect
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

# Canonical event names (SES-019A Appendix D + SES-005).
# Not an enum on purpose — departments may define their own event names;
# these are the well-known ones the platform ships with.
RENDER_STARTED = "render_started"
RENDER_COMPLETED = "render_completed"
UPLOAD_VERIFIED = "upload_verified"
CLEANUP_REQUESTED = "cleanup_requested"
CLEANUP_COMPLETED = "cleanup_completed"
STORAGE_WARNING = "storage_warning"
STORAGE_CRITICAL = "storage_critical"
ARCHIVE_COMPLETED = "archive_completed"
BACKUP_COMPLETED = "backup_completed"

# Storage Intelligence event vocabulary (dotted namespace) — feeds Mission
# Control, OpenObserve, Telegram, Analytics, and the Learning Engine with no
# extra wiring: subscribers just listen for what they care about.
STORAGE_EVENTS = {
    "warning": "storage.warning",
    "cleanup_started": "storage.cleanup.started",
    "cleanup_finished": "storage.cleanup.finished",
    "cleanup_failed": "storage.cleanup.failed",
    "render_blocked": "storage.render.blocked",
    "render_allowed": "storage.render.allowed",
    "disk_full": "storage.disk.full",
    "archive_completed": "storage.archive.completed",
    "lifecycle_deleted": "storage.lifecycle.deleted",
    "lifecycle_protected": "storage.lifecycle.protected",
}

WILDCARD = "*"

Handler = Callable[["Event"], "Awaitable[None] | None"]


@dataclass
class Event:
    name: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: float = field(default_factory=time.time)


@dataclass
class PublishReport:
    event: "Event"
    delivered: int
    errors: list[tuple[Handler, Exception]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.errors


class EventBus:
    def __init__(self) -> None:
        self._subs: dict[str, list[Handler]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Handler) -> Callable[[], None]:
        """Register a handler for an event name (or ``"*"`` for all events).
        Returns an unsubscribe callable."""
        self._subs[event_name].append(handler)

        def _unsub() -> None:
            try:
                self._subs[event_name].remove(handler)
            except ValueError:
                pass

        return _unsub

    def _handlers_for(self, name: str) -> list[Handler]:
        # specific subscribers first, then wildcard subscribers
        return list(self._subs.get(name, [])) + list(self._subs.get(WILDCARD, []))

    async def publish(self, name: str, payload: dict[str, Any] | None = None) -> PublishReport:
        event = Event(name=name, payload=payload or {})
        report = PublishReport(event=event, delivered=0)
        for handler in self._handlers_for(name):
            try:
                result = handler(event)
                if inspect.isawaitable(result):
                    await result
                report.delivered += 1
            except Exception as exc:  # failure isolation — one bad sub can't break others
                report.errors.append((handler, exc))
        return report

    def publish_sync(self, name: str, payload: dict[str, Any] | None = None) -> PublishReport:
        """Convenience for non-async callers. Runs the async publish to
        completion on a fresh loop if none is running."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self.publish(name, payload))
        raise RuntimeError("publish_sync called from within a running event loop; use await publish()")


# Process-wide default fabric. Departments import this unless a test injects its own.
bus = EventBus()
